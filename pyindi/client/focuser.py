#!/usr/bin/env python
# -*-coding:utf-8 -*-
'''
@File      :   pyindi/client/focuser.py
@Time      :   2023/03
@Author    :   Stefano Sartor
@Version   :   0.1
@Contact   :   sartor@oavda.it
@License   :   MIT
@Copyright :   (C) 2023 FONDAZIONE CLÉMENT FILLIETROZ-ONLUS
'''


from .device import Device
from pyindi.core.defer import *
from pyindi.core.indi_types import ISS, IPS


class Focuser(Device):
    def __init__(self, gateway, dev_name) -> None:
        super().__init__(gateway, dev_name)

    def __move_rel(self, steps: int, is_in: bool):
        sw_name = "FOCUS_MOTION"
        pos_name = "REL_FOCUS_POSITION"

        focus_in = 'FOCUS_INWARD'
        focus_out = 'FOCUS_OUTWARD'

        if (sw := self.gw.getVector(self.dev_name, sw_name)) is None:
            return Just(IPS.Alert, "Focuser device not connected or does not support relative motion")

        if (pos := self.gw.getVector(self.dev_name, pos_name)) is None:
            return Just(IPS.Alert, "Focuser device not connected or does not support relative motion")
        
        logging.warning(f'{sw}')

        loop = asyncio.get_running_loop()
        chain = DeferChain()

        sw.items[focus_in] = ISS.On if is_in else ISS.Off
        sw.items[focus_out] = ISS.Off if is_in else ISS.On

        obj = loop.create_task(self.gw.sendVector(sw))
        chain.add(lambda _: wait_await(DeferProperty(
            self.gw, self.dev_name, sw_name, obj)))

        pos.items['FOCUS_RELATIVE_POSITION'] = steps

        async def continuation(x):
            res = x.result()
            if res.state != IPS.Ok:
                return await Just(IPS.Alert, "fail from previous error", data=res)
            else:
                obj = loop.create_task(self.gw.sendVector(pos))
                return await DeferProperty(self.gw, self.dev_name, pos_name, obj)

        chain.add(lambda x: continuation(x))
        return chain

    def moveIn(self, steps):
        return self.__move_rel(steps, True)

    def moveOut(self, steps):
        return self.__move_rel(steps, False)

    def moveAbs(self, steps):
        pos_name = "ABS_FOCUS_POSITION"

        if (pos := self.gw.getVector(self.dev_name, pos_name)) is None:
            return Just(IPS.Alert, "Focuser device not connected or does not support relative motion")

        pos.items['FOCUS_ABSOLUTE_POSITION'] = steps

        loop = asyncio.get_running_loop()
        obj = loop.create_task(self.gw.sendVector(pos))
        return DeferProperty(self.gw, self.dev_name, pos_name, obj)

    def getAbsPos(self):
        pos_name = "ABS_FOCUS_POSITION"

        if (pos := self.gw.getVector(self.dev_name, pos_name)) is None:
            return None

        return pos.items['FOCUS_ABSOLUTE_POSITION']
