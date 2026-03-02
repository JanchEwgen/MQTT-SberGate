import requests
from logger import log_info, log_debug, log_deeptrace
from converters import sber_brightness_to_ha, sber_temp_to_ha


class HARestClient:
    """
    Клиент для отправки команд в Home Assistant через REST API.
    Отвечает только за исходящие HTTP-запросы к HA.
    """

    def __init__(self, device_database, config_options):
        self.device_database = device_database
        self.config_options = config_options

    def _get_headers(self):
        """Формирование заголовков авторизации."""
        token = self.config_options.get('ha-api_token', '')
        return {
            'Authorization': f"Bearer {token}",
            'content-type': 'application/json'
        }

    def _base_url(self):
        return self.config_options.get('ha-api_url', 'http://supervisor/core')

    def _post(self, url, payload):
        log_debug(f"REST запрос в HA: {url} | данные: {payload}")
        try:
            requests.post(url, json=payload, headers=self._get_headers())
        except Exception as e:
            from logger import log_error
            log_error(f"Ошибка REST запроса к HA: {e}")

    def toggle_device_state(self, entity_id):
        """Переключение состояния устройства (вкл/выкл) в Home Assistant."""
        is_on = self.device_database.get_state(entity_id, 'on_off')
        domain, _ = entity_id.split('.', 1)
        log_info(f"Отправляем команду в HA для {entity_id} ON: {is_on}")

        base = f"{self._base_url()}/api/services/{domain}/"
        payload = {"entity_id": entity_id}

        if domain in ('button', 'input_button'):
            self._post(base + 'press', payload)
            log_deeptrace(f"Нажатие кнопки {entity_id}")
            return

        service = 'turn_on' if is_on else 'turn_off'

        if domain == 'light' and is_on:
            payload.update(self._build_light_payload(entity_id))

        self._post(base + service, payload)

    def _build_light_payload(self, entity_id):
        """Формирование дополнительных параметров для команды включения света."""
        extra = {}

        brightness_sber = self.device_database.get_state(entity_id, 'light_brightness')
        if brightness_sber is not None:
            ha_brightness = sber_brightness_to_ha(brightness_sber)
            extra['brightness'] = ha_brightness
            log_info(f"Яркость для {entity_id}: Сбер:{brightness_sber} -> HA:{ha_brightness}")

        light_colour = self.device_database.get_state(entity_id, 'light_colour')
        if light_colour and isinstance(light_colour, dict):
            extra['rgb_color'] = [
                light_colour.get('red', 255),
                light_colour.get('green', 255),
                light_colour.get('blue', 255)
            ]
            log_info(f"RGB для {entity_id}: {extra['rgb_color']}")
        else:
            colour_temp_sber = self.device_database.get_state(entity_id, 'light_colour_temp')
            if colour_temp_sber is not None:
                ha_mireds = sber_temp_to_ha(colour_temp_sber)
                extra['color_temp'] = ha_mireds
                log_info(f"Цветовая температура для {entity_id}: Сбер:{colour_temp_sber} -> HA:{ha_mireds} mired")

        return extra

    def send_vacuum_command(self, entity_id, command: str):
        """
        Отправка команды пылесосу в Home Assistant.

        Маппинг команд Сбера -> сервисы HA vacuum:
          start          -> vacuum/start
          pause          -> vacuum/pause
          return_to_dock -> vacuum/return_to_base
          resume         -> vacuum/start  (HA не различает start и resume)
        """
        COMMAND_TO_HA_SERVICE = {
            'start':          'start',
            'pause':          'pause',
            'return_to_dock': 'return_to_base',
            'resume':         'start',
        }
        service = COMMAND_TO_HA_SERVICE.get(command)
        if not service:
            from logger import log_warning
            log_warning(f"Неизвестная команда пылесоса от Сбера: {command}")
            return

        log_info(f"Команда пылесосу {entity_id}: Сбер:'{command}' -> HA:'{service}'")
        url = f"{self._base_url()}/api/services/vacuum/{service}"
        self._post(url, {"entity_id": entity_id})

    def set_climate_temperature(self, entity_id, changes):
        """Установка целевой температуры для климатических устройств."""
        domain, _ = entity_id.split('.', 1)
        log_info(f"Команда климата в HA для {entity_id}")
        url = f"{self._base_url()}/api/services/{domain}/set_temperature"

        target_temp = self.device_database.get_state(entity_id, 'hvac_temp_set')
        is_on = self.device_database.get_state(entity_id, 'on_off')

        payload = {
            "entity_id": entity_id,
            "temperature": target_temp,
            "hvac_mode": "cool" if is_on else "off"
        }
        self._post(url, payload)