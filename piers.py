# -*- coding: utf-8 -*-

"""
Ugly, highly experimental code.

Created on Sun Sep 29 10:42:12 2013

@author: Portree Kid
"""
import logging
import math
import os
from random import randint
from typing import List

import numpy as np
import parameters
import shapely.geometry as shg
import tools
from cluster import ClusterContainer
from shapely.geometry.base import CAP_STYLE, JOIN_STYLE
from shapely.geometry.linestring import LineString
from utils import osmparser, coordinates, ac3d, stg_io2
from utils.utilities import FGElev
from utils.vec2d import Vec2d

OUR_MAGIC = "osm2piers"  # Used in e.g. stg files to mark edits by osm2Piers


class Pier(object):
    def __init__(self, transform, osm_id, tags, refs, nodes_dict):
        self.osm_id = osm_id
        self.tags = tags
        self.refs = refs
        self.typ = 0
        self.nodes = []
        self.is_area = 'area' in tags
        self.elevation = 0

        self.osm_nodes = list()
        for r in refs:  # safe way instead of [nodes_dict[r] for r in refs] if ref would be missing
            if r in nodes_dict:
                self.osm_nodes.append(nodes_dict[r])
        self.nodes = np.array([transform.toLocal((n.lon, n.lat)) for n in self.osm_nodes])
        self.anchor = Vec2d(self.nodes[0])

    def calc_elevation(self, fg_elev: FGElev) -> None:
        """Calculates the elevation (level above sea) as a minimum of all nodes.

        Minimum is taken because there could be residuals from shore in FlightGear scenery.
        """
        min_elevation = 99999
        for node in self.nodes:
            node_elev = fg_elev.probe_elev(node)
            node_elev = max(node_elev, -9999)  # Account for elevation probing errors
            min_elevation = min(min_elevation, node_elev)
        self.elevation = min_elevation


def _process_osm_piers(nodes_dict, ways_dict, my_coord_transformator, clipping_border: shg.Polygon) -> List[Pier]:
    my_piers = list()

    for key, way in ways_dict.items():
        if not ('man_made' in way.tags and way.tags['man_made'] == 'pier'):
            continue

        if clipping_border is not None:
            first_node = nodes_dict[way.refs[0]]
            if not clipping_border.contains(shg.Point(first_node.lon, first_node.lat)):
                continue

        pier = Pier(my_coord_transformator, way.osm_id, way.tags, way.refs, nodes_dict)
        my_piers.append(pier)

    return my_piers


def _write_piers(stg_manager, replacement_prefix, clusters):
    for cl in clusters:
        if len(cl.objects) > 0:
            center_tile = Vec2d(tools.transform.toGlobal(cl.center))
            ac_file_name = "%spiers%02i%02i.ac" % (replacement_prefix, cl.grid_index.ix, cl.grid_index.iy)
            ac = ac3d.File(stats=tools.stats)
            obj = ac.new_object('piers', "Textures/Terrain/asphalt.png")
            for pier in cl.objects[:]:
                length = len(pier.nodes)
                if length > 3 \
                        and pier.nodes[0][0] == pier.nodes[(length - 1)][0] \
                        and pier.nodes[0][1] == pier.nodes[(length - 1)][1]:
                    _write_pier_area(pier, obj, cl.center)
                else:
                    _write_pier_line(pier, obj, cl.center)
            path = stg_manager.add_object_static(ac_file_name, center_tile, 0, 0)
            file_name = path + os.sep + ac_file_name
            f = open(file_name, 'w')
            f.write(str(ac))
            f.close()


def _write_boats(stg_manager, piers: List[Pier]):
    for pier in piers:
        length = len(pier.nodes)
        if length > 3 \
                and pier.nodes[0][0] == pier.nodes[(length - 1)][0] \
                and pier.nodes[0][1] == pier.nodes[(length - 1)][1]:
            _write_boat_area(pier, stg_manager)
        else:
            _write_boat_line(pier, stg_manager)


def _write_boat_area(pier, stg_manager):
    if len(pier.nodes) < 3:
        return
    # Guess a possible position for realistic boat placement
    linear_ring = shg.LinearRing(pier.nodes)
    centroid = linear_ring.centroid
    # Simplify
    ring = linear_ring.convex_hull.buffer(40, cap_style=CAP_STYLE.square, join_style=JOIN_STYLE.bevel).simplify(20)
    for p in ring.exterior.coords:
        line_coords = [[centroid.x, centroid.y], p]
        target_vector = shg.LineString(line_coords)
        coords = linear_ring.coords
        for i in range(len(coords) - 1):
            segment = LineString(coords[i:i + 2])
            if segment.length > 20 and segment.intersects(target_vector):
                direction = math.degrees(math.atan2(segment.coords[0][0] - segment.coords[1][0],
                                                    segment.coords[0][1] - segment.coords[1][1]))
                parallel = segment.parallel_offset(10, 'right')
                boat_position = parallel.interpolate(segment.length / 2)
                try:
                    pos_global = tools.transform.toGlobal((boat_position.x, boat_position.y))
                    _write_model(segment.length, stg_manager, pos_global, direction, pier.elevation)
                except AttributeError as reason:
                    logging.error(reason)


def _write_boat_line(pier, stg_manager):
    line_string = LineString(pier.nodes)
    right_line = line_string.parallel_offset(4, 'left', resolution=8, join_style=1, mitre_limit=10.0)
    coords = right_line.coords
    for i in range(len(coords) - 1):
        segment = LineString(coords[i:i + 2])
        boat_position = segment.interpolate(segment.length / 2)
        try:
            pos_global = tools.transform.toGlobal((boat_position.x, boat_position.y))
            direction = math.degrees(math.atan2(segment.coords[0][0] - segment.coords[1][0],
                                                segment.coords[0][1] - segment.coords[1][1]))
            if segment.length > 5:
                _write_model(segment.length, stg_manager, pos_global, direction, pier.elevation)
        except AttributeError as reason:
            logging.error(reason)


def _write_model(length, stg_manager, pos_global, direction, my_elev):
    if length < 20:
        models = [('Models/Maritime/Civilian/wooden_boat.ac', 120),
                  ('Models/Maritime/Civilian/wooden_blue_boat.ac', 120),
                  ('Models/Maritime/Civilian/wooden_green_boat.ac', 120)]
        choice = randint(0, len(models) - 1)
        model = models[choice]
    elif length < 70:
        models = [('Models/Maritime/Civilian/small-red-yacht.ac', 180),
                  ('Models/Maritime/Civilian/small-black-yacht.ac', 180),
                  ('Models/Maritime/Civilian/small-clear-yacht.ac', 180),
                  ('Models/Maritime/Civilian/wide-black-yacht.ac', 180),
                  ('Models/Maritime/Civilian/wide-red-yacht.ac', 180),
                  ('Models/Maritime/Civilian/wide-clear-yacht.ac', 180),
                  ('Models/Maritime/Civilian/blue-sailing-boat-20m.ac', 180),
                  ('Models/Maritime/Civilian/red-sailing-boat.ac', 180),
                  ('Models/Maritime/Civilian/red-sailing-boat-11m.ac', 180),
                  ('Models/Maritime/Civilian/red-sailing-boat-20m.ac', 180)]
        choice = randint(0, len(models) - 1)
        model = models[choice]
    elif length < 250:
        models = [('Models/Maritime/Civilian/MediumFerry.xml', 10)]
        choice = randint(0, len(models) - 1)
        model = models[choice]
    elif length < 400:
        models = [('Models/Maritime/Civilian/LargeTrawler.xml', 10),
                  ('Models/Maritime/Civilian/LargeFerry.xml', 100),
                  ('Models/Maritime/Civilian/barge.xml', 80)]
        choice = randint(0, len(models) - 1)
        model = models[choice]
    else:
        models = [('Models/Maritime/Civilian/SimpleFreighter.ac', 20),
                  ('Models/Maritime/Civilian/FerryBoat1.ac', 70)]
        choice = randint(0, len(models) - 1)
        model = models[choice]
    stg_manager.add_object_shared(model[0], Vec2d(pos_global), my_elev, direction + model[1])


def _write_pier_area(pier, obj, offset):
    """Writes a Pier mapped as an area"""
    linear_ring = shg.LinearRing(pier.nodes)
#         print ring_lat_lon
    # TODO shg.LinearRing().is_ccw
    o = obj.next_node_index()
    if linear_ring.is_ccw:
        logging.info('CounterClockWise')
    else:
        # normalize to CCW
        logging.info("Clockwise")
        pier.nodes = pier.nodes[::-1]
    # top ring
    e = pier.elevation + 1
    for p in pier.nodes:
        obj.node(-p[1] + offset.y, e, -p[0] + offset.x)
    top_nodes = np.arange(len(pier.nodes))
    pier.segment_len = np.array([0] + [Vec2d(coord).distance_to(Vec2d(linear_ring.coords[i])) for i, coord in enumerate(linear_ring.coords[1:])])
    rd_len = len(linear_ring.coords)
    pier.dist = np.zeros((rd_len))
    for i in range(1, rd_len):
        pier.dist[i] = pier.dist[i - 1] + pier.segment_len[i]
    face = []
    x = 0.
    # reversed(list(enumerate(a)))
    # Top Face
    for i, n in enumerate(top_nodes):
        face.append((n + o, x, 0.5))
    obj.face(face, mat=0)
    # Build bottom ring
    e = pier.elevation - 5
    for p in pier.nodes:
        obj.node(-p[1] + offset.y, e, -p[0] + offset.x)
    # Build Sides
    for i, n in enumerate(top_nodes[1:]):
        sideface = list()
        sideface.append((n + o + rd_len - 1, x, 0.5))
        sideface.append((n + o + rd_len, x, 0.5))
        sideface.append((n + o, x, 0.5))
        sideface.append((n + o - 1, x, 0.5))
        obj.face(sideface, mat=0)


def _write_pier_line(pier, obj, offset):
    """Writes a Pier as a area which only is mapped as a line."""
    line_string = shg.LineString(pier.nodes)
    o = obj.next_node_index()
    left = line_string.parallel_offset(1, 'left', resolution=8, join_style=1, mitre_limit=10.0)
    right = line_string.parallel_offset(1, 'right', resolution=8, join_style=1, mitre_limit=10.0)
    idx_left = obj.next_node_index()

    e = pier.elevation + 1
    for p in left.coords:
        obj.node(-p[1] + offset.y, e, -p[0] + offset.x)
    idx_right = obj.next_node_index()
    for p in right.coords:
        obj.node(-p[1] + offset.y, e, -p[0] + offset.x)
    nodes_l = np.arange(len(left.coords))
    nodes_r = np.arange(len(right.coords))
    pier.segment_len = np.array([0] + [Vec2d(coord).distance_to(Vec2d(line_string.coords[i])) for i, coord in enumerate(line_string.coords[1:])])
    rd_len = len(line_string.coords)
    pier.dist = np.zeros((rd_len))
    for i in range(1, rd_len):
        pier.dist[i] = pier.dist[i - 1] + pier.segment_len[i]
    # Top Surface
    face = []
    x = 0.
    for i, n in enumerate(nodes_l):
        face.append((n + o, x, 0.5))
    o += len(left.coords)
    for i, n in enumerate(nodes_r):
        face.append((n + o, x, 0.75))
    obj.face(face[::-1], mat=0)
    # Build bottom left line
    idx_bottom_left = obj.next_node_index()

    e = pier.elevation - 1
    for p in left.coords:
        obj.node(-p[1] + offset.y, e, -p[0] + offset.x)
    # Build bottom right line
    idx_bottom_right = obj.next_node_index()
    for p in right.coords:
        obj.node(-p[1] + offset.y, e, -p[0] + offset.x)
    idx_end = obj.next_node_index() - 1
    # Build Sides
    for i, n in enumerate(nodes_l[1:]):
        # Start with Second point looking back
        sideface = list()
        sideface.append((n + idx_bottom_left, x, 0.5))
        sideface.append((n + idx_bottom_left - 1, x, 0.5))
        sideface.append((n + idx_left - 1, x, 0.5))
        sideface.append((n + idx_left, x, 0.5))
        obj.face(sideface, mat=0)
    for i, n in enumerate(nodes_r[1:]):
        # Start with Second point looking back
        sideface = list()
        sideface.append((n + idx_bottom_right, x, 0.5))
        sideface.append((n + idx_bottom_right - 1, x, 0.5))
        sideface.append((n + idx_right - 1, x, 0.5))
        sideface.append((n + idx_right, x, 0.5))
        obj.face(sideface, mat=0)
    # Build Front&Back
    sideface = list()
    sideface.append((idx_left, x, 0.5))
    sideface.append((idx_bottom_left, x, 0.5))
    sideface.append((idx_end, x, 0.5))
    sideface.append((idx_bottom_left - 1, x, 0.5))
    obj.face(sideface, mat=0)
    sideface = list()
    sideface.append((idx_bottom_right, x, 0.5))
    sideface.append((idx_bottom_right - 1, x, 0.5))
    sideface.append((idx_right - 1, x, 0.5))
    sideface.append((idx_right, x, 0.5))
    obj.face(sideface, mat=0)


def process():
    logging.basicConfig(level=logging.INFO)

    import argparse
    parser = argparse.ArgumentParser(description="piers.py reads OSM data and creates Pier models for use with FlightGear")
    parser.add_argument("-f", "--file", dest="filename",
                        help="read parameters from FILE (e.g. params.ini)", metavar="FILE", required=True)
    parser.add_argument("-l", "--loglevel",
                        help="set loglevel. Valid levels are VERBOSE, DEBUG, INFO, WARNING, ERROR, CRITICAL",
                        required=False)
    args = parser.parse_args()

    if args.filename is not None:
        parameters.read_from_file(args.filename)
    parameters.set_loglevel(args.loglevel)  # -- must go after reading params file

    parameters.show()

    # -- prepare transformation to local coordinates
    cmin, cmax = parameters.get_extent_global()
    center_global = parameters.get_center_global()
    coords_transform = coordinates.Transformation(center_global, hdg=0)
    tools.init(coords_transform)
    
    # -- create (empty) clusters
    lmin = Vec2d(tools.transform.toLocal(cmin))
    lmax = Vec2d(tools.transform.toLocal(cmax))
    clusters = ClusterContainer(lmin, lmax)

    if not parameters.USE_DATABASE:
        osm_way_result = osmparser.fetch_osm_file_data(["man_made", "area"], ["man_made"])
    else:
        osm_way_result = osmparser.fetch_osm_db_data_ways_key_values(["man_made=>pier"])
    osm_nodes_dict = osm_way_result.nodes_dict
    osm_ways_dict = osm_way_result.ways_dict

    clipping_border = None
    if parameters.BOUNDARY_CLIPPING_COMPLETE_WAYS:
        clipping_border = shg.Polygon(parameters.get_clipping_extent(False))

    piers = _process_osm_piers(osm_nodes_dict, osm_ways_dict, coords_transform, clipping_border)
    logging.info("ways: %i", len(piers))
    if len(piers) == 0:
        logging.info("No piers found -> aborting")
        return

    for pier in piers:
        clusters.append(pier.anchor, pier)

    fg_elev = FGElev(coords_transform)
    for pier in piers:
        pier.calc_elevation(fg_elev)

    # -- initialize STGManager
    path_to_output = parameters.get_output_path()
    replacement_prefix = parameters.get_repl_prefix()
    stg_manager = stg_io2.STGManager(path_to_output, OUR_MAGIC, replacement_prefix, overwrite=True)

    _write_piers(stg_manager, replacement_prefix, clusters)
    _write_boats(stg_manager, piers)

    # -- write stg
    stg_manager.write()
    fg_elev.save_cache()

    logging.info("******* Finished *******")


if __name__ == "__main__":
    process()
