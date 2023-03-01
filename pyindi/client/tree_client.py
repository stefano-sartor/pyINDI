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
from pyindi.core.indi_types import vector_factory,IPS,BLOBVectorProperty
import logging
from uuid import uuid4

class PropertyControl:
    def __init__(self):
        self.vec = None
        self.futures = []
        self.callbacks = {}
        self.once = {}

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
                logging.info(f"{len(self.futures)} FUTURES FOR {self.vec}")
                f = self.futures.pop()
                if not f.done():
                    f.set_result(vec)
                    logging.info(f"set future {f} for vec {vec}")
                elif f.cancelled():
                    logging.debug(f'future cancelled {f.result() if not f.cancelled() else f} for vec {vec}')
                elif f.done():
                    logging.debug(f'future already done {f} for vec {vec}')
                else:
                    logging.debug(f'invalid future {f.result() if not f.cancelled() else f} for vec {vec}')

        for k,cb in [*self.callbacks.items(),*self.once.items()]:
            try:
                cb(vec)
            except Exception as error:
                logging.error(f'callback[{k}] {vec.device}.{vec.name} error:{error}')
        self.once={}

    def get_future(self):
        loop = asyncio.get_event_loop()
        f = loop.create_future()
        self.futures.append(f)
        if not isinstance(self.vec,BLOBVectorProperty) and self.vec.state != IPS.Busy:
            f.set_result(self.vec)
            logging.debug(f'get already done future {f} for vec {self.vec}')
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
                logging.error(f'[CANCEL] callback[{k}] {self.vec.device}.{self.vec.name} error:{error}')


class TreeClient(INDIClient):

    def __init__(self):
        self.handler=XMLHandler()
        self.parser = ExpatParser()
        self.parser.setContentHandler( self.handler )
        self.parser.feed("<root>")

        self.handler.def_property = self.handle_property
        self.handler.set_property = self.handle_property
        self.handler.del_property = lambda ele : self.prune(ele.attrib.get("device"), ele.attrib.get("name"))
           
        self.handler.new_message = self.new_msg 
        self.tree={}

    async def xml_from_indiserver(self, data):
        self.parser.feed(data)

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

    async def getProperties(self, device=None, name=None):
        if device is None:
            xml = f"<getProperties version='1.7' />\n"
        elif name is None:
            xml = f"<getProperties version='1.7' device='{device}'/>\n"
        else:
            xml = f"<getProperties version='1.7' device='{device}' name='{name}'/>\n"

        await self.xml_to_indiserver(xml)


    def new_msg(self, message):
        pass

    def handle_property(self,ele):
        vec = vector_factory(ele)
        if vec is None:
            return

        dname = vec.device
        pname = vec.name

        if self.tree.get(dname) is None:
            self.tree[dname]={}
        dev = self.tree[dname]
        if dev.get(pname) is None:
            dev[pname]=PropertyControl()
        prop = dev[pname]
        prop.new_vec(vec)

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
