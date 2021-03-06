import argparse
from enum import IntEnum, unique
import datetime
import logging
import logging.config
import multiprocessing as mp
import os
import sys
import time
import traceback
from typing import List
import unittest

from osm2city import details, pylons, roads, buildings, parameters, trees
from osm2city.owbb import landuse as ol
import osm2city.utils.aptdat_io as aio
import osm2city.utils.btg_io as bio
from osm2city.utils import calc_tile
from osm2city.utils import coordinates
from osm2city.utils import stg_io2
from osm2city.utils import utilities as u


class SceneryTile(object):
    __slots__ = ('boundary_west', 'boundary_south', 'boundary_north', 'boundary_east', 'tile_index', 'prefix')

    def __init__(self, my_boundary_west: float, my_boundary_south: float,
                 my_boundary_east: float, my_boundary_north: float,
                 my_tile_index: int, prefix: str) -> None:
        self.boundary_west = my_boundary_west
        self.boundary_south = my_boundary_south
        self.boundary_east = my_boundary_east
        self.boundary_north = my_boundary_north
        self.tile_index = my_tile_index
        self.prefix = prefix

    def __str__(self) -> str:
        my_string = "Tile index: " + str(self.tile_index)
        my_string += ", prefix: " + self.prefix
        my_string += "; boundary west: " + str(self.boundary_west)
        my_string += " - south: " + str(self.boundary_south)
        my_string += " - east: " + str(self.boundary_east)
        my_string += " - north: " + str(self.boundary_north)
        return my_string


@unique
class Procedures(IntEnum):
    all = 0
    main = 1
    buildings = 2
    roads = 3
    pylons = 4
    details = 5
    trees = 6
    owbb = 10  # only land-use


def _parse_exec_for_procedure(exec_argument: str) -> Procedures:
    """Parses a command line argument to determine which osm2city procedure to run.
    Returns KeyError if mapping cannot be done"""
    return Procedures.__members__[exec_argument.lower()]


class RuntimeFormatter(logging.Formatter):
    """A logging formatter which includes the delta time since start.

    Cf. https://stackoverflow.com/questions/25194864/python-logging-time-since-start-of-program
    """
    def __init__(self, *the_args, **kwargs) -> None:
        super().__init__(*the_args, **kwargs)
        self.start_time = time.time()

    def formatTime(self, record, datefmt=None):
        duration = datetime.datetime.utcfromtimestamp(record.created - self.start_time)
        elapsed = duration.strftime('%H:%M:%S')
        return "{}".format(elapsed)


def configure_time_logging(log_level: str, log_to_file: bool) -> None:
    """Set the logging level and maybe write to file.

    See also accepted answer to https://stackoverflow.com/questions/29015958/how-can-i-prevent-the-inheritance-
    of-python-loggers-and-handlers-during-multipro?noredirect=1&lq=1.
    And: https://docs.python.org/3.5/howto/logging-cookbook.html#logging-to-a-single-file-from-multiple-processes
    """
    log_format = '%(processName)-10s %(name)s -- %(asctime)s - %(levelname)-9s: %(message)s'
    console_handler = logging.StreamHandler()
    fmt = RuntimeFormatter(log_format)
    console_handler.setFormatter(fmt)
    logging.getLogger().addHandler(console_handler)
    logging.getLogger().setLevel(log_level)
    if log_to_file:
        process_name = mp.current_process().name
        if process_name == 'MainProcess':
            file_name = 'osm2city_main_{}.log'.format(u.date_time_now())
        else:
            file_name = 'osm2city_process_{}_{}.log'.format(process_name, u.date_time_now())
        file_handler = logging.FileHandler(filename=file_name)
        file_handler.setFormatter(fmt)
        logging.getLogger().addHandler(file_handler)


def pool_initializer(log_level: str, log_to_file: bool):
    configure_time_logging(log_level, log_to_file)


def process_scenery_tile(scenery_tile: SceneryTile, params_file_name: str,
                         exec_argument: Procedures, my_airports: List[aio.Airport],
                         file_lock: mp.Lock, my_progress: str) -> None:
    my_fg_elev = None
    try:
        parameters.read_from_file(params_file_name)
        # adapt boundary
        parameters.set_boundary(scenery_tile.boundary_west, scenery_tile.boundary_south,
                                scenery_tile.boundary_east, scenery_tile.boundary_north)
        parameters.PREFIX = scenery_tile.prefix
        logging.info("Processing tile {} in prefix {} with process id = {} - {}".format(scenery_tile.tile_index,
                                                                                        parameters.PREFIX,
                                                                                        os.getpid(), my_progress))

        the_coords_transform = coordinates.Transformation(parameters.get_center_global())

        my_fg_elev = u.FGElev(the_coords_transform, scenery_tile.tile_index)
        my_stg_entries = stg_io2.read_stg_entries_in_boundary(the_coords_transform, False)

        # run programs
        if (exec_argument is Procedures.details and parameters.C2P_PROCESS_STREETLAMPS is False) or (
            exec_argument is Procedures.pylons):
            lit_areas = None
            water_areas = None
            osm_buildings = None
        else:
            lit_areas, water_areas, osm_buildings = ol.process(the_coords_transform, my_airports)
        process_built_stuff = True  # only relevant for buildings.py and roads.py. E.g. pylons.py can still run
        if lit_areas is None and water_areas is None and osm_buildings is None:
            process_built_stuff = False
        if exec_argument in [Procedures.buildings, Procedures.main, Procedures.all] and process_built_stuff:
            # cannot be read once for all outside of tiles in main function due to local coordinates
            blocked_apt_areas = aio.get_apt_dat_blocked_areas_from_airports(the_coords_transform,
                                                                            parameters.BOUNDARY_WEST,
                                                                            parameters.BOUNDARY_SOUTH,
                                                                            parameters.BOUNDARY_EAST,
                                                                            parameters.BOUNDARY_NORTH,
                                                                            my_airports, True)
            buildings.process_buildings(the_coords_transform, my_fg_elev, blocked_apt_areas, my_stg_entries,
                                        osm_buildings, file_lock)
        if exec_argument in [Procedures.roads, Procedures.main, Procedures.all] and process_built_stuff:
            blocked_apt_areas = aio.get_apt_dat_blocked_areas_from_airports(the_coords_transform,
                                                                            parameters.BOUNDARY_WEST,
                                                                            parameters.BOUNDARY_SOUTH,
                                                                            parameters.BOUNDARY_EAST,
                                                                            parameters.BOUNDARY_NORTH,
                                                                            my_airports, False)
            blocked_apt_areas.extend(bio.get_blocked_areas_from_btg_airport_data(the_coords_transform, my_airports))
            the_stg_entries = stg_io2.read_stg_entries_in_boundary(the_coords_transform, True)
            roads.process_roads(the_coords_transform, my_fg_elev, blocked_apt_areas, lit_areas, water_areas,
                                the_stg_entries, file_lock)
        if exec_argument in [Procedures.pylons, Procedures.main, Procedures.all] and process_built_stuff:
            pylons.process_pylons(the_coords_transform, my_fg_elev, my_stg_entries, file_lock)
        if exec_argument in [Procedures.details, Procedures.all]:
            details.process_details(the_coords_transform, lit_areas, my_fg_elev, file_lock)
        if exec_argument in [Procedures.trees, Procedures.all]:
            trees.process_trees(the_coords_transform, my_fg_elev, osm_buildings, file_lock)

    except:
        logging.exception('Exception occurred while processing tile {}.'.format(scenery_tile.tile_index))
        msg = "******* Exception in tile {} - to reprocess use boundaries: {}_{}_{}_{} *******".format(
            scenery_tile.tile_index, scenery_tile.boundary_west, scenery_tile.boundary_south,
            scenery_tile.boundary_east, scenery_tile.boundary_north)
        logging.exception(msg)

        with open("osm2city-exceptions.log", "a") as f:
            # print info
            f.write(msg + ' at ' + u.date_time_now() + ' -  ' + os.linesep)
            # print exception
            exc_type, exc_value, exc_traceback = sys.exc_info()
            f.write(''.join(traceback.format_exception(exc_type, exc_value, exc_traceback)))

    finally:
        # clean-up
        if my_fg_elev:
            my_fg_elev.close()

    logging.info("******* Finished tile {} - {} *******".format(scenery_tile.tile_index, my_progress))


counter = 0


def counter_callback() -> None:
    global counter
    counter += 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="build-tiles generates a whole scenery of osm2city objects \
    based on a lon/lat defined area")
    parser.add_argument("-f", "--file", dest="filename",
                        help="Read parameters from FILE (e.g. params.ini)", metavar="FILE", required=True)
    parser.add_argument("-b", "--boundary", dest="boundary",
                        help="set the boundary as WEST_SOUTH_EAST_NORTH like *9.1_47.0_11_48.8 (. as decimal)",
                        required=True)
    parser.add_argument("-p", "--processes", dest="processes", type=int,
                        help="Number of parallel processes (should not be more than number of cores/CPUs)",
                        required=True)
    parser.add_argument('-m', '--maxtasksperchild', dest='max_tasks', type=int,
                        help='The number of tasks a worker process completes before it will exit (default: unlimited)',
                        required=False)
    parser.add_argument("-e", "--execute", dest="exec",
                        help="Execute only the given procedure[s] (buildings, pylons, roads, details, trees, main, " +
                              "owbb, all)",
                        required=False)
    parser.add_argument("-l", "--loglevel", dest="logging_level",
                        help="Set loggging level. Valid levels are DEBUG, INFO (default), WARNING, ERROR, CRITICAL",
                        required=False)
    parser.add_argument('-o', '--logtofile', dest='log_to_file', action='store_true',
                        help='Write the logging output to files in addition to stderr')

    args = parser.parse_args()

    # configure logging
    my_log_level = 'INFO'
    if args.logging_level:
        my_log_level = args.logging_level.upper()
    configure_time_logging(my_log_level, args.log_to_file)

    parameters.read_from_file(args.filename)

    exec_procedure = Procedures.all
    if args.exec:
        try:
            exec_procedure = _parse_exec_for_procedure(args.exec)
        except KeyError:
            logging.error('Cannot parse --execute argument: {}'.format(args.exec))
            sys.exit(1)

    try:
        boundary_floats = u.parse_boundary(args.boundary)
    except u.BoundaryError as be:
        logging.error(be.message)
        sys.exit(1)

    boundary_west = boundary_floats[0]
    boundary_south = boundary_floats[1]
    boundary_east = boundary_floats[2]
    boundary_north = boundary_floats[3]
    logging.info("Overall boundary {}, {}, {}, {}".format(boundary_west, boundary_south, boundary_east, boundary_north))
    u.check_boundary(boundary_west, boundary_south, boundary_east, boundary_north)

    # list of sceneries tiles (might have smaller boundaries). Each entry has a list with the 4 boundary points
    scenery_tiles_list = list()

    # loop west-east and south north on full degrees
    epsilon = 0.00000001  # to make sure that top right boundary not x.0
    for full_lon in range(int(boundary_west) - 1, int(boundary_east - epsilon) + 1):  # -1 for west if negative west
        for full_lat in range(int(boundary_south) - 1, int(boundary_north - epsilon) + 1):
            logging.debug("lon: {}, lat:{}".format(full_lon, full_lat))
            if calc_tile.bucket_span(full_lat) > 1:
                num_lon_parts = 1
            else:
                num_lon_parts = int(1 / calc_tile.bucket_span(full_lat))
            num_lat_parts = 8  # always the same no matter the lon
            for lon_index in range(num_lon_parts):
                for lat_index in range(num_lat_parts):
                    tile_boundary_west = full_lon + lon_index / num_lon_parts
                    tile_boundary_east = full_lon + (lon_index + 1) / num_lon_parts
                    tile_boundary_south = full_lat + lat_index / num_lat_parts
                    tile_boundary_north = full_lat + (lat_index + 1) / num_lat_parts
                    if tile_boundary_east <= boundary_west or tile_boundary_west >= boundary_east:
                        continue
                    if tile_boundary_north <= boundary_south or tile_boundary_south >= boundary_north:
                        continue
                    if boundary_west > tile_boundary_west:
                        tile_boundary_west = boundary_west
                    if tile_boundary_east > boundary_east:
                        tile_boundary_east = boundary_east
                    if boundary_south > tile_boundary_south:
                        tile_boundary_south = boundary_south
                    if tile_boundary_north > boundary_north:
                        tile_boundary_north = boundary_north

                    tile_index = calc_tile.calc_tile_index((tile_boundary_west, tile_boundary_south))
                    tile_prefix = ("%s%s%s" % (calc_tile.directory_name((full_lon, full_lat), '_'), '_', tile_index))
                    a_scenery_tile = SceneryTile(tile_boundary_west, tile_boundary_south,
                                                 tile_boundary_east, tile_boundary_north,
                                                 tile_index, tile_prefix)
                    scenery_tiles_list.append(a_scenery_tile)
                    logging.info("Added new scenery tile: {}".format(a_scenery_tile))

    # get airports from apt_dat. Transformation to blocked areas can only be done in sub-process due to local
    # coordinate system
    airports = aio.read_apt_dat_gz_file(boundary_west, boundary_south,
                                        boundary_east, boundary_north)

    start_time = time.time()
    progress = 1
    total = len(scenery_tiles_list)
    if args.processes > 1:
        mp.set_start_method('spawn')  # use safe approach to make sure e.g. parameters module is initialized separately
        # max tasks per child: see https://docs.python.org/3.5/library/multiprocessing.html#module-multiprocessing.pool
        max_tasks_per_child = None  # the default, meaning a worker processes will live as long as the pool
        if args.max_tasks:
            max_tasks_per_child = args.max_tasks
        pool = mp.Pool(processes=args.processes, maxtasksperchild=max_tasks_per_child,
                       initializer=pool_initializer, initargs=(my_log_level, args.log_to_file))
        the_file_lock = mp.Manager().Lock()  # must be after "set_start_method"
        with pool:
            for my_scenery_tile in scenery_tiles_list:
                progress_str = '{}/{}'.format(progress, total)
                pool.apply_async(process_scenery_tile, (my_scenery_tile, args.filename,
                                                        exec_procedure, airports, the_file_lock, progress_str),
                                 callback=counter_callback())
                progress += 1
            pool.close()
            pool.join()

    else:  # do it linearly, which is easier to debug and profile
        the_file_lock = mp.Manager().Lock()
        for my_scenery_tile in scenery_tiles_list:
            progress_str = '{}/{}'.format(progress, total)
            process_scenery_tile(my_scenery_tile, args.filename,
                                 exec_procedure, airports, the_file_lock, progress_str)
            progress += 1

    u.time_logging("Total time used", start_time)
    logging.info('Processed %i tiles', counter)


# ================ UNITTESTS =======================


class TestProcedures(unittest.TestCase):
    def test_middle_angle(self):
        self.assertTrue(_parse_exec_for_procedure('PyloNs') is Procedures.pylons)
        self.assertRaises(KeyError, _parse_exec_for_procedure, 'Hello')
