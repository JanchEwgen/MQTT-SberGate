#!/usr/bin/python3
# -*- coding: utf-8 -*-

import os
import sys
import time
from logger import (
    log_info, log_warning, log_debug, log_error, log_trace, log_deeptrace,
    set_log_level, check_log_file_size, LOG_FILE
)
from config import OPTIONS, DEVICES_DB_FILE_PATH, write_json_file, VERSION, update_option
from devices_db import DevicesDB
from sber_serializer import SberMQTTSerializer
from http_serializer import HttpSerializer
from ha_api import HAClient
from mqtt_client import SberMQTTClient
from web_server import WebServer
import sber_api

# Инициализация логирования
current_log_level = OPTIONS.get('log_level', 'info')
set_log_level(current_log_level)

# Проверка размера лог-файла
check_log_file_size()

log_warning(f"Запуск MQTT SberGate IoT Agent для Home Assistant, версия: {VERSION}")
log_info(f"Операционная система: {os.name}")
log_info(f"Версия Python: {sys.version}")
log_info(f"Путь к скрипту: {os.path.realpath(__file__)}")
log_info(f"Текущая директория: {os.getcwd()}")
log_info(f"Размер файла лога: {os.path.getsize(LOG_FILE)} байт")
log_info(f"Уровень логирования: {current_log_level}")
log_debug(f"Кодировка по умолчанию: {sys.getdefaultencoding()}")
log_debug(f"Файлы в директории: {os.listdir('.')}")

# Проверка существования базы данных устройств
if not os.path.exists(DEVICES_DB_FILE_PATH):
    log_info(f"Файл базы данных не найден, создаем новый: {DEVICES_DB_FILE_PATH}")
    write_json_file(DEVICES_DB_FILE_PATH, {})

log_info(f"Загрузка базы данных устройств из devices.json")
device_db_manager = DevicesDB(DEVICES_DB_FILE_PATH)
sber_serializer = SberMQTTSerializer(device_db_manager)
http_serializer = HttpSerializer(device_db_manager)

# Инициализация MQTT клиента Сбера
sber_mqtt_handler = SberMQTTClient(device_db_manager, sber_serializer, OPTIONS)

# Инициализация клиента Home Assistant
ha_integration_client = HAClient(device_db_manager, sber_serializer, OPTIONS, sber_mqtt_handler.send_status)

# Связывание MQTT клиента с клиентом HA
sber_mqtt_handler.set_ha_client(ha_integration_client)

# Загрузка начальных состояний из Home Assistant через REST API
ha_integration_client.initialize_entities_via_rest()

# Запуск MQTT клиента
sber_mqtt_handler.start()

# Ожидание получения endpoint-а SberDevice HTTP API
if OPTIONS.get('sber-http_api_endpoint', None) is None:
    update_option('sber-http_api_endpoint', '')

while not OPTIONS['sber-http_api_endpoint']:
    log_deeptrace('Ожидание http_api_endpoint от SberDevice...')
    time.sleep(1)

log_trace(f"Получен http_api_endpoint от SberDevice: {OPTIONS['sber-http_api_endpoint']}")

# Загрузка моделей и инициализация категорий
sber_api.fetch_models()
sber_api.init_categories()

# Публикация конфигурации устройств в MQTT
sber_mqtt_handler.publish_config()

# Публикация текущих состояний всех устройств — чтобы Салют знал актуальное состояние с первого момента
log_info("Публикация начальных состояний устройств в Сбер...")
sber_mqtt_handler.send_status(sber_serializer.build_mqtt_states_payload())

# Текущий статус агента
agent_status_report = {
    "online": True,
    "error": "",
    "credentials": {
        'username': OPTIONS.get('sber-mqtt_login', 'UNKNOWN'),
        "password": "***",
        'broker': OPTIONS.get('sber-mqtt_broker', 'UNKNOWN')
    }
}

# Запуск веб-сервера для управления и мониторинга
api_web_server = WebServer(device_db_manager, sber_mqtt_handler, http_serializer, OPTIONS, agent_status_report)
api_web_server.start()

# Запуск WebSocket клиента Home Assistant (блокирующая операция)
try:
    log_info("Запуск прослушивания WebSocket Home Assistant...")
    ha_integration_client.run_websocket_client()
except KeyboardInterrupt:
    log_warning("Агент получил сигнал остановки")
finally:
    log_error("Остановка веб-сервера API...")
    api_web_server.stop()

# Основной цикл (если WebSocket завершится)
while True:
    time.sleep(10)
    log_deeptrace('Проверка работоспособности агента (Heartbeat)')