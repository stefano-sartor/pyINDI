#!/usr/bin/env python
# -*-coding:utf-8 -*-
'''
@File      :   pyindi/client/ccd.py
@Time      :   2023/03
@Author    :   Stefano Sartor
@Version   :   0.1
@Contact   :   sartor@oavda.it
@License   :   MIT
@Copyright :   (C) 2023 FONDAZIONE CLÉMENT FILLIETROZ-ONLUS
'''


from enum import Enum
from astropy.coordinates import TETE, EarthLocation
from astropy.time import Time
from astropy.io import fits
import asyncio

from .device import Device
from pyindi.core.defer import DeferBase,Just,DeferProperty,DeferResult
from pyindi.core.indi_types import IPS,ISS

import datetime

import logging

class DeferImage(DeferBase):
    def __init__(self, fut_exp, gateway, dev_name, sensor_name='CCD1'):
        super().__init__()
        self.log = logging.getLogger('DeferImage')
        self.gw = gateway
        self.dev_name = dev_name
        self.sensor_name = sensor_name
        self.exp_prop = fut_exp
        self.fut_data = self.gw.getFuture(dev_name,sensor_name)

        self.hdulist = None

    async def wait(self):
        exposure = await self.exp_prop

        if exposure.state != IPS.Ok:
            return DeferResult(IPS.Alert,None,f"abort exposure? {exposure.message}")
        else:
            self.log.info(f'EXPOSURE COMPLETE:{exposure.message}')

        p = await self.fut_data
        if p.state != IPS.Ok:
            return(IPS.Alert,f"download failure? {p}")
        else:
            self.log.info(f'DOWNLOAD COMPLETE:{p}')

        return self.check()

    def check(self):
        if self.result is not None:
            return self.result
        
        exp_res = self.exp_prop.check()

        if exp_res.state != IPS.Ok:
            return DeferResult(exp_res.state,None, exp_res.msg)

        if self.fut_data.cancelled():
            return DeferResult(IPS.Alert,None, "IMAGE readout Cancelled")            

        if not self.fut_data.done():
            return DeferResult(IPS.Busy,None,'Downloading data')

        vec = self.gw.getVector(self.dev_name,self.sensor_name)

        for _,v in vec.items.items():
            buff =v['data']
            buff.seek(0)
            self.hdulist = fits.open(buff)
            break 

        self.result = DeferResult(IPS.Ok,self.hdulist,'Data ready')
        return self.result


class CCD(Device):
    Frame = Enum('Frame',['LIGHT','BIAS','DARK','FLAT'])

    def __init__(self, gateway, dev_name) -> None:
        super().__init__(gateway, dev_name)

    def expose(self, secs, exp_name='CCD_EXPOSURE', sensor_name='CCD1'):
        if (exp := self.gw.getVector(self.dev_name,exp_name)) is None:
            return Just(IPS.Alert, "CCD device not connected")

        for k in exp.items:
            exp.items[k] = secs
            break
        
        loop = asyncio.get_running_loop()
        obj = loop.create_task(self.gw.sendVector(exp))
        exp_prop = DeferProperty(self.gw,self.dev_name,exp_name,obj)
        return DeferImage(exp_prop, self.gw, self.dev_name, sensor_name)


    def setTemperature(self, temp):
        pname = "CCD_TEMPERATURE"
        if (t := self.gw.getVector(self.dev_name,pname)) is None:
            return Just(IPS.Alert, "CCD device not connected")

        t.items['CCD_TEMPERATURE_VALUE'] = temp

        loop = asyncio.get_running_loop()
        obj = loop.create_task(self.gw.sendVector(t))
        return DeferProperty(self.gw, self.dev_name, pname,obj)
    
    def setFrameType(self,frame_type : Frame):
        pname = "CCD_FRAME_TYPE"

        if (sw := self.gw.getVector(self.dev_name,pname)) is None:
            return Just(IPS.Alert, "CCD device not connected")
        
        for k in sw.items:
            if frame_type.name in k:
                sw.items[k] = ISS.On
            else:
                sw.items[k] = ISS.Off

        loop = asyncio.get_running_loop()
        obj = loop.create_task(self.gw.sendVector(sw))
        return DeferProperty(self.gw, self.dev_name, pname,obj)
    
    def resetFrame(self):
        pname = "CCD_FRAME_RESET"

        if (sw := self.gw.getVector(self.dev_name,pname)) is None:
            return Just(IPS.Alert, "CCD device not connected")
        
        for k in sw.items:
            sw.items[k] = ISS.On

        loop = asyncio.get_running_loop()
        obj = loop.create_task(self.gw.sendVector(sw))
        return DeferProperty(self.gw, self.dev_name, pname,obj)
    
    def setFrame(self,x,y,width,height):
        pname = "CCD_FRAME"

        if (vec := self.gw.getVector(self.dev_name,pname)) is None:
            return Just(IPS.Alert, "CCD device not connected")

        vec.items['X'] = x
        vec.items['Y'] = y
        vec.items['WIDTH'] = width
        vec.items['HEIGHT'] = height

        loop = asyncio.get_running_loop()
        obj = loop.create_task(self.gw.sendVector(vec))
        return DeferProperty(self.gw, self.dev_name, pname,obj)

    def setBinning(self,hor,vert):
        pname = "CCD_BINNING"

        if (vec := self.gw.getVector(self.dev_name,pname)) is None:
            return Just(IPS.Alert, "CCD device not connected")

        vec.items['HOR_BIN'] = hor
        vec.items['VER_BIN'] = vert

        loop = asyncio.get_running_loop()
        obj = loop.create_task(self.gw.sendVector(vec))
        return DeferProperty(self.gw, self.dev_name, pname,obj)

    def setHeader(self,object='Unknown',obeserver='Unknown'):
        pname = "FITS_HEADER"

        if (vec := self.gw.getVector(self.dev_name,pname)) is None:
            return Just(IPS.Alert, "CCD device not connected")

        vec.items['FITS_OBSERVER'] = obeserver
        vec.items['FITS_OBJECT'] = object

        loop = asyncio.get_running_loop()
        obj = loop.create_task(self.gw.sendVector(vec))
        return DeferProperty(self.gw, self.dev_name, pname,obj)


    def saveOnDevice(self, active: bool = True):
        pname = "UPLOAD_MODE"

        if (sw := self.gw.getVector(self.dev_name,pname)) is None:
            return Just(IPS.Alert, "CCD device not connected")

        sw.items['UPLOAD_CLIENT'] = ISS.Off if active else ISS.On
        sw.items['UPLOAD_BOTH'] = ISS.On if active else ISS.Off
        sw.items['UPLOAD_LOCAL'] = ISS.Off 

        loop = asyncio.get_running_loop()
        obj = loop.create_task(self.gw.sendVector(sw))
        return DeferProperty(self.gw, self.dev_name, pname,obj)

    def savePath(self, path: str, prefix: str):
        pname = "UPLOAD_SETTINGS"

        if (txt := self.gw.getVector(self.dev_name,pname)) is None:
            return Just(IPS.Alert, "CCD device not connected")

        txt.items['UPLOAD_DIR']    = path
        txt.items['UPLOAD_PREFIX'] = prefix + "_XXX"

        loop = asyncio.get_running_loop()
        obj = loop.create_task(self.gw.sendVector(txt))
        return DeferProperty(self.gw, self.dev_name, pname,obj)
   
    def getLastImagePath(self):
        pname = "CCD_FILE_PATH"

        if (txt := self.gw.getVector(self.dev_name,pname)) is None:
            return None

        return txt.items.get('FILE_PATH')
