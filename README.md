# MQTT-SberGate
## MQTT SberGate SberDevice IoT Agent for Home Assistant

Агент представляет собой прослойку между облаком Sber и HomeAssistant (HA).
Его задача взять из HA нужные устройства, отобразить их в облаке Sber и отслеживать
изменения в облаке с последующей передачей в HA.
На данный момент агент выбирает сущности switch и script и отображает их как relay в облаке Sber.

## Первоначальные настройки.

Для работы агента необходима [регистрация в Studio](https://developers.sber.ru/studio/workspaces/).

Требуется создать интеграцию и получить регистрационные данные для агента (sber-mqtt_login, sber-mqtt_password).

Также необходим токен для управления HA. Очень рекомендую завести для этого отдельного пользователя.
Для получения заходим в профиль пользователя и создаём долгосрочный токен доступа (ha-api_token)

## Изменения.
1.0.5 Добавлена возможность выбирать датчики температуры. 
      Мелкие правки панели управления.
      Проверка кода возврата при запросе списка устройств из HA.

1.0.4 Эксперименты с HA WebSocket API

Теперь появилась какая-никакая обратная связь. То есть если в HA трогаем выключатель, его состояние передаётся в облако Сбера.
Функция не особо нужная, добавлена по большей части из любопытства, когда случайно заметил, что оказвается в HA есть WebSocket API.
Добавлено опять же на скорую руку, поэтому возможно всё стало менее стабильным.

## Немного истории.

Проект начался незадолго до нового года, когда подключенную к HomeAsistant ёлочку захотелось включать голосом.
Надо сказать у Салюта "Раз-два-три ёлочка гори" очень здорово получилось.

Благо к тому времени у Sberа уже был [MQTT-to-Cloud для DIY](https://developers.sber.ru/docs/ru/smarthome/mqtt-diy/mqtt-to-diy).
Правда список поддерживаемых контроллеров ограничивается всеголишь двумя: LogicMachine и Wiren Board. Таким образом имеется только два официальных агента под указанные контроллеры.

Экспериментов было масса. Изначально даже проект начинался на php, но со временем пришло понимание, что быстрее и проще всё реализовать
на родном для HomeAssistant python и завернуть в виде аддона. Возможно лучше было бы в виде интеграции, но проблема со свободным временем
не даёт возможности разбираться и двигаться в этом направлении, да и поставленные задачи решины...

Изначально было реализовано два MQTT подключения. Первое смотрело в облако Sber, а второе в локальный MQTT брокер HomeAssistant.
Было очень неудобно, так как приходилось городить огород чтобы HomeAssistant реагировал на данные внутреннего MQTT.
Но, мне подсказали, что у HomeAssistant есть замечательный REST API с помощью которого можно очень просто им управлять.
Поэтому подключение к внутреннему MQTT HomeAssistant было отключено (код до сих пор ещё болтается в недрах агента, возможно для чего-нибудь ещё пригодится),
а управление переведено на REST API.

Также в ходе экспериментов с оригинальным агентом в проект был включен его web-интерфейс, но до конца правильная работа так и не реализована, чисто на посмотреть.

Также подсмотрел замечательную идею управления AndroidTV через adb. Поэтому кроме switch дабавились script.
Теперь стало возможно сказать ассистенту: "Включи камеру на улице". После чего отрабатывает скрипт HA который отправляет в VLC нужный поток.
Попытки прокинуть script как камеру не увенчались успехом, даже писал в поддержку. Получил ответ, что-то вроде "пока не реализовано".

## Сборка докера.
Скачиваем репозиторий через GIT, идём в папку где находится Dockerfile
```
git clone https://github.com/JanchEwgen/MQTT-SberGate/tree/main
```

Собираем образ под текущую версию
```
docker --debug build -t mqttsbergate:1.0.16 --build-arg BUILD_version=1.0.16 --build-arg BUILD_FROM=python:3 --build-arg BUILD_REF=mqttsber2 .
```
Используем следующее для DockerCompose.yaml (portainer или ваш способ на выбор через docker-compose-up например)
```
services:
  salute-bridge:
    container_name: salute-bridge
    image: mqttsbergate:1.0.16
    network_mode: host
    ports:
      - "9123:9123"
    expose:
      - "9123"
    volumes:
      - /DATA/AppData/salutebridge:/data
    restart: always
    logging:
      options:
        max-size: 10m
```
Где - /DATA/AppData/mqttsbergate папка на хосте в которой необходимо создать файл options.json, его нужно будет предзаполнить своими параметрами и рестартовать контейнер

```
{
  "ha-api_url": "http://192.168.2.113:8123",
  "ha-api_token": "*",
  "sber-mqtt_broker": "mqtt-partners.iot.sberdevices.ru",
  "sber-mqtt_broker_port": 8883,
  "sber-mqtt_login": "*",
  "sber-mqtt_password": "*",
  "sber-http_api_endpoint": "https://mqtt-partners.iot.sberdevices.ru",
  "log_level": "INFO",
  "host": "192.168.2.113",
  "port": 9123
}
```

## Ссылки.

Для работы с MQTT используется [Eclipse Paho™ MQTT Python Client](https://github.com/eclipse/paho.mqtt.python)

[Регистрация пространства в Studio](https://developers.sber.ru/docs/ru/smarthome/space/registration)

[Создание проекта интеграции в Studio](https://developers.sber.ru/docs/ru/smarthome/mqtt-diy/create-mqtt-diy-integration-project)

[Авторизация контроллера в облаке Sber](https://developers.sber.ru/docs/ru/smarthome/mqtt-diy/controller-authorization)

[Как работает интеграция Sber](https://developers.sber.ru/docs/ru/smarthome/mqtt-diy/integration-scheme)

[Создание интеграции Sber](https://developers.sber.ru/docs/ru/smarthome/mqtt-diy/create-mqtt-diy-integration)

[HA REST API](https://developers.home-assistant.io/docs/api/rest)

[HA WebSocket API](https://developers.home-assistant.io/docs/api/websocket)

[Telegram](https://t.me/+k_w9uO0h73FkNjJi)
