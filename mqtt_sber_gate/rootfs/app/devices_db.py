import json
from config import read_json_file, write_json_file, VERSION
from logger import log_info, log_debug, log_trace, log_deeptrace, log_warning, log_error


class DevicesDB(object):
    """
    Менеджер локальной базы данных устройств.
    Отвечает только за хранение данных и CRUD операции.
    """

    def __init__(self, db_file_path):
        """Инициализация базы данных из файла."""
        self.db_file_path = db_file_path
        self.devices_registry = read_json_file(db_file_path)

        # Убеждаемся, что у всех устройств есть флаг 'enabled'
        for entity_id in self.devices_registry:
            if self.devices_registry[entity_id].get('enabled') is None:
                self.devices_registry[entity_id]['enabled'] = False

    def generate_new_id(self, prefix):
        """Генерация уникального ID с заданным префиксом."""
        for i in range(1, 99):
            new_id = f"{prefix}_{str(i).zfill(2)}"
            if self.devices_registry.get(new_id) is None:
                return new_id
        return None

    def save_db(self):
        """Сохранение текущей базы данных на диск."""
        write_json_file(self.db_file_path, self.devices_registry)

    def clear_database(self):
        """Удаление всех устройств из базы данных."""
        self.devices_registry = {}
        self.save_db()

    def delete_device(self, entity_id):
        """Удаление устройства из базы данных."""
        if entity_id in self.devices_registry:
            self.devices_registry.pop(entity_id)
            self.save_db()
            log_info(f"Удалено устройство: {entity_id}!")

    def is_device_in_base(self, entity_id):
        """Проверка существования устройства в базе данных."""
        return entity_id in self.devices_registry

    def get_device(self, entity_id):
        """Возвращает объект устройства по ID."""
        return self.devices_registry.get(entity_id)

    def change_state(self, entity_id, state_key, value):
        """Обновление состояния конкретного атрибута устройства."""
        if entity_id not in self.devices_registry:
            log_warning(f"Устройство id={entity_id} не найдено")
            return

        device = self.devices_registry[entity_id]
        if 'States' not in device:
            log_debug(f"Для устройства id={entity_id} не найдены состояния (States). Создаем.")
            device['States'] = {}

        if state_key not in device['States']:
            log_deeptrace(f"Для устройства id={entity_id} ключ={state_key} не найден. Создаем.")

        device['States'][state_key] = value

    def get_states(self, entity_id):
        """Возвращает все состояния для конкретного устройства."""
        device = self.devices_registry.get(entity_id, {})
        return device.get('States', {})

    def get_state(self, entity_id, state_key):
        """Возвращает значение конкретного состояния устройства."""
        device = self.devices_registry.get(entity_id, {})
        states = device.get('States', {})
        return states.get(state_key)

    def update(self, entity_id, data, create_if_missing=True):
        """
        Обновление или создание записи устройства.
        :param entity_id: ID устройства
        :param data: словарь с атрибутами для обновления
        :param create_if_missing: создавать устройство, если оно не найдено
        """
        if entity_id not in self.devices_registry:
            if not create_if_missing:
                log_warning(f"Устройство {entity_id} не найдено и создание запрещено.")
                return

            log_info(f"Устройство {entity_id} не найдено. Добавляем новую запись.")
            default_attributes = {
                'enabled': False,
                'name': '',
                'default_name': '',
                'nicknames': [],
                'home': '',
                'room': '',
                'groups': [],
                'model_id': '',
                'category': '',
                'hw_version': f'hw:{VERSION}',
                'sw_version': f'sw:{VERSION}',
                'entity_ha': False,
                'entity_type': '',
                'friendly_name': ''
            }
            
            self.devices_registry[entity_id] = {}
            for key, default_val in default_attributes.items():
                self.devices_registry[entity_id][key] = data.get(key, default_val)

            if data.get('category') == 'scenario_button':
                self.devices_registry[entity_id]['States'] = {'button_event': ''}

        # Обновление данными
        for key, value in data.items():
            self.devices_registry[entity_id][key] = value

        # Убеждаемся, что имя не пустое
        if not self.devices_registry[entity_id].get('name'):
            self.devices_registry[entity_id]['name'] = self.devices_registry[entity_id].get('friendly_name', '')

        self.save_db()
