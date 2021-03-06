# -*- coding: utf-8 -*-
"""
Transform global (aka geodetic) coordinates to a local cartesian, in meters.
A flat earth approximation (http://williams.best.vwh.net/avform.htm) seems good
enough if distances are up to a few km.

Created on Sat Jun  7 22:38:59 2014
@author: albrecht

# http://williams.best.vwh.net/avform.htm
# Local, flat earth approximation
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

"""

from math import asin, atan2, sin, cos, sqrt, radians, degrees, pi, fabs, floor
import logging
from typing import Tuple
import unittest

import numpy as np
import pyproj
from pyproj.enums import TransformDirection


class Vec2d(object):
    """A simple 2d vector class. Supports basic arithmetics."""

    def __init__(self, x, y=None):
        if y is None:
            if len(x) != 2:
                raise ValueError('Need exactly two values to create Vec2d from list.')
            y = x[1]  # -- Yes, we need to process y first.
            x = x[0]
        self.x = x
        self.y = y

    @property
    def lon(self):
        return self.x

    @lon.setter
    def lon(self, value):
        self.x = value

    @property
    def lat(self):
        return self.y

    @lat.setter
    def lat(self, value):
        self.y = value

    def __getitem__(self, key):
        return (self.x, self.y)[key]

    def __fixtype(self, other):
        if isinstance(other, type(self)):
            return other
        return Vec2d(other, other)

    def __add__(self, other):
        other = self.__fixtype(other)
        return Vec2d(self.x + other.x, self.y + other.y)

    def __sub__(self, other):
        other = self.__fixtype(other)
        return Vec2d(self.x - other.x, self.y - other.y)

    def __mul__(self, other):
        other = self.__fixtype(other)
        return Vec2d(self.x * other.x, self.y * other.y)

    def __floordiv__(self, other):
        other = self.__fixtype(other)
        return Vec2d(self.x // other.x, self.y // other.y)

    def __str__(self):
        return "%1.7f %1.7f" % (self.x, self.y)

    def __neg__(self):
        return Vec2d(-self.x, -self.y)

    def __abs__(self):
        return Vec2d(abs(self.x), abs(self.y))

    def sign(self):
        return Vec2d(np.sign((self.x, self.y)))

    def __lt__(self, other):
        return Vec2d(self.x < other.x, self.y < other.y)

    def list(self):
        print("deprecated call to Vec2d.list(). Iterate instead.")
        return self.x, self.y

    def as_array(self):
        """return as numpy array"""
        return np.array((self.x, self.y))

    def __iter__(self):
        yield (self.x)
        yield (self.y)

    def swap(self):
        return Vec2d(self.y, self.x)

    def int(self):
        return Vec2d(int(self.x), int(self.y))

    def distance_to(self, other):
        d = self - other
        return (d.x ** 2 + d.y ** 2) ** 0.5

    def magnitude(self):
        return (self.x ** 2 + self.y ** 2) ** 0.5

    def normalize(self):
        mag = self.magnitude()
        self.x /= mag
        self.y /= mag

    def rot90ccw(self):
        return Vec2d(-self.y, self.x)

    def atan2(self):
        return atan2(self.y, self.x)


def _convert_wgs_to_utm(lon, lat):
    """Get the EPSG code for a UTM projection based on lon/lat.

    From: https://gis.stackexchange.com/questions/269518/auto-select-suitable-utm-zone-based-on-grid-intersection
    """
    utm_band = str((floor((lon + 180) / 6) % 60) + 1)
    if len(utm_band) == 1:
        utm_band = '0'+utm_band
    if lat >= 0:
        epsg_code = '326' + utm_band
    else:
        epsg_code = '327' + utm_band
    return epsg_code


NAUTICAL_MILES_METERS = 1852

# from WGS84. See simgear/math/SGGeodesy.cxx
EQURAD = 6378137.0
FLATTENING = 298.257223563
SQUASH = 0.9966471893352525192801545

E2 = fabs(1 - SQUASH * SQUASH)
RA2 = 1 / (EQURAD * EQURAD)
E4 = E2 * E2


class Transformation(object):
    """Global <-> local coordinate system transformation, using flat earth approximation

    See explanation in module header. The non-approximations using projections instead of the approximation
    result actually in worse placing of e.g. cables and roads relative to the BTG-stuff and the pylons
    if run near LSME and following e.g. a railroad towards north/tilde edge.


    UTM fails typically if the origin is near an UTM zone boundary.

    The correct approach, though, is probably to do exactly what FG does, and is used in btg_io.py.
    However that projection would then have to be reprojected to cartesian flat somehow.

    See also:
    http://wiki.flightgear.org/Geographic_Coordinate_Systems

    https://projectionwizard.org/ proposes for 1x1 degree large scale maps:
    +proj=tmerc +x_0=500000 +lon_0=-146.5 +k_0=0.9999 +datum=WGS84 +units=m +no_defs
    where -146.5 in this case is the midpoint of -147E/-146E (somewhere in Alaska)

    https://epsg.org
    https://en.wikipedia.org/wiki/Transverse_Mercator_projection
    UTM: https://en.wikipedia.org/wiki/Universal_Transverse_Mercator_coordinate_system
    https://en.wikipedia.org/wiki/Map_projection
    EPSG:4326: https://en.wikipedia.org/wiki/World_Geodetic_System

    """
    def __init__(self, lon_lat=(0, 0), use_approximation: bool = True):
        (lon, lat) = lon_lat
        self._lon = lon
        self._lat = lat
        self.trans_proj = None
        self.approximation = use_approximation
        if self.approximation:
            self._update()
        else:
            out_projection = 'tcea'  # equi-area; tmerc: conformal
            self.trans_proj = pyproj.Transformer.from_crs('EPSG:4326',
                                                          {'proj': out_projection,
                                                           'x_0': '500000.0',
                                                           'lon_0': str(self._lon),
                                                           'lat_0': str(self._lat),
                                                           'k_0': '0.9999',
                                                           'datum': 'WGS84'},
                                                          always_xy=True)
            # utm_code = _convert_wgs_to_utm(self._lon, self._lat)
            # _ = pyproj.Transformer.from_crs('EPSG:4326', 'EPSG:{0}'.format(utm_code), always_xy=True)

    @property
    def anchor(self) -> Vec2d:
        return Vec2d(self._lon, self._lat)

    @property
    def anchor_local(self) -> Vec2d:
        x, y = self.to_local((self._lon, self._lat))
        return Vec2d(x, y)

    @property
    def cos_lat_factor(self) -> float:
        return self._coslat

    def _update(self):
        """compute radii for local origin"""
        f = 1. / FLATTENING
        e2 = f * (2.-f)

        self._coslat = cos(radians(self._lat))
        sinlat = sin(radians(self._lat))
        self._R1 = EQURAD * (1.-e2)/(1.-e2*(sinlat**2))**(3./2.)
        self._R2 = EQURAD / sqrt(1-e2*sinlat**2)

    def to_local(self, coord_tuple: Tuple[float, float]) -> Tuple[float, float]:
        """transform global -> local coordinates"""
        (lon, lat) = coord_tuple
        if self.approximation:
            y = self._R1 * radians(lat - self._lat)
            x = self._R2 * radians(lon - self._lon) * self._coslat
        else:
            x, y = self.trans_proj.transform(lon, lat, radians=False)
        return x, y

    def to_global(self, coord_tuple: Tuple[float, float]) -> Tuple[float, float]:
        """transform local -> global coordinates"""
        (x, y) = coord_tuple
        if self.approximation:
            lat = degrees(y / self._R1) + self._lat
            lon = degrees(x / (self._R2 * self._coslat)) + self._lon
        else:
            lon, lat = self.trans_proj.transform(x, y, radians=False, direction=TransformDirection.INVERSE)
        return lon, lat

    def __str__(self):
        return "(%f %f)" % (self._lon, self._lat)


class Vec3d(object):
    """A simple 3d object"""
    __slots__ = ('x', 'y', 'z')

    def __init__(self, x: float, y: float, z: float) -> None:
        self.x = x  # or lon
        self.y = y  # or lat
        self.z = z  # or height

    @staticmethod
    def dot(first: 'Vec3d', other: 'Vec3d') -> float:
        return first.x * other.x + first.y * other.y + first.z * other.z

    @staticmethod
    def cross(first: 'Vec3d', other: 'Vec3d') -> 'Vec3d':
        # (a1, a2, a3) X (b1, b2, b3) = (a2*b3-a3*b2, a3*b1-a1*b3, a1*b2-a2*b1)
        x = first.y * other.z - first.z * other.y
        y = first.z * other.x - first.x * other.z
        z = first.x * other.y - first.y * other.x
        return Vec3d(x, y, z)

    def multiply(self, multiplier: float) -> None:
        self.x *= multiplier
        self.y *= multiplier
        self.z *= multiplier

    def add(self, other: 'Vec3d') -> None:
        self.x += other.x
        self.y += other.y
        self.z += other.z

    def subtract(self, other: 'Vec3d') -> None:
        self.x -= other.x
        self.y -= other.y
        self.z -= other.z

    def to_local(self, transformer: Transformation) -> None:
        """Translates to local coordinate system."""
        self.x, self.y = transformer.to_local((self.x, self.y))
        # nothing to do for z

    def __copy__(self) -> 'Vec3d':
        return Vec3d(self.x, self.y, self.z)


def cart_to_geod(center: Vec3d) -> Tuple[float, float, float]:
    """Converts a cartesian point to geodetic coordinates. Returns lon, lat in radians and elevation in meters
    See SGGeodesy::SGCartToGeod in simgear/math/SGGeodesy.cxx

    Description in simgear/math/SGGeod.hxx:
    Factory to convert position from a cartesian position assumed to be in wgs84 measured in meters
    Note that this conversion is relatively expensive to compute
    """
    xx_p_yy = center.x * center.x + center.y * center.y
    if xx_p_yy + center.z * center.z < 25.:
        return 0.0, 0.0, -EQURAD

    sqrt_xx_p_yy = sqrt(xx_p_yy)
    p = xx_p_yy * RA2
    q = center.z * center.z * (1 - E2) * RA2
    r = 1 / 6.0 * (p + q - E4)
    s = E4 * p * q / (4 * r * r * r)
    if -2.0 <= s <= 0.0:
        s = 0.0

    t = pow(1 + s + sqrt(s * (2 + s)), 1 / 3.0)
    u = r * (1 + t + 1 / t)
    v = sqrt(u * u + E4 * q)
    w = E2 * (u + v - q) / (2 * v)
    k = sqrt(u + v + w * w) - w
    d = k * sqrt_xx_p_yy / (k + E2)
    lon_rad = 2 * atan2(center.y, center.x + sqrt_xx_p_yy)
    sqrt_dd_p_zz = sqrt(d * d + center.z * center.z)
    lat_rad = 2 * atan2(center.z, d + sqrt_dd_p_zz)
    elev = (k + E2 - 1) * sqrt_dd_p_zz / k
    return lon_rad, lat_rad, elev


def calc_angle_of_line_local(x1: float, y1: float, x2: float, y2: float) -> float:
    """Returns the angle in degrees of a line relative to North.
    Based on local coordinates (x,y) of two points.
    """
    angle = atan2(x2 - x1, y2 - y1)
    degree = degrees(angle)
    return normal_degrees(degree)


def calc_point_angle_away(x: float, y: float, added_distance: float, angle: float) -> Tuple[float, float]:
    new_x = x + added_distance * sin(radians(angle))
    new_y = y + added_distance * cos(radians(angle))
    return new_x, new_y


def calc_point_on_line_local(x1: float, y1: float, x2: float, y2: float, factor: float) -> Tuple[float, float]:
    """Returns the x,y coordinates of a point along the line defined by the input coordinates factor away from first.
    """
    angle = calc_angle_of_line_local(x1, y1, x2, y2)
    length = calc_distance_local(x1, y1, x2, y2) * factor

    x_diff = sin(radians(angle)) * length
    y_diff = cos(radians(angle)) * length
    return x1 + x_diff, y1 + y_diff


def calc_angle_of_corner_local(prev_point_x: float, prev_point_y: float,
                               corner_point_x: float, corner_point_y,
                               next_point_x: float, next_point_y) -> float:
    """The angle seen from the corner looking at the prev_point and then the next point."""
    first_angle = calc_angle_of_line_local(corner_point_x, corner_point_y, prev_point_x, prev_point_y)
    second_angle = calc_angle_of_line_local(corner_point_x, corner_point_y, next_point_x, next_point_y)
    final_angle = fabs(first_angle - second_angle)
    if final_angle > 180:
        final_angle = 360 - final_angle
    return final_angle


def calc_delta_bearing(bearing1: float, bearing2: float) -> float:
    """Calculates the difference between two bearings. If positive with clock, if negative against the clock sense.

    I.e. from bearing1 to bearing2 you need to turn delta with or against the clock."""
    if bearing1 == 360.:
        bearing1 = 0.
    if bearing2 == 360.:
        bearing2 = 0.
    delta = bearing2 - bearing1

    if delta > 180:
        delta = delta - 360
    elif delta < -180:
        delta = 360 + delta

    return delta


def calc_distance_local(x1, y1, x2, y2):
    """Returns the distance between two points based on local coordinates (x,y)."""
    return sqrt(pow(x1 - x2, 2) + pow(y1 - y2, 2))


def calc_distance_global(lon1, lat1, lon2, lat2):
    lon1_r = radians(lon1)
    lat1_r = radians(lat1)
    lon2_r = radians(lon2)
    lat2_r = radians(lat2)
    distance_radians = calc_distance_global_radians(lon1_r, lat1_r, lon2_r, lat2_r)
    return distance_radians * ((180 * 60) / pi) * NAUTICAL_MILES_METERS


def calc_distance_global_radians(lon1_r, lat1_r, lon2_r, lat2_r):
    return 2*asin(sqrt(pow(sin((lat1_r-lat2_r)/2), 2) + cos(lat1_r)*cos(lat2_r)*pow(sin((lon1_r-lon2_r)/2), 2)))


def calc_angle_of_line_global(lon1: float, lat1: float, lon2: float, lat2: float,
                              transformation: Transformation) -> float:
    x1, y1 = transformation.to_local((lon1, lat1))
    x2, y2 = transformation.to_local((lon2, lat2))
    return calc_angle_of_line_local(x1, y1, x2, y2)


def disjoint_bounds(bounds_1: Tuple[float, float, float, float], bounds_2: Tuple[float, float, float, float]) -> bool:
    """Returns True if the two input bounds are disjoint. False otherwise.
    Bounds are Shapely (minx, miny, maxx, maxy) tuples (float values) that bounds the object -> geom.bounds.
    """
    try:
        x_overlap = bounds_1[0] <= bounds_2[0] <= bounds_1[2] or bounds_1[0] <= bounds_2[2] <= bounds_1[2] or \
            bounds_2[0] <= bounds_1[0] <= bounds_2[2] or bounds_2[0] <= bounds_1[2] <= bounds_2[2]
        y_overlap = bounds_1[1] <= bounds_2[1] <= bounds_1[3] or bounds_1[1] <= bounds_2[3] <= bounds_1[3] or \
            bounds_2[1] <= bounds_1[1] <= bounds_2[3] or bounds_2[1] <= bounds_1[3] <= bounds_2[3]
        if x_overlap and y_overlap:
            return False
        return True
    except IndexError:
        logging.exception('Something wrong with the tuples in input')
        logging.warning('bounds_1 has %i values, bounds_2 has %i values', len(bounds_1), len(bounds_2))
        return True


def calc_horizon_elev(distance_1: float, distance_2) -> float:
    """Calculates how much a given pint a distance away is elevated over the round world.
    The distance_1 and distance_2 are right-angled in a cartesian coordinate system."""
    distance_square = distance_1**2 + distance_2**2
    hypotenuse = sqrt(distance_square + EQURAD**2)
    return hypotenuse - EQURAD


def normal_degrees(degree: float) -> float:
    """Makes sure that degrees are between 0 and 360."""
    if degree < 0:
        return degree + 360
    elif degree >= 360:
        return degree - 360
    return degree


# ================ UNITTESTS =======================


class TestCoordinates(unittest.TestCase):
    def test_calc_angle_of_line_local(self):
        self.assertEqual(0, calc_angle_of_line_local(0, 0, 0, 1), "North")
        self.assertEqual(90, calc_angle_of_line_local(0, 0, 1, 0), "East")
        self.assertEqual(180, calc_angle_of_line_local(0, 1, 0, 0), "South")
        self.assertEqual(270, calc_angle_of_line_local(1, 0, 0, 0), "West")
        self.assertEqual(45, calc_angle_of_line_local(0, 0, 1, 1), "North East")
        self.assertEqual(315, calc_angle_of_line_local(1, 0, 0, 1), "North West")
        self.assertEqual(225, calc_angle_of_line_local(1, 1, 0, 0), "South West")

    def test_calc_angle_of_line_global(self):
        trans = Transformation()
        self.assertAlmostEqual(0, calc_angle_of_line_global(1, 46, 1, 47, trans), delta=0.5)  # "North"
        self.assertAlmostEqual(90, calc_angle_of_line_global(1, -46, 2, -46, trans), delta=0.5)  # "East"
        self.assertAlmostEqual(180, calc_angle_of_line_global(-1, -33, -1, -34, trans), delta=0.5)  # "South"
        self.assertAlmostEqual(270, calc_angle_of_line_global(-29, 20, -30, 20, trans), delta=0.5)  # "West"
        self.assertAlmostEqual(45, calc_angle_of_line_global(0, 0, 1, 1, trans), delta=0.5)  # "North East"
        self.assertAlmostEqual(315, calc_angle_of_line_global(1, 0, 0, 1, trans), delta=0.5)  # "North West"
        self.assertAlmostEqual(225, calc_angle_of_line_global(1, 1, 0, 0, trans), delta=0.5)  # "South West"

    def test_calc_distance_local(self):
        self.assertEqual(5, calc_distance_local(0, -1, -4, 2))

    def test_calc_distance_global(self):
        self.assertAlmostEqual(NAUTICAL_MILES_METERS * 60, calc_distance_global(1, 46, 1, 47), delta=10)
        self.assertAlmostEqual(NAUTICAL_MILES_METERS * 60, calc_distance_global(1, -33, 1, -34), delta=10)
        self.assertAlmostEqual(NAUTICAL_MILES_METERS * 60, calc_distance_global(1, 0, 2, 0), delta=10)
        self.assertAlmostEqual(NAUTICAL_MILES_METERS * 60 * sqrt(2), calc_distance_global(1, 0, 2, 1), delta=10)

    def test_disjoint_bounds(self):
        bounds_1 = (0, 0, 10, 10)
        bounds_2 = (2, 2, 8, 8)
        self.assertFalse(disjoint_bounds(bounds_1, bounds_2), 'Within 1-2')
        self.assertFalse(disjoint_bounds(bounds_2, bounds_1), 'Within 2-1')

        bounds_2 = (10, 10, 20, 20)
        self.assertFalse(disjoint_bounds(bounds_1, bounds_2), 'Touch 1-2')
        self.assertFalse(disjoint_bounds(bounds_2, bounds_1), 'Touch 2-1')

        bounds_2 = (0, 20, 20, 30)
        self.assertTrue(disjoint_bounds(bounds_1, bounds_2), 'Disjoint 1-2')
        self.assertTrue(disjoint_bounds(bounds_2, bounds_1), 'Disjoint 2-1')

    def test_calc_angle_of_corner_local(self):
        self.assertAlmostEqual(180, calc_angle_of_corner_local(-1, 0, 0, 0, 1, 0), 2)
        self.assertAlmostEqual(180, calc_angle_of_corner_local(1, 0, 0, 0, -1, 0), 2)

        self.assertAlmostEqual(90, calc_angle_of_corner_local(1, 0, 0, 0, 0, 1), 2)
        self.assertAlmostEqual(90, calc_angle_of_corner_local(0, 1, 0, 0, 1, 0), 2)

        self.assertAlmostEqual(90, calc_angle_of_corner_local(1, 0, 0, 0, 0, -1), 2)
        self.assertAlmostEqual(90, calc_angle_of_corner_local(0, -1, 0, 0, 1, 0), 2)

        self.assertAlmostEqual(45, calc_angle_of_corner_local(1, 0, 0, 0, 1, 1), 2)
        self.assertAlmostEqual(45, calc_angle_of_corner_local(1, 1, 0, 0, 1, 0), 2)

        self.assertAlmostEqual(135, calc_angle_of_corner_local(-1, 0, 0, 0, 1, 1), 2)
        self.assertAlmostEqual(135, calc_angle_of_corner_local(1, 1, 0, 0, -1, 0), 2)

        self.assertAlmostEqual(45, calc_angle_of_corner_local(-1, 1, 0, 0, 0, 1), 2)
        self.assertAlmostEqual(45, calc_angle_of_corner_local(-1, 1, 0, 0, -1, 0), 2)

    def test_calc_delta_bearing(self):
        bearing1 = 0.
        bearing2 = 0.
        self.assertEqual(0., calc_delta_bearing(bearing1, bearing2), 'No difference 0')

        bearing1 = 0.
        bearing2 = 360.
        self.assertEqual(0., calc_delta_bearing(bearing1, bearing2), 'No difference 0/360')

        bearing1 = 360.
        bearing2 = 0.
        self.assertEqual(0., calc_delta_bearing(bearing1, bearing2), 'No difference 360/0')

        bearing1 = 20
        bearing2 = 200
        self.assertEqual(180., fabs(calc_delta_bearing(bearing1, bearing2)), '180 degrees')

        bearing1 = 10
        bearing2 = 20
        self.assertEqual(10., calc_delta_bearing(bearing1, bearing2), '10 with clock')

        bearing1 = 20
        bearing2 = 10
        self.assertEqual(-10., calc_delta_bearing(bearing1, bearing2), '10 against clock')

        bearing1 = 350
        bearing2 = 10
        self.assertEqual(20., calc_delta_bearing(bearing1, bearing2), 'Through 0: 20 with clock')

        bearing1 = 10
        bearing2 = 350
        self.assertEqual(-20., calc_delta_bearing(bearing1, bearing2), 'Through 0: 20 against clock')

    def test_calc_point_on_line_local(self):
        # straight up
        x, y = calc_point_on_line_local(0, 1, 0, 2, 0.5)
        self.assertAlmostEqual(0., x)
        self.assertAlmostEqual(1.5, y)
        x, y = calc_point_on_line_local(0, 1, 0, 2, 2.0)
        self.assertAlmostEqual(0., x)
        self.assertAlmostEqual(3., y)
        # straight down
        x, y = calc_point_on_line_local(1, -1, 1, -2, 0.5)
        self.assertAlmostEqual(1., x)
        self.assertAlmostEqual(-1.5, y)
        # straight right
        x, y = calc_point_on_line_local(1, -1, 2, -1, 0.5)
        self.assertAlmostEqual(1.5, x)
        self.assertAlmostEqual(-1., y)
        # straight left
        x, y = calc_point_on_line_local(-1, 1, -2, 1, 0.5)
        self.assertAlmostEqual(-1.5, x)
        self.assertAlmostEqual(1, y)
        # 45 degrees
        x, y = calc_point_on_line_local(1, 1, 2, 2, 2.)
        self.assertAlmostEqual(3., x)
        self.assertAlmostEqual(3., y)
        # straight right with negative value
        x, y = calc_point_on_line_local(1, -1, 2, -1, -1)
        self.assertAlmostEqual(0, x)
        self.assertAlmostEqual(-1., y)

    def test_calc_horizon_elev(self):
        elev_1 = calc_horizon_elev(2000, 2000)
        elev_2 = calc_horizon_elev(2000, 0)
        self.assertGreater(elev_1, elev_2)


if __name__ == '__main__':
    my_lon = 24
    my_lat = 70
    centre = (my_lon + 0.125, my_lat + 0.125)
    approx_trans = Transformation(centre, True)
    real_trans = Transformation(centre, False)
    for trans in [approx_trans, real_trans]:
        lon_lat_1 = (my_lon, my_lat)
        x_y_1 = trans.to_local(lon_lat_1)
        print('1', x_y_1)
        lon_lat_2 = (my_lon, my_lat + 0.25)
        x_y_2 = trans.to_local(lon_lat_2)
        print('2', x_y_2)
        dist = calc_distance_local(x_y_1[0], x_y_1[1], x_y_2[0], x_y_2[1])
        print('Dist 1->2:', dist)
        lon_lat_3 = (my_lon + 0.25, my_lat)
        x_y_3 = trans.to_local(lon_lat_3)
        print('3', x_y_3)
        dist = calc_distance_local(x_y_1[0], x_y_1[1], x_y_3[0], x_y_3[1])
        print('Dist 1->3:', dist)
        lon_lat_back = trans.to_global(x_y_3)
        print('3 back', lon_lat_back)
