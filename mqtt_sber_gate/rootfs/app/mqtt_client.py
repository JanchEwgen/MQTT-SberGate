import json
import ssl
import paho.mqtt.client as mqtt
from logger import log_info, log_error, log_warning, log_debug, log_deeptrace
from config import update_option
from converters import sber_hsv_to_rgb

class SberMQTTClient:
    """
    Клиент для взаимодействия с MQTT-брокером Сбера.
    Обеспечивает получение команд и отправку состояний устройств.
    """
    def __init__(self, device_database, sber_serializer, config_options):
        """Инициализация MQTT клиента Сбера."""
        self.device_database = device_database
        self.sber_serializer = sber_serializer
        self.config_options = config_options
        self.ha_client = None  # Устанавливается через set_ha_client
        self.mqtt_client = mqtt.Client()
        
        # Структура топиков SberDevice MQTT
        self.sber_user_login = self.config_options.get('sber-mqtt_login', 'UNKNOWN_USER')
        if self.sber_user_login == 'UNKNOWN_USER':
            log_error("КРИТИЧЕСКАЯ ОШИБКА: 'sber-mqtt_login' отсутствует в конфигурации!")
            
        self.root_topic = f"sberdevices/v1/{self.sber_user_login}"
        self.downlink_topic = f"{self.root_topic}/down"
        self.uplink_topic = f"{self.root_topic}/up"
        
        self.setup_mqtt_client()

    def set_ha_client(self, ha_client_instance):
        """Связывание с клиентом Home Assistant."""
        self.ha_client = ha_client_instance

    def on_connect(self, client, userdata, flags, reason_code):
        """Обработчик успешного подключения к брокеру."""
        if reason_code == 0:
            log_info(f"Успешное подключение к брокеру SberDevices (rc: {reason_code})")
            # Подписка на команды и обновления конфигурации
            client.subscribe(f"{self.downlink_topic}/#", qos=0)
            client.subscribe("sberdevices/v1/__config", qos=0)
        else:
            log_error(f"Ошибка подключения к брокеру SberDevices (rc: {reason_code})")

    def on_disconnect(self, client, userdata, reason_code):
        """Обработчик отключения от брокера."""
        if reason_code != 0:
            log_error(f"Неожиданное отключение от MQTT (rc: {reason_code}). Автореконнект включен.")

    def on_message_received(self, client, userdata, message):
        """Общий обработчик входящих MQTT сообщений."""
        log_deeptrace(f"MQTT сообщение: {message.topic} (QoS: {message.qos}) -> {message.payload}")

    def on_subscribe_success(self, client, userdata, mid, granted_qos):
        """Обработчик успешной подписки на топик."""
        log_info(f"Подписка успешна (MID: {mid}, QoS: {granted_qos})")

    def send_status(self, status_payload):
        """Отправка текущего статуса устройств в Сбер."""
        status_topic = f"{self.uplink_topic}/status"
        self.mqtt_client.publish(status_topic, status_payload, qos=0)

    def handle_command_message(self, client, userdata, message):
        """Обработка команд управления устройствами от Сбера."""
        try:
            command_data = json.loads(message.payload)
        except json.JSONDecodeError:
            log_error(f"Ошибка декодирования команды: {message.payload}")
            return

        log_debug(f"Получена команда от Сбера через MQTT: {command_data}")
        
        last_entity_id = None
        for entity_id, device_data in command_data.get('devices', {}).items():
            last_entity_id = entity_id
            state_changes = {}
            
            for state_item in device_data.get('states', []):
                key = state_item['key']
                value_wrapper = state_item['value']
                value_type = value_wrapper.get('type', '')
                
                new_value = None
                if value_type == 'BOOL':
                    new_value = value_wrapper.get('bool_value', False)
                elif value_type == 'INTEGER':
                    new_value = value_wrapper.get('integer_value', 0)
                elif value_type == 'ENUM':
                    new_value = value_wrapper.get('enum_value', '')
                elif value_type == 'COLOUR':
                    # Сбер отправляет цвет в формате HSV: h (0-360), s (0-1000), v (100-1000)
                    colour_value = value_wrapper.get('colour_value', {})
                    h = colour_value.get('h', 0)
                    s = colour_value.get('s', 1000)
                    v = colour_value.get('v', 1000)
                    
                    # Конвертируем HSV в RGB
                    r, g, b = sber_hsv_to_rgb(h, s, v)
                    new_value = {
                        'red': r,
                        'green': g,
                        'blue': b
                    }
                    log_deeptrace(f"HSV(h={h}, s={s}, v={v}) -> RGB({r},{g},{b})")

                # Отслеживаем, изменилось ли значение на самом деле
                current_value = self.device_database.get_state(entity_id, key)
                state_changes[key] = (current_value != new_value)

                # Обновляем локальную базу данных
                self.device_database.change_state(entity_id, key, new_value)
                
                # Устанавливаем ожидаемое состояние для фильтрации эха
                device_info = self.device_database.devices_registry.get(entity_id, {})
                device_info['_expected_mqtt_state'] = new_value

            # Передаем команду в Home Assistant
            if self.ha_client:
                device_info = self.device_database.devices_registry.get(entity_id, {})
                if device_info.get('entity_type') == 'climate':
                    self.ha_client.set_climate_temperature(entity_id, state_changes)
                elif device_info.get('entity_type') == 'vacuum':
                    # Команды пылесоса приходят как vacuum_cleaner_command
                    vacuum_command = self.device_database.get_state(entity_id, 'vacuum_cleaner_command')
                    if vacuum_command:
                        self.ha_client.send_vacuum_command(entity_id, vacuum_command)
                    else:
                        log_warning(f"Получена команда пылесосу {entity_id}, но vacuum_cleaner_command пуст")
                elif device_info.get('entity_ha', False):
                    self.ha_client.toggle_device_state(entity_id)
                else:
                    log_info(f"Устройство не найдено или не управляется HA: {entity_id}")
        
        # Отправляем подтверждение с обновленным статусом
        if last_entity_id:
            self.send_status(self.sber_serializer.build_mqtt_states_payload([last_entity_id]))

    def handle_status_request(self, client, userdata, message):
        """Обработка запроса текущего состояния устройств."""
        try:
            request_data = json.loads(message.payload)
            device_ids = request_data.get('devices', [])
        except:
            device_ids = []
            
        log_debug(f"Получен запрос статуса для: {device_ids}")
        response_payload = self.sber_serializer.build_mqtt_states_payload(device_ids)
        self.send_status(response_payload)

    def handle_config_request(self, client, userdata, message):
        """Обработка запроса конфигурации устройств."""
        log_info("Получен запрос конфигурации устройств")
        config_payload = self.sber_serializer.build_mqtt_devices_payload()
        self.mqtt_client.publish(f"{self.uplink_topic}/config", config_payload, qos=0)

    def handle_global_config(self, client, userdata, message):
        """Обработка глобальной конфигурации от Сбера."""
        try:
            global_config = json.loads(message.payload)
            endpoint = global_config.get('http_api_endpoint', '')
            if endpoint:
                update_option('sber-http_api_endpoint', endpoint)
        except Exception as e:
            log_error(f"Ошибка обработки глобальной конфигурации: {e}")

    def on_mqtt_error(self, client, userdata, message):
        """Обработчик ошибок MQTT."""
        log_error(f"Ошибка Sber MQTT: {message.topic} -> {message.payload}")

    def setup_mqtt_client(self):
        """Настройка MQTT клиента: коллбэки, авторизация, TLS."""
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_subscribe = self.on_subscribe_success
        self.mqtt_client.on_message = self.on_message_received
        self.mqtt_client.on_disconnect = self.on_disconnect
        
        # Коллбэки для конкретных топиков
        self.mqtt_client.message_callback_add("sberdevices/v1/__config", self.handle_global_config)
        self.mqtt_client.message_callback_add(f"{self.downlink_topic}/errors", self.on_mqtt_error)
        self.mqtt_client.message_callback_add(f"{self.downlink_topic}/commands", self.handle_command_message)
        self.mqtt_client.message_callback_add(f"{self.downlink_topic}/status_request", self.handle_status_request)
        self.mqtt_client.message_callback_add(f"{self.downlink_topic}/config_request", self.handle_config_request)

        # Авторизация и TLS
        mqtt_user = self.config_options.get('sber-mqtt_login', '')
        mqtt_pass = self.config_options.get('sber-mqtt_password', '')
        
        if mqtt_user and mqtt_pass:
            self.mqtt_client.username_pw_set(mqtt_user, mqtt_pass)
        else:
            log_warning("ПРЕДУПРЕЖДЕНИЕ: Данные MQTT отсутствуют в конфигурации!")
            
        # Сбер использует специфические сертификаты, отключаем проверку для совместимости
        self.mqtt_client.tls_set(certfile=None, keyfile=None, cert_reqs=ssl.CERT_NONE, tls_version=None)
        self.mqtt_client.tls_insecure_set(True)

    def start(self):
        """Подключение к брокеру и запуск цикла обработки сообщений."""
        broker_host = self.config_options.get('sber-mqtt_broker', 'mqtt.sberdevices.ru')
        broker_port = self.config_options.get('sber-mqtt_broker_port', 8883)
        log_info(f"Подключение к брокеру Sber MQTT: {broker_host}:{broker_port}")
        
        try:
            self.mqtt_client.connect(broker_host, broker_port, keepalive=60)
            self.mqtt_client.loop_start()
        except Exception as e:
            log_error(f"КРИТИЧЕСКАЯ ОШИБКА: Не удалось подключиться к Sber MQTT: {e}")

    def publish_config(self):
        """Публикация конфигурации всех включенных устройств в Сбер."""
        config_payload = self.sber_serializer.build_mqtt_devices_payload()
        self.mqtt_client.publish(f"{self.uplink_topic}/config", config_payload, qos=0)
        log_info("Конфигурация устройств опубликована в Sber MQTT")
