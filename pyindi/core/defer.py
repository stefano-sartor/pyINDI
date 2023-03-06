#!/usr/bin/env python
# -*-coding:utf-8 -*-
'''
@File      :   pyindi/core/defer_async.py
@Time      :   2023/03
@Author    :   Stefano Sartor
@Version   :   0.1
@Contact   :   sartor@oavda.it
@License   :   MIT
@Copyright :   (C) 2023 FONDAZIONE CLÉMENT FILLIETROZ-ONLUS
'''


import asyncio
from abc import ABC, abstractmethod
import logging
from .indi_types import IPS
from collections import namedtuple


async def wait_await(obj):
    return await obj

async def continue_if_ok(fut, callback,*args):
    res = fut.result()
    if res.state != IPS.Ok:
        return await Just(IPS.Alert,"fail from previous error",data=res)
    else:
        return await callback(*args)
    
DeferResult = namedtuple('DeferResult','state data message',defaults=[IPS.Idle,None,''])

class DeferBase(ABC):
    def __init__(self) -> None:
        super().__init__()
        loop = asyncio.get_event_loop()
        self.log = logging.getLogger('Defer')
        self.result = None

    @abstractmethod
    async def wait(self):
        return DeferResult(IPS.Alert, None, "Error: Absctract class")

    @abstractmethod
    def check(self):
        return DeferResult(IPS.Alert,None, "Error: Absctract class")

    def __await__(self):
        return self.wait().__await__()

class Just(DeferBase):
    def __init__(self, state, error="", data=None):
        super().__init__()
        self.log = logging.getLogger('Just')
        self.result = DeferResult(state, data, error)

    async def wait(self):
        return self.check()

    def check(self):
        return self.result

class DeferProperty(DeferBase):
    def __init__(self, gateway, dev_name, prop_name, step0=None):
        super().__init__()
        loop = asyncio.get_event_loop()
        self.log = logging.getLogger('DeferProperty')
        self.gateway = gateway
        self.dev_name = dev_name
        self.prop_name = prop_name
        self.prop = None

        self.step_0 = None
        self.step_1 = None
        self.step_2 = None

        if step0 is None:
            self.step_2 = self.gateway.getFuture(self.dev_name, self.prop_name)

            self.step_0 = loop.create_future()
            self.step_1 = loop.create_future()

            self.step_0.set_result(True)
            self.step_1.set_result(True)
        else:
            self.step_0 = step0
            self.step_1 = loop.create_future()
            self.step_0.add_done_callback(lambda _: self.__switch_future())

    def __switch_future(self):
        self.step_2 = self.gateway.getFuture(self.dev_name, self.prop_name)
        self.step_1.set_result(True)

    async def wait(self):
        await self.step_0
        await self.step_1
        await self.step_2

        return self.check()

    def check(self):
        if self.result is not None:
            return self.result
                      
        if not self.step_0.done():
            return DeferResult(IPS.Busy,None, "Waiting for triggering event to complete")
        if not self.step_1.done():
            return DeferResult(IPS.Busy,None, "Waiting for callback to complete")

        if self.step_2.cancelled():
            return DeferResult(IPS.Alert,None, "Future cancelled, maybe device has crashed")

        if (vec := self.gateway.getVector(self.dev_name, self.prop_name)) is None:
            return DeferResult(IPS.Alert,None, "Property not available, maybe device has crashed")

        self.prop = vec
        self.result = DeferResult(self.prop.state, self.prop, "data ready")
        return self.result
        
    def __repr__(self) -> str:
        return f'DeferProperty("{self.dev_name}"."{self.prop_name}" = {self.prop})'

     
class DeferAction(DeferBase):
    def __init__(self, step0,action) -> None:
        super().__init__()
        loop = asyncio.get_event_loop()
        self.log = logging.getLogger('DeferAction')

        self.step_0 = loop.create_task(wait_await(step0))

        self.action = action

        self.step_1 = loop.create_future()
        self.step_2 = None

        self.step_0.add_done_callback(lambda x: self.__run(x))

    @classmethod
    def create_task(cls,awaitable,action,*args):
        return cls(awaitable,lambda x : continue_if_ok(x,action,*args))

    def __run(self, res):
        self.log.info(f'step0: {res.result()}')
        loop = asyncio.get_event_loop()
        self.step_2 = loop.create_task(self.action(res))
        self.step_1.set_result(True)

    async def wait(self):
        await self.step_0
        await self.step_1
        await self.step_2
        return self.check()
    

    def check(self):
        if self.result is not None:
            return self.result

        if not self.step_0.done():
            return DeferResult(IPS.Busy,None, "Waiting for triggering event to complete")
        if not self.step_1.done():
            return DeferResult(IPS.Busy,None, "Waiting for action setup")
        if not self.step_2.done():
            return DeferResult(IPS.Busy,None, "Waiting for action to complete")
        if self.step_2.cancelled():
            return DeferResult(IPS.Alert,None, "Future cancelled, maybe device has crashed")

        self.result = self.step_2.result()
        self.log.debug(f'check()->{self.result}')
        return self.result
        
    

class DeferChain(DeferBase):
    def __init__(self,first=None) -> None:
        super().__init__()
        self.log = logging.getLogger('DeferChain')

        b = first
        if b is None:
            b = Just(IPS.Ok,"chain begin")
        self.future_links = [b]

    def add(self,action):
        self.result = None
        a =  DeferAction(self.future_links[-1],action)
        self.future_links.append(a)

    async def wait(self):
        self.result =  await self.future_links[-1]
        return self.result

    def check(self):
        if self.result is not None:
            return self.result
        return self.future_links[-1].check()

    

