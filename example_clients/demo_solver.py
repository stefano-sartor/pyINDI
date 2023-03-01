#!/usr/bin/env python
# -*-coding:utf-8 -*-
'''
@File      :   example_clients/demo_solver.py
@Time      :   2023/03
@Author    :   Stefano Sartor
@Version   :   0.1
@Contact   :   sartor@oavda.it
@License   :   MIT
@Copyright :   (C) 2023 FONDAZIONE CLÉMENT FILLIETROZ-ONLUS
'''

import asyncio
import argparse
from astropy.io import fits
from pathlib import Path
from pyindi.client.solver import FieldSolver
import logging


#create formatter and handler for terminal output logging
consoleHandler = logging.StreamHandler()
consoleHandler.setLevel(logging.INFO) # INFO vermosity should be ok

rootLogger = logging.getLogger()
rootLogger.setLevel(logging.DEBUG)
rootLogger.addHandler(consoleHandler)

    
async def main(args):

    solver = FieldSolver()

    hdulist = fits.open(args.fits_file)

    res = await solver.solve(hdulist[0])
    logging.info(f'{res.message}:{res.state} {res.data}')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog='Field sover')
    parser.add_argument('fits_file', type=Path)

    args = parser.parse_args()

    asyncio.run( main(args))

