#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
TODO:
* what to do if another valid land-use is intersecting or within another land-use
* link places to land-uses and use in logic
"""
import argparse
import logging
import math
import os
import unittest
import xml.sax

from shapely import affinity
from shapely.geometry import box
from shapely.geometry import LineString
from shapely.geometry import MultiLineString
from shapely.geometry import Point
from shapely.geometry import Polygon

import vec2d
import calc_tile
import coordinates
# import osm2pylon
import osmparser
import osmparser_wrapper
import parameters
import stg_io2


def process_osm_building_refs(nodes_dict, ways_dict, my_coord_transformator):
    my_buildings = {}  # osm_id as key, Polygon
    for way in ways_dict.values():
        for key in way.tags:
            if "building" == key:
                coordinates = []
                for ref in way.refs:
                    if ref in nodes_dict:
                        my_node = nodes_dict[ref]
                        coordinates.append(my_coord_transformator.toLocal((my_node.lon, my_node.lat)))
                if 2 < len(coordinates):
                    my_polygon = Polygon(coordinates)
                    if my_polygon.is_valid and not my_polygon.is_empty:
                        my_buildings[way.osm_id] = my_polygon.convex_hull
    return my_buildings


class LinearOSMFeature(object):
    def __init__(self, osm_id):
        self.osm_id = osm_id
        self.type_ = 0
        self.linear = None  # The LinearString of the line

    def get_width(self):
        """The width incl. border as a float in meters"""
        raise NotImplementedError("Please implement this method")


class Highway(LinearOSMFeature):
    TYPE_MOTORWAY = 11
    TYPE_TRUNK = 12
    TYPE_PRIMARY = 13
    TYPE_SECONDARY = 14
    TYPE_TERTIARY = 15
    TYPE_UNCLASSIFIED = 16
    TYPE_ROAD = 17
    TYPE_RESIDENTIAL = 18
    TYPE_LIVING_STREET = 19
    TYPE_SERVICE = 20
    TYPE_PEDESTRIAN = 21
    TYPE_SLOW = 30  # cycle ways, tracks, footpaths etc

    def __init__(self, osm_id):
        super(Highway, self).__init__(osm_id)
        self.is_roundabout = False

    def get_width(self):  # FIXME: replace with parameters and a bit of logic including number of lanes
        my_width = 3.0  # TYPE_SLOW
        if self.type_ in [Highway.TYPE_SERVICE, Highway.TYPE_RESIDENTIAL, Highway.TYPE_LIVING_STREET
                          , Highway.TYPE_PEDESTRIAN]:
            my_width = 5.0
        elif self.type_ in [Highway.TYPE_ROAD, Highway.TYPE_UNCLASSIFIED, Highway.TYPE_TERTIARY]:
            my_width = 6.0
        elif self.type_ in [Highway.TYPE_SECONDARY, Highway.TYPE_PRIMARY, Highway.TYPE_TRUNK]:
            my_width = 7.0
        else:  # MOTORWAY
            my_width = 14.0
        return my_width

    def populate_buildings_along(self):
        """Whether or not the highway determines were buildings are built. E.g. motorway would be false"""
        if self.type_ in (Highway.TYPE_MOTORWAY, Highway.TYPE_TRUNK):
            return False
        return True


def process_osm_highway(nodes_dict, ways_dict, my_coord_transformator):
    my_highways = {}  # osm_id as key, Highway

    for way in ways_dict.values():
        my_highway = Highway(way.osm_id)
        valid_highway = False
        is_challenged = False
        for key in way.tags:
            value = way.tags[key]
            if "highway" == key:
                valid_highway = True
                if value in ["motorway", "motorway_link"]:
                    my_highway.type_ = Highway.TYPE_MOTORWAY
                elif value in ["trunk", "trunk_link"]:
                    my_highway.type_ = Highway.TYPE_TRUNK
                elif value in ["primary", "primary_link"]:
                    my_highway.type_ = Highway.TYPE_PRIMARY
                elif value in ["secondary", "secondary_link"]:
                    my_highway.type_ = Highway.TYPE_SECONDARY
                elif value in ["tertiary", "tertiary_link"]:
                    my_highway.type_ = Highway.TYPE_TERTIARY
                elif value == "unclassified":
                    my_highway.type_ = Highway.TYPE_UNCLASSIFIED
                elif value == "road":
                    my_highway.type_ = Highway.TYPE_ROAD
                elif value == "residential":
                    my_highway.type_ = Highway.TYPE_RESIDENTIAL
                elif value == "living_street":
                    my_highway.type_ = Highway.TYPE_LIVING_STREET
                elif value == "service":
                    my_highway.type_ = Highway.TYPE_SERVICE
                elif value == "pedestrian":
                    my_highway.type_ = Highway.TYPE_PEDESTRIAN
                elif value in ["tack", "footway", "cycleway", "bridleway", "steps", "path"]:
                    my_highway.type_ = Highway.TYPE_SLOW
                else:
                    valid_highway = False
            elif ("tunnel" == key) and ("yes" == value):
                is_challenged = True
            elif ("junction" == key) and ("roundabout" == value):
                my_highway.is_roundabout = True
        if valid_highway and not is_challenged:
            # Process the Nodes
            my_coordinates = []
            for ref in way.refs:
                if ref in nodes_dict:
                    my_node = nodes_dict[ref]
                    x, y = my_coord_transformator.toLocal((my_node.lon, my_node.lat))
                    my_coordinates.append((x, y))
            if len(my_coordinates) >= 2:
                my_highway.linear = LineString(my_coordinates)
                my_highways[my_highway.osm_id] = my_highway

    return my_highways


class Railway(LinearOSMFeature):
    """FIXME: should be merged with osm2pylon.Railway"""

    def __init__(self, osm_id):
        super(Railway, self).__init__(osm_id)

    def get_width(self):  # FIXME: replace with parameters and a bit of logic
        return 6.0


def process_osm_railway(nodes_dict, ways_dict, my_coord_transformator):
    my_railways = {}  # osm_id as key, Railway as value

    for way in ways_dict.values():
        valid_railway = False
        is_challenged = False
        my_railway = Railway(way.osm_id)
        for key in way.tags:
            value = way.tags[key]
            if "railway" == key:
                if value in ["abandoned", "construction", "disused", "funicular", "light_rail", "monorail"
                             , "narrow_gauge", "preserved", "rail", "subway"]:
                    valid_railway = True
            elif ("tunnel" == key) and ("yes" == value):
                is_challenged = True
        if valid_railway and not is_challenged:
            # Process the Nodes
            my_coordinates = []
            for ref in way.refs:
                if ref in nodes_dict:
                    my_node = nodes_dict[ref]
                    x, y = my_coord_transformator.toLocal((my_node.lon, my_node.lat))
                    my_coordinates.append((x, y))
            if len(my_coordinates) >= 2:
                my_railway.linear = LineString(my_coordinates)
                my_railways[way.osm_id] = my_railway

    return my_railways


class Waterway(LinearOSMFeature):
    TYPE_LARGE = 10
    TYPE_NARROW = 20

    def __init__(self, osm_id):
        super(Waterway, self).__init__(osm_id)

    def get_width(self):  # FIXME: replace with parameters
        if self.type_ == Waterway.TYPE_LARGE:
            return 15.0
        return 5.0


def process_osm_waterway(nodes_dict, ways_dict, my_coord_transformator):
    my_waterways = {}  # osm_id as key, Waterway as value

    for way in ways_dict.values():
        my_waterway = Waterway(way.osm_id)
        valid_waterway = False
        is_challenged = False
        for key in way.tags:
            value = way.tags[key]
            if "waterway" == key:
                if value in ["river", "canal"]:
                    valid_waterway = True
                    my_waterway.type_ = Waterway.TYPE_LARGE
                elif value in ["stream", "wadi", "drain", "ditch"]:
                    valid_waterway = True
                    my_waterway.type_ = Waterway.TYPE_NARROW
            elif ("tunnel" == key) and ("culvert" == value):
                is_challenged = True
        if valid_waterway and not is_challenged:
            # Process the Nodes
            my_coordinates = []
            for ref in way.refs:
                if ref in nodes_dict:
                    my_node = nodes_dict[ref]
                    x, y = my_coord_transformator.toLocal((my_node.lon, my_node.lat))
                    my_coordinates.append((x, y))
            if len(my_coordinates) >= 2:
                my_waterway.linear = LineString(my_coordinates)
                my_waterways[way.osm_id] = my_waterway

    return my_waterways


class GenBuilding(object):
    """An object representing a generated non-OSM building"""
    max_id = 0

    TYPE_HOUSE = 10

    def __init__(self, building_type, highway_width):
        self.gen_id = GenBuilding._next_gen_id()
        self.type_ = building_type
        self.width = 10  # FIXME: hard-coded
        self.depth = 7  # FIXME: hard-coded
        self.ideal_buffer_front = 5  # FIXME: hard-coded
        # takes into account that ideal buffer_front is challenged in curve
        self.min_buffer_front = 3  # FIXME: hard-coded,
        self.buffer_back = 5  # FIXME: hard-coded
        self.buffer_side = 5  # FIXME: hard-coded
        self.area_polygon = None  # A polygon representing only the building, not the buffer around
        self.buffer_polygon = None  # A polygon representing the building incl. front/back/side buffers
        self._create_area_polygons(highway_width)
        # below location attributes are set after population
        self.x = 0  # the x coordinate of the mid-point in relation to the local coordinate system
        self.y = 0  # the y coordinate of the mid-point in relation to the local coordinate system
        self.angle = 0  # the angle in degrees from North (y-axis) in the local coordinate system for the building's
                        # static object local x-axis

    @staticmethod
    def _next_gen_id():
        GenBuilding.max_id += 1
        return GenBuilding.max_id

    def _create_area_polygons(self, highway_width):
        """Creates polygons at (0,0) and no angle"""
        self.buffer_polygon = box(-1*(self.width/2 + self.buffer_side)
                                  , highway_width/2 + (self.ideal_buffer_front - self.min_buffer_front)
                                  , self.width/2 + self.buffer_side
                                  , highway_width/2 + self.ideal_buffer_front + self.depth + self.buffer_back)
        self.area_polygon = box(-1*(self.width/2)
                                , highway_width/2 + self.ideal_buffer_front
                                , self.width/2
                                , highway_width/2 + self.ideal_buffer_front + self.depth)

    def get_area_polygon(self, has_buffer, highway_point, highway_angle):
        """
        Create a polygon for the building and place it in relation to the point and angle of the highway.
        """
        if has_buffer:
            my_box = self.buffer_polygon
        else:
            my_box = self.area_polygon
        rotated_box = affinity.rotate(my_box, -1 * (90 + highway_angle), (0, 0))  # plus 90 degrees because right side of
                                                                          # street along; -1 to go clockwise
        return affinity.translate(rotated_box, highway_point.x, highway_point.y)

    def set_location(self, point_on_line, angle, area_polygon, buffer_polygon):
        # FIXME: calculate x, y and angle based on parameters plus self.buffer_*
        self.area_polygon = area_polygon
        self.buffer_polygon = buffer_polygon


class Landuse(object):
    TYPE_COMMERCIAL = 10
    TYPE_INDUSTRIAL = 20
    TYPE_RESIDENTIAL = 30
    TYPE_RETAIL = 40
    TYPE_NON_OSM = 50  # used for land-uses constructed with heuristics and not in original data from OSM

    def __init__(self, osm_id):
        self.osm_id = osm_id
        self.type_ = 0
        self.polygon = None  # the polygon defining its outer boundary
        self.number_of_buildings = 0  # only set for generated TYPE_NON_OSM land-uses during generation
        self.linked_blocked_areas = []  # List of Polygon objects for blocked areas. E.g.
                                          # open-space, existing building, static objects, *-buffers
        self.generated_buildings = []  # List og GenBuilding objects for generated non-osm buildings along the highways


class Place(object):
    """ Cf. http://wiki.openstreetmap.org/wiki/Key:place"""
    TYPE_CITY = 10
    TYPE_BOROUGH = 11
    TYPE_SUBURB = 12
    TYPE_QUARTER = 13
    TYPE_NEIGHBOURHOOD = 14
    TYPE_CITY_BLOCK = 15
    TYPE_TOWN = 20
    TYPE_VILLAGE = 30
    TYPE_HAMLET = 40

    def __init__(self, osm_id, is_node):
        self.osm_id = osm_id
        self.is_node = is_node  # A Place in OSM can either be a node or a way
        self.type_ = 0
        self.polygon = None
        self.point = None
        self.population = -1  # based on OSM population tag


def process_osm_place_refs(nodes_dict, ways_dict, my_coord_transformator):
    my_places = {}  # osm_id as key, Place as value

    # First get all Places from OSM ways
    for way in ways_dict.values():
        my_type, my_population = _parse_place_tags(way.tags)
        if my_type > 0:
            my_place = Place(way.osm_id, False)
            if my_population > 0:
                my_place.population = my_population

            # Process the Nodes
            my_coordinates = []
            for ref in way.refs:
                if ref in nodes_dict:
                    my_node = nodes_dict[ref]
                    x, y = my_coord_transformator.toLocal((my_node.lon, my_node.lat))
                    my_coordinates.append((x, y))
            if len(my_coordinates) >= 3:
                my_place.polygon = Polygon(my_coordinates)
                if my_place.polygon.is_valid and not my_place.polygon.is_empty:
                    my_places[my_place.osm_id] = my_place
    logging.debug("OSM places of type polygon found: %s", len(my_places))

    # Get the Places from OSM nodes
    for node in nodes_dict.values():
        my_type, my_population = _parse_place_tags(node.tags)
        if my_type > 0:
            my_place = Place(node.osm_id, True)
            if my_population > 0:
                my_place.population = my_population
            x, y = my_coord_transformator.toLocal((node.lon, node.lat))
            my_place.point = Point(x, y)
            my_places[my_place.osm_id] = my_place

    logging.debug("Total OSM places (points and polygons) found: %s", len(my_places))
    return my_places


def _parse_place_tags(tags_dict):
    """Parses OSM tags for Places"""
    my_type = 0
    my_population = 0
    for key in tags_dict:
        value = tags_dict[key]
        if "place" == key:
            if value == "city":
                my_type = Place.TYPE_CITY
            elif value == "borough":
                my_type = Place.TYPE_BOROUGH
            elif value == "suburb":
                my_type = Place.TYPE_SUBURB
            elif value == "quarter":
                my_type = Place.TYPE_QUARTER
            elif value == "neighbourhood":
                my_type = Place.TYPE_NEIGHBOURHOOD
            elif value == "city_block":
                my_type = Place.TYPE_CITY_BLOCK
            elif value == "town":
                my_type = Place.TYPE_TOWN
            elif value == "village":
                my_type = Place.TYPE_VILLAGE
            elif value == "hamlet":
                my_type = Place.TYPE_HAMLET
        if ("population" == key) and osmparser.is_parsable_int(value):
            my_population = int(value)
    return my_type, my_population


def process_osm_landuse_refs(nodes_dict, ways_dict, my_coord_transformator):
    my_landuses = {}  # osm_id as key, Landuse as value

    for way in ways_dict.values():
        my_landuse = Landuse(way.osm_id)
        valid_landuse = True
        for key in way.tags:
            value = way.tags[key]
            if "landuse" == key:
                if value == "commercial":
                    my_landuse.type_ = Landuse.TYPE_COMMERCIAL
                elif value == "industrial":
                    my_landuse.type_ = Landuse.TYPE_INDUSTRIAL
                elif value == "residential":
                    my_landuse.type_ = Landuse.TYPE_RESIDENTIAL
                elif value == "retail":
                    my_landuse.type_ = Landuse.TYPE_RETAIL
                else:
                    valid_landuse = False
            else:
                valid_landuse = False
        if valid_landuse:
            # Process the Nodes
            my_coordinates = []
            for ref in way.refs:
                if ref in nodes_dict:
                    my_node = nodes_dict[ref]
                    x, y = my_coord_transformator.toLocal((my_node.lon, my_node.lat))
                    my_coordinates.append((x, y))
            if len(my_coordinates) >= 3:
                my_landuse.polygon = Polygon(my_coordinates)
                if my_landuse.polygon.is_valid and not my_landuse.polygon.is_empty:
                    my_landuses[my_landuse.osm_id] = my_landuse

    logging.debug("OSM land-uses found: %s", len(my_landuses))
    return my_landuses


def generate_landuse_from_buildings(osm_landuses, building_refs):
    """Adds "missing" landuses based on building clusters"""
    my_landuse_candidates = {}
    index = 10000000000
    for my_building in building_refs.values():
        # check whether the building already is in a land use
        within_existing_landuse = False
        for osm_landuse in osm_landuses.values():
            if my_building.intersects(osm_landuse.polygon):
                within_existing_landuse = True
                break
        if not within_existing_landuse:
            # create new clusters of land uses
            buffer_distance = parameters.LU_LANDUSE_BUILDING_BUFFER_DISTANCE
            if my_building.area > parameters.LU_LANDUSE_BUILDING_BUFFER_DISTANCE**2:
                factor = math.sqrt(my_building.area / parameters.LU_LANDUSE_BUILDING_BUFFER_DISTANCE**2)
                buffer_distance = min(factor*parameters.LU_LANDUSE_BUILDING_BUFFER_DISTANCE
                                      , parameters.LU_LANDUSE_BUILDING_BUFFER_DISTANCE_MAX)
            buffer_polygon = my_building.buffer(buffer_distance)
            buffer_polygon = buffer_polygon
            within_existing_landuse = False
            for candidate in my_landuse_candidates.values():
                if buffer_polygon.intersects(candidate.polygon):
                    candidate.polygon = candidate.polygon.union(buffer_polygon)
                    candidate.number_of_buildings += 1
                    within_existing_landuse = True
                    break
            if not within_existing_landuse:
                index += 1
                my_candidate = Landuse(index)
                my_candidate.polygon = buffer_polygon
                my_candidate.number_of_buildings = 1
                my_candidate.type_ = Landuse.TYPE_NON_OSM
                my_landuse_candidates[my_candidate.osm_id] = my_candidate
    # add landuse candidates to landuses
    logging.debug("Candidate land-uses found: %s", len(my_landuse_candidates))
    for candidate in my_landuse_candidates.values():
        if candidate.polygon.area < parameters.LU_LANDUSE_MIN_AREA:
            del my_landuse_candidates[candidate.osm_id]
    logging.debug("Candidate land-uses with sufficient area found: %s", len(my_landuse_candidates))

    return my_landuse_candidates


def process_osm_openspaces_refs(nodes_dict, ways_dict, my_coord_transformator):
    """Parses OSM way input for areas, where there would be open space with no buildings"""
    my_areas = {}  # osm_id as key, Polygon as value

    for way in ways_dict.values():
        valid_area = False
        is_building = False
        has_pedestrian = False
        is_area = False
        for key in way.tags:
            value = way.tags[key]
            if "building" == key:
                is_building = True
                break
            elif "parking" == key and "multi-storey" == value:
                is_building = True
                break
            elif "landuse" == key:
                if value not in ["commercial", "industrial", "residential", "retail"]:  # must be in sync with Landuse
                    valid_area = True
            elif "amenity" == key:
                if value in ["grave_yard", "parking"]:
                    valid_area = True
            elif key in ["leisure", "natural", "public_transport"]:
                valid_area = True
            elif "highway" == key:
                if "pedestrian" == value:
                    has_pedestrian = True
            elif "area" == key:
                if "yes" == value:
                    is_area = True
        if has_pedestrian and is_area:  # pedestrian street or place
            valid_area = True
        if valid_area and not is_building:
            # Process the Nodes
            my_coordinates = []
            for ref in way.refs:
                if ref in nodes_dict:
                    my_node = nodes_dict[ref]
                    x, y = my_coord_transformator.toLocal((my_node.lon, my_node.lat))
                    my_coordinates.append((x, y))
            if len(my_coordinates) >= 3:
                my_poly = Polygon(my_coordinates)
                if my_poly.is_valid and not my_poly.is_empty:
                    my_areas[way.osm_id] = my_poly

    logging.debug("OSM open spaces found: %s", len(my_areas))
    return my_areas


def parse_ac_file_name(xml_string):
    """Finds the corresponding ac-file in an xml-file"""
    try:
        x1 = xml_string.index("<path>")
        x2 = xml_string.index("</path>", x1)
    except ValueError as e:
        raise e
    ac_file_name = (xml_string[x1+6:x2]).strip()
    return ac_file_name


def extract_boundary(ac_filename):
    """Reads an ac-file and finds a box of minimum and maximum x/z values as a proxy to the real boundary.
    No attempt is made to follow rotations and translations.
    Returns a tuple (x_min, y_min, x_max, y_max) in meters."""
    x_min = 100000
    y_min = 100000
    x_max = -100000
    y_max = -100000
    numvert = 0
    try:
        with open(ac_filename, 'r') as my_file:
            for my_line in my_file:
                if 0 == my_line.find("numvert"):
                    numvert = int(my_line.split()[1])
                elif numvert > 0:
                    vertex_values = my_line.split()
                    x_min = min(x_min, float(vertex_values[0]))
                    x_max = max(x_max, float(vertex_values[0]))
                    y_min = min(y_min, float(vertex_values[2]))
                    y_max = max(y_max, float(vertex_values[2]))
                    numvert -= 1
    except IOError as e:
        raise e
    return x_min, y_min, x_max, y_max


def create_static_obj_boxes(my_coord_transformator):
    """
    Finds all static objects referenced in stg-files within the scenery boundaries and returns them as a list of
    Shapely box geometries in the local x/y coordinate system
    """
    static_obj_boxes = []
    stg_files = calc_tile.get_stg_files_in_boundary(parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH
                                                    , parameters.BOUNDARY_EAST, parameters.BOUNDARY_NORTH
                                                    , parameters.PATH_TO_SCENERY)
    for filename in stg_files:
        # find referenced files for STATIC_OBJECTs.
        stg_entries = stg_io2.read_stg_entries(filename, None)
        for entry in stg_entries:
            if not entry.is_static:
                continue
            try:
                ac_filename = entry.obj_filename
                if ac_filename.endswith(".xml"):
                    with open(entry.get_obj_path_and_name(), 'r') as f:
                        xml_data = f.read()
                        ac_filename = parse_ac_file_name(xml_data)
                boundary_tuple = extract_boundary(entry.stg_path + os.sep + ac_filename)
                x_y_point = my_coord_transformator.toLocal(vec2d.vec2d(entry.lon, entry.lat))
                my_box = box(boundary_tuple[0] + x_y_point[0], boundary_tuple[1] + x_y_point[1]
                             , boundary_tuple[2] + x_y_point[0], boundary_tuple[3] + x_y_point[1])
                rotated_box = affinity.rotate(my_box, entry.hdg + 90)  # FIXME: not sure whether +90 or -90 degrees
                static_obj_boxes.append(rotated_box)
            except IOError, reason:
                logging.warning("Ignoring unreadable stg_entry %s", reason)

    return static_obj_boxes


def process_ways_for_blocked_areas(my_ways, landuses):
    """
    Adds intersecting ways with buffer to blocked areas in landuse
    """
    for way in my_ways.values():
        for landuse in landuses.values():
            if way.linear.within(landuse.polygon):
                landuse.linked_blocked_areas.append(way.linear.buffer(way.get_width()/2))
                break
            intersection = way.linear.intersection(landuse.polygon)
            if not intersection.is_empty:
                if isinstance(intersection, LineString):
                    landuse.linked_blocked_areas.append(intersection.buffer(way.get_width()/2))
                elif isinstance(intersection, MultiLineString):
                    for my_line in intersection:
                        if isinstance(my_line, LineString):
                            landuse.linked_blocked_areas.append(my_line.buffer(way.get_width()/2))


def process_open_spaces_for_blocked_areas(open_spaces, landuses):
    for open_space in open_spaces.values():
        for landuse in landuses.values():
            if open_space.within(landuse.polygon) or open_space.intersects(landuse.polygon):
                landuse.linked_blocked_areas.append(open_space)


def process_building_refs_for_blocked_areas(building_refs, landuses):
    for building in building_refs.values():
        for landuse in landuses.values():
            if building.within(landuse.polygon) or building.intersects(landuse.polygon):
                landuse.linked_blocked_areas.append(building)


def process_static_obj_boxes_for_blocked_areas(static_obj_boxes, landuses):
    for box in static_obj_boxes:
        for landuse in landuses.values():
            if box.within(landuse.polygon) or box.intersects(landuse.polygon):
                landuse.linked_blocked_areas.append(box)


def calc_angle_of_line(x1, y1, x2, y2):
    """Returns the angle in degrees of a line relative to North"""
    # FIXME: copy of osm2pylon
    angle = math.atan2(x2 - x1, y2 - y1)
    degree = math.degrees(angle)
    if degree < 0:
        degree += 360
    return degree


def generate_buildings_along_highway(landuse, highway, is_reverse, step_length):
    """
    The central assumption is that existing blocked areas incl. buildings du not need a buffer.
    The to be populated buildings all bring their own constraints with regards to distance to road, distance to other
    buildings etc.
    A populated buildings is appended to the current landuse's generated_buildings list.
    FIXME: parameter for list of possible GenBuildings
    """
    travelled_along = 0
    highway_length = highway.linear.length
    my_gen_building = GenBuilding(GenBuilding.TYPE_HOUSE, highway.get_width())
    if not is_reverse:
        point_on_line = highway.linear.interpolate(0)
    else:
        point_on_line = highway.linear.interpolate(highway_length)
    while travelled_along < highway_length:
        travelled_along += step_length
        prev_point_on_line = point_on_line
        if not is_reverse:
            point_on_line = highway.linear.interpolate(travelled_along)
        else:
            point_on_line = highway.linear.interpolate(highway_length - travelled_along)
        angle = calc_angle_of_line(prev_point_on_line.x, prev_point_on_line.y
                                             , point_on_line.x, point_on_line.y)
        buffer_polygon = my_gen_building.get_area_polygon(True, point_on_line, angle)
        if buffer_polygon.within(landuse.polygon):
            valid_new_gen_place = True
            for blocked_area in landuse.linked_blocked_areas:
                #if buffer_polygon.crosses(blocked_area) or buffer_polygon.contains(blocked_area) \
                        #or buffer_polygon.within(blocked_area):
                if buffer_polygon.intersects(blocked_area):
                    valid_new_gen_place = False
                    break
            if valid_new_gen_place:
                area_polygon = my_gen_building.get_area_polygon(False, point_on_line, angle)
                my_gen_building.set_location(point_on_line, angle, area_polygon, buffer_polygon)
                landuse.generated_buildings.append(my_gen_building)
                landuse.linked_blocked_areas.append(area_polygon)
                my_gen_building = GenBuilding(GenBuilding.TYPE_HOUSE, highway.get_width())  # new building needed


# ================ PLOTTING FOR VISUAL TEST ========
from descartes import PolygonPatch
from matplotlib import pyplot


def plot_line(ax, ob, my_color, my_width):
    x, y = ob.xy
    ax.plot(x, y, color=my_color, alpha=0.7, linewidth=my_width, solid_capstyle='round', zorder=2)


def draw_polygons(highways, buildings, landuses, static_obj_boxes
                  , x_min, y_min, x_max, y_max):
    # Create a matplotlib figure
    my_figure = pyplot.figure(num=1, figsize=(16, 10), dpi=90)

    # Create a subplot
    ax = my_figure.add_subplot(111)

    # Make the polygons into a patch and add it to the subplot
    for my_land_use in landuses.values():
        my_color = "red"  # TYPE_NON_OSM
        if Landuse.TYPE_COMMERCIAL == my_land_use.type_:
            my_color = "magenta"
        elif Landuse.TYPE_INDUSTRIAL == my_land_use.type_:
            my_color = "cyan"
        elif Landuse.TYPE_RETAIL == my_land_use.type_:
            my_color = "cyan"
        elif Landuse.TYPE_RESIDENTIAL == my_land_use.type_:
            my_color = "pink"

        patch = PolygonPatch(my_land_use.polygon, facecolor=my_color, edgecolor='#999999')
        ax.add_patch(patch)

    for building in buildings.values():
        patch = PolygonPatch(building, facecolor='blue', edgecolor='blue')
        ax.add_patch(patch)

    for my_box in static_obj_boxes:
        patch = PolygonPatch(my_box, facecolor='black', edgecolor='black', alpha=0.5)
        ax.add_patch(patch)

    for my_highway in highways.values():
        if Highway.TYPE_ROAD < my_highway.type_:
            plot_line(ax, my_highway.linear, "black", 1)
        else:
            plot_line(ax, my_highway.linear, "gray", 1)
    for my_land_use in landuses.values():
        for blocked in my_land_use.linked_blocked_areas:
            patch = PolygonPatch(blocked, facecolor='green', edgecolor='green')
            ax.add_patch(patch)
        for gen_building in my_land_use.generated_buildings:
            patch = PolygonPatch(gen_building.area_polygon, facecolor='yellow', edgecolor='black')
            ax.add_patch(patch)

    # Fit the figure around the polygons, bounds, render, and show
    w = x_max - x_min
    h = y_max - y_min
    ax.set_xlim(x_min - 0.2*w, x_max + 0.2*w)
    ax.set_ylim(y_min - 0.2*h, y_max + 0.2*h)
    ax.set_aspect(1)
    pyplot.show()


def generate_extra_buildings(building_refs, static_obj_boxes, landuse_refs, places_refs, open_spaces
                             , highways, railways, waterways, x_min, y_min, x_max, y_max):
    # FIXME: use place_refs to influence type and density of buildings
    # FIXME: break land-uses up into blocks (e.g. to determine default building densities and speed up to find blocked
    # areas - also if density of buildings in block already enough, then do not calculate
    # FIXME: use slope to determine angle of houses
    process_open_spaces_for_blocked_areas(open_spaces, landuse_refs)
    process_ways_for_blocked_areas(highways, landuse_refs)
    process_ways_for_blocked_areas(railways, landuse_refs)
    process_ways_for_blocked_areas(waterways, landuse_refs)
    process_building_refs_for_blocked_areas(building_refs, landuse_refs)
    process_static_obj_boxes_for_blocked_areas(static_obj_boxes, landuse_refs)

    for landuse in landuse_refs.values():
        if not landuse.type_ == Landuse.TYPE_NON_OSM:  # assume generated land-uses already have the needed buildings
            for highway in highways.values():
                if highway.populate_buildings_along():  # e.g. do not populate buildings along motorways
                    process_this_highway = False
                    if highway.linear.within(landuse.polygon):
                        process_this_highway = True
                    else:
                        intersection = highway.linear.intersection(landuse.polygon)
                        if not intersection.is_empty and not isinstance(intersection, Point):
                            process_this_highway = True
                    if process_this_highway:
                        generate_buildings_along_highway(landuse, highway, False, 2)  # FIXME: hard_coded step size
                        generate_buildings_along_highway(landuse, highway, True, 2)  # FIXME: hard_coded step size

    draw_polygons(highways, building_refs, landuse_refs, static_obj_boxes, x_min, y_min, x_max, y_max)
    i = 0


def main():
    logging.basicConfig(level=logging.DEBUG)
    # Handling arguments and parameters
    parser = argparse.ArgumentParser(
        description="landuse reads OSM data and creates landuses and places for support of osm2city/osm2pyons in FlightGear")
    parser.add_argument("-f", "--file", dest="filename",
                        help="read parameters from FILE (e.g. params.ini)", metavar="FILE")
    args = parser.parse_args()
    if args.filename is not None:
        parameters.read_from_file(args.filename)
    center_global = parameters.get_center_global()
    osm_fname = parameters.get_OSM_file_name()
    coord_transformator = coordinates.Transformation(center_global, hdg=0)

    # Transform to real objects
    logging.info("Transforming OSM data to Line and Pylon objects")
    # the lists below are in sequence: buildings references, power/aerialway, railway overhead, landuse and highway
    valid_node_keys = ["place", "population"]
    valid_way_keys = ["building", "landuse", "place", "population", "highway", "junction", "tunnel"
                      , "leisure", "natural", "public_transport", "amenity", "area", "parking"
                      , "railway", "waterway"]
    valid_relation_keys = []
    req_relation_keys = []
    req_way_keys = ["building", "landuse", "place", "highway"
                    , "leisure", "natural", "public_transport", "amenity"
                    , "railway", "waterway"]
    handler = osmparser_wrapper.OSMContentHandler(valid_node_keys, valid_way_keys, req_way_keys, valid_relation_keys,
                                                  req_relation_keys)
    source = open(osm_fname)
    xml.sax.parse(source, handler)
    # References for buildings
    building_refs = process_osm_building_refs(handler.nodes_dict, handler.ways_dict, coord_transformator)
    logging.info('Number of reference buildings: %s', len(building_refs))
    static_obj_boxes = create_static_obj_boxes(coord_transformator)
    landuse_refs = process_osm_landuse_refs(handler.nodes_dict, handler.ways_dict, coord_transformator)
    generated_landuses = generate_landuse_from_buildings(landuse_refs, building_refs)
    for generated in generated_landuses.values():
        landuse_refs[generated.osm_id] = generated
    logging.info('Number of landuse references: %s', len(landuse_refs))
    places_refs = process_osm_place_refs(handler.nodes_dict, handler.ways_dict, coord_transformator)
    highways = process_osm_highway(handler.nodes_dict, handler.ways_dict, coord_transformator)
    open_spaces = process_osm_openspaces_refs(handler.nodes_dict, handler.ways_dict, coord_transformator)
    railways = process_osm_railway(handler.nodes_dict, handler.ways_dict, coord_transformator)
    waterways = process_osm_waterway(handler.nodes_dict, handler.ways_dict, coord_transformator)

    cmin = coord_transformator.toLocal(vec2d.vec2d(parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH))
    cmax = coord_transformator.toLocal(vec2d.vec2d(parameters.BOUNDARY_EAST, parameters.BOUNDARY_NORTH))

    generate_extra_buildings(building_refs, static_obj_boxes, landuse_refs, places_refs, open_spaces
                             , highways, railways, waterways
                             , cmin[0], cmin[1], cmax[0], cmax[1])

if __name__ == "__main__":
    main()


# ================ UNITTESTS =======================

class TestExtraBuildings(unittest.TestCase):
    def test_parse_ac_file_name(self):
        self.assertEqual("foo.ac", parse_ac_file_name("sdfsfsdf <path>  foo.ac </path> sdfsdf"))
        self.assertRaises(ValueError, parse_ac_file_name, "foo")  # do not use () and instead add parameter as arg

    def test_extract_boundary(self):
        ac_lines = ["foo", "hello"]
        ac_lines.append("numvert 2")
        ac_lines.append("0 12 0")
        ac_lines.append("-2.0 4 -4.2")
        ac_lines.append("-99 99 -99")
        ac_lines.append("numsurf 6")
        ac_lines.append("numvert 1")
        ac_lines.append("4 4 4")
        ac_lines.append(("99 99 99"))
        boundary = extract_boundary(ac_lines)
        self.assertEqual(-2.0, boundary[0], "x_min")
        self.assertEqual(4, boundary[3], "y_max")

    def test_extra_building_generation(self):
        highways = {}
        # Create the streets
        linear = LineString([(60, 270), (100, 270)])
        my_highway = Highway(1)
        my_highway.linear = linear
        my_highway.type_ = Highway.TYPE_RESIDENTIAL
        highways[my_highway.osm_id] = my_highway
        linear = LineString([(40, 270), (40, 230)])
        my_highway = Highway(2)
        my_highway.linear = linear
        my_highway.type_ = Highway.TYPE_RESIDENTIAL
        highways[my_highway.osm_id] = my_highway
        linear = LineString([(80, 250), (80, 150)])
        my_highway = Highway(3)
        my_highway.linear = linear
        my_highway.type_ = Highway.TYPE_RESIDENTIAL
        highways[my_highway.osm_id] = my_highway
        linear = LineString([(0, 180), (170, 180)])
        my_highway = Highway(4)
        my_highway.linear = linear
        my_highway.type_ = Highway.TYPE_RESIDENTIAL
        highways[my_highway.osm_id] = my_highway
        linear = LineString([(80, 150), (70, 140), (80, 130), (90, 140), (80, 150)])
        my_highway = Highway(5)
        my_highway.linear = linear
        my_highway.type_ = Highway.TYPE_RESIDENTIAL
        my_highway.is_roundabout = True
        highways[my_highway.osm_id] = my_highway
        linear = LineString([(90, 140), (110, 140), (130, 120), (130, 100), (110, 80), (110, 60), (130, 40), (150, 60), (190, 60)])
        my_highway = Highway(6)
        my_highway.linear = linear
        my_highway.type_ = Highway.TYPE_RESIDENTIAL
        highways[my_highway.osm_id] = my_highway
        linear = LineString([(50, 80), (50, 120)])
        my_highway = Highway(7)
        my_highway.linear = linear
        my_highway.type_ = Highway.TYPE_RESIDENTIAL
        highways[my_highway.osm_id] = my_highway
        linear = LineString([(70, 20), (100, 20)])
        my_highway = Highway(8)
        my_highway.linear = linear
        my_highway.type_ = Highway.TYPE_RESIDENTIAL
        highways[my_highway.osm_id] = my_highway
        linear = LineString([(70, 50), (100, 50)])
        my_highway = Highway(9)
        my_highway.linear = linear
        my_highway.type_ = Highway.TYPE_MOTORWAY
        highways[my_highway.osm_id] = my_highway
        # railways
        railways = {}
        linear = LineString([(140, 250), (140, 200), (200, 200)])
        my_rail = Railway(11)
        my_rail.linear = linear
        railways[my_rail.osm_id] = my_rail
        # waterways
        waterways = {}
        linear = LineString([(150, 250), (150, 140)])
        my_water = Waterway(21)
        my_water.linear = linear
        my_water.type_ = Waterway.TYPE_NARROW
        waterways[my_water.osm_id] = my_water
        # buildings
        building_refs = {}
        polygon = Polygon([(90, 200), (90, 190), (100, 190), (100, 200), (90, 200)])
        building_refs[100] = polygon
        polygon = Polygon([(80, 250), (80, 240), (90, 240), (90, 250), (80, 250)])
        building_refs[101] = polygon
        # static object boxes
        static_obj_boxes = [box(50, 160, 70, 180)]
        # open spaces
        open_spaces = {500: Polygon([(30, 100), (50, 100), (50, 120), (30, 120), (30, 100)])}
        # land-uses
        landuse_refs = {}
        polygon = box(20, 20, 170, 230)
        my_lu = Landuse(1000)
        my_lu.type_ = Landuse.TYPE_RESIDENTIAL
        my_lu.polygon = polygon
        landuse_refs[my_lu.osm_id] = my_lu
        generate_extra_buildings(building_refs, static_obj_boxes, landuse_refs, None, open_spaces
                                 , highways, railways, waterways
                                 , 0, 0, 200, 280)


