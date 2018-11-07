"""Handles reading from apt.dat airport files and read/write to pickle file for minimized representation.
See http://developer.x-plane.com/?article=airport-data-apt-dat-file-format-specification for the specification.

Currently only reading runway data in order to avoid roads/railways to cross a runway.

There is also data available in apt.dat for taxiways an apron, but is not used at current point in time.

Flightgear 2016.4 can read multiple apt.data files - see e.g. http://wiki.flightgear.org/FFGo
and https://sourceforge.net/p/flightgear/flightgear/ci/516a5cf016a7d504b09aaac2e0e66c7e9efd42b2/.
However this module does only support reading from one apt.dat.gz by the user's choice (normally in
$FG_ROOT/Airports/apt.dat.gz).

"""

from abc import ABCMeta, abstractmethod
import gzip
import logging
import math
import os
import time
from typing import List, Optional

from shapely.geometry import CAP_STYLE, LineString, Point, Polygon

from utils import coordinates
from utils import utilities
from utils.vec2d import Vec2d


class AirportBoundary:
    def __init__(self) -> None:
        self.nodes_lists = list()  # a list of list of Nodes, where a Node is a tuple (lon, lat)

    def append_nodes_list(self, nodes_list) -> None:
        self.nodes_lists.append(nodes_list)

    def within_boundary(self, min_lon, min_lat, max_lon, max_lat):
        """If no node within - or there are no nodes - then return False.
        That is ok, because at least the runways will be checked."""
        if len(self.nodes_lists) == 0:
            return False
        for my_list in self.nodes_lists:
            for lon_lat in my_list:
                if (min_lon <= lon_lat[0] <= max_lon) and (min_lat <= lon_lat[1] <= max_lat):
                    return True
        return False

    def create_polygon_buffer(self, transformer: coordinates.Transformation) -> Optional[List[Polygon]]:
        if self.not_empty:
            boundaries = list()
            for my_list in self.nodes_lists:
                my_boundary = Polygon([transformer.to_local(n) for n in my_list])
                if my_boundary.is_valid:
                    boundaries.append(my_boundary)
            return utilities.merge_buffers(boundaries)
        return None

    @property
    def not_empty(self) -> bool:
        if self.nodes_lists:
            return True
        return False


class Runway(metaclass=ABCMeta):
    @abstractmethod
    def within_boundary(self, min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> bool:
        pass

    @abstractmethod
    def create_blocked_area(self, coords_transform: coordinates.Transformation) -> Polygon:
        pass


class LandRunway(Runway):
    def __init__(self, width: float, start: Vec2d, end: Vec2d) -> None:
        self.width = width
        self.start = start  # global coordinates
        self.end = end  # global coordinates

    def within_boundary(self, min_lon, min_lat, max_lon, max_lat):
        if (min_lon <= self.start.x <= max_lon) and (min_lat <= self.start.y <= max_lat):
            return True
        if (min_lon <= self.end.x <= max_lon) and (min_lat <= self.end.y <= max_lat):
            return True
        return False

    def create_blocked_area(self, coords_transform):
        line = LineString([coords_transform.to_local((self.start.x, self.start.y)),
                           coords_transform.to_local((self.end.x, self.end.y))])
        return line.buffer(self.width / 2.0, cap_style=CAP_STYLE.flat)


class Helipad(Runway):
    def __init__(self, length: float, width: float, center: Vec2d) -> None:
        self.length = length
        self.width = width
        self.center = center  # global coordinates

    def within_boundary(self, min_lon, min_lat, max_lon, max_lat):
        if (min_lon <= self.center.x <= max_lon) and (min_lat <= self.center.y <= max_lat):
            return True
        return False

    def create_blocked_area(self, coords_transform):
        my_point = Point(coords_transform.to_local((self.center.x, self.center.y)))
        return my_point.buffer(math.sqrt(self.length + self.width) / 2)


class Airport(object):
    def __init__(self, code: str) -> None:
        self.code = code
        self.runways = list()  # LandRunways, Helipads
        self.airport_boundary = None

    def append_runway(self, runway: Runway) -> None:
        self.runways.append(runway)

    def append_airport_boundary(self, airport_boundary: AirportBoundary) -> None:
        self.airport_boundary = airport_boundary

    def within_boundary(self, min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> bool:
        for runway in self.runways:
            if runway.within_boundary(min_lon, min_lat, max_lon, max_lat):
                return True
        if self.airport_boundary is not None \
                and self.airport_boundary.within_boundary(min_lon, min_lat, max_lon, max_lat):
            return True
        return False

    def create_blocked_areas(self, coords_transform: coordinates.Transformation) -> List[Polygon]:
        blocked_areas = list()
        for runway in self.runways:
            blocked_areas.append(runway.create_blocked_area(coords_transform))
        return blocked_areas

    def create_boundary_polygons(self, coords_transform: coordinates.Transformation) -> Optional[List[Polygon]]:
        if self.airport_boundary is None:
            return None
        else:
            return self.airport_boundary.create_polygon_buffer(coords_transform)


def read_apt_dat_gz_file(min_lon: float, min_lat: float,
                         max_lon: float, max_lat: float) -> List[Airport]:
    apt_dat_gz_file = os.path.join(utilities.get_fg_root(), 'Airports', 'apt.dat.gz')
    start_time = time.time()
    airports = list()
    total_airports = 0
    with gzip.open(apt_dat_gz_file, 'rt', encoding="latin-1") as f:
        my_airport = None
        airport_boundary = None
        current_boundary_nodes = list()
        in_airport_boundary = False
        for line in f:
            parts = line.split()
            if not parts:
                continue
            if in_airport_boundary:
                if parts[0] not in ['111', '112', '113', '114', '115', '116']:
                    in_airport_boundary = False
                else:
                    current_boundary_nodes.append((float(parts[2]), float(parts[1])))
                    if parts[0] in ['113', '114']:  # closed loop
                        airport_boundary.append_nodes_list(current_boundary_nodes)
                        current_boundary_nodes = list()
            if parts[0] in ['1', '16', '17', '99']:
                # first actually append the previously read airport data to the collection if within bounds
                if (my_airport is not None) and (my_airport.within_boundary(min_lon, min_lat, max_lon, max_lat)):
                    airports.append(my_airport)
                # and then create a new empty airport
                if not parts[0] == '99':
                    my_airport = Airport(parts[4])
                    total_airports += 1
            elif parts[0] == '100':
                my_runway = LandRunway(float(parts[1]), Vec2d(float(parts[10]), float(parts[9])),
                                       Vec2d(float(parts[19]), float(parts[18])))
                my_airport.append_runway(my_runway)
            elif parts[0] == '102':
                my_helipad = Helipad(float(parts[5]), float(parts[6]), Vec2d(float(parts[3]), float(parts[2])))
                my_airport.append_runway(my_helipad)
            elif parts[0] == '130':
                airport_boundary = AirportBoundary()
                in_airport_boundary = True
                my_airport.airport_boundary = airport_boundary

    logging.info("Read %d airports, %d having runways/helipads within the boundary", total_airports, len(airports))
    utilities.time_logging("Execution time", start_time)
    return airports


def get_apt_dat_blocked_areas_from_airports(coords_transform: coordinates.Transformation,
                                            min_lon: float, min_lat: float, max_lon: float, max_lat: float,
                                            airports: List[Airport]) -> List[Polygon]:
    """Transforms runways in airports to polygons.
    Even though get_apt_dat_blocked_areas(...) already checks for boundary it is checked here again because if used
    from batch, then first boundary of whole batch area is used - and first then reduced to tile boundary."""
    blocked_areas = list()
    for airport in airports:
        if airport.within_boundary(min_lon, min_lat, max_lon, max_lat):
            blocked_areas.extend(airport.create_blocked_areas(coords_transform))
    return blocked_areas


def get_apt_dat_blocked_areas(coords_transform: coordinates.Transformation,
                              min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> List[Polygon]:
    airports = read_apt_dat_gz_file(min_lon, min_lat, max_lon, max_lat)
    return get_apt_dat_blocked_areas_from_airports(coords_transform, min_lon, min_lat, max_lon, max_lat, airports)
