import time
import requests
from logger import log_info, log_error

from ha_rest_client import HARestClient
from ha_entity_updater import HAEntityUpdater
from ha_websocket_client import HAWebSocketClient


class HAClient:
    """
    Фасад для взаимодействия с Home Assistant.
    Делегирует ответственность специализированным классам:
      - HARestClient       — отправка команд через REST API
      - HAEntityUpdater    — маппинг и обновление сущностей в локальной БД
      - HAWebSocketClient  — подписка на события через WebSocket
    """

    def __init__(self, devices_db, sber_serializer, options, publish_status_callback):
        self.device_database = devices_db
        self.config_options = options

        self._rest = HARestClient(devices_db, options)
        self._updater = HAEntityUpdater(devices_db)
        self._ws = HAWebSocketClient(devices_db, sber_serializer, options, publish_status_callback)

    # ------------------------------------------------------------------ #
    #  Публичный API (обратная совместимость с mqtt_client.py и sber-gate) #
    # ------------------------------------------------------------------ #

    def toggle_device_state(self, entity_id):
        """Переключение состояния устройства в Home Assistant."""
        self._rest.toggle_device_state(entity_id)

    def set_climate_temperature(self, entity_id, changes):
        """Установка температуры для климатического устройства."""
        self._rest.set_climate_temperature(entity_id, changes)

    def send_vacuum_command(self, entity_id, command: str):
        """Отправка команды пылесосу."""
        self._rest.send_vacuum_command(entity_id, command)

    def initialize_entities_via_rest(self):
        """Первичная загрузка всех сущностей из HA через REST API."""
        api_url = self.config_options.get('ha-api_url', 'http://supervisor/core')
        url = f"{api_url}/api/states"
        log_info(f"Подключаемся к HA (ha-api_url: {api_url})")

        headers = self._rest._get_headers()
        response = None

        for attempt in range(1, 11):
            try:
                response = requests.get(url, headers=headers)
                break
            except Exception:
                log_error(f"Ошибка подключения к HA. Ждём 5 сек. Попытка {attempt}/10")
                time.sleep(5)

        if response and response.status_code == 200:
            log_info("Список сущностей HA получен, обрабатываем...")
            ha_entities = response.json()
        else:
            log_error("ОШИБКА! Не удалось получить сущности от HA.")
            if response:
                log_error(f"Код ответа: {response.status_code}")
            ha_entities = []

        for entity in ha_entities:
            self._updater.update_entity(entity['entity_id'], entity)

        self._updater.merge_sensor_states(ha_entities)

    def run_websocket_client(self):
        """Запуск WebSocket клиента (блокирующий, с автоматическим переподключением)."""
        self._ws.run_forever()
