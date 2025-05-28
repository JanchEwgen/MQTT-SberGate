﻿#!/usr/bin/python3
# -*- coding: utf-8 -*-

import re
import os
import sys
import ssl
import time
import json
import paho
import random
import requests
import websocket
import threading
# deprecated import pkg_resources
import paho.mqtt.client as mqtt
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

#import locale
#locale.getpreferredencoding()

VERSION = '1.0.16'
LOG_LEVEL_LIST={'deeptrace':0,'trace':1,'debug':2,'info':3,'notice':4,'warning':5,'error':6,'fatal':7}
LOG_FILE = 'SberGate.log'
LOG_FILE_MAX_SIZE = 1024*1024*7
log_level = 3
HA_AREA = {}

fOptions='options.json'
fDevicesDB='devices.json'
fCategories='categories.json'

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

def ha_OnOff(id):
   OnOff = DevicesDB.get_state(id,'on_off')
   entity_domain,entity_name=id.split('.',1)
   log('Отправляем команду в HA для '+id+' ON: '+str(OnOff))
   url=Options['ha-api_url']+'/api/services/'+entity_domain+'/'
   if entity_domain == 'button':
      url += 'press'
   else:
      if OnOff:
         url += 'turn_on'
      else:
         url += 'turn_off'
   log('HA REST API REQUEST: '+ url)
   hds = {'Authorization': 'Bearer '+Options['ha-api_token'], 'content-type': 'application/json'}
   response=requests.post(url, json={"entity_id": id}, headers=hds)
#   print(response)

def ha_switch(id,OnOff):
#   if DevicesDB.DB[id].get('entity_ha',False):
   log('Отправляем команду в HA для '+id+' ON: '+str(OnOff))
   if OnOff:
      url=Options['ha-api_url']+'/api/services/switch/turn_on'
   else:
      url=Options['ha-api_url']+'/api/services/switch/turn_off'
   hds = {'Authorization': 'Bearer '+Options['ha-api_token'], 'content-type': 'application/json'}
   response=requests.post(url, json={"entity_id": id}, headers=hds)
#   if response.status_code == 200:
#      log(response.text)
#   else:
#      log(response.status_code)

def ha_script(id,OnOff):
   log('Отправляем команду в HA для '+id+' ON: '+str(OnOff))
   if OnOff:
      url=Options['ha-api_url']+'/api/services/script/turn_on'
   else:
      url=Options['ha-api_url']+'/api/services/script/turn_off'
   hds = {'Authorization': 'Bearer '+Options['ha-api_token'], 'content-type': 'application/json'}
   response=requests.post(url, json={"entity_id": id}, headers=hds)

#*******************************
class CDevicesDB(object):
   """docstring"""
   def __init__(self, f):
      """Constructor 'devices.json'"""
      self.fDB=f
      self.DB=json_read(f)
      for id in self.DB:
         if self.DB[id].get('enabled',None) == None:
             self.DB[id]['enabled'] = False

      self.mqtt_json_devices_list='{}'
      self.mqtt_json_states_list='{}'
      self.http_json_devices_list='{}'
#      self.do_mqtt_json_devices_list()
#      self.do_mqtt_json_states_list({})
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

   def clear(self,d):
      self.DB={}
      self.save_DB()

   def dev_add(self):
      print('device_Add')

   def dev_del(self,id):
      self.DB.pop(id, None)
      self.save_DB()
      log('Delete Device: '+id+'!')

   def dev_inBase(self,id):
      if self.DB.get(id,None) is None:
         return False
      else:
         return True

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
#      self.do_mqtt_json_states_list([id])

   def get_states(self,id):
      d=self.DB.get(id,{})
      return d.get('States',{})

   def get_state(self,id,key):
      d=self.DB.get(id,{})
      s=d.get('States',{})
      k=s.get(key,None)
      if k:
         return k

   def update_only(self,id,d):
      if (self.DB.get(id,None) is not None):
         for k,v in d.items():
            self.DB[id][k]=d.get(k,v)
         self.save_DB()

   def update(self,id,d):
      fl={'enabled':False,'name':'','default_name':'','nicknames':[],'home':'','room':'','groups':[],'model_id':'','category':'','hw_version':'hw:'+VERSION,'sw_version':'sw:'+VERSION}
      fl['entity_ha']=False
      fl['entity_type']=''
      fl['friendly_name']=''
      if (self.DB.get(id,None) is None):
         log('Device '+id+' Not Found. Adding')
         self.DB[id]={}
         for k,v in fl.items():
            self.DB[id][k]=d.get(k,v)
         if d['category'] == 'scenario_button':
            self.DB[id]['States'] = {'button_event':''}

      for k,v in d.items():
         self.DB[id][k]=d.get(k,v)
      if (self.DB[id]['name'] == ''):
         self.DB[id]['name'] = self.DB[id]['friendly_name']
      self.save_DB()

   def DeviceStates_mqttSber(self,id):
      d=self.DB.get(id,None)
#      log(d)
      r=[]
      if (d is None):
         log('Запрошен несуществующий объект: '+id)
         return r
      s=d.get('States',None)
      if (s is None):
         log('У объекта: '+id+'отсутствует информация о состояниях')
         return r
      if d['category'] == 'relay':
         v=s.get('on_off',False)
         r.append({'key':'online','value':{"type": "BOOL", "bool_value": True}})
         r.append({'key':'on_off','value':{"type": "BOOL", "bool_value": v}})
      if d['category'] == 'sensor_temp':
         v=round(s.get('temperature',0)*10)
         r.append({'key':'online','value':{"type": "BOOL", "bool_value": True}})
         r.append({'key':'temperature','value':{"type": "INTEGER", "integer_value": v}})

      if d['category'] == 'scenario_button':
         v=s.get('button_event','click')
         r.append({'key':'online','value':{"type": "BOOL", "bool_value": True}})
         r.append({'key':'button_event','value':{"type": "ENUM", "enum_value": v}})


      if d['category'] == 'hvac_radiator':
#         log('hvac')
         v=round(s.get('temperature',0)*10)
         r.append({'key':'online','value':{"type": "BOOL", "bool_value": True}})
         r.append({'key':'on_off','value':{"type": "BOOL", "bool_value": True}})
         r.append({'key':'temperature','value':{"type": "INTEGER", "integer_value": v}})
         r.append({'key':'hvac_temp_set','value':{"type": "INTEGER", "integer_value": 30}})
#         log(r)



#      for k,v in s.items():
#         log(k)
#         if (isinstance(v,bool)):
#            o={'key':k,'value':{"type": "BOOL", "bool_value": v}}
#         elif (isinstance(v, int)):
#            o={'key':k,'value':{"type": "INTEGER", "integer_value": v}}
#         else:
#            log(v)
#            o={'key':k,'value':{"type": "BOOL", "bool_value": False}}
#         r.append(o)
      return r

   def do_mqtt_json_devices_list(self):
      Dev={}
      Dev['devices']=[]
      Dev['devices'].append({"id": "root", "name": "Вумный контроллер", 'hw_version':VERSION, 'sw_version':VERSION })
      Dev['devices'][0]['model']={'id': 'ID_root_hub', 'manufacturer': 'Janch', 'model': 'VHub', 'description': "HA MQTT SberGate HUB", 'category': 'hub', 'features': ['online']}
      for k,v in self.DB.items():
         if v.get('enabled',False):
            d={'id': k, 'name': v.get('name',''), 'default_name': v.get('default_name','')}
            d['home']=v.get('home','Мой дом')
            d['room']=v.get('room','')
#            d['groups']=['Спальня']
            d['hw_version']=v.get('hw_version','')
            d['sw_version']=v.get('sw_version','')
            dev_cat=v.get('category','relay')
            c=Categories.get(dev_cat)
            f=[]
            for ft in c:
               if ft.get('required',False):
                  f.append(ft['name'])
               else:
                  for st in self.get_states(k):
                     if ft['name'] == st:
                        f.append(ft['name'])

            d['model']={'id': 'ID_'+dev_cat, 'manufacturer': 'Janch', 'model': 'Model_'+dev_cat, 'category': dev_cat, 'features': f}
#            log(d['model'])
            d['model_id']=''
            Dev['devices'].append(d)
      self.mqtt_json_devices_list=json.dumps(Dev)
      log('New Devices List for MQTT: '+self.mqtt_json_devices_list,1)
      return self.mqtt_json_devices_list

   def DefaultValue(self,feature):
      t=feature['data_type']
      dv_dict={
         'BOOL': False,
         'INTEGER': 0,
         'ENUM': ''
      }
      v=dv_dict.get(t, None)
      if v is None:
         log('Неизвестный тип даных: '+t)
         return False
      else:
         if feature['name'] == 'online':
            return True
         else:
            return v
      
   def StateValue(self,id,feature):
      #{'key':'online','value':{"type": "BOOL", "bool_value": True}}
      State=self.DB[id]['States'][feature['name']]
      if feature['name'] == 'temperature':
         State=State*10
      if feature['data_type'] == 'BOOL':
         r={'key':feature['name'],'value':{'type': 'BOOL', 'bool_value': bool(State)}}
      if feature['data_type'] == 'INTEGER':
         r={'key':feature['name'],'value':{'type': 'INTEGER', 'integer_value': int(State)}}
      if feature['data_type'] == 'ENUM':
         r={'key':feature['name'],'value':{'type': 'ENUM', 'enum_value': State}}
      log(id+': '+str(r),0)
      return r

   def do_mqtt_json_states_list(self,dl):
      DStat={}
      DStat['devices']={}
      if (len(dl) == 0):
         dl=self.DB.keys()
      for id in dl:
         device=self.DB.get(id,None)
         if not (device is None):
            if device['enabled']:
               device_category=device.get('category',None)
               if device_category is None:
                  device_category='relay'
                  self.DB[id]['category']=device_category
               DStat['devices'][id]={}
               features=Categories.get(device_category)
               if self.DB[id].get('States',None) is None:
                  self.DB[id]['States']={}
               r=[]
               for ft in features:
                  state_value = self.DB[id]['States'].get(ft['name'],None)
                  if state_value is None:
                     if ft.get('required',False):
                        log('отсутствует обязательное состояние сущности: ' + ft['name'])
                        self.DB[id]['States'][ft['name']]=self.DefaultValue(ft)
                  if not (self.DB[id]['States'].get(ft['name'], None) is None):
                     r.append(self.StateValue(id,ft))
                     if ft['name'] == 'button_event':
                        self.DB[id]['States']['button_event']=''
               DStat['devices'][id]['states']=r
#               if (s is None):
#                  log('У объекта: '+id+'отсутствует информация о состояниях')
#                  self.DB[id]['States']={}
#                  self.DB[id]['States']['online']=True
#               DStat['devices'][id]['states']=self.DeviceStates_mqttSber(id)

      if (len(DStat['devices']) == 0):
            DStat['devices']={"root": {"states": [{"key": "online", "value": {"type": "BOOL", "bool_value": True}}]}}
      self.mqtt_json_states_list=json.dumps(DStat)
      log(f"Отправка состояний в Sber: {self.mqtt_json_states_list}",1)
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
        log("Unexpected MQTT disconnection. Will auto-reconnect. rc: "+str(rc))

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
   log("Sber MQTT Command: " + str(data))
   for id,v in data['devices'].items():
      for k in v['states']:
         type=k['value'].get('type','')
         val=''
         if type == 'BOOL':
            val=k['value'].get('bool_value',False)
         if type == 'INTEGER':
            val=k['value'].get('integer_value',0)
         if type == 'ENUM':
            val=k['value'].get('enum_value','')
         DevicesDB.change_state(id,k['key'],val)
      if DevicesDB.DB[id].get('entity_ha',False):
         ha_OnOff(id)
      else:
         log('Объект отсутствует в HA: ' + id)
   send_status(mqttc,DevicesDB.do_mqtt_json_states_list([id]))

#   log(DevicesDB.mqtt_json_states_list)

def on_message_stat(mqttc, obj, msg):
   try:
      data=json.loads(msg.payload).get('devices',[])
   except:
      data=[]
   log("GetStatus: "  +  str(msg.payload))
   send_status(mqttc,DevicesDB.do_mqtt_json_states_list(data))
   log("Answer: "+DevicesDB.mqtt_json_states_list,0)

def on_errors(mqttc, obj, msg):
   log("Sber MQTT Errors: " + msg.topic + " " + str(msg.qos) + " " + str(msg.payload))

def on_message_conf(mqttc, obj, msg):
   log("Config: " + msg.topic + " " + str(msg.qos) + " " + str(msg.payload))
   infot = mqttc.publish(sber_root_topic+'/up/config', DevicesDB.do_mqtt_json_devices_list(), qos=0)
#!!!!!!!

def on_global_conf(mqttc, obj, msg):
   data=json.loads(msg.payload)
   options_change('sber-http_api_endpoint',data.get('http_api_endpoint',''))

def log(s,l=3):
   out_file = open(LOG_FILE, "a", encoding="utf-8")

#   log_lv=LOG_LEVEL_LIST.get(l,2)
   if l >= log_level:
      dt=datetime.now().strftime("%Y%m%d-%H%M%S.%f")+': '+str(s)
      print(dt)
      out_file.write(dt+'\r\n')

#   dt=time.strftime("%Y%m%d-%H%M%S.%f", time.localtime())[:-3]
#   dt=datetime.utcnow().strftime("%Y%m%d-%H%M%S.%f")
   out_file.close()

#vvvvvvv WebSocket vvvvvvv

def ws_on_open(ws):
   log("WebSocket: opened",3)

def ws_on_close(ws,a,b):
   log("WebSocket: Connection closed")
def ws_on_message(ws, message):
   log(f"WebSocket: Received message: {message}",0)
   mdata=json.loads(message)
   ws_dict={
      'auth_required': ws_auth_required,
      'auth_ok': ws_auth_ok,
      'auth_invalid': ws_auth_invalid,
      'result': ws_result,
      'event': ws_event,
      'None': ws_default
   }
   ws_dict.get(mdata.get('type', 'None'), ws_default )(ws,mdata)

def ws_auth_required(ws,mdata):
   log("WebSocket: auth_required")
   ws.send(json.dumps({"type": "auth", "access_token": Options['ha-api_token']}))
def ws_auth_ok(ws,mdata):
   log("WebSocket: auth_ok")
   ws.send(json.dumps({'id': 1, 'type': 'subscribe_events', 'event_type': 'state_changed'}))
   ws.send(json.dumps({'id': 2, 'type': 'config/area_registry/list'}))
#   ws.send(json.dumps({'id': 3, 'type': 'config/device_registry/list'}))
   ws.send(json.dumps({'id': 4, 'type': 'config/entity_registry/list'}))

def ws_auth_invalid(ws,mdata):
   log("WebSocket: auth_invalid",7)
def ws_result(ws,mdata):
   global HA_AREA
   log(f"WebSocket: result: {mdata}",0)
   if mdata.get('id', 'None') == 2:
      log(f"WebSocket: Получен список зон: {mdata}",0)
      HA_AREA = {}
      for a in mdata.get('result',[]):
         HA_AREA[a['area_id']]=a['name']
      log(f"HA_AREA: {HA_AREA}",1)
         
   if mdata.get('id', 'None') == 4:
      log(f"WebSocket: Получен список сущностей.")
      log(f"Данные: {mdata}",0)
      res=mdata.get('result',[])
      for a in res:
         entity=DevicesDB.DB.get(a['entity_id'],False)
#         log(f"entity list: {a['entity_id']}")
         if entity:
            room=HA_AREA.get(a['area_id'],'')
            room_db=DevicesDB.DB[a['entity_id']].get('room',False)
            if room_db != room:
               log(f"Изменилось расположение сущности {a['entity_id']} с {room_db} на {room}")
               DevicesDB.update_only(a['entity_id'],{'entity_ha': True,'room': room})

def ws_event(ws,mdata):
#   log("vvv WebSocket: event vvv",0)
   id=mdata['event']['data']['new_state']['entity_id']
   old_state=mdata['event']['data']['old_state']['state']
   new_state=mdata['event']['data']['new_state']['state']
   dev=DevicesDB.DB.get(id,None)
   if not (dev is None): #   if DevicesDB.dev_inBase(id):
      #log(dev)
      if dev['enabled']:
         log('HA Event: ' + id + ': ' + old_state + ' -> ' + new_state)
         if dev['category'] == 'sensor_temp':
            DevicesDB.change_state(id,'temperature',float(new_state))
         if new_state == 'on':
            DevicesDB.change_state(id,'on_off',True)
            if not (DevicesDB.DB[id]['States'].get('button_event',None) is None):
               DevicesDB.DB[id]['States']['button_event']='click'
         else:
            DevicesDB.change_state(id,'on_off',False)
            if not (DevicesDB.DB[id]['States'].get('button_event',None) is None):
               DevicesDB.DB[id]['States']['button_event']='double_click'
         send_status(mqttc,DevicesDB.do_mqtt_json_states_list([id]))
      else:
         log('!HA Event: ' + id + ': ' + old_state + ' -> ' + new_state)
#   else:
#      print(id+' нет в базе')
#   log("^^^ WebSocket: event ^^^",0)

def ws_default(ws,mdata):
   log("WebSocket: default")

#^^^^^^^ WebSocket ^^^^^^^^^^^^^^^^^^^^^^^^^^^^

#********** Start **********************************

Options=json_read(fOptions)
log_level = LOG_LEVEL_LIST.get(Options.get('log_level','info'),3)

#https://developers.sber.ru/docs/ru/smarthome/c2c/value
sber_types={'FLOAT':'float_value','INTEGER':'integer_value','STRING':'string_value','BOOL':'bool_value','ENUM':'enum_value','JSON':'','COLOUR':'colour_value'}
#
if os.path.isfile(LOG_FILE):
   if os.path.getsize(LOG_FILE)>LOG_FILE_MAX_SIZE:
      os.remove(LOG_FILE)
log('Start MQTT SberGate IoT Agent for Home Assistant version: '+VERSION)
log("Запущено в системе: "+ os.name)
log("Версия Python     : "+ sys.version)
log("Размещение скрипта: "+ os.path.realpath(__file__))
log("Текущая директория: "+ os.getcwd())
log("Размер Log файла  : "+ str(os.path.getsize(LOG_FILE)))
log("Log Level         : "+ Options.get('log_level','info'))
#log("LOG_FILE_MAX_SIZE : "+ str(LOG_FILE_MAX_SIZE)
log("Кодировка         : "+ sys.getdefaultencoding())
log("Список файлов     : "+ str(os.listdir('.')))
#log("Список файлов2   : "+ str(os.listdir('../app/data')))
#log(": "+ sys.getfilesystemencoding())
#log(": "+ sys.getfilesystemencodeerrors())
#log(": "+ str(sys.maxunicode))

#installed_packages = pkg_resources.working_set
#installed_packages_list = sorted(["%s==%s" % (i.key, i.version) for i in installed_packages])
#pkg=[]
#for i in pkg_resources.working_set:
#   pkg.append(i.key)
#log(pkg)

#sys.setdefaultencoding('utf8')
#print(sys.stdout.encoding)

if not os.path.exists(fDevicesDB):
   json_write(fDevicesDB,{})

log('Чтение базы устройств')
DevicesDB=CDevicesDB(fDevicesDB)
AgentStatus={"online": True, "error": "",  "credentials": {'username':Options['sber-mqtt_login'],"password": "***",'broker': Options['sber-mqtt_broker']}}

#log(Options['ha-api_url'])
#log(Options['ha-api_token'])


#url = "http://localhost:8123/ENDPOINT"
hds = {'Authorization': 'Bearer '+Options['ha-api_token'], 'content-type': 'application/json'}
url=Options['ha-api_url']+'/api/states'
log('Подключаемся к HA, (ha-api_url: ' + Options['ha-api_url'] + ')')
cx=0
while cx<10:
   cx = cx+1
   try:
      res = requests.get(url, headers=hds)
   except:
      log('Ошибка подключения к HA. Ждём 5 сек перед повторным подключением.')
      time.sleep(5)
if res.status_code == 200:
   log('Запрос устройств из Home Assistant выполнен штатно.')
   ha_dev=res.json()
   log(ha_dev,0)
else:
   log('ОШИБКА! Запрос устройств из Home Assistant выполнен некоректно.')
   ha_dev=[]
   log('Запрошенный URL: ' + url)
   log('Код ответа сервера: ' + str(res.status_code))
   #Нет смысла продолжать выполнение


def upd_sw(id,s):
   attr=s['attributes'].get('friendly_name','')
   log('switch: ' + s['entity_id'] + ' '+attr,0)
   DevicesDB.update(s['entity_id'],{'entity_ha': True,'entity_type': 'sw','friendly_name':attr,'category': 'relay'})
def upd_light(id,s):
   attr=s['attributes'].get('friendly_name','')
   log('light: ' + s['entity_id'] + ' '+attr,0)
   DevicesDB.update(s['entity_id'],{'entity_ha': True,'entity_type': 'light','friendly_name':attr,'category': 'light'})

def upd_scr(id,s):
   attr=s['attributes'].get('friendly_name','')
   log('script: ' + s['entity_id'] + ' '+attr,0)
   DevicesDB.update(s['entity_id'],{'entity_ha': True,'entity_type': 'scr','friendly_name':attr,'category': 'relay'})
def upd_sensor(id,s):
   dc=s['attributes'].get('device_class','')
   fn=s['attributes'].get('friendly_name','')
   if dc == 'temperature':
#      log('Сенсор температуры: ' + id + ' ' + fn)
      DevicesDB.update(id,{'entity_ha': True,'entity_type': 'sensor_temp', 'friendly_name': fn,'category': 'sensor_temp'})
#   if dc == 'pressure':
#      DevicesDB.update(id,{'entity_ha': True,'entity_type': 'sensor_pressure', 'friendly_name': fn,'category': 'sensor_pressure'})


def upd_button(id,s):
   dc=s['attributes'].get('device_class','')
   fn=s['attributes'].get('friendly_name','')
   log('button: ' + s['entity_id'] + ' '+fn+'('+dc+')',0)
   DevicesDB.update(id,{'entity_ha': True,'entity_type': 'button', 'friendly_name': fn,'category': 'relay'})

def upd_input_boolean(id,s):
   dc=s['attributes'].get('device_class','')
   fn=s['attributes'].get('friendly_name','')
   log('input_boolean: ' + s['entity_id'] + ' '+fn+'('+dc+')',0)
   DevicesDB.update(id,{'entity_ha': True,'entity_type': 'input_boolean', 'friendly_name': fn,'category': 'scenario_button'})

def upd_hvac_radiator(id,s):
   dc=s['attributes'].get('device_class','')
   fn=s['attributes'].get('friendly_name','')
   if dc == 'temperature':
#      log('Радиатор отопления: ' + id + ' ' + fn)
      DevicesDB.update(id,{'entity_ha': True,'entity_type': 'hvac_radiator', 'friendly_name': fn,'category': 'hvac_radiator'})

def upd_default(id,s):
   log('Неиспользуемый тип: ' + s['entity_id'],0)
   pass

for s in ha_dev:
   a,b=s['entity_id'].split('.',1)
   dict={
      'switch': upd_sw,
      'light': upd_light,
      'script': upd_scr,
      'sensor': upd_sensor,
      'button': upd_button,
      'input_boolean': upd_input_boolean,
      'hvac_radiator': upd_hvac_radiator
   }
   dict.get(a, upd_default)(s['entity_id'],s)

#******************* Configure Local client (HA Broker)
#mqttHA = mqtt.Client("SberDevicesAgent local client")
#mqttHA.on_connect = on_connect_local
#mqttHA.username_pw_set(Options['ha-mqtt_login'], Options['ha-mqtt_password'])
#mqttHA.connect(Options['ha-mqtt_broker'], Options['ha-mqtt_broker_port'], 60)

#******************* Configure client (SberDevices Broker)
#mqttc = mqtt.Client("HA client")
mqttc = mqtt.Client()
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

#infot = mqttc.publish(sber_root_topic+'/up/config', DevicesDB.do_mqtt_json_devices_list(), qos=0)

#*********************************
mqttc.loop_start()
#mqttHA.loop_start()

#Хитрое получение sber-http_api_endpoint от Сберовского MQTT из глобальной конфигурации. Типа только после этого можно идти дальше, но...
if Options.get('sber-http_api_endpoint',None) is None:
   options_change('sber-http_api_endpoint','')
while (Options['sber-http_api_endpoint'] == ''):
   log('Ожидаем получение SberDevice http_api_endpoint')
   time.sleep(1)
log('SberDevice http_api_endpoint: '+Options['sber-http_api_endpoint'])

hds = {'content-type': 'application/json'}
if not os.path.exists('models.json'):
   log('Файл моделей отсутствует. Получаем...')
   SD_Models = requests.get(Options['sber-http_api_endpoint']+'/v1/mqtt-gate/models', headers=hds,auth=(Options['sber-mqtt_login'], Options['sber-mqtt_password']))
   if SD_Models.status_code == 200:
#      log(SD_Models.text)
      json_write('models.json',SD_Models.json())
   else:
      log('ОШИБКА! Запрос models завершился с ошибкой: '+str(SD_Models.status_code))
   
def GetCategory():
   if not os.path.exists(fCategories):
      log('Файл категорий отсутствует. Получаем...')
      Categories={}
      SD_Categories = requests.get(Options['sber-http_api_endpoint']+'/v1/mqtt-gate/categories', headers=hds,auth=(Options['sber-mqtt_login'], Options['sber-mqtt_password'])).json()
      for id in SD_Categories['categories']:
         log('Получаем опции для котегории: '+id)
         SD_Features = requests.get(Options['sber-http_api_endpoint']+'/v1/mqtt-gate/categories/'+id+'/features', headers=hds,auth=(Options['sber-mqtt_login'], Options['sber-mqtt_password'])).json()
         Categories[id]=SD_Features['features']
   #   log(Categories)
      json_write('categories.json',Categories)
   else:
      log('Список категорий получен из файла: ' + fCategories)
      Categories=json_read(fCategories)
   return Categories

Categories=GetCategory()

if Categories.get('categories',False):
   log('Старая версия файла категорий, удаляем.')
   os.remove(fCategories)
   log('Повторное получения категорий.')
   Categories=GetCategory()

#Получаем список категорий в формате Сбер API для возврата по запросу
resCategories={'categories':[]}
for id in Categories:
   resCategories['categories'].append(id)



infot = mqttc.publish(sber_root_topic+'/up/config', DevicesDB.do_mqtt_json_devices_list(), qos=0)

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


def command_default(d):
   log('Получили неизвестную команду'+str(d))

def command_exit(d):
   log('Выход. '+str(d))
   sys.exit()

def api2_command_post(self,d):
   dict={
      'DB_delete': DevicesDB.clear,
      'exit': command_exit
   }
   dict.get(d.get('command','unknow'), command_default)(d)

def api2_devices(self):
   send_data(self, DevicesDB.do_http_json_devices_list_2(), "application/json")

def api_status(self):
#   d='{  "online": true, "error": "",  "credentials": {    "username": "cc94hhd7uhdtqejhmhh0",    "password": "***",    "broker": "hasrv.janch.ru:1883"  }}'
   send_data(self,json.dumps(AgentStatus),"application/json")

def api_objects(self):
   d='{"objects": [{"id": "__false","description": "Always false fake object","readonly": false},{"id": "__true","description": "Always true fake object","readonly": false}]}'
   send_data(self,d,"application/json")
def api_transformations(self):
   f =open('../app/data/transformations.json' ,'r', encoding='utf-8')
   d=f.read()
   f.close()
   send_data(self,d,"application/json")

def api_aggregations(self):
   d='{"aggregations": ["bool_status_oneof"]}'
   send_data(self,d,"application/json")
def api_categories(self):
   log('Запрос категорий')
#   d='{"categories": ["light","socket","relay","led_strip","hub","ipc","sensor_pir","sensor_door","sensor_temp","scenario_button","hvac_ac","hvac_fan","hvac_humidifier","hvac_air_purifier","hvac_heater","hvac_radiator","hvac_boiler","hvac_underfloor_heating","window_blind","curtain","gate","kettle","sensor_water_leak","valve"]}'
   d=json.dumps(resCategories)
   send_data(self,d,"application/json")
def api_categories_relay_features(self):
   d='{"features": [{"name": "online","required": true,"type": "BOOL"},{"name": "voltage","type": "INTEGER","allowed_integer_values": {"max": "500"}},{"name": "on_off","required": true,"type": "BOOL"    },    {      "name": "current",      "type": "INTEGER",      "allowed_integer_values": {        "max": "3000"      }    },    {      "name": "power",      "type": "INTEGER",      "allowed_integer_values": {        "max": "5000"      }    }  ]}'
   send_data(self,d,"application/json")

def api_default_d(self):
   d='<html><head><title>HA</title></head>'\
      '<p>Request: ' + self.path + '</p>'\
      '<body><p>This is an example web server.</p></body></html>'
   send_data(self,d,"text/html")
   return self.path

def api_default(self):
   #Проверка на запрос features
   get_feature=re.findall(r'/api/v1/categories/(.+)/features',self.path)
   if len(get_feature) == 1:
#      log('Запрошен: ' + get_feature[0])
      #Получаем список опций для категории в формате Сбер API для возврата по запросу
      resFeatures={'features':Categories.get(get_feature[0],[])}
#      log('Ответ: ' + json.dumps(resFeatures))
      send_data(self,json.dumps(resFeatures),"application/json")
   else:
   #Иначе прокси
      api='/api/v1/'
      if self.path[:len(api)] == api:
         log('PROXY '+api+': '+self.path)
         url=Options['sber-http_api_endpoint']+'/v1/mqtt-gate/' + self.path[len(api):]
         req_v1=requests.get(url, headers=hds,auth=(Options['sber-mqtt_login'], Options['sber-mqtt_password']))
         if req_v1.status_code == 200:
   #         log(req_v1.text)
            send_data(self,req_v1.text,"application/json")
         else:
            log('ОШИБКА! Запрос: '+url+' завершился с ошибкой: '+str(req_v1.status_code))
      else:
         api_default_d(self)
#   dict.get(self.path, api_default )(self)

def static_answer(self,file):
   p,e = os.path.splitext(file)
   m=ext_mime_types.get(e,ext_mime_types['default'])
   if (os.name == 'nt'):
      f=file.replace('/','\\')
   else:
      f=file
   log('Отправка файла: '+f+'; MIME:'+m)
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

            '/api/v1/status': api_status,
            '/api/v1/objects': api_objects,
            '/api/v1/transformations': api_transformations,
            '/api/v1/aggregations': api_aggregations,

            '/api/v1/models': api_models,
            '/api/v1/categories': api_categories,
#            '/api/v1/categories/relay/features': api_categories_relay_features,

            '/api/v1/devices': api_devices,
            '/api/v2/devices': api2_devices

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
         '/api/v2/devices': api2_devices_post,
         '/api/v2/command': api2_command_post
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
   ".log" : "application/octet-stream",
   "default" : "text/plain"
}

static_request={
#   '/api/v1/models': 'models.json',
#   '/api/v1/categories': 'categories.json',
   '/SberGate.log': 'SberGate.log',
   '/': '../app/ui2/index.html',
   '/ui2/main.js': '../app/ui2/main.js',
   '/ui2/main.css': '../app/ui2/main.css',
   '/favicon.ico': '../app/ui2/favicon.ico',
   '/index.html': '../app/ui/index.html',
   '/static/css/2.b9b863b2.chunk.css': '../app/ui/static/css/2.b9b863b2.chunk.css',
   '/static/css/main.1359096b.chunk.css': '../app/ui/static/css/main.1359096b.chunk.css',
   '/static/js/2.e21fd42c.chunk.js': '../app/ui/static/js/2.e21fd42c.chunk.js',
   '/static/js/main.a57bb958.chunk.js': '../app/ui/static/js/main.a57bb958.chunk.js',
   '/static/js/runtime-main.ccc7405a.js': '../app/ui/static/js/runtime-main.ccc7405a.js'
}


webServer = HTTPServer((hostName, serverPort), MyServer)
log("Server started http://%s:%s" % (hostName, serverPort))

try:
#   webServer.serve_forever()
   tsrv=threading.Thread(target=webServer.serve_forever)
   tsrv.daemon = True
   tsrv.start()


except KeyboardInterrupt:
   pass


ws_url=Options['ha-api_url'].replace('http','ws',1) + '/api/websocket'
log('Start WebSocket Client URL: ' + ws_url)
#websocket.enableTrace(True)
ws = websocket.WebSocketApp(ws_url,
                            on_open=ws_on_open,
                            on_message=ws_on_message,
                            on_close=ws_on_close)

socketRun=True
while socketRun:
   ws.run_forever()
   log('Socket disconect')
   time.sleep(1)
   log('Connecting')



#tsrv.join()

webServer.server_close()
log("Server stopped.")

#---------------------------------------------

while True:
   time.sleep(10)
   log('Agent HB')
