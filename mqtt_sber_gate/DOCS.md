## Для корректной работы необходимо задать следующие параметры

### Адрес API Home Assistant
  ha-api_url: "http://ha_server_ip:8123"
Вместо ha_server_ip и стандартного порта 8123, необходимо указать свои данные.
Можно указать либо IP адрес сервера HA, либо его имя, если есть такая возможность.

### Токен авторизации в Home Assistant
  ha-api_token: ""
Очень длинная строка. Внимательно копипастим полностью.
Настоятельно рекомендуется завести для этого отдельного пользователя.
Для получения заходим в профиль пользователя и создаём долгосрочный токен доступа.

### Адрес и порт MQTT брокера Сбера
  sber-mqtt_broker: "mqtt-partners.iot.sberdevices.ru"
  sber-mqtt_broker_port: 8883
Не знаю придётся ли их когда-либо менять.

###Логин и пароль для доступа к облаку Сбер
  sber-mqtt_login: "mqtt-sber-login"
  sber-mqtt_password: "mqtt-sber-password"
Выдаётся при регистрации в [Studio](https://developers.sber.ru/studio/workspaces/).
Для получения этих данных необходимо создать интеграцию.

###Адрес API Сбера
  sber-http_api_endpoint: "https://mqtt-partners.iot.sberdevices.ru"
  log_level: info


