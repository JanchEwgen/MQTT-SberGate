import json
import os
import re
from logger import log_info, log_error

base_dir = os.path.dirname(os.path.abspath(__file__))

def _read_version_from_yaml():
    try:
        yaml_path = os.path.abspath(os.path.join(base_dir, '..', '..', 'config.yaml'))
        with open(yaml_path, 'r', encoding='utf-8') as f:
            text = f.read()
        m = re.search(r'^\s*version:\s*["\']?([^"\']+)', text, re.MULTILINE)
        if m:
            return m.group(1).strip()
    except Exception:
        pass
    env_version = (
        os.environ.get('MQTT_SBERGATE_VERSION')
        or os.environ.get('BUILD_VERSION')
        or os.environ.get('HASSIO_ADDON_VERSION')
    )
    return env_version if env_version else 'unknown'

VERSION = _read_version_from_yaml()

# В Home Assistant конфигурация аддона (options.json) всегда находится в /data
# Остальные файлы (devices.json) также лучше хранить в /data для персистентности
if os.path.exists('/data'):
    DATA_DIR = '/data'
else:
    DATA_DIR = base_dir

OPTIONS_FILE_PATH = os.path.join(DATA_DIR, 'options.json')
DEVICES_DB_FILE_PATH = os.path.join(DATA_DIR, 'devices.json')
CATEGORIES_FILE_PATH = os.path.join(DATA_DIR, 'categories.json')

OPTIONS = {}

def read_json_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = f.read()
        result = json.loads(data)
    except Exception as e:
        result = {}
        log_error(f'!!! Ошибка чтения или разбора файла {file_path}: {e}')
    return result

def write_json_file(file_path, data):
    with open(file_path, "w", encoding='utf-8') as out_file:
        json.dump(data, out_file, ensure_ascii=False, indent=4)

def load_options():
    global OPTIONS
    OPTIONS.update(read_json_file(OPTIONS_FILE_PATH))
    return OPTIONS

def update_option(key, value):
    current_value = OPTIONS.get(key, None)
    if current_value is None:
        log_info(f'В настройках отсутствует параметр: {key} (добавляю.)')
        OPTIONS[key] = value
        write_json_file(OPTIONS_FILE_PATH, OPTIONS)
    elif current_value != value:
        log_info(f'В настройках изменился параметр: {key} с {current_value} на {value} (обновляю и сохраняю).')
        OPTIONS[key] = value
        write_json_file(OPTIONS_FILE_PATH, OPTIONS)

# Автоматическая загрузка настроек при импорте
load_options()
