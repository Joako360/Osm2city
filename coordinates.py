#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Transform global (aka geodetic) coordinates to a local cartesian, in meters.
A flat earth approximation (http://williams.best.vwh.net/avform.htm) seems good
enough if distances are up to a few km.

Alternatively, use UTM, but that fails if the origin is near an UTM zone boundary.
Also, this requires the utm python package (pip install utm).

The correct approach, though, is probably to do exactly what FG does, which I think is
- transform geodetic to geocentric coordinates (find a python lib for that)
- from there, compute the (geocentric) Cartesian coordinates as described here:
    http://www.flightgear.org/Docs/Scenery/CoordinateSystem/CoordinateSystem.html
- project them onto local Cartesian (including correct up vector etc)

Created on Sat Jun  7 22:38:59 2014
@author: albrecht
"""
#http://williams.best.vwh.net/avform.htm
#Local, flat earth approximation
# If you stay in the vicinity of a given fixed point (lat0,lon0), it may be a 
# good enough approximation to consider the earth as "flat", and use a North,
# East, Down rectangular coordinate system with origin at the fixed point. If
# we call the changes in latitude and longitude dlat=lat-lat0, dlon=lon-lon0 
# (Here treating North and East as positive!), then
#
#       distance_North=R1*dlat
#       distance_East=R2*cos(lat0)*dlon
#
# R1 and R2 are called the meridional radius of curvature and the radius of 
# curvature in the prime vertical, respectively.
#
#      R1=a(1-e^2)/(1-e^2*(sin(lat0))^2)^(3/2)
#      R2=a/sqrt(1-e^2*(sin(lat0))^2)
#
# a is the equatorial radius of the earth (=6378.137000km for WGS84), and
# e^2=f*(2-f) with the flattening f=1/298.257223563 for WGS84.
#
# In the spherical model used elsewhere in the Formulary, R1=R2=R, the earth's
# radius. (using R=1 we get distances in radians, using R=60*180/pi distances are in nm.)
#
# In the flat earth approximation, distances and bearings are given by the
# usual plane trigonometry formulae, i.e:
#
#    distance = sqrt(distance_North^2 + distance_East^2)
#    bearing to (lat,lon) = mod(atan2(distance_East, distance_North), 2*pi)
#                        (= mod(atan2(cos(lat0)*dlon, dlat), 2*pi) in the spherical case)
#
# These approximations fail in the vicinity of either pole and at large 
# distances. The fractional errors are of order (distance/R)^2.


#import utm
from math import sin, cos, sqrt, radians, degrees
import logging

class Transformation(object):
    """global <-> local coordinate system transformation, using flat earth approximation
       http://williams.best.vwh.net/avform.htm#flat
    """
    def __init__(self, (lon, lat) = (0,0), hdg=0):
        if hdg != 0.:
            logging.error("heading != 0 not yet implemented.")
            raise NotImplemented
        self._lon = lon
        self._lat = lat
        self._update()

    def _update(self):
        """compute radii for local origin"""
        a = 6378137.000 # m for WGS84
        f=1./298.257223563
        e2 = f*(2.-f)

        self._coslat = cos(radians(self._lat))
        sinlat = sin(radians(self._lat))
        self._R1 = a*(1.-e2)/(1.-e2*(sinlat**2))**(3./2.)
        self._R2 = a/sqrt(1-e2*(sinlat)**2)

    def setOrigin(self, (lon, lat)):
        """set origin to given global coordinates (lon, lat)"""
        self._lon, self._lat = lon, lat
        self._update()

    def getOrigin(self):
        """return origin in global coordinates"""
        return self._lat, self._lon

    origin = property(getOrigin, setOrigin)

    def toLocal(self, (lon, lat)):
        """transform global -> local coordinates"""
        y = self._R1 * radians(lat - self._lat)
        x = self._R2 * radians(lon - self._lon) * self._coslat
        return x, y

    def toGlobal(self, (x, y)):
        """transform local -> global coordinates"""
        lat = degrees(y / self._R1) + self._lat
        lon = degrees(x / (self._R2 * self._coslat)) + self._lon
        return lon, lat

    def __str__(self):
        return "(%f %f)" % (self._lon, self._lat)


class Transformation_UTM(object):
    """global <-> local coordinate system transformation, using UTM.
       Likely to fail if local origin is near UTM zone boundary. A point provided
       to toGlobal() could then well be in another UTM zone. Use at your own risk!
    """
    def __init__(self, (lon, lat) = (0,0), hdg=0):
    #def __init__(self, transform, observers, lon, lat, alt=0, hdg=0, pit=0, rol=0):
        if hdg != 0.:
            logging.error("heading != 0 not yet implemented.")
            raise NotImplemented
        self._lon = lon
        self._lat = lat
        self._update()

    def _update(self):
        """get origin in meters"""
        self._easting, self._northing, self._zone_number, self._zone_letter \
            = utm.from_latlon(self._lat, self._lon)

    def toLocal(self, (lon, lat)):
        """transform global -> local coordinates"""
        e, n, zone_number, zone_letter = utm.from_latlon(lat, lon)
        if zone_number != self._zone_number:
            logging.error("Transformation failed: your point is in a different UTM zone! Use another transformation.")

        return e - self._easting, n - self._northing

    def toGlobal(self, (x, y)):
        """transform local -> global coordinates"""
        lat, lon = utm.to_latlon(x + self._easting, y + self._northing, self._zone_number, self._zone_letter)
        return lon, lat

    def __str__(self):
        return "(%f %f)" % (self._lon, self._lat)


if __name__ == "__main__":
    #print utm.from_latlon(51.2, 7.5)
    #>>> (395201.3103811303, 5673135.241182375, 32, 'U')

    #The syntax is utm.from_latlon(LATITUDE, LONGITUDE).

    #The return has the form (EASTING, NORTHING, ZONE NUMBER, ZONE LETTER).

    #Convert an UTM coordinate into a (latitude, longitude) tuple:

    #print utm.to_latlon(340000, 5710000, 32, 'U')
    #>>> (51.51852098408468, 6.693872395145327)

    t = Transformation((0, 0))
    print t.toLocal((0.,0))
    print t.toLocal((1.,0))
    print t.toLocal((0,1.))
    print
    print t.toGlobal((100.,0))
    print t.toGlobal((1000.,0))
    print t.toGlobal((10000.,0))
    print t.toGlobal((100000.,0))
