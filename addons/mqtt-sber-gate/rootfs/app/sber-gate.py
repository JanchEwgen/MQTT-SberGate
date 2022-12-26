#!/usr/bin/python3
# -*- coding: utf-8 -*-

import paho
import sys
import os
import time
import random
import json
import paho.mqtt.client as mqtt
import ssl
import requests

from http.server import BaseHTTPRequestHandler, HTTPServer

#import locale
#locale.getpreferredencoding()

#*******************************
def json_read(f):
   d=open(f,'r', encoding='utf-8').read()
   try:
      r=json.loads(d)
   except:
      r={}
      log('!!! Неверная конфигурация в файле: '+f)
   return r

def json_write(f,d):
   out_file = open(f, "w")
   json.dump(d, out_file)
   out_file.close()

def options_change(k,v):
   t=Options.get(k,None)
   if (t is None):
      log('В настройках отсутствует параметр: '+k+' (добавляю.)')
   if (t != v):
      Options[k]=v
      log('В настройках изменился параметр: '+k+' с '+str(t)+' на '+str(v)+' (обновляю и сохраняю).')
      json_write(fOptions,Options)

def ha_switch(id,OnOff):
   log('Отправляем команду в HA для '+id+' ON: '+str(OnOff))
   if OnOff:
      url=Options['ha-api_url']+'/api/services/switch/turn_on'
   else:
      url=Options['ha-api_url']+'/api/services/switch/turn_off'
   hds = {'Authorization': 'Bearer '+Options['ha-api_token'], 'content-type': 'application/json'}
   response=requests.post(url, json={"entity_id": "switch."+id}, headers=hds)
   if response.status_code == 200:
      log(response.text)
   else:
      log(response.status_code)


#*******************************
class CDevicesDB(object):
   """docstring"""
   def __init__(self, f):
      """Constructor 'devices.json'"""
      self.fDB=f
      self.DB=json_read(fDevicesDB)
      self.mqtt_json_devices_list='{}'
      self.mqtt_json_states_list='{}'
      self.http_json_devices_list='{}'
      self.do_mqtt_json_devices_list()
      self.do_mqtt_json_states_list({})
      self.do_http_json_devices_list()

   def NewID(self,a):
      r=''
      for i in range(1,99):
         r=a+'_'+('00'+str(i))[-2:]
         if (self.DB.get(r,None) is None):
            return r

   def save_DB(self):
      json_write(self.fDB,self.DB)
#      self.do_http_json_devices_list()


   def dev_add(self):
      print('device_Add')

   def dev_del(self,id):
      self.DB.pop(id, None)
      self.save_DB()
      log('Delete Device: '+id+'!')

   def change_state(self,id,key,value):
      if self.DB.get(id,None) is None:
         log('Device id='+str(id)+' not found')
         return
      if self.DB[id].get('States',None) is None:
         log('Device id='+str(id)+' States not Found. Create.')
         self.DB[id]['States']={}
      if self.DB[id]['States'].get(key,None) is None:
         log('Device id='+str(id)+' key='+str(key)+' not Found. Create.')
      self.DB[id]['States'][key]=value
      self.do_mqtt_json_states_list([id])

   def get_state(self,id,key):
      d=self.DB.get(id,{})
      s=d.get('States',{})
      k=s.get(key,None)
      if k:
         return k

   def update(self,id,d):
      fl={'enabled':True,'name':'','default_name':'','nicknames':[],'home':'','room':'','groups':[],'model_id':'','category':'','hw_version':'','sw_version':''}
      fl['entity']=''
      fl['friendly_name']=''
      if (self.DB.get(id,None) is None):
         log('Device '+id+' Not Found. Adding')
         self.DB[id]={}
         for k,v in fl.items():
            self.DB[id][k]=d.get(k,v)
      for k,v in d.items():
         self.DB[id][k]=d.get(k,v)
      if (self.DB[id]['name'] == ''):
         self.DB[id]['name'] = self.DB[id]['friendly_name']
      self.save_DB()

   def DeviceStates_mqttSber(self,id):
      d=self.DB.get(id,None)
      r=[]
      if (d is None):
         log('Запрошен несуществующий объект: '+id)
         return r
      s=d.get('States',None)
      if (s is None):
         log('У объекта: '+id+'отсутствует информация о состояниях')
         return r
      for k,v in s.items():
         if (isinstance(v,bool)):
            o={'key':k,'value':{"type": "BOOL", "bool_value": v}}
         elif (isinstance(v, int)):
            o={'key':k,'value':{"type": "INTEGER", "integer_value": v}}
         else:
            o={'key':k,'value':{"type": "BOOL", "bool_value": False}}
         r.append(o)
      return r

   def do_mqtt_json_devices_list(self):
      Dev={}
      Dev['devices']=[]
      for k,v in self.DB.items():
         if v.get('enabled',False):
            d={}
            d['id']=k
            d['name']=v.get('name','')
            d['default_name']=v.get('default_name','')
            d['model']={'id': 'model_01', 'manufacturer': 'Janch', 'model': 'Janch Device', 'category': 'relay', 'features': ['online','on_off']}
            d['model_id']=''
            Dev['devices'].append(d)
      self.mqtt_json_devices_list=json.dumps(Dev)
      log('New Devices List for MQTT: '+self.mqtt_json_devices_list)
      return self.mqtt_json_devices_list

   def do_mqtt_json_states_list(self,dl):
      if (len(dl) == 0):
         dl=self.DB.keys()
      DStat={}
      DStat['devices']={}
      for id in dl:
         d=self.DB.get(id,None)
         if not (d is None):
            s=d.get('States',None)
            if (s is None):
               log('У объекта: '+id+'отсутствует информация о состояниях')
               self.DB[id]['States']={}
               self.DB[id]['States']['online']=True
            DStat['devices'][id]={}
            DStat['devices'][id]['states']=self.DeviceStates_mqttSber(id)
      self.mqtt_json_states_list=json.dumps(DStat)
      return self.mqtt_json_states_list

   def do_http_json_devices_list(self):
      Dev={}
      Dev['devices']=[]
      x=[]
      for k,v in self.DB.items():
         r={}
         r['id']=k
         r['name']=v.get('name','')
         r['default_name']=v.get('default_name','')
         r['nicknames']=v.get('nicknames',[])
         r['home']=v.get('home','')
         r['room']=v.get('room','')
         r['groups']=v.get('groops',[])
         r['model_id']=v['model_id']
         r['category']=v.get('category','')
         r['hw_version']=v.get('hw_version','')
         r['sw_version']=v.get('sw_version','')
         x.append(r)
         Dev['devices'].append(r)
      self.http_json_devices_list=json.dumps({'devices':x})
      return self.http_json_devices_list

   def do_http_json_devices_list_2(self):
      return json.dumps({'devices':self.DB})

#-------------------------------------------------
def on_connect_local(mqttc, obj, flags, rc):
   log("HA Connect Local Broker, rc: " + str(rc))

#-------------------------------------------------
def on_connect(mqttc, obj, flags, rc):
   if rc==0:
      log("Connect OK SberDevices Broker, rc: " + str(rc))
      mqttc.subscribe(stdown+"/#", 0)
      mqttc.subscribe("sberdevices/v1/__config", 0)
   else:
      log("Connect Fail SberDevices Broker, rc: " + str(rc))
#0: Connection successful
#1: Connection refused – incorrect protocol version
#2: Connection refused – invalid client identifier
#3: Connection refused – server unavailable
#4: Connection refused – bad username or password
#5: Connection refused – not authorised
#6-255: Currently unused.



def on_disconnect(client, userdata, rc):
    if rc != 0:
        log("Unexpected MQTT disconnection. Will auto-reconnect")

def on_message(mqttc, obj, msg):
    log(msg.topic + " " + str(msg.qos) + " " + str(msg.payload))

def on_publish(mqttc, obj, mid):
    log("mid: " + str(mid))

def on_subscribe(mqttc, obj, mid, granted_qos):
    log("SD Subscribed: " + str(mid) + " " + str(granted_qos))

def on_log(mqttc, obj, level, string):
    log(string)

def send_status(mqttc, s):
   infot = mqttc.publish(sber_root_topic+'/up/status', s, qos=0)

#********************************************

def on_message_cmd(mqttc, obj, msg):
   data=json.loads(msg.payload)
#Command: {'devices': {'Relay_03': {'states': [{'key': 'on_off', 'value': {'type': 'BOOL'}}]}}}
   log("Command: " + str(data))
#   log('DevicesDB: '+str(DevicesDB.DB))
   for id,v in data['devices'].items():
      for k in v['states']:
         if k['key'] == 'on_off':
            val=k['value'].get('bool_value',False)
            log('on_off set to '+str(val))
#            infot = mqttHA.publish("sberdevices/"+id, str(val), qos=0)
            DevicesDB.change_state(id,k['key'],val)
            ha_switch(id,val)
         if k['value']['type'] == 'INTEGER':
            DevicesDB.change_state(id,k['key'],k['value'].get('integer_value',0))
   send_status(mqttc,DevicesDB.do_mqtt_json_states_list([]))
   log(DevicesDB.mqtt_json_states_list)

def on_message_stat(mqttc, obj, msg):
   data=json.loads(msg.payload).get('devices',[])
   log("GetStatus: "  +  str(msg.payload))
   send_status(mqttc,DevicesDB.do_mqtt_json_states_list(data))
   log("Answer: "+DevicesDB.mqtt_json_states_list)


def on_errors(mqttc, obj, msg):
   log("Sber MQTT Errors: " + msg.topic + " " + str(msg.qos) + " " + str(msg.payload))

def on_message_conf(mqttc, obj, msg):
   print("Config: " + msg.topic + " " + str(msg.qos) + " " + str(msg.payload))

def on_global_conf(mqttc, obj, msg):
   data=json.loads(msg.payload)
   options_change('sber-http_api_endpoint',data.get('http_api_endpoint',''))

def log(s):
   dt=time.strftime("%Y%m%d-%H%M%S", time.localtime())
   print(dt+': '+str(s))

#********** Start **********************************
#https://developers.sber.ru/docs/ru/smarthome/c2c/value
sber_types={'FLOAT':'float_value','INTEGER':'integer_value','STRING':'string_value','BOOL':'bool_value','ENUM':'enum_value','JSON':'','COLOUR':'colour_value'}
#

log('Start MQTT SberDevice IoT Agent for Home Assistant')
log("Запущено в системе: "+ os.name)
log("Текущая директория: "+ os.getcwd())
log("Кодировка: "+ sys.getdefaultencoding())
#log(": "+ sys.getfilesystemencoding())
#log(": "+ sys.getfilesystemencodeerrors())
#log(": "+ str(sys.maxunicode))

#sys.setdefaultencoding('utf8')
#print(sys.stdout.encoding)

fOptions='options.json'
fDevicesDB='devices.json'

Options=json_read(fOptions)
if not os.path.exists(fDevicesDB):
   json_write(fDevicesDB,{})

DevicesDB=CDevicesDB(fDevicesDB)
AgentStatus={"online": True, "error": "",  "credentials": {'username':Options['sber-mqtt_login'],"password": "***",'broker': Options['sber-mqtt_broker']}}

#log(Options['ha-api_url'])
#log(Options['ha-api_token'])


#url = "http://localhost:8123/ENDPOINT"
hds = {'Authorization': 'Bearer '+Options['ha-api_token'], 'content-type': 'application/json'}
url=Options['ha-api_url']+'/api/states'
res = requests.get(url, headers=hds).json()

for s in res:
   a,b=s['entity_id'].split('.',1)
   if (a == 'switch'):
      attr=s['attributes'].get('friendly_name','')
      log('switch: ' + b + ' '+attr)
      DevicesDB.update(b,{'entity':a,'friendly_name':attr})

#******************* Configure Local client (HA Broker)

#mqttHA = mqtt.Client("SberDevicesAgent local client")
#mqttHA.on_connect = on_connect_local
#mqttHA.username_pw_set(Options['ha-mqtt_login'], Options['ha-mqtt_password'])
#mqttHA.connect(Options['ha-mqtt_broker'], Options['ha-mqtt_broker_port'], 60)

#******************* Configure client (SberDevices Broker)
mqttc = mqtt.Client("HA client")
mqttc.on_connect = on_connect
mqttc.on_subscribe = on_subscribe
#mqttc.on_publish = on_publish
mqttc.on_message = on_message
mqttc.on_disconnect = on_disconnect
# Uncomment to enable debug messages
#mqttc.on_log = on_log
mqttc.message_callback_add("sberdevices/v1/__config", on_global_conf)
sber_root_topic='sberdevices/v1/'+Options['sber-mqtt_login']
stdown=sber_root_topic + "/down"
mqttc.message_callback_add(stdown+"/errors", on_errors)
mqttc.message_callback_add(stdown+"/commands", on_message_cmd)
mqttc.message_callback_add(stdown+"/status_request", on_message_stat)
mqttc.message_callback_add(stdown+"/config_request", on_message_conf)

#mqttc = mqtt.Client("",0)
mqttc.username_pw_set(Options['sber-mqtt_login'], Options['sber-mqtt_password'])
mqttc.tls_set(certfile=None, keyfile=None, cert_reqs=ssl.CERT_NONE, tls_version=None)
mqttc.tls_insecure_set(True)
mqttc.connect(Options['sber-mqtt_broker'], Options['sber-mqtt_broker_port'], 60)

infot = mqttc.publish(sber_root_topic+'/up/config', DevicesDB.do_mqtt_json_devices_list(), qos=0)

#*********************************
mqttc.loop_start()
#mqttHA.loop_start()

if Options.get('sber-http_api_endpoint',None) is None:
   options_change('sber-http_api_endpoint','')
while (Options['sber-http_api_endpoint'] == ''):
   log('Ожидаем получение SberDevice http_api_endpoint')
   time.sleep(1)
log('SberDevice http_api_endpoint: '+Options['sber-http_api_endpoint'])


hds = {'content-type': 'application/json'}
if not os.path.exists('models.json'):
   log('Файл моделей отсутствует. Получаем...')
   SD_Models = requests.get(Options['sber-http_api_endpoint']+'/v1/mqtt-gate/models', headers=hds,auth=(Options['sber-mqtt_login'], Options['sber-mqtt_password'])).json()
   json_write('models.json',SD_Models)

if not os.path.exists('categories.json'):
   log('Файл категорий отсутствует. Получаем...')
   SD_Categories = requests.get(Options['sber-http_api_endpoint']+'/v1/mqtt-gate/categories', headers=hds,auth=(Options['sber-mqtt_login'], Options['sber-mqtt_password'])).json()
   json_write('categories.json',SD_Categories)

#************** WebServer*********************************
def send_data(self,data,ct):
   self.send_response(200) 
   self.send_header("Content-type", ct)
   self.end_headers()
   self.wfile.write(bytes(data, "utf-8"))
   return 'send_sata'

def send_file(self,file,ct):
   self.send_response(200) 
   self.send_header("Content-type", ct)
   self.end_headers()
   f = open(file, 'rb')
   self.wfile.write(f.read())

def api_root(self):
   self.send_response(200) 
   self.send_header("Content-type", "text/html")
   self.end_headers()
   self.wfile.write(bytes('<!doctype html><html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/><title>Интеграция с умным домом Сбер</title></head><body>', "utf-8"))
   self.wfile.write(bytes('<h1>Управление устройствами</h1> <p><a href="index.html">Сбер Агент</a></p>', "utf-8"))
   self.wfile.write(bytes('<h1>Список устройств:</h1> <br>', "utf-8"))
   for k in DevicesDB.DB:
      self.wfile.write(bytes(k + ':' + DevicesDB.DB[k]['name']+'<br>', "utf-8"))
   self.wfile.write(bytes('</body></html>', "utf-8"))

def api_models(self):
   d='{"models":[{"id":"root_device","manufacturer":"MQTT","model":"MQTT Root Device","description":"Root device model","features":["online"],"category":"hub"},{"id":"ID_1","manufacturer":"Я","model":"Моя модель","hw_version":"1","sw_version":"1","description":"Моя модель","features":["online","on_off"],"category":"relay"},{"id":"temp_device","manufacturer":"tempDev","model":"Термометр","hw_version":"1","sw_version":"1","description":"Датчик температуры","features":["on_off","online"],"category":"relay"},{"id":"ID_2","manufacturer":"Я","model":"Датчик температуры","hw_version":"v1","sw_version":"v1","description":"Датчик температуры","features":["online","temperature"],"category":"sensor_temp","allowed_values":{"temperature":{"type":"INTEGER","integer_values":{"min":"-400","max":"2000"}}}}]}'
   send_data(self,d,"application/json")
   return 'models'

def api_devices(self):
   send_data(self, DevicesDB.do_http_json_devices_list(), "application/json")

def api_devices_post(self,d):
   log('SberAgent добавляет новое устройство: '+str(d))
   cat=d.get('category','')
   if cat != '':
      id=DevicesDB.NewID(cat)
      DevicesDB.DB[id]={}
      DevicesDB.update(id, d)
      DevicesDB.save_DB()
      infot = mqttc.publish(sber_root_topic+'/up/config', DevicesDB.do_mqtt_json_devices_list(), qos=0)

def api_default_post(self,d):
   log('Неизвестный POST запрос '+str(d))

def api2_devices_post(self,d):
   log('Меняем данные для'+str(d['devices']))
   for i in d['devices']:
      for id,prop in i.items():
         log(id+':'+str(prop))
         DevicesDB.update(id, prop)
   infot = mqttc.publish(sber_root_topic+'/up/config', DevicesDB.do_mqtt_json_devices_list(), qos=0)
   DevicesDB.save_DB()

def api2_devices(self):
   send_data(self, DevicesDB.do_http_json_devices_list_2(), "application/json")

def api_status(self):
#   d='{  "online": true, "error": "",  "credentials": {    "username": "cc94hhd7uhdtqejhmhh0",    "password": "***",    "broker": "hasrv.janch.ru:1883"  }}'
   send_data(self,json.dumps(AgentStatus),"application/json")

def api_objects(self):
   d='{"objects": [{"id": "__false","description": "Always false fake object"},{"id": "__true","description": "Always true fake object"}]}'
   send_data(self,d,"application/json")
def api_transformations(self):
   d='{"transformations": [{"name": "integer_scale","help": "Args format: %d,%d->%d,%d"},{"name": "float_scale","help": "Args format: %d,%d->%d,%d"},{"name": "boolean_invert","help": "Inverts boolean value"},{"name": "multiplication","help": "Args format: %f"},{"name": "mapping","help": "Args example (last is fallback): BOOL->INTEGER|false->0|true->100"}]}'
   send_data(self,d,"application/json")
def api_categories(self):
   d='{"categories": ["light","socket","relay","led_strip","hub","ipc","sensor_pir","sensor_door","sensor_temp","scenario_button","hvac_ac","hvac_fan","hvac_humidifier","hvac_air_purifier","hvac_heater","hvac_radiator","hvac_boiler","hvac_underfloor_heating","window_blind","curtain","gate","kettle","sensor_water_leak","valve"]}'
   send_data(self,d,"application/json")
def api_categories_relay_features(self):
   d='{"features": [{"name": "online","required": true,"type": "BOOL"},{"name": "voltage","type": "INTEGER","allowed_integer_values": {"max": "500"}},{"name": "on_off","required": true,"type": "BOOL"    },    {      "name": "current",      "type": "INTEGER",      "allowed_integer_values": {        "max": "3000"      }    },    {      "name": "power",      "type": "INTEGER",      "allowed_integer_values": {        "max": "5000"      }    }  ]}'
   send_data(self,d,"application/json")

def api_default(self):
   d='<html><head><title>HA</title></head>'\
      '<p>Request: ' + self.path + '</p>'\
      '<body><p>This is an example web server.</p></body></html>'
   send_data(self,d,"text/html")
   return self.path

def static_answer(self,file):
   p,e = os.path.splitext(file)
   m=ext_mime_types.get(e,ext_mime_types['default'])
   if (os.name == 'nt'):
      f=file.replace('/','\\')
   else:
      f=file
   log('Отправка статического файла: '+f+'; MIME:'+m)
   send_file(self,f,m+'; charset=utf-8')

hostName = ''
serverPort = 9123
class MyServer(BaseHTTPRequestHandler):
   def do_DELETE(self):
      send_data(self,'{}',"application/json")
      api='/api/v1/devices/'
      if self.path[:len(api)] == api:
         DevicesDB.dev_del(self.path[len(api):])
      log('DELETE: '+self.path+'; ')
      infot = mqttc.publish(sber_root_topic+'/up/config', DevicesDB.do_mqtt_json_devices_list(), qos=0)

   def do_GET(self):
      sf=static_request.get(self.path, None)
      if (sf is None):
         dict={
            '/': api_root,
            '/api/v1/models': api_models,
            '/api/v1/devices': api_devices,
            '/api/v2/devices': api2_devices,
            '/api/v1/status': api_status,
            '/api/v1/objects': api_objects,
            '/api/v1/transformations': api_transformations,
            '/api/v1/categories': api_categories,
            '/api/v1/categories/relay/features': api_categories_relay_features
         }
         dict.get(self.path, api_default )(self)
      else:
         static_answer(self, sf)

   def do_PUT(self):
      send_data(self,'{}',"application/json")
      log('PUT: '+self.path)
      data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
      api='/api/v1/devices/'
      if self.path[:len(api)] == api:
         dev=self.path[len(api):]
         if (dev == data['id']):
            DevicesDB.update(dev, data)
            infot = mqttc.publish(sber_root_topic+'/up/config', DevicesDB.do_mqtt_json_devices_list(), qos=0)
      else:
         dev=''
      
   def do_POST(self):
      send_data(self,'{}',"application/json")
      log('POST: '+self.path)
      d=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
      dict={
         '/api/v1/devices': api_devices_post,
         '/api/v2/devices': api2_devices_post
      }
      dict.get(self.path, api_default_post )(self,d)





ext_mime_types = {
   ".html" : "text/html",
   ".js" : "text/javascript",
   ".css" : "text/css",
   ".jpg" : "image/jpeg",
   ".png" : "image/png",
   ".json" : "application/json",
   ".ico" : "image/vnd.microsoft.icon",
   "default" : "text/plain"
}

static_request={
   '/api/v1/models': 'models.json',
   '/api/v1/categories': 'categories.json',
   '/': '../app/ui2/index.html',
   '/ui2/main.js': '../app/ui2/main.js',
   '/favicon.ico': '../app/ui2/favicon.ico',
   '/index.html': '../app/ui/index.html',
   '/static/css/2.a1e3eec8.chunk.css': '../app/ui/static/css/2.a1e3eec8.chunk.css',
   '/static/css/main.1359096b.chunk.css': '../app/ui/static/css/main.1359096b.chunk.css',
   '/static/js/2.e77e3dbd.chunk.js': '../app/ui/static/js/2.e77e3dbd.chunk.js',
   '/static/js/main.a9292504.chunk.js': '../app/ui/static/js/main.a9292504.chunk.js'
}

webServer = HTTPServer((hostName, serverPort), MyServer)
print("Server started http://%s:%s" % (hostName, serverPort))
try:
   webServer.serve_forever()

except KeyboardInterrupt:
   pass

webServer.server_close()
print("Server stopped.")

#---------------------------------------------

while True:
   time.sleep(10)
#   log('Agent HB')
