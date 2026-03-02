from logger import log_deeptrace, log_info
from converters import ha_brightness_to_sber, ha_temp_to_sber


class HAEntityUpdater:
    """
    Отвечает за маппинг сущностей HA в локальную БД и обновление их состояний.
    Применяется при первичной загрузке (REST) и при событиях (WebSocket).
    """

    ENTITY_TYPE_MAP = {
        'switch':        {'entity_type': 'switch',        'category': 'relay'},
        'script':        {'entity_type': 'scr',           'category': 'relay'},
        'button':        {'entity_type': 'button',        'category': 'relay'},
        'input_boolean': {'entity_type': 'input_boolean', 'category': 'scenario_button'},
        'input_button':  {'entity_type': 'input_button',  'category': 'scenario_button'},
        'climate':       {'entity_type': 'climate',       'category': 'hvac_ac'},
        'light':         {'entity_type': 'light',         'category': 'light'},
        'vacuum':        {'entity_type': 'vacuum',        'category': 'vacuum_cleaner'},
    }

    def __init__(self, device_database):
        self.device_database = device_database

    def update_entity(self, entity_id, state_data):
        """Универсальное обновление сущности по данным из HA."""
        domain = entity_id.split('.')[0]
        attributes = state_data.get('attributes', {})
        friendly_name = attributes.get('friendly_name', '')
        device_class = attributes.get('device_class', '')

        config = self._resolve_config(domain, device_class)
        if not config:
            return

        log_deeptrace(f"Обновление {domain}: {entity_id} '{friendly_name}' ({device_class})")

        existing = self.device_database.get_device(entity_id)

        update_data = {
            'entity_ha': True,
            # Сохраняем entity_type и category, выставленные пользователем вручную.
            # Автоматически определённые значения применяются только при первом появлении устройства.
            'entity_type': (existing or {}).get('entity_type') or config['entity_type'],
            'category':    (existing or {}).get('category')    or config['category'],
            'friendly_name': friendly_name,
        }
        if device_class:
            update_data['device_class'] = device_class

        self.device_database.update(entity_id, update_data)

        state = state_data.get('state')

        if domain in ('switch', 'script', 'light'):
            self.device_database.change_state(entity_id, 'on_off', state == 'on')

        if domain == 'light':
            self.update_light_attributes(entity_id, attributes)

        if domain == 'vacuum':
            self.update_vacuum_attributes(entity_id, state, attributes)

    def _resolve_config(self, domain, device_class):
        """Определение конфига сущности по домену и device_class."""
        config = self.ENTITY_TYPE_MAP.get(domain)
        if not config:
            if domain == 'sensor' and device_class in (
                    'temperature', 'humidity', 'pressure', 'atmospheric_pressure'):
                config = {'entity_type': 'sensor_temp', 'category': 'sensor_temp'}
            elif domain == 'hvac_radiator' and device_class == 'temperature':
                config = {'entity_type': 'hvac_radiator', 'category': 'hvac_radiator'}
        return config

    def update_light_attributes(self, entity_id, attributes):
        """Обновление атрибутов света: яркость, цвет, температура."""
        brightness = attributes.get('brightness')
        if brightness is not None:
            self.device_database.change_state(
                entity_id, 'light_brightness', ha_brightness_to_sber(brightness))

        supported_color_modes = attributes.get('supported_color_modes', [])
        if any(m in supported_color_modes for m in ('rgb', 'rgbw', 'rgbww')):
            rgb_color = attributes.get('rgb_color')
            if rgb_color and len(rgb_color) >= 3:
                self.device_database.change_state(entity_id, 'light_colour', {
                    'red': rgb_color[0],
                    'green': rgb_color[1],
                    'blue': rgb_color[2]
                })
                self.device_database.change_state(entity_id, 'light_mode', 'colour')

        if 'color_temp' in supported_color_modes:
            color_temp = attributes.get('color_temp')
            if color_temp is not None:
                self.device_database.change_state(
                    entity_id, 'light_colour_temp', ha_temp_to_sber(color_temp))
                if not self.device_database.get_state(entity_id, 'light_colour'):
                    self.device_database.change_state(entity_id, 'light_mode', 'white')

    # Маппинг состояний HA vacuum -> статус Сбера
    # Допустимые значения Сбера: cleaning / docked / pause / returning_to_dock
    HA_VACUUM_STATUS_MAP = {
        'cleaning':    'cleaning',
        'paused':      'pause',
        'returning':   'returning_to_dock',
        'docked':      'docked',
        'idle':        'pause',
        'error':       'pause',
    }

    def update_vacuum_attributes(self, entity_id, ha_state: str, attributes: dict):
        """
        Обновление состояний пылесоса из данных HA.

        HA state: cleaning / paused / returning / docked / idle / error / unavailable
        Сбер vacuum_cleaner_status: cleaning / paused / return_to_dock / charging
        Сбер vacuum_cleaner_command: хранит последнюю команду (start/pause/return_to_dock/resume)
        """
        # --- vacuum_cleaner_status ---
        sber_status = self.HA_VACUUM_STATUS_MAP.get(ha_state, 'charging')
        self.device_database.change_state(entity_id, 'vacuum_cleaner_status', sber_status)

        # --- battery_percentage ---
        battery = attributes.get('battery_level')
        if battery is not None:
            self.device_database.change_state(entity_id, 'battery_percentage', int(battery))

        # --- vacuum_cleaner_command: восстанавливаем из статуса при инициализации ---
        # Если команда ещё не выставлена, ставим разумное начальное значение
        if self.device_database.get_state(entity_id, 'vacuum_cleaner_command') is None:
            initial_cmd = 'start' if ha_state == 'cleaning' else 'return_to_dock'
            self.device_database.change_state(entity_id, 'vacuum_cleaner_command', initial_cmd)

    def merge_sensor_states(self, ha_entities):
        """
        Объединяет значения temperature/humidity/pressure между датчиками
        одного физического устройства (одинаковый device_id).
        """
        sensor_temp_devices: dict[str, list[str]] = {}

        for entity in ha_entities:
            entity_id = entity['entity_id']
            db_entity = self.device_database.devices_registry.get(entity_id)
            if not db_entity or db_entity.get('category') != 'sensor_temp':
                continue

            device_class = entity['attributes'].get('device_class', '')
            if device_class not in ('temperature', 'humidity', 'pressure', 'atmospheric_pressure'):
                continue

            device_id = db_entity.get('device_id')
            if device_id:
                sensor_temp_devices.setdefault(device_id, []).append(entity_id)

        for device_id, entity_ids in sensor_temp_devices.items():
            if len(entity_ids) < 2:
                continue

            combined: dict = {}
            for eid in entity_ids:
                for key, value in self.device_database.get_states(eid).items():
                    if key in ('temperature', 'humidity', 'air_pressure'):
                        combined[key] = value

            for eid in entity_ids:
                for key, value in combined.items():
                    self.device_database.change_state(eid, key, value)
