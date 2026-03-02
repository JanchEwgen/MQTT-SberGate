import json

class HttpSerializer:
    """
    Сериализатор для формирования payload HTTP ответов веб-сервера.
    """
    def __init__(self, devices_db):
        self.devices_db = devices_db

    def build_http_devices_list(self):
        """Генерация упрощенного списка устройств для UI/HTTP API."""
        device_list = []
        for entity_id, device in self.devices_db.devices_registry.items():
            device_info = {
                'id': entity_id,
                'name': device.get('name', ''),
                'default_name': device.get('default_name', ''),
                'nicknames': device.get('nicknames', []),
                'home': device.get('home', ''),
                'room': device.get('room', ''),
                'groups': device.get('groups', []),
                'model_id': device.get('model_id', ''),
                'category': device.get('category', ''),
                'hw_version': device.get('hw_version', ''),
                'sw_version': device.get('sw_version', '')
            }
            device_list.append(device_info)

        return json.dumps({'devices': device_list})

    def build_http_devices_list_full(self):
        """Возвращает всю базу данных в формате JSON."""
        return json.dumps({'devices': self.devices_db.devices_registry})
