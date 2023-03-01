#!/usr/bin/env python
# -*-coding:utf-8 -*-
'''
@File      :   example_clients/demo_telescope.py
@Time      :   2023/03
@Author    :   Stefano Sartor
@Version   :   0.1
@Contact   :   sartor@oavda.it
@License   :   MIT
@Copyright :   (C) 2023 FONDAZIONE CLÉMENT FILLIETROZ-ONLUS
'''

import asyncio
import argparse
from astropy.coordinates import SkyCoord

from pyindi.client import Gateway
from pyindi.client.telescope import DIRECTION
from pyindi.core.defer import DeferChain,wait_await
from pyindi.core.indi_types import IPS

import logging

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

    tel = ie.getTelescope()

    tp = await tel.connect()
    logging.info(f'CONNECT AWAITED {tp}')

    capella = SkyCoord.from_name('Capella')

    res = await tel.goto(capella)
    logging.error(f'SLEW {res.state} {res.message} {res.data}') 
    
       
    chain = DeferChain()
    chain.add(lambda _ : wait_await(tel.motion(DIRECTION.WEST,1000)))
    chain.add(lambda _ : wait_await(tel.motion(DIRECTION.NORTH,1000)))
    chain.add(lambda _ : wait_await(tel.motion(DIRECTION.EAST,1000)))
    chain.add(lambda _ : wait_await(tel.motion(DIRECTION.SOUTH,1000)))

    res = await chain
    if res.state != IPS.Ok:
        logging.error(f'error {res.state} {res.message} {res.data}')
    
    chain = DeferChain()
    chain.add(lambda _ : wait_await(tel.timed_guide(DIRECTION.WEST, 1000)))
    chain.add(lambda _ : wait_await(tel.timed_guide(DIRECTION.NORTH,1000)))
    chain.add(lambda _ : wait_await(tel.timed_guide(DIRECTION.EAST, 1000)))
    chain.add(lambda _ : wait_await(tel.timed_guide(DIRECTION.SOUTH,1000)))

    res = await chain
    if res.state == IPS.Alert:
        logging.error(f'error {res.state} {res.message} {res.data}')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog='Image Loop')
    parser.add_argument('indiserver', default='localhost')
    parser.add_argument('-p', '--port', type=int, default=7624)
    

    args = parser.parse_args()
    asyncio.run( main(args))

