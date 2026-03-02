import json
import time
import websocket
from logger import log_info, log_debug, log_deeptrace, log_trace, log_error, log_fatal, log_warning
from converters import ha_brightness_to_sber, ha_temp_to_sber


class HAWebSocketClient:
    """
    WebSocket клиент для подписки на события Home Assistant.
    Обрабатывает изменения состояний и обновляет локальную БД.
    """

    def __init__(self, device_database, sber_serializer, config_options, publish_status_callback):
        self.device_database = device_database
        self.sber_serializer = sber_serializer
        self.config_options = config_options
        self.publish_status_callback = publish_status_callback
        self.areas_registry: dict = {}
        self.devices_registry: dict = {}
        self.websocket_client = None

    # ------------------------------------------------------------------ #
    #  Жизненный цикл соединения                                           #
    # ------------------------------------------------------------------ #

    def run_forever(self):
        """Запуск WebSocket клиента с автоматическим переподключением."""
        url = self._build_ws_url()

        while True:
            try:
                log_info(f"WebSocket: подключение к {url}")
                self.websocket_client = websocket.WebSocketApp(
                    url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=lambda ws, err: log_error(f"WebSocket: ошибка: {err}"),
                    on_close=self._on_close
                )
                self.websocket_client.run_forever(
                    ping_interval=30,
                    ping_timeout=3,
                    ping_payload=b'ping'
                )
            except Exception as e:
                log_fatal(f"WebSocket: критическая ошибка: {e}")

            log_info("WebSocket: переподключение через 5 секунд...")
            time.sleep(5)

    def _build_ws_url(self):
        url = self.config_options.get('ha-api_url', 'ws://supervisor/core/websocket')
        if url.startswith('http'):
            url = url.replace('http', 'ws', 1)
        if not url.endswith('/websocket'):
            url = url + '/api/websocket'
        return url

    def _on_open(self, ws):
        log_info("WebSocket: соединение открыто")

    def _on_close(self, ws, code, msg):
        log_info("WebSocket: соединение закрыто")

    # ------------------------------------------------------------------ #
    #  Диспетчер сообщений                                                 #
    # ------------------------------------------------------------------ #

    def _on_message(self, ws, raw):
        log_deeptrace(f"WebSocket: сообщение: {raw}")
        data = json.loads(raw)

        handlers = {
            'auth_required': self._handle_auth_required,
            'auth_ok':       self._handle_auth_ok,
            'auth_invalid':  self._handle_auth_invalid,
            'result':        self._handle_result,
            'event':         self._handle_event,
        }
        handlers.get(data.get('type'), lambda ws, d: None)(ws, data)

    # ------------------------------------------------------------------ #
    #  Авторизация                                                         #
    # ------------------------------------------------------------------ #

    def _handle_auth_required(self, ws, data):
        log_info("WebSocket: требуется авторизация")
        token = self.config_options.get('ha-api_token', '')
        try:
            ws.send(json.dumps({"type": "auth", "access_token": token}))
        except Exception as e:
            log_error(f"WebSocket: ошибка отправки auth: {e}")

    def _handle_auth_ok(self, ws, data):
        log_info("WebSocket: авторизация успешна")
        try:
            ws.send(json.dumps({'id': 1, 'type': 'subscribe_events', 'event_type': 'state_changed'}))
            ws.send(json.dumps({'id': 2, 'type': 'config/area_registry/list'}))
            ws.send(json.dumps({'id': 3, 'type': 'config/device_registry/list'}))
            ws.send(json.dumps({'id': 4, 'type': 'config/entity_registry/list'}))
        except Exception as e:
            log_error(f"WebSocket: ошибка отправки команд: {e}")

    def _handle_auth_invalid(self, ws, data):
        log_fatal("WebSocket: ошибка авторизации, проверьте ha-api_token")

    # ------------------------------------------------------------------ #
    #  Результаты запросов реестров                                        #
    # ------------------------------------------------------------------ #

    def _handle_result(self, ws, data):
        log_deeptrace(f"WebSocket: результат: {data}")
        rid = data.get('id')

        if rid == 2:
            self.areas_registry = {
                a['area_id']: a['name']
                for a in data.get('result', [])
            }
            log_trace(f"Зоны HA: {self.areas_registry}")

        elif rid == 3:
            self.devices_registry = {
                d['id']: {
                    'id': d['id'],
                    'name': d.get('name') or d.get('name_by_user') or 'Unknown',
                    'area_id': d.get('area_id', 'Unknown')
                }
                for d in data.get('result', [])
            }
            log_trace(f"Устройства HA: найдено {len(self.devices_registry)}")

        elif rid == 4:
            self._apply_entity_registry(data.get('result', []))

    def _apply_entity_registry(self, entities):
        """Обновление room и device_id из реестра сущностей HA."""
        for entity in entities:
            entity_id = entity['entity_id']
            db_entity = self.device_database.devices_registry.get(entity_id)
            if not db_entity:
                continue

            device_id = entity.get('device_id')

            # Приоритет: area_id самого объекта > area_id устройства
            entity_area_id = entity.get('area_id')
            device_area_id = (
                self.devices_registry[device_id].get('area_id')
                if device_id and device_id in self.devices_registry
                else None
            )
            area_id = entity_area_id or device_area_id
            room_name = self.areas_registry.get(area_id, '') if area_id else ''

            if device_id != db_entity.get('device_id'):
                self.device_database.update(entity_id, {'entity_ha': True, 'device_id': device_id})

            if db_entity.get('room') != room_name:
                log_info(f"Зона '{entity_id}': '{db_entity.get('room')}' -> '{room_name}'")
                self.device_database.update(entity_id, {'entity_ha': True, 'room': room_name})

    # ------------------------------------------------------------------ #
    #  Обработка событий state_changed                                     #
    # ------------------------------------------------------------------ #

    def _handle_event(self, ws, data):
        event_data = data['event']['data']
        if not event_data.get('new_state'):
            return

        new_state_obj = event_data['new_state']
        entity_id = new_state_obj['entity_id']
        old_state = event_data['old_state']['state'] if event_data.get('old_state') else 'None'
        new_state = new_state_obj['state']

        db_entity = self.device_database.devices_registry.get(entity_id)
        is_enabled = db_entity and db_entity.get('enabled', False)

        if is_enabled:
            log_debug(f"!Новое состояние от HA: {entity_id} {old_state} -> {new_state}")
        else:
            log_deeptrace(f"Новое состояние от HA (неактивное): {entity_id} {old_state} -> {new_state}")

        if not db_entity:
            return

        category = db_entity.get('category', '')
        attributes = new_state_obj.get('attributes', {})
        device_class = attributes.get('device_class', '')

        changed = self._update_state_in_db(entity_id, db_entity, category, new_state, attributes, device_class)

        if is_enabled and changed:
            payload = self.sber_serializer.build_mqtt_states_payload([entity_id])
            self.publish_status_callback(payload)

    def _update_state_in_db(self, entity_id, db_entity, category, new_state, attributes, device_class) -> bool:
        """
        Обновляет состояние в БД. Возвращает True, если нужно оповестить Сбер.
        """
        if category == 'sensor_temp':
            return self._handle_sensor(entity_id, db_entity, new_state, device_class)

        if category == 'scenario_button':
            return self._handle_scenario_button(entity_id, db_entity, new_state)

        if category in ('relay', 'light'):
            return self._handle_relay_or_light(entity_id, db_entity, category, new_state, attributes)

        if category == 'vacuum_cleaner':
            return self._handle_vacuum(entity_id, new_state, attributes)

        return False

    # ------------------------------------------------------------------ #
    #  Обработчики по категориям                                           #
    # ------------------------------------------------------------------ #

    def _handle_sensor(self, entity_id, db_entity, new_state, device_class) -> bool:
        key_map = {
            'temperature': 'temperature',
            'humidity': 'humidity',
            'pressure': 'air_pressure',
            'atmospheric_pressure': 'air_pressure',
        }
        key = key_map.get(device_class)
        if not key:
            return False

        try:
            value = float(new_state)
        except (ValueError, TypeError):
            return False

        self.device_database.change_state(entity_id, key, value)

        # Синхронизация с другими датчиками того же физического устройства
        current_device_id = db_entity.get('device_id')
        if current_device_id:
            for other_id, other_dev in self.device_database.devices_registry.items():
                if (other_id != entity_id
                        and other_dev.get('device_id') == current_device_id
                        and other_dev.get('category') == 'sensor_temp'):
                    self.device_database.change_state(other_id, key, value)
                    if other_dev.get('enabled', False):
                        payload = self.sber_serializer.build_mqtt_states_payload([other_id])
                        self.publish_status_callback(payload)

        return True

    def _handle_scenario_button(self, entity_id, db_entity, new_state) -> bool:
        entity_type = db_entity.get('entity_type')
        if entity_type == 'input_boolean':
            event = 'click' if new_state == 'on' else 'double_click'
            self.device_database.change_state(entity_id, 'button_event', event)
            return True
        if entity_type == 'input_button':
            self.device_database.change_state(entity_id, 'button_event', 'click')
            return True
        return False

    def _handle_relay_or_light(self, entity_id, db_entity, category, new_state, attributes) -> bool:
        entity_type = db_entity.get('entity_type')
        expected_state = db_entity.get('_expected_mqtt_state')

        if entity_type == 'button':
            if expected_state is not None:
                log_deeptrace(f"Игнорируем эхо кнопки {entity_id}")
                db_entity.pop('_expected_mqtt_state', None)
                return False

            click_type = attributes.get('click_type') or attributes.get('event_type')
            is_on = click_type not in ('double_click', 'long_press')
            self.device_database.change_state(entity_id, 'on_off', is_on)
        else:
            is_on = new_state == 'on'

            # Фильтрация эха от MQTT-команды
            if expected_state is not None:
                if is_on == expected_state:
                    log_deeptrace(f"Эхо подавлено для {entity_id} (ожидалось: {expected_state})")
                    db_entity.pop('_expected_mqtt_state', None)
                else:
                    log_deeptrace(f"Промежуточное состояние {entity_id} ({is_on}), ждём {expected_state}")
                return False

            # Защита от дребезга контактов
            current_on_off = self.device_database.get_state(entity_id, 'on_off')
            if is_on == current_on_off:
                log_deeptrace(f"Состояние {entity_id} не изменилось ({is_on}), пропуск")
                return False

            last_ts = db_entity.get('_last_state_change_ts', 0)
            now = time.time()
            if now - last_ts < 0.5:
                log_deeptrace(f"Слишком частое переключение {entity_id}, пропуск")
                return False

            db_entity['_last_state_change_ts'] = now
            self.device_database.change_state(entity_id, 'on_off', is_on)

        if category == 'light':
            self._update_light_states(entity_id, attributes)

        return True

    def _handle_vacuum(self, entity_id, ha_state: str, attributes: dict) -> bool:
        """Обновление состояний пылесоса из события HA state_changed."""
        from ha_entity_updater import HAEntityUpdater
        # Переиспользуем маппинг из апдейтера, чтобы не дублировать логику
        sber_status = HAEntityUpdater.HA_VACUUM_STATUS_MAP.get(ha_state, 'charging')
        self.device_database.change_state(entity_id, 'vacuum_cleaner_status', sber_status)

        battery = attributes.get('battery_level')
        if battery is not None:
            self.device_database.change_state(entity_id, 'battery_percentage', int(battery))

        return True

    def _update_light_states(self, entity_id, attributes):
        """Обновление яркости, цвета и температуры света из события HA."""
        brightness = attributes.get('brightness')
        if brightness is not None:
            self.device_database.change_state(
                entity_id, 'light_brightness', ha_brightness_to_sber(brightness))

        rgb_color = attributes.get('rgb_color')
        if rgb_color and len(rgb_color) >= 3:
            self.device_database.change_state(entity_id, 'light_colour', {
                'red': rgb_color[0],
                'green': rgb_color[1],
                'blue': rgb_color[2]
            })
            self.device_database.change_state(entity_id, 'light_mode', 'colour')

        color_temp = attributes.get('color_temp')
        if color_temp is not None:
            self.device_database.change_state(
                entity_id, 'light_colour_temp', ha_temp_to_sber(color_temp))
            if not self.device_database.get_state(entity_id, 'light_colour'):
                self.device_database.change_state(entity_id, 'light_mode', 'white')
