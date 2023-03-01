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

class FilterWheel(Device):
    def __init__(self, gateway, dev_name) -> None:
        super().__init__(gateway, dev_name)
        self.filters=[]


    def getFilters(self):
        if len(self.filters) >0:
            return self.filters
        
        if (prop := self.gw.getVector(self.dev_name,"FILTER_NAME")) is None:
            return []
        l = []
        for _,v in prop.items.items():
            l.append(v)
        
        self.filters = l
        return self.filters
    
    def setFilter(self,f):
        nf = -1
        if type(f) == int:
            nf = f
        if type(f) == str:
            if f in self.getFilters():
                nf = 1 + self.filters.index(f)

        pname = "FILTER_SLOT"

        if (slot := self.gw.getVector(self.dev_name,pname)) is None:
            return Just(IPS.Alert, "FilterWheel device not connected")
        
        #FIXME find a solution for limits...
        # if nf < slot[0].min:
            # return Just(IPS.Alert, "Bad filter value")
        # 
        # if nf > slot[0].max:
            # return Just(IPS.Alert, "Bad filter value")
        
        slot.items['FILTER_SLOT_VALUE'] =nf

        loop = asyncio.get_running_loop()
        obj = loop.create_task(self.gw.sendVector(slot))
        return DeferProperty(self.gw, self.dev_name, pname,obj)
