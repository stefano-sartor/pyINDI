#!/usr/bin/env python
# -*-coding:utf-8 -*-
'''
@File      :   pyindi/client/client_async.py
@Time      :   2023/03
@Author    :   Stefano Sartor
@Version   :   0.1
@Contact   :   sartor@oavda.it
@License   :   MIT
@Copyright :   (C) 2023 FONDAZIONE CLÉMENT FILLIETROZ-ONLUS
'''


from .xml_handler import XMLHandler
from xml.sax.expatreader import ExpatParser
from pyindi.client import INDIClient
import asyncio
import time
import datetime as dt
from pyindi.core.indi_types import vector_factory,IPS,ISS,BLOBVectorProperty
import logging
from uuid import uuid4

class PropertyControl:
    def __init__(self,update_secs=20):
        self.log = logging.getLogger('vec_ctl')
        self.vec = None
        self.futures = []
        self.callbacks = {}
        self.once = {}
        self.update_secs = update_secs
        self.last_update = dt.datetime.now()

    def __busyORempty(self,vec):
        if isinstance(vec,BLOBVectorProperty):
            for i in vec.items:
                if vec.items[i]['size'] == 0:
                    return True
            return False
        return vec.state == IPS.Busy   
    
    def new_vec(self,vec):
        self.vec = vec

        if not self.__busyORempty(vec):
            while len(self.futures) > 0:
                f = self.futures.pop()
                if not f.done():
                    f.set_result(vec)
                elif f.cancelled():
                    self.log.debug(f'future cancelled {f.result() if not f.cancelled() else f} for vec {vec}')
                elif f.done():
                    self.log.debug(f'future already done {f} for vec {vec}')
                else:
                    self.log.debug(f'invalid future {f.result() if not f.cancelled() else f} for vec {vec}')

        for k,cb in [*self.callbacks.items(),*self.once.items()]:
            try:
                cb(vec)
            except Exception as error:
                self.log.error(f'callback[{k}] {vec.device}.{vec.name} error:{error}')
        self.once={}

        now = dt.datetime.now()
        if len(self.futures) == 0:
            self.last_update = now
        elif (now - self.last_update).total_seconds() > self.update_secs:
            self.log.info(f'{self.vec}')
            self.last_update = now

    def get_future(self):
        loop = asyncio.get_event_loop()
        f = loop.create_future()
        self.futures.append(f)
        if not isinstance(self.vec,BLOBVectorProperty) and self.vec.state != IPS.Busy:
            f.set_result(self.vec)
            self.log.debug(f'get already done future {f} for vec {self.vec}')
        return f

    def register_callback(self,callback,once=False):
        key = uuid4().hex
        if once:
            self.once[key] = callback
        else:
            self.callbacks[key] = callback
        return key

    def unregister_callback(self,key):
        if key in self.callbacks:
            self.callbacks.pop(key)
            return True
        if key in self.once:
            self.once.pop(key)
            return True
        return False

    def remove(self):
        for f in self.futures:
            f.cancel()
        self.futures = []
        for k,cb in self.callbacks.items():
            try:
                cb(None)
            except Exception as error:
                self.log.error(f'[CANCEL] callback[{k}] {self.vec.device}.{self.vec.name} error:{error}')


class TreeClient(INDIClient):

    def __init__(self):
        self.handler=XMLHandler()
        self.parser = ExpatParser()
        self.parser.setContentHandler( self.handler )
        self.parser.feed("<root>")

        self.handler.def_property = self._def_property
        self.handler.set_property = self._set_property
        self.handler.del_property = self._del_property
        self.handler.new_message = self.new_msg  
        
        self.tree={}
        self.blob_set = set()

        loop = asyncio.get_event_loop()
        self.task_check = loop.create_task(self.check_devices())

    async def xml_from_indiserver(self, data):
        try:
            self.parser.feed(data)
        except Exception as e:
            logging.critical(f'error decoding message from server: {e}')
            logging.debug(f'data: {data}')
            raise e

    async def connection(self, timeout=0):
        if timeout > 0:
            start = time.time()
            while (time.time() - start) < timeout:
                if self.is_connected:
                    return
                else:
                    await asyncio.sleep(0.25)
        else:
            while 1:
                if self.is_connected:
                    return
                else:
                    await asyncio.sleep(0.25) 

    def _set_parser(self):
        handler=XMLHandler()
        parser = ExpatParser()
        parser.setContentHandler( self.handler )
        parser.feed("<root>")

        handler.def_property = self.handler.def_property
        handler.set_property = self.handler.set_property
        handler.del_property = self.handler.del_property
        handler.new_message = self.handler.new_message

        self.handler = handler
        self.parser = parser

    async def on_disconnect(self):
        logging.debug('on_disconnect')
        self._set_parser()

    async def on_connect(self):
        await super().on_connect()

        # if we've just reconnected, this might not be empty
        for xml in self.blob_set:
            await self.xml_to_indiserver(xml)

    def new_msg(self, message):
        pass

    def _del_property(self,ele):
        self.prune(ele.attrib.get("device"), ele.attrib.get("name"))

    def _def_property(self,ele):
        return self._set_property(ele)

    def _set_property(self,ele):
        vec = vector_factory(ele)
        if vec is None:
            logging.error(f'bad vector {ele}')
            return None

        dname = vec.device
        pname = vec.name

        if self.tree.get(dname) is None:
            self.tree[dname]={}
        dev = self.tree[dname]
        if dev.get(pname) is None:
            dev[pname]=PropertyControl()
        prop = dev[pname]
        prop.new_vec(vec)
        return vec

    def prune(self,device:str, pname=None):
        if (dev := self.tree.get(device)) is None:
            return

        if pname is not None:
            if (prop := dev.get(pname)) is None:
                return
            prop.remove()
            dev.pop(pname)
        else :
            for p in list(dev.keys()):
                self.prune(device,p)
            self.tree.pop(device)
            return
    
    def enable_blob(self,device:str):
        xml = f'<enableBLOB device="{device}">Also</enableBLOB>'
        self.blob_set.add(xml)
        asyncio.create_task(self.xml_to_indiserver(xml))


    async def check_devices(self):
        await asyncio.sleep(10)
        try:
            now = dt.datetime.now()

            zombie_devs = []
            for dev in self.tree:
                poll = self.tree[dev].get('POLLING_PERIOD')
                conn = self.tree[dev].get('CONNECTION')

                if conn is None:
                    continue

                if poll is None:
                    continue

                if conn.vec.items['CONNECT'] == ISS.Off:
                    continue

                pt = poll.vec.items['PERIOD_MS']
                deadline = now - dt.timedelta(milliseconds=pt*10)
                zombieline = now - dt.timedelta(milliseconds=pt*5)

                if not any(map(lambda x: x.last_update > deadline,self.tree[dev].values())):
#                    logging.error(f'device "{dev}" WILL BE REMOVED for not sendind data since {deadline}.')
                    zombie_devs.append(dev)
                    continue

                if not any(map(lambda x: x.last_update > zombieline,self.tree[dev].values())):
#                    logging.warning(f'device "{dev}" is late on POLLING_PERIOD, not sendind data since {zombieline}.')
                    await self.getProperties(dev)

#            for dev in zombie_devs:
#                self.prune(dev)
        except Exception as e:
            logging.error(f'check_devices error {e}')

        logging.debug('check_devices terminated, rescheduling...')
        loop = asyncio.get_event_loop()
        self.task_check = loop.create_task(self.check_devices())
