function Init(){
   AddBlok('<h1>SberGate</h1>')
   AddBlok('<a href="index.html">Перейти к настройкам СберАгента</a></p>')
   AddBlok('<h2>Команды:</h2>')
//   AddBlok('<button class="btn">&#128465; Удалить</button>')
   AddBlok('<button id="DB_delete" onclick="RunCmd(this.id)">   &#128465; Удалить базу устройств</button><button id="exit" onclick="RunCmd(this.id)">Выход</button>')
   AddBlok('<h2>Устройства:</h2>','alert')
   apiGet()
}
function AddBlok(str,CN){
   let div = document.createElement('div');
   if (CN) {div.className = CN;}
   div.innerHTML = str;
   let el = document.getElementById('root');
   if (el) {el.append(div)}
//   document.body.append(div);
}

function RunCmd(id,opt){
   alert(id+':'+opt);
   let s = {'command':id}
   apiSend(s,'/api/v2/command');
}


function ChangeDev(d){
   var t={};   var s={};
   t[d.dataset.id]={}
   t[d.dataset.id]['enabled']=d.checked;
   s['devices']=[];
   s['devices'].push(t);
   apiSend(s,'/api/v2/devices');
   //console.dir(d)
//   console.log(d.dataset.id);
//   console.log(d.checked);
}

function UpdateDeviceList(d){
console.log(d);
   let f={'enabled':'Включено','id':'ID','name':'Имя'}
   let table = document.getElementById('devices');
   if (! table) {
      table = document.createElement('table');
      table.id = 'devices';
      let pel = document.getElementById('root');
      pel.append(table);
   }

   let thead = document.createElement('thead');
   let tbody = document.createElement('tbody');

   let thead_row = document.createElement('tr');
   for (k in f) {
      let el = document.createElement('th');
      el.innerHTML = f[k];
      thead_row.append(el)
   }
   thead.appendChild(thead_row);

   for (i in d){
      let tbody_row = document.createElement('tr');
      for (k in f) {
         let el = document.createElement('td');
         switch(k){
            case 'id':
               r=i;
               break;
            case 'enabled':
               if (d[i][k]){
                  r = '<input type="checkbox" data-id="'+i+'" checked onchange=ChangeDev(this)>';
               }else{
                  r = '<input type="checkbox" data-id="'+i+'" onchange=ChangeDev(this)>';
               }

               break;
            default:
               r = d[i][k];
               break;
         }
         el.innerHTML = r; tbody_row.append(el)
      }
      tbody.appendChild(tbody_row);
   }


   table.appendChild(thead);
   table.appendChild(tbody);
//   document.getElementById('body').appendChild(table);
//   for (let k in d['devices']){
//      let v=d['devices'][k];
//      AddBlok(v['id']+':'+v['name']);
//   }
}

function apiGet(){
   let xhr = new XMLHttpRequest();
   xhr.open('GET', '/api/v2/devices');
   xhr.send();
   xhr.onload = function() {
      if (xhr.status == 200) {
//         alert(`Готово, получили ${xhr.response.length} байт`);
         UpdateDeviceList(JSON.parse(xhr.response)['devices'])
      } else { // если всё прошло гладко, выводим результат
         console.log(`Ошибка ${xhr.status}: ${xhr.statusText}`); // Например, 404: Not Found
      }
   };
   xhr.onprogress = function(event) {
      if (event.lengthComputable) {
         console.log(`Получено ${event.loaded} из ${event.total} байт`);
      } else {
         console.log(`Получено ${event.loaded} байт`); // если в ответе нет заголовка Content-Length
      }
   };
   xhr.onerror = function() {
      console.log("Запрос не удался");
   };
}

function apiSend(d,api){ console.log(d);
   if (typeof api == "undefined" ) { api = '/api/v2/devices';}
   let xhr = new XMLHttpRequest();
   let json = JSON.stringify(d);
   xhr.open('POST', api, true);
   xhr.setRequestHeader('Content-type', 'application/json; charset=utf-8');
   ///xhr.onreadystatechange = ...;
   xhr.send(json);
}