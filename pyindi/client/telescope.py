#!/usr/bin/env python
# -*-coding:utf-8 -*-
'''
@File      :   pyindi/client/telescope.py
@Time      :   2023/03
@Author    :   Stefano Sartor
@Version   :   0.1
@Contact   :   sartor@oavda.it
@License   :   MIT
@Copyright :   (C) 2023 FONDAZIONE CLÉMENT FILLIETROZ-ONLUS
'''


from enum import Enum
from astropy.coordinates import SkyCoord, TETE, AltAz, EarthLocation
from astropy.time import Time
import astropy.units as u
from astropy.wcs import WCS

from .device import Device
from pyindi.core.indi_types import SwitchVectorProperty, NumberVectorProperty, ISS
from pyindi.core.defer import *

from copy import deepcopy
import logging


class DIRECTION(Enum):
    NORTH = 'MOTION_NORTH'
    SOUTH = 'MOTION_SOUTH'
    WEST = 'MOTION_WEST'
    EAST = 'MOTION_EAST'


class Telescope(Device):
    def __init__(self, gateway, dev_name) -> None:
        super().__init__(gateway, dev_name)
        self.location = None

    def getLocation(self):
        if self.location is not None:
            return self.location
        try:
            coord = self.gw.getVector(self.dev_name, 'GEOGRAPHIC_COORD')
            lat = coord.items['LAT']
            lon = coord.items['LONG']
            elev = coord.items['ELEV']
            self.location = EarthLocation(lon=lon, lat=lat, height=elev)
            return self.location
        except:
            return None

    def abort(self):
        pname = 'TELESCOPE_ABORT_MOTION'
        sp = SwitchVectorProperty()
        sp.device = self.dev_name
        sp.name = pname
        sp.items['ABORT'] = ISS.On

        loop = asyncio.get_running_loop()
        obj = loop.create_task(self.gw.sendVector(sp))
        return DeferProperty(self.gw, self.dev_name, pname, obj)

    def motion(self, dir: DIRECTION, ms=250):
        sp = SwitchVectorProperty()
        sp.device = self.dev_name

        if dir == DIRECTION.NORTH or dir == DIRECTION.SOUTH:
            sp.name = 'TELESCOPE_MOTION_NS'
            sp.items[DIRECTION.NORTH.value] = ISS.On if dir == DIRECTION.NORTH else ISS.Off
            sp.items[DIRECTION.SOUTH.value] = ISS.Off if dir == DIRECTION.NORTH else ISS.On
        else:
            sp.name = 'TELESCOPE_MOTION_WE'
            sp.items[DIRECTION.WEST.value] = ISS.On if dir == DIRECTION.WEST else ISS.Off
            sp.items[DIRECTION.EAST.value] = ISS.Off if dir == DIRECTION.WEST else ISS.On

        spp = deepcopy(sp)

        loop = asyncio.get_running_loop()
        obj = loop.create_task(self.gw.sendVector(spp))

        for k in sp.items:
            sp.items[k] = ISS.Off

        async def delay_send():
            await asyncio.sleep(ms/1000)
            obj2 = loop.create_task(self.gw.sendVector(sp))
            return await DeferProperty(self.gw, self.dev_name, sp.name, obj2)

        return DeferAction(obj, lambda _: delay_send())

    def timed_guide(self, dir: DIRECTION, ms: int):
        sp = NumberVectorProperty()
        sp.device = self.dev_name

        if dir == DIRECTION.NORTH or dir == DIRECTION.SOUTH:
            sp.name = 'TELESCOPE_TIMED_GUIDE_NS'
            sp.items['TIMED_GUIDE_N'] = ms if dir == DIRECTION.NORTH else 0
            sp.items['TIMED_GUIDE_S'] = 0 if dir == DIRECTION.NORTH else ms
        else:
            sp.name = 'TELESCOPE_TIMED_GUIDE_WE'
            sp.items['TIMED_GUIDE_W'] = ms if dir == DIRECTION.WEST else 0
            sp.items['TIMED_GUIDE_E'] = 0 if dir == DIRECTION.WEST else ms

        spp = deepcopy(sp)

        loop = asyncio.get_running_loop()
        obj = loop.create_task(self.gw.sendVector(spp))
        return DeferProperty(self.gw, self.dev_name, sp.name, obj)

    def park(self):
        return self.__change_park(True)

    def unpark(self):
        return self.__change_park(False)

    def __change_park(self, park=True):
        pname = 'TELESCOPE_PARK'
        sp = SwitchVectorProperty()
        sp.device = self.dev_name
        sp.name = pname
        sp.items['PARK'] = ISS.On if park else ISS.Off
        sp.items['UNPARK'] = ISS.Off if park else ISS.On

        return self._defer_prop(pname, sp)

    def goto(self, coord, track=True):
        ''' Moves telescope to coord
        Parameters
        ----------
        coord : astropy.coordinate
            The coordinate of the target. The frame does not matter,
            this method will take care of frame conversions.
        track : bool, optional
            whether the telescope needs to start tracking or not
            once the slew is completed (default is True)

        Returns
        -------
        DeferProperty which can be waited or checked.
            for more on Defer objects, check its documentation

        Raises
        ------
        RuntimeError if no TELESCOPE device is found on the server
        '''
        return self.set_coord(coord, 'TRACK' if track else 'SLEW')

    def sync(self, coord):
        ''' sync the telescope to coord
        Parameters
        ----------
        coord : astropy.coordinate
            The coordinate of the target. The frame does not matter,
            this method will take care of frame conversions.

        Returns
        -------
        DeferProperty which can be waited or checked.
            for more on Defer objects, check its documentation

        Raises
        ------
        RuntimeError if no TELESCOPE device is found on the server
        '''
        return self.set_coord(coord, 'SYNC')

    def getAA(self, coord):
        ''' Calculates AltAzimuth coordinates based on the site of the mount
        Parameters
        ----------
        coord : astropy.coordinate
            The coordinate of the target. The frame does not matter,
            this method will take care of frame conversions.

        Returns
        -------
        astropy.coordinates.AltAz at the current time. 

        None is returned if the site information cannot be retreived
            (telescope deviced non connected for example) 
        '''

        if self.getLocation() is None:
            return None

        aa = AltAz(location=self.getLocation(), obstime=Time.now())
        return coord.transform_to(aa)

    def set_coord(self, coord, action='TRACK'):
        t = TETE(location=self.getLocation(), obstime=Time.now())
        jnow = coord.transform_to(t)

        eq_name = "EQUATORIAL_EOD_COORD"
        ocs_name = "ON_COORD_SET"

        if (ocs := self.gw.getVector(self.dev_name, ocs_name)) is None:
            return Just(IPS.Alert, "Cannot set ON_COORD_SET")

        if (radec := self.gw.getVector(self.dev_name, eq_name)) is None:
            return Just(IPS.Alert, f"EQ Coord not available for device {self.dev_name}")

        for k in ocs.items:
            ocs.items[k] = ISS.Off

        ocs.items[action] = ISS.On

        sv = self.gw.sendVector(ocs)
        chain = DeferChain(sv)
        chain.add(lambda _: wait_await(DeferProperty(
            self.gw, self.dev_name, ocs_name)))

        radec.items['RA'] = jnow.ra.hour
        radec.items['DEC'] = jnow.dec.deg

        async def continuation(x):
            res = x.result()
            if res.state != IPS.Ok:
                return await Just(IPS.Alert, "fail from previous error", data=res)
            else:
                loop = asyncio.get_event_loop()
                obj = loop.create_task(self.gw.sendVector(radec))
                return await DeferProperty(self.gw, self.dev_name, eq_name, obj)

        chain.add(lambda x: continuation(x))
        return chain

    def get_coord(self):
        eq_name = "EQUATORIAL_EOD_COORD"
        if (radec := self.gw.getVector(self.dev_name, eq_name)) is None:
            raise RuntimeError(f'Cannot find curred EOD coordinates')
        return TETE(ra=radec.items['RA'] * u.hour, dec=radec.items['DEC']*u.deg, location=self.getLocation(), obstime=Time.now())
                            
    def refine_pointing(self, solver, hdulist, target,use_guide=True):
        step0 = None
        if hdulist[0].header.get('WCSAXES'):
            try:
                data = WCS(hdulist[0].header)
                step0 = Just(IPS.Ok, 'WCS already available',data = data)
            except Exception as e:
                self.log.error(f'error while creating WCS: {e}')
            
        if step0 is None:
            step0 = solver.solve(hdulist[0])

        chain = DeferChain(step0)

        async def continuation(x):
            GUIDE_SPEED_ARCSECSEC = 15.041067 * 0.5
            log = logging.getLogger("refine_pointing")
            res = x.result()
            if res.state != IPS.Ok:
                return await Just(IPS.Alert, "cannot solve field")

            # N.B. RA--DEC e CRVAL1--CRVAL2 sono coordinate J2000.

            ra_sol = hdulist[0].header['CRVAL1'] * u.deg
            dec_sol = hdulist[0].header['CRVAL2'] * u.deg


            actual_coord = SkyCoord(ra=ra_sol, dec=dec_sol, frame="fk5")

            target_fk5 = target.transform_to(actual_coord)

            delta_ra, delta_dec = actual_coord.spherical_offsets_to(target_fk5.frame)


            log.info(
                f'delta RA: {delta_ra.to_value(u.arcsec):.2f}", Dec: {delta_dec.to_value(u.arcsec):.2f}"')
            
            if not use_guide:
                log.info('using goto')
                coord = SkyCoord(ra=ra_sol + delta_ra, dec=dec_sol +
                                 delta_dec, frame="fk5")
                return await self.goto(coord)
            else:
                guide_chain = DeferChain()

                ra_sec  = delta_ra.to_value(u.arcsec) / GUIDE_SPEED_ARCSECSEC
                dec_sec = delta_dec.to_value(u.arcsec) / GUIDE_SPEED_ARCSECSEC

                guide_ra  = abs(ra_sec*1000)
                guide_dec = abs(dec_sec*1000)

                if ra_sec < 0:
                    obj = self.timed_guide(DIRECTION.WEST,guide_ra)
                    guide_chain.add(lambda _ : wait_await(obj))
                    log.info(f'GUIDE WEST {guide_ra:.1f}')
                else:
                    obj = self.timed_guide(DIRECTION.EAST,guide_ra)
                    guide_chain.add(lambda _ : wait_await(obj))
                    log.info(f'GUIDE EAST {guide_ra:.1f}')

                if dec_sec > 0:
                    obj = self.timed_guide(DIRECTION.NORTH,guide_dec)
                    guide_chain.add(lambda _ : wait_await(obj))
                    log.info(f'GUIDE NORTH {guide_dec:.1f}')
                else:
                    obj = self.timed_guide(DIRECTION.SOUTH,guide_dec)
                    guide_chain.add(lambda _ : wait_await(obj))
                    log.info(f'GUIDE SOUTH {guide_dec:.1f}')

                return await guide_chain

        
        chain.add(lambda x: continuation(x))
        return chain
