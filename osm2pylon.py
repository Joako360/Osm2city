# -*- coding: utf-8 -*-
"""
Script part of osm2city which takes OpenStreetMap data for overground power lines and aerialways
as input and generates data to be used in FlightGear sceneries.

* Cf. OSM Power: 
    http://wiki.openstreetmap.org/wiki/Map_Features#Power
    http://wiki.openstreetmap.org/wiki/Tag:power%3Dtower
* Cf. OSM Aerialway: http://wiki.openstreetmap.org/wiki/Map_Features#Aerialway

TODO:
* Cables should have different diameter depending on WayLine.type_
* For aerialways make sure there is a station at both ends
* For aerialways handle stations if represented as ways instead of nodes.
* For powerlines handle power stations if represented as ways instead of nodes
* If a pylon is shared between lines but not at end points, then move one pylon a bit away
* Calculate cables
* LOD / clusters

@author: vanosten
"""

import argparse
import logging
import math
import os
import unittest
import xml.sax

import calc_tile
import coordinates
import osmparser
import parameters
import stg_io
import tools
import vec2d

OUR_MAGIC = "osm2pylon"  # Used in e.g. stg files to mark edits by osm2pylon


class Cable(object):
    def __init__(self, start_cable_vertex, end_cable_vertex, radius=0.5):
        self.start_cable_vertex = start_cable_vertex
        self.end_cable_vertex = end_cable_vertex
        self.vertices = [self.start_cable_vertex, self.end_cable_vertex]
        self.radius = radius
        self.heading = calc_angle_of_line(start_cable_vertex.x, start_cable_vertex.y
                                          , end_cable_vertex.x, end_cable_vertex.y)

    def translate_vertices_relative(self, rel_x, rel_y, rel_elevation):
        """
        Translates the CableVertices relatively to a reference position
        """
        for cable_vertex in self.vertices:
            cable_vertex.x -= rel_x
            cable_vertex.y -= rel_y
            cable_vertex.elevation -= rel_elevation

    def create_numvert_lines(self, cable_vertex):
        """
        In the map-data x-axis is towards East and y-axis is towards North and z-axis is elevation.
        In ac-files the y-axis is pointing upwards and the z-axis points to South -
        therefore y and z are switched and z * -1
        """
        numvert_lines = str(cable_vertex.x + math.sin(math.radians(self.heading + 90))*self.radius)
        numvert_lines += " " + str(cable_vertex.elevation - self.radius)
        numvert_lines += " " + str(-1*(cable_vertex.y + math.cos(math.radians(self.heading + 90))*self.radius)) + "\n"
        numvert_lines += str(cable_vertex.x - math.sin(math.radians(self.heading + 90))*self.radius)
        numvert_lines += " " + str(cable_vertex.elevation - self.radius)
        numvert_lines += " " + str(-1*(cable_vertex.y - math.cos(math.radians(self.heading + 90))*self.radius)) + "\n"
        numvert_lines += str(cable_vertex.x)
        numvert_lines += " " + str(cable_vertex.elevation + self.radius)
        numvert_lines += " " + str(-1*cable_vertex.y)
        return numvert_lines

    def make_ac_entry(self, material):
        """
        Returns an ac entry for this cable.
        """
        lines = []
        lines.append("OBJECT poly")
        lines.append("numvert 6")
        lines.append(self.create_numvert_lines(self.start_cable_vertex))
        lines.append(self.create_numvert_lines(self.end_cable_vertex))
        lines.append("numsurf 3")
        lines.append("SURF 0x40")
        lines.append("mat " + str(material))
        lines.append("refs 4")
        lines.append("0 0 0")
        lines.append("3 0 0")
        lines.append("5 0 0")
        lines.append("2 0 0")
        lines.append("SURF 0x40")
        lines.append("mat " + str(material))
        lines.append("refs 4")
        lines.append("0 0 0")
        lines.append("1 0 0")
        lines.append("4 0 0")
        lines.append("3 0 0")
        lines.append("SURF 0x40")
        lines.append("mat " + str(material))
        lines.append("refs 4")
        lines.append("4 0 0")
        lines.append("1 0 0")
        lines.append("2 0 0")
        lines.append("5 0 0")
        lines.append("kids 0")
        return "\n".join(lines)


class CableVertex(object):
    def __init__(self, out, height, along=0):
        self.out = out  # the distance from the middle vertical line of the pylon
        self.height = height  # the distance above ground relative to the pylon's ground level (y-axis in ac-file)
        #  not yet used: self.along = along  # the distance along the x-axis away from the middle vertical line
        self.x = 0.0  # local position x
        self.y = 0.0  # local position y
        self.elevation = 0.0  # elevation above sea level in meters

    def calc_position(self, pylon_x, pylon_y, pylon_elevation, pylon_heading):
        self.elevation = pylon_elevation + self.height
        self.x = pylon_x + math.sin(math.radians(pylon_heading + 90))*self.out
        self.y = pylon_y + math.cos(math.radians(pylon_heading + 90))*self.out


def create_generic_pylon_25_vertices():
    vertices = [CableVertex(5.0, 12.6)
                , CableVertex(-5.0, 12.6)
                , CableVertex(5.0, 16.8)
                , CableVertex(-5.0, 16.8)
                , CableVertex(5.0, 21.0)
                , CableVertex(-5.0, 21.0)
                , CableVertex(0.0, 25.2)]
    return vertices


def create_generic_pylon_50_vertices():
    vertices = [CableVertex(10.0, 25.2)
                , CableVertex(-10.0, 25.2)
                , CableVertex(10.0, 33.6)
                , CableVertex(-10.0, 33.6)
                , CableVertex(10.0, 42.0)
                , CableVertex(-10.0, 42.0)
                , CableVertex(0.0, 50.4)]
    return vertices


def create_generic_pylon_100_vertices():
    vertices = [CableVertex(20.0, 50.4)
                , CableVertex(-20.0, 50.4)
                , CableVertex(20.0, 67.2)
                , CableVertex(-20.0, 67.2)
                , CableVertex(20.0, 84.0)
                , CableVertex(-20.0, 84.0)
                , CableVertex(0.0, 100.8)]
    return vertices


def create_streetlamp3_vertices():
    vertices = [CableVertex(1.7, 6.07)
                , CableVertex(-1.7, 6.07)]
    return vertices


def create_rail_power_vertices():
    vertices = [CableVertex(2.0, 5.9)
                , CableVertex(2.0, 5.0)]
    return vertices


def get_cable_vertices(pylon_model):
    if "generic_pylon_25m" in pylon_model:
        return create_generic_pylon_25_vertices()
    if "generic_pylon_50m" in pylon_model:
        return create_generic_pylon_50_vertices()
    if "generic_pylon_100m" in pylon_model:
        return create_generic_pylon_100_vertices()
    elif "RailPower" in pylon_model:
        return create_rail_power_vertices()
    elif "lamp3" in pylon_model:
        return create_streetlamp3_vertices()
    else:
        return None


class WaySegment(object):
    """Represents the part between the pylons and is a container for the cables"""

    def __init__(self, start_pylon, end_pylon):
        self.start_pylon = start_pylon
        self.end_pylon = end_pylon
        self.cables = []
        self.length = calc_distance(start_pylon.x, start_pylon.y, end_pylon.x, end_pylon.y)
        self.heading = calc_angle_of_line(start_pylon.x, start_pylon.y
                                          , end_pylon.x, end_pylon.y)


class Pylon(object):
    def __init__(self, osm_id):
        self.osm_id = osm_id
        self.type_ = 0  # 11 = electric tower, 12 = electric pole, 21 = aerialway pylon, 22 = aerialway station
        self.height = 0.0  # parsed as float
        self.structure = None
        self.material = None
        self.colour = None
        self.my_wayline = None  # a reference to the way - either an electrical line or an aerialway
        self.prev_pylon = None
        self.next_pylon = None
        self.lon = 0.0  # longitude coordinate in decimal as a float
        self.lat = 0.0  # latitude coordinate in decimal as a float
        self.x = 0.0  # local position x
        self.y = 0.0  # local position y
        self.elevation = 0.0  # elevation above sea level in meters
        self.heading = 0.0  # heading of pylon in degrees

    def make_stg_entry(self):
        """
        Returns a stg entry for this pylon.
        E.g. OBJECT_SHARED Models/Airport/ils.xml 5.313108 45.364122 374.49 268.92
        """
        entry = ["OBJECT_SHARED", self.my_wayline.pylon_model, str(self.lon), str(self.lat), str(self.elevation)
                 , str(stg_angle(self.heading - 90))]  # 90 less because arms are in x-direction in ac-file
        return " ".join(entry)


class WayLine(object):  # The name "Line" is also used in e.g. SymPy
    """
    11 = power line, 12 = power minor line
    21 = cable_car, 22 = chair_lift/mixed_lift, 23 = drag_lift/t-bar/platter, 24 = gondola, 25 = goods
    """
    def __init__(self, osm_id):
        self.osm_id = osm_id
        self.pylons = []
        self.way_segments = []
        self.type_ = 0
        self.pylon_model = None  # the path to the ac/xml model
        self.length = 0.0  # the total length of all segments

    def make_pylons_stg_entries(self):
        """
        Returns the stg entries for the pylons of this WayLine in a string separated by linebreaks
        """
        entries = []
        for my_pylon in self.pylons:
            entries.append(my_pylon.make_stg_entry())
        return "\n".join(entries)

    def make_cables_ac_xml_stg_entries(self, filename, path):
        """
        Returns the stg entries for the cables of this WayLine in a string separated by linebreaks
        E.g. OBJECT_STATIC LSZSpylons1901.xml 9.75516 46.4135 2000.48 0

        Before this it creates the xml-file and ac-file containing the cables.

        Each WaySegment is represented as an object group in ac with each cable of the WaySegment as a kid

        """
        xml_file_lines = []
        xml_file_lines.append('<?xml version="1.0"?>')
        xml_file_lines.append('<PropertyList>')
        xml_file_lines.append('<path>' + filename + '.ac</path>')  # the ac-file is in the same directory
        xml_file_lines.append('</PropertyList>')
        with open(path + filename + ".xml", 'w') as f:
            f.write("\n".join(xml_file_lines))

        ac_file_lines = []
        ac_file_lines.append("AC3Db")
        ac_file_lines.append('MATERIAL "cable" rgb 0.5 0.5 0.5 amb 0.5 0.5 0.5 emis 0.0 0.0 0.0 spec 0.5 0.5 0.5 shi 64 trans 0')
        ac_file_lines.append('MATERIAL "yellow" rgb 1   1   0 amb 1 1 1  emis 0.0 0.0 0.0  spec 0.5 0.5 0.5  shi 64  trans 0')
        ac_file_lines.append('MATERIAL "blue" rgb 0   0   1 amb 1 1 1  emis 0.0 0.0 0.0  spec 0.5 0.5 0.5  shi 64  trans 0')
        ac_file_lines.append("OBJECT world")
        ac_file_lines.append("kids " + str(len(self.way_segments)))
        way_segment_index = 0
        for way_segment in self.way_segments:
            material = 1
            if self.is_aerialway():
                material = 2
            way_segment_index += 1
            ac_file_lines.append("OBJECT group")
            ac_file_lines.append('"segment%05d"' % way_segment_index)
            ac_file_lines.append("kids " + str(len(way_segment.cables)))
            for cable in way_segment.cables:
                cable.translate_vertices_relative(self.pylons[0].x, self.pylons[0].y, self.pylons[0].elevation)
                ac_file_lines.append(cable.make_ac_entry(material))  # material is 0-indexed
        ac_file_content = "\n".join(ac_file_lines)
        with open(path + filename + ".ac", 'w') as f:
            f.write("\n".join(ac_file_lines))

        entry = ["OBJECT_STATIC", filename + ".xml", str(self.pylons[0].lon), str(self.pylons[0].lat)
                 , str(self.pylons[0].elevation), "90"]
        return " ".join(entry)

    def is_aerialway(self):
        return self.type_ > 20

    def calc_and_map(self):
        """Calculates various aspects of the line and its nodes and attempt to correct if needed. """
        max_length = self._calc_segments()
        if self.is_aerialway():
            self._calc_and_map_aerialway()
        else:
            self._calc_and_map_powerline(max_length)
        self._calc_headings_pylons()
        self._calc_cables()

    def _calc_and_map_aerialway(self):
        self.pylon_model = "Models/StreetFurniture/RailPower.xml"  # FIXME: make real implementation

    def _calc_and_map_powerline(self, max_length):
        """
        Danish rules of thumb:
        400KV: height 30-42 meter, distance 200-420 meter, sagging 4.5-13 meter
        150KV: height 25-32 meter, distance 180-350 meter, sagging 2.5-9 meter
        60KV: height 15-25 meter, distance 100-250 meter, sagging 1-5 meter"""
        # calculate min, max, averages etc.
        max_height = 0.0
        average_height = 0.0
        found = 0
        nbr_poles = 0
        nbr_towers = 0
        for my_pylon in self.pylons:
            if my_pylon.type_ == 11:
                nbr_towers += 1
            elif my_pylon.type_ == 12:
                nbr_poles += 1
            if my_pylon.height > 0:
                average_height += my_pylon.height
                found += 1
            if my_pylon.height > max_height:
                max_height = my_pylon.height
        if found > 0:
            average_height /= found

        # use statistics to determine type_ and pylon_model
        if self.type_ == 12 and nbr_towers <= nbr_poles and max_height <= 25.0 and max_length <= 250.0:
            self.type_ = 12
            self.pylon_model = "Models/StreetFurniture/streetlamp3.xml"
        else:
            self.type_ = 11
            if average_height < 35.0 and max_length < 300.0:
                self.pylon_model = "Models/Power/generic_pylon_25m.xml"
            elif average_height < 75.0 and max_length < 500.0:
                self.pylon_model = "Models/Power/generic_pylon_50m.xml"
            else:
                self.pylon_model = "Models/Power/generic_pylon_100m.xml"

    def get_center_coordinates(self):
        """Returns the lon/lat coordinates of the line"""
        my_pylon = self.pylons[0]
        return my_pylon.lon, my_pylon.lat  # FIXME: needs to be calculated more properly with shapely

    def _calc_headings_pylons(self):
        current_pylon = self.pylons[0]
        next_pylon = self.pylons[1]
        current_angle = calc_angle_of_line(current_pylon.x, current_pylon.y, next_pylon.x, next_pylon.y)
        current_pylon.heading = current_angle
        for x in range(1, len(self.pylons) - 1):
            prev_angle = current_angle
            current_pylon = self.pylons[x]
            next_pylon = self.pylons[x + 1]
            current_angle = calc_angle_of_line(current_pylon.x, current_pylon.y, next_pylon.x, next_pylon.y)
            current_pylon.heading = calc_middle_angle(prev_angle, current_angle)
        self.pylons[-1].heading = current_angle

    def _calc_segments(self):
        """Creates the segments of this WayLine and calculates the total length.
        Returns the maximum length of segments"""
        max_length = 0.0
        total_length = 0.0
        self.way_segments = []  # if this method would be called twice by mistake
        for x in range(0, len(self.pylons) - 1):
            segment = WaySegment(self.pylons[x], self.pylons[x + 1])
            self.way_segments.append(segment)
            if segment.length > max_length:
                max_length = segment.length
            total_length += segment.length
        self.length = total_length
        return max_length

    def _calc_cables(self):
        """
        Creates the cables per WaySegment. First find the start and end points depending on pylon model.
        Then calculate the local positions of all start and end points.
        Afterwards use the start and end points to create all cables for a given WaySegment
        """
        for segment in self.way_segments:
            start_cable_vertices = get_cable_vertices(self.pylon_model)
            end_cable_vertices = get_cable_vertices(self.pylon_model)
            for i in xrange(0, len(start_cable_vertices)):
                start_cable_vertices[i].calc_position(segment.start_pylon.x, segment.start_pylon.y
                                                      , segment.start_pylon.elevation, segment.start_pylon.heading)
                end_cable_vertices[i].calc_position(segment.end_pylon.x, segment.end_pylon.y
                                                    , segment.end_pylon.elevation, segment.end_pylon.heading)
                cable = Cable(start_cable_vertices[i], end_cable_vertices[i])
                segment.cables.append(cable)


def process_osm_elements(nodes_dict, ways_dict, _elev_interpolator, _coord_transformator):
    """
    Transforms a dict of Node and a dict of Way OSMElements from osmparser.py to a dict of WayLine objects for
    electrical power lines and a dict of WayLine objects for aerialways. Nodes are transformed to Pylons.
    The elevation of the pylons is calculated as part of this process.
    """
    my_powerlines = {}  # osm_id as key, WayLine object as value
    my_aerialways = {}  # osm_id as key, WayLine object as value
    my_shared_nodes = {}  # node osm_id as key, list of WayLine objects as value
    for way in ways_dict.values():
        my_line = WayLine(way.osm_id)
        for key in way.tags:
            value = way.tags[key]
            if "power" == key:
                if "line" == value:
                    my_line.type_ = 11
                elif "minor_line" == value:
                    my_line.type_ = 12
            elif "aerialway" == key:
                if "cable_car" == value:
                    my_line.type_ = 21
                elif value in ["chair_lift", "mixed_lift"]:
                    my_line.type_ = 22
                elif value in ["drag_lift", "t-bar", "platter"]:
                    my_line.type_ = 23
                elif "gondola" == value:
                    my_line.type_ = 24
                elif "goods" == value:
                    my_line.type_ = 25
        if 0 != my_line.type_:
            prev_pylon = None
            for ref in way.refs:
                if ref in nodes_dict:
                    my_node = nodes_dict[ref]
                    my_pylon = Pylon(my_node.osm_id)
                    my_pylon.lat = my_node.lat
                    my_pylon.lon = my_node.lon
                    my_pylon.x, my_pylon.y = _coord_transformator.toLocal((my_node.lon, my_node.lat))
                    my_pylon.my_wayline = my_line
                    my_pylon.elevation = _elev_interpolator(vec2d.vec2d(my_pylon.lon, my_pylon.lat), True)
                    for key in my_node.tags:
                        value = my_node.tags[key]
                        if "power" == key:
                            if "tower" == value:
                                my_pylon.type_ = 11
                            elif "pole" == value:
                                my_pylon.type_ = 12
                        elif "aerialway" == key:
                            if "pylon" == value:
                                my_pylon.type_ = 21
                            elif "station" == value:
                                my_pylon.type_ = 22
                        elif "height" == key:
                            my_pylon.height = osmparser.parse_length(value)
                        elif "structure" == key:
                            my_pylon.structure = value
                        elif "material" == key:
                            my_pylon.material = value
                    if my_pylon.elevation != -9999:  # if elevation is -9999, then point is outside of boundaries
                        my_line.pylons.append(my_pylon)
                        if my_node.osm_id in my_shared_nodes.keys():
                            my_shared_nodes[my_node.osm_id].append(my_line)
                        else:
                            my_shared_nodes[my_node.osm_id] = [my_line]
                    else:
                        logging.debug('Node outside of boundaries with osm_id = %s and therefore ignored',
                                      my_node.osm_id)
                    if None != prev_pylon:
                        prev_pylon.next_pylon = my_pylon
                        my_pylon.prev_pylon = prev_pylon
                    prev_pylon = my_pylon
            if len(my_line.pylons) > 1:
                if my_line.is_aerialway():
                    my_aerialways[my_line.osm_id] = my_line
                else:
                    my_powerlines[my_line.osm_id] = my_line
            else:
                logging.warning('Line could not be validated or corrected. osm_id = %s', my_line.osm_id)

    for key in my_shared_nodes.keys():
        shared_node = my_shared_nodes[key]
        if len(shared_node) == 2:
            return_code = merge_lines(key, shared_node[0], shared_node[1])
            if 0 == return_code:  # remove the merged line
                if shared_node[0].is_aerialway() and (shared_node[1].osm_id in my_aerialways):
                    del my_aerialways[shared_node[1].osm_id]
                elif shared_node[1].osm_id in my_powerlines:
                    del my_powerlines[shared_node[1].osm_id]
                logging.info("Merged two lines with node osm_id: %s", key)
            elif 1 == return_code:
                logging.warning(
                    "A node is referenced in two ways, but the lines have not same type. Node osm_id: %s; %s; %s"
                    , key, shared_node[0].type_, shared_node[1].type_)
            else:
                logging.warning(
                    "A node is referenced in two ways, but the common node is not at start/end. Node osm_id: %s; %s"
                    , key, shared_node[0].type_)
        if len(shared_node) > 2:
            logging.warning("A node is referenced in more than two ways. Most likely OSM problem. Node osm_id: %s", key)

    return my_powerlines, my_aerialways


def merge_lines(osm_id, line0, line1):
    """Takes two Line objects and attempts to merge them at a given node.
    Returns 1 if the Line objects are not of same type.
    Returns 2 if the node is not first or last node in both Line objects
    in a given Line object.
    Returns 0 if the added/merged pylons are in line0"""
    if line0.type_ != line1.type_:
        return 1
    if line0.pylons[0].osm_id == osm_id:
        line0_first = True
    elif line0.pylons[-1].osm_id == osm_id:
        line0_first = False
    else:
        return 2
    if line1.pylons[0].osm_id == osm_id:
        line1_first = True
    elif line1.pylons[-1].osm_id == osm_id:
        line1_first = False
    else:
        return 2

    if (False == line0_first) and (True == line1_first):
        for x in range(1, len(line1.pylons), 1):
            line0.pylons.append(line1.pylons[x])
    elif (False == line0_first) and (False == line1_first):
        for x in range(len(line1.pylons) - 2, 0, -1):
            line0.pylons.append(line1.pylons[x])
    elif (True == line0_first) and (True == line1_first):
        for x in range(1, len(line1.pylons), 1):
            line0.pylons.insert(0, line1.pylons[x])
    else:
        for x in range(len(line1.pylons) - 2, 0, -1):
            line0.pylons.insert(0, line1.pylons[x])
    return 0


def write_stg_entries(stg_fp_dict, lines_dict, wayname):
    line_index = 0
    for line in lines_dict.values():
        line_index += 1
        center = line.get_center_coordinates()
        stg_fname = calc_tile.construct_stg_file_name(center)
        if parameters.PATH_TO_OUTPUT:
            path = calc_tile.construct_path_to_stg(parameters.PATH_TO_OUTPUT, center)
        else:
            path = calc_tile.construct_path_to_stg(parameters.PATH_TO_SCENERY, center)
        if not stg_fname in stg_fp_dict:
            if not os.path.exists(path):
                try:
                    os.makedirs(path)
                except OSError:
                    logging.exception("Unable to create path to output directory")
                    pass
            stg_io.uninstall_ours(path, stg_fname, OUR_MAGIC)
            stg_file = open(path + stg_fname, "a")
            logging.info('Opening new stg-file for append: ' + path + stg_fname)
            stg_file.write(stg_io.delimiter_string(OUR_MAGIC, True) + "\n# do not edit below this line\n#\n")
            stg_fp_dict[stg_fname] = stg_file
        else:
            stg_file = stg_fp_dict[stg_fname]
        stg_file.write(line.make_pylons_stg_entries() + "\n")
        filename = parameters.PREFIX + wayname + "%05d" % line_index
        stg_file.write(line.make_cables_ac_xml_stg_entries(filename, path) + "\n")


def calc_angle_of_line(x1, y1, x2, y2):
    """Returns the angle in degrees of a line relative to North"""
    angle = math.atan2(x2 - x1, y2 - y1)
    degree = math.degrees(angle)
    if degree < 0:
        degree += 360
    return degree


def calc_middle_angle(angle_line1, angle_line2):
    """Returns the angle halfway between two lines"""
    if angle_line1 == angle_line2:
        middle = angle_line1
    elif angle_line1 > angle_line2:
        if 0 == angle_line2:
            middle = calc_middle_angle(angle_line1, 360)
        else:
            middle = angle_line1 - (angle_line1 - angle_line2) / 2
    else:
        if math.fabs(angle_line2 - angle_line1) > 180:
            middle = calc_middle_angle(angle_line1 + 360, angle_line2)
        else:
            middle = angle_line2 - (angle_line2 - angle_line1) / 2
    if 360 <= middle:
        middle -= 360
    return middle


def stg_angle(angle_normal):
    """Returns the input angle in degrees to an angle for the stg-file in degrees.
    stg-files use angles counter-clockwise starting with 0 in North."""
    if 0 == angle_normal:
        return 0
    else:
        return 360 - angle_normal


def calc_distance(x1, y1, x2, y2):
    return math.sqrt(math.pow(x1 - x2, 2) + math.pow(y1 - y2, 2))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Handling arguments and parameters
    parser = argparse.ArgumentParser(
        description="osm2city reads OSM data and creates buildings for use with FlightGear")
    parser.add_argument("-f", "--file", dest="filename",
                        help="read parameters from FILE (e.g. params.ini)", metavar="FILE")
    args = parser.parse_args()
    if args.filename is not None:
        parameters.read_from_file(args.filename)

    # Reading OSM-file and transform to Pylons / Lines objects
    valid_node_keys = ["power", "structure", "material", "height", "colour", "aerialway"]
    valid_way_keys = ["power", "aerialway"]
    req_way_keys = ["power", "aerialway"]
    valid_relation_keys = []
    req_relation_keys = []
    handler = osmparser.OSMContentHandler(valid_node_keys, valid_way_keys, req_way_keys, valid_relation_keys,
                                          req_relation_keys)
    source = open(parameters.PREFIX + os.sep + parameters.OSM_FILE)
    logging.info("Reading the OSM file might take some time ...")
    xml.sax.parse(source, handler)

    # Initializing tools for global/local coordinate transformations
    cmin = vec2d.vec2d(parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH)
    cmax = vec2d.vec2d(parameters.BOUNDARY_EAST, parameters.BOUNDARY_NORTH)
    center = (cmin + cmax) * 0.5
    coord_transformator = coordinates.Transformation(center, hdg=0)
    tools.init(coord_transformator)
    # Reading elevation data
    logging.info("Reading ground elevation data might take some time ...")
    elev_interpolator = tools.Interpolator(parameters.PREFIX + os.sep + "elev.out", fake=parameters.NO_ELEV)

    # Transform to real objects
    logging.info("Transforming OSM data to Line and Pylon objects")
    powerlines, aerialways = process_osm_elements(handler.nodes_dict, handler.ways_dict, elev_interpolator,
                                                  coord_transformator)
    handler = None  # free memory
    logging.info('Number of power lines: %s', len(powerlines))
    logging.info('Number of aerialways: %s', len(aerialways))

    # Work on objects
    for wayline in powerlines.values():
        wayline.calc_and_map()
    for wayline in aerialways.values():
        wayline.calc_and_map()

    # Write to Flightgear
    stg_file_pointers = {}  # -- dictionary of stg file pointers
    write_stg_entries(stg_file_pointers, powerlines, "powerline")
    write_stg_entries(stg_file_pointers, aerialways, "aerialway")

    for stg in stg_file_pointers.values():
        stg.write(stg_io.delimiter_string(OUR_MAGIC, False) + "\n")
        stg.close()

    logging.info("******* Finished *******")


# ================ UNITTESTS =======================


class TestOSMPylons(unittest.TestCase):
    def test_angle_of_line(self):
        self.assertEqual(0, calc_angle_of_line(0, 0, 0, 1), "North")
        self.assertEqual(90, calc_angle_of_line(0, 0, 1, 0), "East")
        self.assertEqual(180, calc_angle_of_line(0, 1, 0, 0), "South")
        self.assertEqual(270, calc_angle_of_line(1, 0, 0, 0), "West")
        self.assertEqual(45, calc_angle_of_line(0, 0, 1, 1), "North East")
        self.assertEqual(315, calc_angle_of_line(1, 0, 0, 1), "North West")
        self.assertEqual(225, calc_angle_of_line(1, 1, 0, 0), "South West")

    def test_middle_angle(self):
        self.assertEqual(0, calc_middle_angle(0, 0), "North North")
        self.assertEqual(45, calc_middle_angle(0, 90), "North East")
        self.assertEqual(130, calc_middle_angle(90, 170), "East Almost_South")
        self.assertEqual(90, calc_middle_angle(135, 45), "South_East North_East")
        self.assertEqual(0, calc_middle_angle(45, 315), "South_East North_East")
        self.assertEqual(260, calc_middle_angle(170, 350), "Almost_South Almost_North")

    def test_distance(self):
        self.assertEqual(5, calc_distance(0, -1, -4, 2))

    def test_wayline_calculate_and_map(self):
        # first test headings
        pylon1 = Pylon(1)
        pylon1.x = -100
        pylon1.y = -100
        pylon2 = Pylon(2)
        pylon2.x = 100
        pylon2.y = 100
        wayline1 = WayLine(100)
        wayline1.type_ = 11  # high voltage powerline
        wayline1.pylons.append(pylon1)
        wayline1.pylons.append(pylon2)
        wayline1.calc_and_map()
        self.assertAlmostEqual(45, pylon1.heading, 2)
        self.assertAlmostEqual(45, pylon2.heading, 2)
        pylon3 = Pylon(3)
        pylon3.x = 0
        pylon3.y = 100
        pylon4 = Pylon(4)
        pylon4.x = -100
        pylon4.y = 200
        wayline1.pylons.append(pylon3)
        wayline1.pylons.append(pylon4)
        wayline1.calc_and_map()
        self.assertAlmostEqual(337.5, pylon2.heading, 2)
        self.assertAlmostEqual(292.5, pylon3.heading, 2)
        self.assertAlmostEqual(315, pylon4.heading, 2)
        pylon5 = Pylon(5)
        pylon5.x = -100
        pylon5.y = 300
        wayline1.pylons.append(pylon5)
        wayline1.calc_and_map()
        self.assertAlmostEqual(337.5, pylon4.heading, 2)
        self.assertAlmostEqual(0, pylon5.heading, 2)
        # then test other stuff
        self.assertEqual(4, len(wayline1.way_segments))
        wayline1.make_cables_ac_xml_stg_entries("foo", "foo")

    def test_cable_vertex_calc_position(self):
        vertex = CableVertex(10, 5)
        vertex.calc_position(0, 0, 20, 0)
        self.assertAlmostEqual(25, vertex.elevation, 2)
        self.assertAlmostEqual(10, vertex.x, 2)
        self.assertAlmostEqual(0, vertex.y, 2)
        vertex.calc_position(0, 0, 20, 90)
        self.assertAlmostEqual(0, vertex.x, 2)
        self.assertAlmostEqual(-10, vertex.y, 2)
        vertex.calc_position(0, 0, 20, 210)
        self.assertAlmostEqual(-8.660, vertex.x, 2)
        self.assertAlmostEqual(5, vertex.y, 2)
        vertex.calc_position(20, 50, 20, 180)
        self.assertAlmostEqual(10, vertex.x, 2)
        self.assertAlmostEqual(50, vertex.y, 2)
