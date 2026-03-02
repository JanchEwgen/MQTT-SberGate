import json
import sber_api
from config import VERSION
from converters import rgb_to_sber_hsv
from logger import log_debug, log_error, log_deeptrace, log_trace, log_warning


class SberMQTTSerializer:
    """
    Сериализатор для формирования payload MQTT сообщений Сбера.
    Отвечает за преобразование данных устройств в формат, понятный Сберу.
    """

    def __init__(self, devices_db):
        self.devices_db = devices_db

    def build_mqtt_devices_payload(self):
        """Генерация JSON для публикации конфигурации устройств в Sber MQTT."""
        payload = {'devices': []}

        # Добавляем корневой хаб
        payload['devices'].append({
            "id": "root",
            "name": "Вумный контроллер",
            'hw_version': VERSION,
            'sw_version': VERSION,
            'model': {
                'id': 'ID_root_hub',
                'manufacturer': 'TM',
                'model': 'VHub',
                'description': "HA MQTT SberGate HUB",
                'category': 'hub',
                'features': ['online']
            }
        })

        for entity_id, device in self.devices_db.devices_registry.items():
            if device.get('enabled', False):
                dev_entry = {
                    'id': entity_id,
                    'name': device.get('name', ''),
                    'default_name': device.get('default_name', ''),
                    'home': device.get('home', 'Мой дом'),
                    'room': device.get('room', ''),
                    'hw_version': device.get('hw_version', ''),
                    'sw_version': device.get('sw_version', '')
                }

                category = device.get('category', 'relay')
                category_features = sber_api.Categories.get(category)

                active_features = []
                if category_features:
                    for feature in category_features:
                        feature_name = feature['name']
                        is_required = feature.get('required', False)

                        # Для датчиков игнорируем обязательность, если нет данных
                        if category == 'sensor_temp' and feature_name in ['temperature', 'humidity', 'air_pressure']:
                            is_required = False

                        if is_required:
                            active_features.append(feature_name)
                        else:
                            # Добавляем необязательные функции, если они есть в текущих состояниях
                            if feature_name in self.devices_db.get_states(entity_id):
                                active_features.append(feature_name)

                dev_entry['model'] = {
                    'id': f'ID_{category}',
                    'manufacturer': 'TM',
                    'model': f'Model_{category}',
                    'category': category,
                    'features': active_features
                }
                dev_entry['model_id'] = ''
                payload['devices'].append(dev_entry)

        json_payload = json.dumps(payload)
        log_debug(f'Новый список устройств для MQTT: {json_payload}')
        return json_payload

    def get_default_value_for_feature(self, feature):
        """Возвращает значение по умолчанию на основе типа данных Сбера."""
        data_type = feature['data_type']
        feature_name = feature.get('name', '')

        default_values_by_type = {
            'BOOL': False,
            'INTEGER': 0,
            'ENUM': '',
            'COLOUR': {'red': 255, 'green': 255, 'blue': 255}  # Белый в формате dict
        }

        value = default_values_by_type.get(data_type)
        if value is None:
            log_error(f'Неизвестный тип данных: {data_type}')
            return False

        if feature_name == 'online':
            return True
        return value

    def format_state_for_sber(self, entity_id, feature, state_value):
        """Форматирование одного значения состояния для полезной нагрузки Sber MQTT."""
        feature_name = feature['name']
        data_type = feature['data_type']

        # Сбер ожидает температуру, умноженную на 10
        if feature_name == 'temperature' and state_value is not None:
            try:
                state_value = state_value * 10
            except TypeError:
                pass

        result = {'key': feature_name, 'value': {'type': data_type}}

        if data_type == 'BOOL':
            result['value']['bool_value'] = bool(state_value)
        elif data_type == 'INTEGER':
            try:
                result['value']['integer_value'] = int(state_value) if state_value is not None else 0
            except ValueError:
                result['value']['integer_value'] = 0
        elif data_type == 'ENUM':
            result['value']['enum_value'] = str(state_value) if state_value is not None else ""
        elif data_type == 'COLOUR':
            # COLOUR в Сбере использует HSV формат: h (0-360), s (0-1000), v (100-1000)
            if isinstance(state_value, dict):
                r = state_value.get('red', 255)
                g = state_value.get('green', 255)
                b = state_value.get('blue', 255)

                h_sber, s_sber, v_sber = rgb_to_sber_hsv(r, g, b)

                result['value']['colour_value'] = {
                    'h': h_sber,
                    's': s_sber,
                    'v': v_sber
                }
                log_deeptrace(f"RGB({r},{g},{b}) -> HSV(h={h_sber}, s={s_sber}, v={v_sber})")
            else:
                log_warning(f"ПРЕДУПРЕЖДЕНИЕ: Неверный формат COLOUR для {entity_id}: {state_value}")
                result['value']['colour_value'] = {'h': 0, 's': 0, 'v': 1000}

        log_deeptrace(f"{entity_id}: {result}")
        return result

    def build_mqtt_states_payload(self, entity_id_list=None):
        """
        Генерация JSON для обновлений состояния в Sber MQTT.
        Оптимизированная версия: объединяет проверку обязательных полей и форматирование в один проход.
        """
        # Функции, которые Сбер присылает нам как команды управления.
        # Их не нужно включать в статусные обновления — Сбер и так знает их значение,
        # поскольку сам их и устанавливает.
        COMMAND_ONLY_FEATURES = {'vacuum_cleaner_command'}

        states_payload = {'devices': {}}

        if entity_id_list is None:
            # Используем keys() напрямую, чтобы избежать создания лишнего списка
            entity_id_list = self.devices_db.devices_registry.keys()

        for entity_id in entity_id_list:
            device = self.devices_db.get_device(entity_id)

            # Пропускаем отключенные или несуществующие устройства
            if not device or not device.get('enabled'):
                continue

            # Определяем категорию без записи в БД (side-effect removed)
            category = device.get('category')
            if not category:
                category = 'relay'

            features = sber_api.Categories.get(category)
            if not features:
                continue

            formatted_states = []

            for feature in features:
                feature_name = feature['name']

                # Пропускаем функции-команды — они не должны включаться в статусные обновления
                if feature_name in COMMAND_ONLY_FEATURES:
                    continue

                current_val = self.devices_db.get_state(entity_id, feature_name)

                # Если значения нет, проверяем обязательность и инициализируем дефолтным
                if current_val is None:
                    is_required = feature.get('required', False)

                    # Специальная обработка для датчиков (sensor_temp):
                    # Игнорируем флаг required для температуры и влажности, если их нет в БД.
                    # Это нужно, чтобы не отправлять humidity для чистого датчика температуры и наоборот.
                    if category == 'sensor_temp' and feature_name in ['temperature', 'humidity', 'air_pressure']:
                        is_required = False

                    if is_required:
                        current_val = self.get_default_value_for_feature(feature)
                        self.devices_db.change_state(entity_id, feature_name, current_val)
                    else:
                        # Необязательное состояние отсутствует — пропускаем
                        continue

                # Форматируем значение для Сбера
                formatted_states.append(self.format_state_for_sber(entity_id, feature, current_val))

                # Сброс событий кнопок после отправки
                if feature_name == 'button_event':
                    self.devices_db.change_state(entity_id, 'button_event', '')

            # Добавляем устройство в payload только если есть состояния
            if formatted_states:
                states_payload['devices'][entity_id] = {'states': formatted_states}

        # Если список устройств пуст, отправляем статус online для корневого хаба
        if not states_payload['devices']:
            states_payload['devices'] = {
                "root": {"states": [{"key": "online", "value": {"type": "BOOL", "bool_value": True}}]}
            }

        json_payload = json.dumps(states_payload)
        log_debug(f"Отправка состояний в Сбер: {json_payload}")
        return json_payload