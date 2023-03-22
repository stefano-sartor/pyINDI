#!/usr/bin/env python
# -*-coding:utf-8 -*-
'''
@File      :   pyindi/client/solver.py
@Time      :   2023/03
@Author    :   Stefano Sartor
@Version   :   0.1
@Contact   :   sartor@oavda.it
@License   :   MIT
@Copyright :   (C) 2023 FONDAZIONE CLÉMENT FILLIETROZ-ONLUS
'''

from pathlib import Path
from astropy.io import fits
from astropy.wcs import WCS
from uuid import uuid4
from asyncio.subprocess import PIPE
from pyindi.core.defer import *
import numpy as np
import logging
import asyncio
from pyindi.core.indi_types import IPS
from copy import deepcopy

SEX_PARAM = [
    'X_IMAGE',
    'Y_IMAGE',
    'MAG_AUTO',
    'FLUX_AUTO',
    'FLUX_MAX',
    'FWHM_IMAGE',
    'CXX_IMAGE',
    'CYY_IMAGE',
    'CXY_IMAGE',
    'A_IMAGE',
    'B_IMAGE',
    'THETA_IMAGE',
]

SEX_FILTER = [
    'CONV Filter Generated by StellarSolver Internal Library',
    '1 2 1',
    '2 4 2',
    '1 2 1',
]


ASTROMETRY_CFG = [
    'minwidth 0.1',
    'maxwidth 180',
    'cpulimit 600',
    'autoindex',
]


SEXTRACTOR_COMMAND = [
    '{sex_exec}',
    '-CATALOG_NAME {fits_file}.xyls',
    '-CATALOG_TYPE FITS_1.0',
    '-PARAMETERS_NAME {sex_param_file}',
    '-DETECT_TYPE CCD',
    '-DETECT_MINAREA 10',
    '-FILTER Y',
    '-FILTER_NAME {sex_filter_file}',
    '-DEBLEND_NTHRESH 32',
    '-DEBLEND_MINCONT 0.005',
    '-CLEAN Y',
    '-CLEAN_PARAM 1',
    '-PHOT_AUTOPARAMS 2.5,3.5',
    '-MAG_ZEROPOINT 20',
]

ASTROMETRY_COMMAND = [
    '{astrometry_exec}',
    '-O',
    '--no-plots',
    '--no-verify',
    '--crpix-center',
    '--match none',
    '--corr none',
    '--new-fits none',
    '--rdls none',
    '--resort',
    '--odds-to-solve 1.00003e+09',
    '--odds-to-tune-up 999989',
    '-L {scale_low}',
    '-H {scale_high}',
    '-u arcsecperpix',
    '--ra {ra}',
    '--dec {dec}',
    '--radius {radius}',
    '--width {width}',
    '--height {height}',
    '--x-column X_IMAGE',
    '--y-column Y_IMAGE',
    '--sort-column MAG_AUTO',
    '--sort-ascending',
    '--no-remove-lines',
    '--uniformize 0',
    '--cancel {fits_file}.cancel',
    '-W {fits_file}.wcs',
]


class DelBucket(object):
    def __init__(self) -> None:
        self.log = logging.getLogger('DelBucket')
        self.bucket = []

    def add(self, p):
        pp = Path(p).expanduser().absolute()
        self.bucket.append(pp)

    def __del__(self):
        for p in self.bucket:
            try:
                p.unlink()
            except Exception as e:
                self.log.debug(f'cannot remove file {e}')


class DeferSEx(DeferBase):
    def __init__(self, hdu, conf, delete_temp=True) -> None:
        super().__init__()
        self.conf = conf
        self.log = logging.getLogger('SExtractor')

        self.rc = None
        self.data = None

        self.del_temp = delete_temp

        self.uu = uuid4().hex
        self.conf['uu'] = self.uu
        self.conf['fits_file'] = self.conf['base_path'].joinpath(self.uu)
        self.conf['path_xyls'] = self.conf['base_path'].joinpath(
            self.uu+'.xyls')

        path_fits = self.conf['base_path'].joinpath(self.uu+'.fits')
        path_xyls = self.conf['base_path'].joinpath(self.uu+'.xyls')

        hdu.writeto(path_fits, overwrite=True)

        self.conf['SEXTRACTOR_COMMAND'].append('{fits_file}.fits')
        sexcommand = ' '.join(
            self.conf['SEXTRACTOR_COMMAND']).format(**self.conf)
        self.log.debug(sexcommand)

        self.proc = None

        async def create_subprocess():
            self.proc = await asyncio.create_subprocess_shell(
                sexcommand, stdout=PIPE, stderr=PIPE)
            return self.proc

        async def stream_read():
            while True:
                out_eof = self.proc.stdout.at_eof()
                err_eof = self.proc.stderr.at_eof()

                if not out_eof:
                    line = await self.proc.stdout.readline()
                    l = line.decode('utf8')
                    s = l.replace('\x1b[1A', '').replace('\x1b[1M', '').strip()
                    self.log.debug(s)

                if not err_eof:
                    line = await self.proc.stderr.readline()
                    l = line.decode('utf8')
                    s = l.replace('\x1b[1A', '').replace('\x1b[1M', '').strip()
                    self.log.debug(s)

                if out_eof and err_eof:
                    break

        self.sub_chain = DeferChain()
        self.sub_chain.add(lambda _: wait_await(create_subprocess()))
        self.sub_chain.add(lambda _: wait_await(stream_read()))

        self.conf['bucket'] = DelBucket()
        if delete_temp:
            self.conf['bucket'].add(path_fits)
            self.conf['bucket'].add(path_xyls)

    async def wait(self):
        await self.sub_chain
        self.rc = await self.proc.wait()
        return self.check()

    def check(self):
        if self.result is not None:
            return self.result

        if self.proc is None:
            return DeferResult(IPS.Busy, None, 'subprocess not created yet')

        if self.rc is None:
            self.rc = self.proc.returncode

        if self.rc is None:
            return DeferResult(IPS.Busy, None, 'SExtractior still running')
        elif self.rc != 0:
            self.result = DeferResult(
                IPS.Alert, None, f'SExtractor exited with code {self.rc}')
            return self.result
        else:
            self.result = DeferResult(IPS.Ok, self.conf, "data ready")
            return self.result


class DeferAstrometry(DeferBase):
    def __init__(self, hdu, conf, delete_temp=True) -> None:
        super().__init__()
        self.conf = conf
        self.log = logging.getLogger('Astrometry.net')

        self.hdu = hdu
        uu = self.conf['uu']

        self.rc = None
        self.del_temp = delete_temp

        self.path_wcs = self.conf['base_path'].joinpath(uu+'.wcs')
        path_indx = self.conf['base_path'].joinpath(uu+'-indx.xyls')
        self.conf['path_indx'] = path_indx

        scale = hdu.header['SCALE']
        self.conf['scale_low'] = scale * 0.8
        self.conf['scale_high'] = scale * 1.2
        self.conf['ra'] = hdu.header['RA']
        self.conf['dec'] = hdu.header['DEC']
        self.conf['width'] = hdu.header['NAXIS1']
        self.conf['height'] = hdu.header['NAXIS2']

        self.conf['ASTROMETRY_COMMAND'].append('{fits_file}.xyls')
        astrocommand = ' '.join(
            self.conf['ASTROMETRY_COMMAND']).format(**self.conf)
        self.log.debug(astrocommand)
        self.proc = None

        async def create_subprocess():
            self.proc = await asyncio.create_subprocess_shell(
                astrocommand, stdout=PIPE, stderr=PIPE)
            return self.proc

        async def stream_read():
            while True:
                out_eof = self.proc.stdout.at_eof()
                err_eof = self.proc.stderr.at_eof()

                if not out_eof:
                    line = await self.proc.stdout.readline()
                    s = line.decode('utf8')
                    self.log.debug(s.strip())

                if not err_eof:
                    line = await self.proc.stderr.readline()
                    s = line.decode('utf8')
                    self.log.debug(s.strip())

                if out_eof and err_eof:
                    break

        self.sub_chain = DeferChain()
        self.sub_chain.add(lambda _: wait_await(create_subprocess()))
        self.sub_chain.add(lambda _: wait_await(stream_read()))

        if delete_temp:
            path_axy = self.conf['base_path'].joinpath(uu+'.axy')
            path_solved = self.conf['base_path'].joinpath(uu+'.solved')
            self.conf['bucket'].add(self.path_wcs)
            self.conf['bucket'].add(path_indx)
            self.conf['bucket'].add(path_axy)
            self.conf['bucket'].add(path_solved)

    async def wait(self):
        await self.sub_chain
        self.rc = await self.proc.wait()
        return self.check()

    def check(self):
        if self.result is not None:
            return self.result

        if self.proc is None:
            return DeferResult(IPS.Busy, None, 'subprocess not created yet')
        if self.rc is None:
            self.rc = self.proc.returncode
        if self.rc is None:
            return DeferResult(IPS.Busy, None, 'Astrometry.net still running')
        elif Path(self.path_wcs).exists():
            fw = fits.open(self.path_wcs)
            self.wcs = WCS(fw[0])
            self.hdu.header.update(self.wcs.to_header())
            self.result = DeferResult(IPS.Ok, self.wcs, 'field solved')
            fw.close()
            return self.result
        else:
            self.result = DeferResult(
                IPS.Alert, None, f'Astrometry failed to solve field, exit code {self.proc.returncode}')
            return self.result


class FieldSolver:
    def __init__(self, sex_exec='/usr/bin/sex', astrometry_exec='/usr/bin/solve-field', base_path='/tmp/astrometry') -> None:
        bp = Path(base_path)
        bp.mkdir(exist_ok=True)

        self.conf = {}
        self.conf['sex_exec'] = sex_exec
        self.conf['astrometry_exec'] = astrometry_exec
        self.conf['radius'] = 3

        self.conf['base_path'] = bp

        self.conf['ASTROMETRY_CFG'] = deepcopy(ASTROMETRY_CFG)
        self.conf['SEX_PARAM'] = deepcopy(SEX_PARAM)
        self.conf['SEX_FILTER'] = deepcopy(SEX_FILTER)
        self.conf['SEXTRACTOR_COMMAND'] = deepcopy(SEXTRACTOR_COMMAND)
        self.conf['ASTROMETRY_COMMAND'] = deepcopy(ASTROMETRY_COMMAND)

        self.regen_conf()

    def regen_conf(self):
        uu = uuid4().hex

        bp = self.conf['base_path']

        self.conf['astrometry_cfg_file'] = bp / f'astrometry_{uu}_.cfg'
        self.conf['sex_param_file'] = bp / f'sex_{uu}_.param'
        self.conf['sex_filter_file'] = bp / f'filter_{uu}_.conv'

        with open(self.conf['astrometry_cfg_file'], 'wt') as f:
            f.write('\n'.join(self.conf['ASTROMETRY_CFG']))
            f.close()

        with open(self.conf['sex_param_file'], 'wt') as f:
            f.write('\n'.join(self.conf['SEX_PARAM']))
            f.close()

        with open(self.conf['sex_filter_file'], 'wt') as f:
            f.write('\n'.join(self.conf['SEX_FILTER']))
            f.close()

    def sex(self, hdu, delete_temp=True):
        return DeferSEx(hdu, deepcopy(self.conf), delete_temp)

    def solve(self, hdu, defersex=None, delete_temp=True):
        obj = self.sex(hdu, delete_temp) if defersex is None else defersex
        chain = DeferChain()
        chain.add(lambda _: wait_await(obj))

        async def continuation(x):
            res = x.result()
            if res.state != IPS.Ok:
                return await Just(IPS.Alert, "fail from previous error", data=res)
            else:
                return await DeferAstrometry(hdu, res.data, delete_temp)

        chain.add(lambda x: continuation(x))
        return chain
