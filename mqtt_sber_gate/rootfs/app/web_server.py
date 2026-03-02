import json
import os
import sys
import threading
import re
import requests
from http.server import BaseHTTPRequestHandler, HTTPServer
from logger import log_info, log_error, log_warning, log_debug, LOG_FILE
import sber_api
from config import VERSION

MIME_TYPES = {
    ".html": "text/html",
    ".js": "text/javascript",
    ".css": "text/css",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".json": "application/json",
    ".ico": "image/vnd.microsoft.icon",
    ".log": "application/octet-stream",
    "default": "text/plain"
}

# Базовая директория приложения для корректного поиска статических файлов
APP_DIR = os.path.dirname(os.path.abspath(__file__))

STATIC_ROUTES = {
    '/SberGate.log': 'SberGate.log',
    '/': 'ui2/index.html',
    '/ui2/main.js': 'ui2/main.js',
    '/ui2/main.css': 'ui2/main.css',
    '/favicon.ico': 'ui2/favicon.ico',
    '/index.html': 'ui/index.html',
    '/static/css/2.b9b863b2.chunk.css': 'ui/static/css/2.b9b863b2.chunk.css',
    '/static/css/main.1359096b.chunk.css': 'ui/static/css/main.1359096b.chunk.css',
    '/static/js/2.e21fd42c.chunk.js': 'ui/static/js/2.e21fd42c.chunk.js',
    '/static/js/main.a57bb958.chunk.js': 'ui/static/js/main.a57bb958.chunk.js',
    '/static/js/runtime-main.ccc7405a.js': 'ui/static/js/runtime-main.ccc7405a.js'
}

class RequestHandler(BaseHTTPRequestHandler):
    device_database = None
    mqtt_client = None
    http_serializer = None
    config_options = None
    agent_status_data = {}

    def send_json_response(self, data_dict):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(bytes(json.dumps(data_dict), "utf-8"))

    def send_text_response(self, text_content, content_type="text/plain"):
        self.send_response(200)
        self.send_header("Content-type", content_type)
        self.end_headers()
        self.wfile.write(bytes(text_content, "utf-8"))

    def send_static_file(self, file_path, content_type):
        self.send_response(200)
        self.send_header("Content-type", content_type)
        self.end_headers()
        try:
            with open(file_path, 'rb') as f:
                self.wfile.write(f.read())
        except Exception as e:
            log_error(f"Ошибка чтения файла {file_path}: {e}")

    def handle_root(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(bytes(
            '<!doctype html><html lang="ru"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/><title>Интеграция с умным домом Сбер</title></head><body>',
            "utf-8"))
        self.wfile.write(bytes('<h1>Управление устройствами</h1> <p><a href="index.html">Сбер Агент</a></p>', "utf-8"))
        self.wfile.write(bytes('<h1>Список устройств:</h1> <br>', "utf-8"))
        self.wfile.write(bytes('<table border="1" cellpadding="5" cellspacing="0">', "utf-8"))
        self.wfile.write(bytes('<tr><th>ID</th><th>Имя</th><th>Тип</th></tr>', "utf-8"))
        for entity_id in self.device_database.devices_registry:
            device = self.device_database.devices_registry[entity_id]
            device_name = device.get('name', '')
            device_type = device.get('entity_type', 'unknown')
            self.wfile.write(bytes(f"<tr><td>{entity_id}</td><td>{device_name}</td><td>{device_type}</td></tr>", "utf-8"))
        self.wfile.write(bytes('</table>', "utf-8"))
        self.wfile.write(bytes('</body></html>', "utf-8"))

    def handle_api_models(self):
        # TODO: Переместить этот захардкоженный список в файл конфигурации
        models_data = {
            "models": [
                {"id": "root_device", "manufacturer": "MQTT", "model": "MQTT Root Device", "description": "Модель корневого устройства", "features": ["online"], "category": "hub"},
                {"id": "ID_1", "manufacturer": "Я", "model": "Моя модель", "hw_version": "1", "sw_version": "1", "description": "Моя модель", "features": ["online", "on_off"], "category": "relay"},
                {"id": "temp_device", "manufacturer": "tempDev", "model": "Термометр", "hw_version": "1", "sw_version": "1", "description": "Датчик температуры", "features": ["on_off", "online"], "category": "relay"},
                {"id": "ID_2", "manufacturer": "Я", "model": "Датчик температуры", "hw_version": "v1", "sw_version": "v1", "description": "Датчик температуры", "features": ["online", "temperature"], "category": "sensor_temp", "allowed_values": {"temperature": {"type": "INTEGER", "integer_values": {"min": "-400", "max": "2000"}}}},
                {"id": "ID_3", "manufacturer": "Я", "model": "Датчик влажности", "hw_version": "v1", "sw_version": "v1", "description": "Датчик влажности", "features": ["online", "humidity"], "category": "sensor_temp", "allowed_values": {"humidity": {"type": "INTEGER", "integer_values": {"min": "0", "max": "1000"}}}}
            ]
        }
        self.send_json_response(models_data)

    def handle_api_devices_get(self):
        self.send_text_response(self.http_serializer.build_http_devices_list(), "application/json")

    def handle_api_devices_post(self, post_data):
        log_info(f"Сбер Агент добавляет новое устройство: {post_data}")
        category = post_data.get('category', '')
        if category:
            new_id = self.device_database.generate_new_id(category)
            self.device_database.devices_registry[new_id] = {}
            self.device_database.update(new_id, post_data)
            self.device_database.save_db()
            self.mqtt_client.publish_config()

    def handle_api_v2_devices_post(self, post_data):
        log_info(f"Обновление данных устройств: {post_data['devices']}")
        for device_entry in post_data['devices']:
            for entity_id, properties in device_entry.items():
                log_info(f"Обновление {entity_id}: {properties}")
                self.device_database.update(entity_id, properties)
        self.mqtt_client.publish_config()
        self.device_database.save_db()

    def handle_api_v2_command_post(self, post_data):
        command = post_data.get('command', 'unknown')
        if command == 'DB_delete':
            log_warning("Запрошено удаление базы данных")
            self.device_database.clear_database()
        elif command == 'exit':
            log_warning("Запрошена остановка сервера")
            sys.exit()
        else:
            log_warning(f"Получена неизвестная команда: {post_data}")

    def handle_api_v2_devices_get(self):
        self.send_text_response(self.http_serializer.build_http_devices_list_full(), "application/json")

    def handle_api_status(self):
        self.send_json_response(self.agent_status_data)

    def handle_api_categories(self):
        log_info('Запрос категорий')
        self.send_json_response(sber_api.resCategories)

    def handle_api_proxy_v1(self):
        # Проксирование запроса к HTTP API Сбера
        api_prefix = '/api/v1/'
        log_debug(f"PROXY {api_prefix}: {self.path}")
        
        # Фиктивные ответы для несуществующих эндпоинтов Сбера, которые запрашивает старый UI
        if self.path.endswith('/transformations'):
            # Загружаем локальный файл transformations.json
            try:
                transformations_path = os.path.join(os.path.dirname(__file__), 'data', 'transformations.json')
                if os.path.exists(transformations_path):
                    with open(transformations_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        # Если файл содержит ключ "transformations", возвращаем его значение, иначе весь объект
                        if "transformations" in data:
                             self.send_json_response(data["transformations"])
                        else:
                             self.send_json_response(data)
                    return
                else:
                    log_warning(f"Файл {transformations_path} не найден. Возвращаем пустой список.")
                    self.send_json_response([])
                    return
            except Exception as e:
                log_error(f"Ошибка при чтении transformations.json: {e}")
                self.send_json_response([])
                return

        if self.path.endswith('/aggregations'):
            log_warning(f"Возвращаем пустой список для {self.path} (эндпоинт устарел или не существует)")
            self.send_json_response([])
            return

        if self.path.endswith('/objects'):
             log_warning(f"Возвращаем пустой список объектов для {self.path} (эндпоинт устарел или не существует)")
             self.send_json_response({"objects": []})
             return

        target_url = f"{self.config_options['sber-http_api_endpoint']}/v1/mqtt-gate/{self.path[len(api_prefix):]}"
        headers = {'content-type': 'application/json'}
        auth = (self.config_options['sber-mqtt_login'], self.config_options['sber-mqtt_password'])
        
        try:
            response = requests.get(target_url, headers=headers, auth=auth)
            if response.status_code == 200:
                self.send_text_response(response.text, "application/json")
            else:
                log_error(f"ОШИБКА ПРОКСИ! Запрос {target_url} завершился с кодом: {response.status_code}")
        except Exception as e:
            log_error(f"Исключение ПРОКСИ: {e}")

    def do_DELETE(self):
        self.send_json_response({})
        api_prefix = '/api/v1/devices/'
        if self.path.startswith(api_prefix):
            entity_id = self.path[len(api_prefix):]
            log_info(f"УДАЛЕНИЕ устройства: {entity_id}")
            self.device_database.delete_device(entity_id)
            self.mqtt_client.publish_config()

    def do_GET(self):
        if self.path == '/SberGate.log':
            full_path = os.path.join(os.getcwd(), LOG_FILE)
            mime_type = MIME_TYPES.get('.log', MIME_TYPES['default'])
            log_debug(f"Отдача лог-файла: {full_path}")
            self.send_static_file(full_path, f"{mime_type}; charset=utf-8")
            return

        static_file_path = STATIC_ROUTES.get(self.path)
        if static_file_path:
            _, ext = os.path.splitext(static_file_path)
            mime_type = MIME_TYPES.get(ext, MIME_TYPES['default'])
            
            # Строим полный путь относительно директории приложения
            full_path = os.path.join(APP_DIR, static_file_path)
            log_debug(f"Отдача файла: {full_path} (MIME: {mime_type})")
            self.send_static_file(full_path, f"{mime_type}; charset=utf-8")
            return

        # Маршрутизация API
        routes = {
            '/': self.handle_root,
            '/api/v1/status': self.handle_api_status,
            '/api/v1/models': self.handle_api_models,
            '/api/v1/categories': self.handle_api_categories,
            '/api/v1/devices': self.handle_api_devices_get,
            '/api/v2/devices': self.handle_api_v2_devices_get,
            '/api/version': lambda: self.send_json_response({'version': VERSION})
        }
        
        handler = routes.get(self.path)
        if handler:
            handler()
        elif self.path.startswith('/api/v1/'):
            self.handle_api_proxy_v1()
        else:
            self.send_text_response(f"Запрос: {self.path}", "text/html")

    def do_PUT(self):
        self.send_json_response({})
        log_debug(f"PUT: {self.path}")
        content_length = int(self.headers['Content-Length'])
        put_data = json.loads(self.rfile.read(content_length))
        
        api_prefix = '/api/v1/devices/'
        if self.path.startswith(api_prefix):
            entity_id = self.path[len(api_prefix):]
            if entity_id == put_data.get('id'):
                self.device_database.update(entity_id, put_data)
                self.mqtt_client.publish_config()

    def do_POST(self):
        self.send_json_response({})
        log_debug(f"POST: {self.path}")
        content_length = int(self.headers['Content-Length'])
        post_data = json.loads(self.rfile.read(content_length))
        
        routes = {
            '/api/v1/devices': self.handle_api_devices_post,
            '/api/v2/devices': self.handle_api_v2_devices_post,
            '/api/v2/command': self.handle_api_v2_command_post
        }
        
        handler = routes.get(self.path)
        if handler:
            handler(post_data)
        else:
            log_warning(f"Неизвестный POST запрос: {post_data}")

class WebServer:
    def __init__(self, device_db, mqtt_client, http_serializer, config_options, agent_status):
        self.device_db = device_db
        self.mqtt_client = mqtt_client
        self.http_serializer = http_serializer
        self.config_options = config_options
        self.agent_status = agent_status
        self.host_name = ''
        self.server_port = 9123
        self.server = None
        self.server_thread = None

    def start(self):
        RequestHandler.device_database = self.device_db
        RequestHandler.mqtt_client = self.mqtt_client
        RequestHandler.http_serializer = self.http_serializer
        RequestHandler.config_options = self.config_options
        RequestHandler.agent_status_data = self.agent_status
        
        self.server = HTTPServer((self.host_name, self.server_port), RequestHandler)
        log_info(f"Веб-сервер запущен на http://{self.host_name or 'localhost'}:{self.server_port}")
        
        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.daemon = True
        self.server_thread.start()

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            log_info("Веб-сервер остановлен.")
