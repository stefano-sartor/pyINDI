#!/usr/bin/env python
# -*-coding:utf-8 -*-
'''
@File      :   pyindi/client/filter.py
@Time      :   2023/03
@Author    :   Stefano Sartor
@Version   :   0.1
@Contact   :   sartor@oavda.it
@License   :   MIT
@Copyright :   (C) 2023 FONDAZIONE CLÉMENT FILLIETROZ-ONLUS
'''

from .device import Device
from pyindi.core.defer import *
from pyindi.core.indi_types import IPS
import logging

class FilterWheel(Device):
    def __init__(self, gateway, dev_name) -> None:
        super().__init__(gateway, dev_name)


    def getFilters(self):
        if (prop := self.gw.getVector(self.dev_name,"FILTER_NAME")) is None:
            logging.warning(f'no FILTER_NAME present in filterwheel device {self.dev_name}')
            return []
        l = []
        for _,v in prop.items.items():
            l.append(v)
        return l
    
    def setFilter(self,f):
        filters = self.getFilters()

        nf = -1
        if type(f) == int:
            nf = f
        if type(f) == str:
            if f in filters:
                nf = 1 + filters.index(f)

        pname = "FILTER_SLOT"

        if (slot := self.gw.getVector(self.dev_name,pname)) is None:
            return Just(IPS.Alert, "FilterWheel device not connected")
        
        if nf <= 0:
            return Just(IPS.Alert, "Bad filter value")

        if nf > len(filters):
            return Just(IPS.Alert, "Bad filter value")
        
        slot.items['FILTER_SLOT_VALUE'] =nf

        loop = asyncio.get_running_loop()
        obj = loop.create_task(self.gw.sendVector(slot))
        return DeferProperty(self.gw, self.dev_name, pname,obj)
    
    def getFilter(self):
        filters = self.getFilters()
        if (slot := self.gw.getVector(self.dev_name,"FILTER_SLOT")) is None:
            return None
        
        idx = int(slot.items['FILTER_SLOT_VALUE']) -1
        return filters[idx]
