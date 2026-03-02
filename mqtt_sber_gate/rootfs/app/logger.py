import os
import sys
from datetime import datetime

LOG_LEVEL_LIST = {'deeptrace': 0, 'trace': 1, 'debug': 2, 'info': 3, 'notice': 4, 'warning': 5, 'error': 6, 'fatal': 7}
LOG_FILE = 'SberGate.log'
LOG_FILE_MAX_SIZE = 1024 * 1024 * 7

# Глобальный уровень логирования, по умолчанию 3 (info)
log_level = 3
log_file_handle = None

def init_logger():
    """Инициализация файлового дескриптора логгера."""
    global log_file_handle
    if log_file_handle is None or log_file_handle.closed:
        check_log_file_size()
        try:
            log_file_handle = open(LOG_FILE, "a", encoding="utf-8", buffering=1)  # Line buffering
        except Exception as e:
            print(f"FATAL ERROR: Cannot open log file {LOG_FILE}: {e}")
            sys.exit(1)

def close_logger():
    """Закрытие файлового дескриптора."""
    global log_file_handle
    if log_file_handle and not log_file_handle.closed:
        log_file_handle.close()
        log_file_handle = None

def set_log_level(level_name):
    global log_level
    log_level = LOG_LEVEL_LIST.get(level_name, 3)
    init_logger()  # Ensure logger is initialized when setting level

def log(s, l=3):
    """
    Deprecated: Используйте именованные вызовы (log_info, log_error, etc.)
    """
    global log_file_handle
    
    if l >= log_level:
        dt = datetime.now().strftime("%Y%m%d-%H%M%S.%f") + ': ' + str(s)
        print(dt)
        
        if log_file_handle and not log_file_handle.closed:
            try:
                log_file_handle.write(dt + '\n')
                # flush вызывается автоматически благодаря buffering=1 (line buffering), 
                # но для надежности при важных сообщениях можно добавить принудительный flush
                if l >= 5: # warning and above
                    log_file_handle.flush()
            except Exception as e:
                print(f"Error writing to log file: {e}")

# Именованные обертки для улучшения читаемости кода
def log_deeptrace(msg): log(msg, 0)
def log_trace(msg): log(msg, 1)
def log_debug(msg): log(msg, 2)
def log_info(msg): log(msg, 3)
def log_notice(msg): log(msg, 4)
def log_warning(msg): log(msg, 5)
def log_error(msg): log(msg, 6)
def log_fatal(msg): log(msg, 7)

def check_log_file_size():
    global log_file_handle
    if os.path.isfile(LOG_FILE):
        if os.path.getsize(LOG_FILE) > LOG_FILE_MAX_SIZE:
            # Закрываем текущий файл перед удалением
            if log_file_handle and not log_file_handle.closed:
                log_file_handle.close()
            
            try:
                os.remove(LOG_FILE)
            except Exception as e:
                print(f"Error removing log file: {e}")
            
            # Открываем новый файл
            try:
                log_file_handle = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
            except Exception as e:
                print(f"Error reopening log file: {e}")
