#!/usr/bin/with-contenv bashio

export PYTHONUNBUFFERED=1
export MQTT_SBERGATE_VERSION="$(bashio::addon.version)"

CUSTOM_DIR="/share"
APP_DIR="/app"

# Копируем Python-файлы из /share в /app, если они есть
if ls "$CUSTOM_DIR"/*.py >/dev/null 2>&1; then
    echo "$(date '+%Y%m%d-%H%M%S'): Найдены кастомные .py файлы в $CUSTOM_DIR. Копирование в $APP_DIR..."
    cp "$CUSTOM_DIR"/*.py "$APP_DIR"/
else
    echo "$(date '+%Y%m%d-%H%M%S'): Нет кастомных .py файлов в $CUSTOM_DIR, используем встроенные версии"
fi

# Копируем папку ui из /share в /app, если она есть
if [ -d "$CUSTOM_DIR/ui" ]; then
    echo "$(date '+%Y%m%d-%H%M%S'): Найдена кастомная папка ui в $CUSTOM_DIR. Копирование в $APP_DIR..."
    cp -r "$CUSTOM_DIR/ui/." "$APP_DIR/ui/"
else
    echo "$(date '+%Y%m%d-%H%M%S'): Нет кастомной папки ui в $CUSTOM_DIR, используем встроенную версию"
fi

# Копируем папку ui2 из /share в /app, если она есть
if [ -d "$CUSTOM_DIR/ui2" ]; then
    echo "$(date '+%Y%m%d-%H%M%S'): Найдена кастомная папка ui2 в $CUSTOM_DIR. Копирование в $APP_DIR..."
    cp -r "$CUSTOM_DIR/ui2/." "$APP_DIR/ui2/"
else
    echo "$(date '+%Y%m%d-%H%M%S'): Нет кастомной папки ui2 в $CUSTOM_DIR, используем встроенную версию"
fi

# Запуск основного скрипта
while true; do
    echo "$(date '+%Y%m%d-%H%M%S'): ========== SberGate запускается =========="
    python3 -u "$APP_DIR/sber-gate.py"
    echo "$(date '+%Y%m%d-%H%M%S'): Скрипт остановлен. Перезапуск через 2 секунды..."
    sleep 2
done
