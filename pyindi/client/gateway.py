#!/usr/bin/env python
# -*-coding:utf-8 -*-
'''
@File      :   pyindi/client/gateway.py
@Time      :   2023/03
@Author    :   Stefano Sartor
@Version   :   0.1
@Contact   :   sartor@oavda.it
@License   :   MIT
@Copyright :   (C) 2023 FONDAZIONE CLÉMENT FILLIETROZ-ONLUS
'''
import asyncio
import logging
from .tree_client import TreeClient
from pyindi.core.indi_types import INTERFACE, IPS
from .focuser import Focuser
from .filter import FilterWheel
from .telescope import Telescope
from .ccd import CCD
from pyindi.core.defer import DeferResult
from copy import deepcopy


class DeviceNotFoundError(RuntimeError):
    pass


class Gateway(TreeClient):
    def __init__(self):
        super().__init__()
        self.stream = None

    async def beginStream(self, indiserver, port):
        self.start(indiserver, port)
        self.stream = asyncio.create_task(self.connect())
        await self.connection()
        await self.getProperties()

    def register_callback(self, device, prop, callback, once=False):
        if (dev := self.tree.get(device)) is None:
            return None
        if (pc := dev.get(prop)) is None:
            return None
        return pc.register_callback(callback, once)

    def unregister_callback(self, device, prop, key):
        if (dev := self.tree.get(device)) is None:
            return False
        if (pc := dev.get(prop)) is None:
            return False
        return pc.unregister_callback(key)

    def getDeviceInterface(self, device):
        if (dev := self.tree.get(device)) is None:
            return 0
        if (pc := dev.get('DRIVER_INFO')) is None:
            return 0
        if (value := pc.vec.items.get('DRIVER_INTERFACE')) is None:
            return 0
        return int(value)

    def getDeviceFromInterface(self, interface, dev_name=None):
        if dev_name is not None:
            if interface.value & self.getDeviceInterface(dev_name) > 0:
                return dev_name
            else:
                raise DeviceNotFoundError(
                    f'Device {dev_name} does not implement {interface.name} interface')

        for k in self.tree.keys():
            if interface.value & self.getDeviceInterface(k) > 0:
                return k

        raise DeviceNotFoundError(
            f'No Device implements {interface.name} interface')

    def getFocuser(self, dev_name=None):
        dname = self.getDeviceFromInterface(INTERFACE.FOCUSER, dev_name)
        return Focuser(self, dname)

    def getFilterWheel(self, dev_name=None):
        dname = self.getDeviceFromInterface(INTERFACE.FILTER, dev_name)
        return FilterWheel(self, dname)

    def getTelescope(self, dev_name=None):
        dname = self.getDeviceFromInterface(INTERFACE.TELESCOPE, dev_name)
        return Telescope(self, dname)

    def getCCD(self, dev_name=None):
        dname = self.getDeviceFromInterface(INTERFACE.CCD, dev_name)
        self.enable_blob(dev_name)
        return CCD(self, dname)

    def __getPC(self, device: str, name: str):
        if (dev := self.tree.get(device)) is None:
            return None
        return dev.get(name)

    def getVector(self, device: str, name: str):
        if (pc := self.__getPC(device, name)) is None:
            return None
        return pc.vec

    def getFuture(self, device: str, name: str):
        loop = asyncio.get_event_loop()
        if (dev := self.tree.get(device)) is None:
            f = loop.create_future()
            f.cancel()
            return f
        if (pc := dev.get(name)) is None:
            f = loop.create_future()
            f.cancel()
            return f
        return pc.get_future()

    async def sendVector(self, vec):
        if (pc := self.__getPC(vec.device, vec.name)) is not None:
            pc.vec.state = IPS.Busy
        xml = vec.to_xml()
        await self.xml_to_indiserver(xml)
        return DeferResult(IPS.Ok, vec, "vec sent")

    async def setSendVector(self, device: str, name: str, items: dict, fill=None):
        v = self.getVector(device, name)
        if v is None:
            return DeferResult(IPS.Alert, None, f"cannot find '{device}.{name}'")

        vec = deepcopy(v)
        if fill is not None:
            for k in vec.items:
                vec.items[k] = fill

        for k, val in items.items():
            vec.items[k] = val

        return await self.sendVector(vec)
