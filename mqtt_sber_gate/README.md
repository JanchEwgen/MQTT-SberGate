# MQTT-SberGate
## MQTT SberGate SberDevice IoT Agent for Home Assistant

Агент представляет собой прослойку между облаком Sber и HomeAssistant (HA).
Его задача взять из HA нужные устройства, отобразить их в облаке Sber и отслеживать
изменения в облаке с последующей передачей в HomeAssistant.
На данный момент агент выбирает сущности switch (включая розетки), script, light, input_boolean, button, climate, а также датчики температуры, влажности и давления. Сущности switch, script и button отображаются как relay в облаке Sber. Сущности input_boolean отображаются как scenario_button. Сущности climate отображаются как hvac_ac. Сущности light отображаются как light. Датчики температуры, влажности и давления объединяются в один sensor_temp, если имеют одинаковый device_id.

## Первоначальные настройки.

Для работы агента необходима [регистрация в Studio](https://developers.sber.ru/studio/workspaces/) Сбера. 
В которой нужно создать интеграцию и получить регистрационные данные для агента (sber-mqtt_login, sber-mqtt_password).

Также необходим токен для взаимодействия аддона с HomeAssistant. Очень рекомендую завести для этого отдельного пользователя.
Для получения заходим в профиль пользователя и создаём долгосрочный токен доступа (ha-api_token)


## Полезные Ссылки.

Для работы с MQTT используется [Eclipse Paho™ MQTT Python Client](https://github.com/eclipse/paho.mqtt.python)

[Регистрация пространства в Studio](https://developers.sber.ru/docs/ru/smarthome/space/registration)

[Создание проекта интеграции в Studio](https://developers.sber.ru/docs/ru/smarthome/mqtt-diy/create-mqtt-diy-integration-project)

[Авторизация контроллера в облаке Sber](https://developers.sber.ru/docs/ru/smarthome/mqtt-diy/controller-authorization)

[Как работает интеграция Sber](https://developers.sber.ru/docs/ru/smarthome/mqtt-diy/integration-scheme)

[Создание интеграции Sber](https://developers.sber.ru/docs/ru/smarthome/mqtt-diy/create-mqtt-diy-integration)

[HA REST API](https://developers.home-assistant.io/docs/api/rest)

[HA WebSocket API](https://developers.home-assistant.io/docs/api/websocket)
