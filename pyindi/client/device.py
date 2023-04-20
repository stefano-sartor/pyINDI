#!/usr/bin/env python
# -*-coding:utf-8 -*-
'''
@File      :   pyindi/client/device.py
@Time      :   2023/03
@Author    :   Stefano Sartor
@Version   :   0.1
@Contact   :   sartor@oavda.it
@License   :   MIT
@Copyright :   (C) 2023 FONDAZIONE CLÉMENT FILLIETROZ-ONLUS
'''

from pyindi.core.indi_types import IPS,ISS
from pyindi.core.defer import Just,DeferProperty
import asyncio
class Device:
    def __init__(self, gateway, dev_name):
        self.gw = gateway
        self.dev_name = dev_name

    def _defer_prop(self,pname,vec=None):
        loop = asyncio.get_running_loop()
        
        obj = None
        if vec is not None:
            obj = loop.create_task(self.gw.sendVector(vec))

        return DeferProperty(self.gw,self.dev_name,pname,obj)

    def config_load(self):
        return self.__do_config('CONFIG_LOAD')
    
    def config_save(self):
        return self.__do_config('CONFIG_SAVE')
    
    def config_default(self):
        return self.__do_config('CONFIG_DEFAULT')
    
    def config_purge(self):
        return self.__do_config('CONFIG_PURGE')

    async def setTCPConnection(self, addr, port):
        #TODO update using DeferChain
        loop = asyncio.get_running_loop()

        if (conn_mode := self.gw.getVector(self.dev_name,"CONNECTION_MODE")) is None:
            return Just(IPS.Alert,"Cannot find CONNECTION_MODE property")

        conn_mode.items['CONNECTION_SERIAL'] = ISS.Off
        conn_mode.items['CONNECTION_TCP'] = ISS.On

        await self.gw.sendVector(conn_mode)
        await asyncio.sleep(1)

        pname = 'DEVICE_ADDRESS'

        timeout = 10
        vec_addr =  self.gw.getVector(self.dev_name,pname)
        while vec_addr is None and timeout > 0:
            asyncio.sleep(1)
            timeout -= 1
            vec_addr =  self.gw.getVector(self.dev_name,pname)

        if vec_addr is None:
            return Just(IPS.Alert,"timeout") 

        vec_addr.items['ADDRESS'] = addr
        vec_addr.items['PORT'] = str(port)

        obj = loop.create_task(self.gw.sendVector(vec_addr))
        return DeferProperty(self.gw,self.dev_name,pname,obj)

    def __do_connect(self,connect=True):
        loop = asyncio.get_running_loop()
        pname = "CONNECTION"
        if (conn := self.gw.getVector(self.dev_name,pname)) is None:
            return Just(IPS.Alert,"Cannot find CONNECTION property")

        conn.items['CONNECT']    = ISS.On if connect else ISS.Off
        conn.items['DISCONNECT'] = ISS.Off if connect else ISS.On 

        obj = loop.create_task(self.gw.sendVector(conn))
        return DeferProperty(self.gw,self.dev_name,pname,obj)

    def __do_config(self,action):
        loop = asyncio.get_running_loop()
        pname = "CONFIG_PROCESS"
        if (config := self.gw.getVector(self.dev_name,pname)) is None:
            return Just(IPS.Alert,"Cannot find CONFIG_PROCESS property")

        for k in config.items:
            config.items[k] = ISS.Off
        
        config.items[action]    = ISS.On 

        obj = loop.create_task(self.gw.sendVector(config))
        return DeferProperty(self.gw,self.dev_name,pname,obj)

    def isConnected(self):
        if (conn := self.gw.getVector(self.dev_name,"CONNECTION")) is None:
            return False
        return conn.items['CONNECT']   == ISS.On    

    def connect(self):
        return self.__do_connect(True)

    def disconnect(self):
        return self.__do_connect(False)