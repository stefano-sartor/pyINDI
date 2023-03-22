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




    
async def main(args):
    #create formatter and handler for terminal output logging
    consoleHandler = logging.StreamHandler()
    consoleHandler.setLevel(logging.DEBUG if args.verbose else logging.INFO) # INFO vermosity should be ok

    rootLogger = logging.getLogger()
    rootLogger.setLevel(logging.DEBUG)
    rootLogger.addHandler(consoleHandler)    

    solver = FieldSolver()
    solver.conf['SEXTRACTOR_COMMAND'].append('-MASK_TYPE NONE')
    solver.conf['SEXTRACTOR_COMMAND'].append('-VERBOSE_TYPE FULL')    
    solver.regen_conf()


    hdulist = fits.open(args.fits_file)

    res = await solver.solve(hdulist[0],delete_temp=not args.keep_temp)
    logging.info(f'{res.message}:{res.state} {res.data}')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog='Field sover')
    parser.add_argument('fits_file', type=Path)
    parser.add_argument('-k', '--keep-temp', type=bool, default=False)
    parser.add_argument('-v', '--verbose', action='store_true')  

    args = parser.parse_args()

    asyncio.run( main(args))

