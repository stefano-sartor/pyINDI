#!/usr/bin/env python
# -*-coding:utf-8 -*-
'''
@File      :   example_clients/demo_focuser.py
@Time      :   2023/03
@Author    :   Stefano Sartor
@Version   :   0.1
@Contact   :   sartor@oavda.it
@License   :   MIT
@Copyright :   (C) 2023 FONDAZIONE CLÉMENT FILLIETROZ-ONLUS
'''

from pyindi.client import Gateway
import asyncio
import argparse

import logging
from pyindi.core.indi_types import IPS


#create formatter and handler for terminal output logging
consoleHandler = logging.StreamHandler()
consoleHandler.setLevel(logging.INFO) # INFO vermosity should be ok

rootLogger = logging.getLogger()
rootLogger.setLevel(logging.DEBUG) # we always need to set max verbosity here
rootLogger.addHandler(consoleHandler)

    
async def main(args):
    ie = Gateway()
    ie.start(args.indiserver,args.port)

    stream = asyncio.create_task(ie.connect(),name='STREAM')
    await ie.connection()

    await ie.getProperties()

    await asyncio.sleep(1)

    foc = ie.getFocuser()

    tp = await foc.connect()
    logging.info(f'CONNECT AWAITED {tp}')


    res = await foc.moveIn(49999)
    if res.state != IPS.Ok:
        logging.error(f'error {res.state} {res.message} {res.data}')

    await asyncio.sleep(1)
    logging.info('-----------------------------------------------')


    res = await foc.moveOut(50001)
    if res.state != IPS.Ok:
        logging.error(f'error {res.state} {res.message} {res.data}')


    await asyncio.sleep(1)
    logging.info('-----------------------------------------------')

    res = await foc.moveAbs(5000)
    if res.state != IPS.Ok:
        logging.error(f'error {res.state} {res.message} {res.data}')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog='Image Loop')
    parser.add_argument('indiserver', default='localhost')
    parser.add_argument('-p', '--port', type=int, default=7624)    

    args = parser.parse_args()

    asyncio.run( main(args))

