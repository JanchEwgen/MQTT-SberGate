// Глобальные переменные
window.categoriesList = [];  // список категорий Сбера, загружается один раз при старте
window.devicesList = {};     // список устройств из БД, обновляется после каждого запроса


// ─── Инициализация ───────────────────────────────────────────────────────────

/**
 * Точка входа — вызывается браузером после полной загрузки страницы.
 * Строит шапку страницы, затем загружает категории и устройства.
 */
function Init() {
    showVersion();
    AddBlok('<a href="index.html">Перейти к настройкам СберАгента</a>');
    AddBlok('<a href="SberGate.log">Скачать SberGate.log</a>');
    AddBlok('<h2>Команды:</h2>');
    AddBlok(
        '<button id="DB_delete" onclick="RunCmd(this.id)">🗑 Удалить базу устройств</button>' +
        '<button id="exit" onclick="RunCmd(this.id)">Выход</button>'
    );
    AddBlok('<h2>Устройства:</h2>', 'alert');

    // Сначала загружаем категории, и только после — устройства.
    // Это важно: таблица строится уже с готовым списком категорий для <select>.
    apiGetCategories(() => apiGet());
}

function showVersion() {
    const root = document.getElementById('root');
    const versionDiv = document.createElement('div');
    versionDiv.id = 'version';
    versionDiv.innerHTML = '<h1>SberGate version: unknown</h1>';
    root.insertBefore(versionDiv, root.firstChild || null);

    const xhr = new XMLHttpRequest();
    xhr.open('GET', '/api/version');
    xhr.onload = function () {
        if (xhr.status === 200) {
            let v = 'unknown';
            try {
                v = (JSON.parse(xhr.response).version) || 'unknown';
            } catch (e) {}
            versionDiv.innerHTML = '<h1>SberGate version: ' + v + '</h1>';
        }
    };
    xhr.send();
}

/**
 * Создаёт <div> с переданным HTML и добавляет его в корневой элемент страницы.
 * @param {string} str  — HTML-содержимое блока
 * @param {string} [CN] — CSS-класс для блока (необязательно)
 */
function AddBlok(str, CN) {
    let div = document.createElement('div');
    if (CN) {
        div.className = CN;
    }
    div.innerHTML = str;

    let root = document.getElementById('root');
    if (root) {
        root.append(div);
    }
}


// ─── Обработчики действий пользователя ───────────────────────────────────────

/**
 * Отправляет команду на сервер (удаление БД, перезапуск и т.п.).
 * Вызывается кнопками с атрибутом onclick="RunCmd(this.id)".
 * @param {string} id — id кнопки, он же код команды
 */
function RunCmd(id) {
    alert(id);
    apiSend({ 'command': id }, '/api/v2/command');
}

/**
 * Вызывается при переключении чекбокса "Включено" в строке устройства.
 * Сохраняет новое значение локально и отправляет на сервер.
 * @param {HTMLInputElement} checkbox — элемент <input type="checkbox">
 */
function ChangeDev(checkbox) {
    let id = checkbox.dataset.id;
    let isEnabled = checkbox.checked;

    // Обновляем локальный кэш, чтобы при перерисовке таблицы не потерять значение
    if (window.devicesList[id]) {
        window.devicesList[id]['enabled'] = isEnabled;
    }

    let update = {};
    update[id] = { 'enabled': isEnabled };
    apiSend({ 'devices': [update] }, '/api/v2/devices');
}

/**
 * Вызывается при выборе новой категории Сбера в выпадающем списке.
 * Сохраняет новое значение локально и отправляет на сервер.
 * @param {HTMLSelectElement} select — элемент <select>
 */
function ChangeCategory(select) {
    let id = select.dataset.id;
    let newCategory = select.value;

    // Обновляем локальный кэш
    if (window.devicesList[id]) {
        window.devicesList[id]['category'] = newCategory;
    }

    let update = {};
    update[id] = { 'category': newCategory };
    apiSend({ 'devices': [update] }, '/api/v2/devices');
}


// ─── Таблица устройств ────────────────────────────────────────────────────────

/**
 * Строит или перестраивает таблицу устройств.
 * При клике на заголовок колонки — пересортировывает таблицу.
 *
 * @param {Object} devicesObj — словарь устройств вида { "entity_id": { ...поля... } }
 * @param {string|null} sortKey  — поле, по которому сортировать (null = без сортировки)
 * @param {boolean}     sortAsc  — направление сортировки (true = по возрастанию)
 */
function UpdateDeviceList(devicesObj, sortKey = null, sortAsc = true) {

    // Описание колонок: ключ — поле устройства, значение — заголовок
    const COLUMNS = {
        'enabled':     'Включено',
        'home':        'Дом',
        'room':        'Комната',
        'id':          'ID',
        'name':        'Имя',
        'entity_type': 'Тип в HomeAssistant',
        'category':    'Тип в Салюте',
        'States':      'Состояния',
    };

    // Очищаем таблицу если уже есть, или создаём новую
    let table = document.getElementById('devices');
    if (table) {
        table.innerHTML = '';
    } else {
        table = document.createElement('table');
        table.id = 'devices';
        document.getElementById('root').append(table);
    }

    // Преобразуем объект { id: device } в массив и вкладываем id внутрь каждого устройства
    let devices = Object.entries(devicesObj).map(([id, device]) => {
        device.id = id;
        return device;
    });

    // Сортировка
    if (sortKey) {
        devices.sort((a, b) => {
            let valA = (sortKey === 'States')
                ? JSON.stringify(a[sortKey] || {})
                : a[sortKey];
            let valB = (sortKey === 'States')
                ? JSON.stringify(b[sortKey] || {})
                : b[sortKey];

            // null и undefined считаем пустой строкой
            valA = (valA == null) ? '' : valA;
            valB = (valB == null) ? '' : valB;

            if (valA < valB) return sortAsc ? -1 : 1;
            if (valA > valB) return sortAsc ? 1 : -1;
            return 0;
        });
    }

    // Строим заголовок таблицы
    let thead = document.createElement('thead');
    let headerRow = document.createElement('tr');

    for (let key in COLUMNS) {
        let th = document.createElement('th');
        th.style.cursor = 'pointer';
        th.innerHTML = COLUMNS[key];

        // Стрелка направления сортировки у активной колонки
        if (sortKey === key) {
            th.innerHTML += sortAsc ? ' &#9650;' : ' &#9660;';
        }

        // Клик по заголовку — перерисовать с новой сортировкой.
        // Повторный клик по той же колонке — меняет направление.
        th.onclick = () => {
            let newSortAsc = (sortKey === key) ? !sortAsc : true;
            UpdateDeviceList(devicesObj, key, newSortAsc);
        };

        headerRow.append(th);
    }
    thead.appendChild(headerRow);

    // Строим тело таблицы
    let tbody = document.createElement('tbody');

    for (let device of devices) {
        let row = document.createElement('tr');

        for (let key in COLUMNS) {
            let td = document.createElement('td');
            td.innerHTML = renderCell(key, device);
            row.append(td);
        }

        tbody.appendChild(row);
    }

    table.appendChild(thead);
    table.appendChild(tbody);
}

/**
 * Возвращает HTML-содержимое ячейки таблицы для конкретного поля устройства.
 * @param {string} key    — ключ колонки
 * @param {Object} device — объект устройства
 * @returns {string} HTML
 */
function renderCell(key, device) {
    switch (key) {

        case 'enabled':
            // Чекбокс — data-id хранит entity_id для идентификации в обработчике
            return `<input type="checkbox" data-id="${device.id}"` +
                   (device.enabled ? ' checked' : '') +
                   ` onchange="ChangeDev(this)">`;

        case 'category':
            // Выпадающий список всех категорий Сбера
            let currentCat = device.category || '';
            let options = window.categoriesList
                .map(cat =>
                    `<option value="${cat}"${cat === currentCat ? ' selected' : ''}>${cat}</option>`
                )
                .join('');

            // Если текущая категория устройства не входит в список — добавляем её первой
            if (currentCat && !window.categoriesList.includes(currentCat)) {
                options = `<option value="${currentCat}" selected>${currentCat}</option>` + options;
            }

            return `<select data-id="${device.id}" onchange="ChangeCategory(this)">${options}</select>`;

        case 'States':
            // Состояния показываем как JSON-строку
            return device.States ? JSON.stringify(device.States) : '';

        default:
            // Все остальные поля — просто текст
            return device[key] || '';
    }
}


// ─── API: запросы к серверу ───────────────────────────────────────────────────

/**
 * Загружает список категорий Сбера с сервера.
 * Сохраняет результат в window.categoriesList.
 * После завершения (успешного или нет) вызывает callback.
 * @param {Function} callback — функция, вызываемая после загрузки
 */
function apiGetCategories(callback) {
    let xhr = new XMLHttpRequest();
    xhr.open('GET', '/api/v1/categories');

    xhr.onload = function () {
        if (xhr.status === 200) {
            let data = JSON.parse(xhr.response);
            window.categoriesList = (data.categories || []).sort();
        } else {
            console.log(`Ошибка загрузки категорий: ${xhr.status} ${xhr.statusText}`);
        }
        if (callback) callback();
    };

    xhr.onerror = function () {
        console.log('Не удалось загрузить категории');
        if (callback) callback();
    };

    xhr.send();
}

/**
 * Загружает полный список устройств из БД и отрисовывает таблицу.
 */
function apiGet() {
    let xhr = new XMLHttpRequest();
    xhr.open('GET', '/api/v2/devices');

    xhr.onload = function () {
        if (xhr.status === 200) {
            window.devicesList = JSON.parse(xhr.response)['devices'];
            UpdateDeviceList(window.devicesList);
        } else {
            console.log(`Ошибка загрузки устройств: ${xhr.status} ${xhr.statusText}`);
        }
    };

    xhr.onerror = function () {
        console.log('Не удалось загрузить список устройств');
    };

    xhr.send();
}

/**
 * Загружает данные по произвольному URL и передаёт ответ в Res_Processing.
 * @param {string} url — адрес запроса
 */
function apiGet_url(url) {
    let xhr = new XMLHttpRequest();
    xhr.open('GET', url);

    xhr.onload = function () {
        if (xhr.status === 200) {
            Res_Processing(xhr.response);
        } else {
            console.log(`Ошибка ${xhr.status}: ${xhr.statusText}`);
        }
    };

    xhr.onerror = function () {
        console.log('Запрос не удался');
    };

    xhr.send();
}

/**
 * Отправляет данные на сервер методом POST в формате JSON.
 * @param {Object} data              — данные для отправки
 * @param {string} [endpoint]        — URL эндпоинта (по умолчанию /api/v2/devices)
 */
function apiSend(data, endpoint = '/api/v2/devices') {
    let xhr = new XMLHttpRequest();
    xhr.open('POST', endpoint, true);
    xhr.setRequestHeader('Content-type', 'application/json; charset=utf-8');
    xhr.send(JSON.stringify(data));
}

/**
 * Обработчик ответа для apiGet_url. Сейчас только логирует в консоль.
 * @param {string} response — текст ответа сервера
 */
function Res_Processing(response) {
    console.log(response);
}
