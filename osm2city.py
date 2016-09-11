# -*- coding: utf-8 -*-
"""
osm2city.py aims at generating 3D city models for FG, using OSM data.
Currently, it generates 3D textured buildings.
However, it has a somewhat more advanced texture manager, and comes with a
number of facade/roof textures.

- cluster a number of buildings into a single .ac files
- LOD animation based on building height and area
- terrain elevation probing: places buildings at correct elevation

You should disable random buildings.
"""

# TODO:
# - FIXME: texture size meters works reversed??
# x one object per tile only. Now drawables 1072 -> 30fps
# x use geometry library
# x read original .stg+.xml, don't place OSM buildings when there's a static model near/within
# - compute static_object stg's on the fly
# x put roofs into separate LOD
# x lights
# x read relations tag == fix empty backyards
# x simplify buildings
# x put tall, large buildings in LOD bare, and small buildings in LOD detail
# - more complicated roof geometries
#   x split, new roofs.py?
# x cmd line switches
# -

# - city center??

# FIXME:
# - off-by-one error in building counter

# LOWI:
# - floating buildings
# - LOD?
# - rename textures
# x respect ac

# cmd line
# x skip nearby check
# x fake elev
# - log level

# development hints:
# variables
# b: a building instance
#
# coding style
# - indend 4 spaces, avoid tabulators
# - variable names: use underscores (my_long_variable), avoid CamelCase
# - capitalize class names: class Interpolator(object):
# - comments: code # -- comment

import argparse
import pickle
import logging
import os
import random
import sys
import textwrap

import numpy as np
import shapely.geometry as shgm
import shapely.geos as shgs

import building_lib
import calc_tile
import cluster
import coordinates
import osmparser
import parameters
import stg_io2
import textures.manager as tex_manager
from textures.manager import TextureManager, FacadeManager  # this is needed to make pickle know the context
import tools
import troubleshoot
import vec2d as v


buildings = []  # -- master list, holds all buildings
OUR_MAGIC = "osm2city"  # Used in e.g. stg files to mark edits by osm2city


class Building(object):
    """Central object class.
       Holds all data relevant for a building. Coordinates, type, area, ...
       Read-only access to node coordinates via self.X[node][0|1]
    """
    LOD_BARE = 0
    LOD_ROUGH = 1
    LOD_DETAIL = 2

    def __init__(self, osm_id, tags, outer_ring, name, height, levels,
                 stg_typ=None, stg_hdg=None, inner_rings_list=[], building_type='unknown', roof_type='flat', roof_height=0, refs=[]):
        self.osm_id = osm_id
        self.tags = tags
        self.refs = refs
        self.inner_rings_list = inner_rings_list
        self.name = name
        self.stg_typ = stg_typ  # stg: OBJECT_SHARED or _STATIC
        self.stg_hdg = stg_hdg
        self.height = height
        self.roof_height = roof_height
        self.roof_height_X = []
        self.longest_edge_len = 0.
        self.levels = levels
        self.first_node = 0  # index of first node in final OBJECT node list
        self.anchor = v.vec2d(list(outer_ring.coords[0]))
        self.facade_texture = None
        self.roof_texture = None
        self.roof_complex = False
        self.roof_separate_LOD = False # May or may not be faster
        self.ac_name = None
        self.ceiling = 0.
        self.LOD = None  # see Building.LOD_* for values
        self.outer_nodes_closest = []
        if len(outer_ring.coords) > 2:
            self.set_polygon(outer_ring, self.inner_rings_list)
        else:
            self.polygon = None
        if self.inner_rings_list: self.roll_inner_nodes()
        self.building_type = building_type
        self.roof_type = roof_type
        self.parent = None
        self.parent_part = []
        self.parents_parts = []
        self.cand_buildings = []
        self.children = []
        self.ground_elev = None
        self.ground_elev_min = None
        self.ground_elev_max = None

    def roll_inner_nodes(self):
        """Roll inner rings such that the node closest to an outer node goes first.

           Also, create a list of outer corresponding outer nodes.
        """
        new_inner_rings_list = []
        self.outer_nodes_closest = []
        outer_nodes_avail = list(range(self.nnodes_outer))
        for inner in self.polygon.interiors:
            min_r = 1e99
            for i, node_i in enumerate(list(inner.coords)[:-1]):
                node_i = v.vec2d(node_i)
                for o in outer_nodes_avail:
                    r = node_i.distance_to(v.vec2d(self.X_outer[o]))
                    if r <= min_r:
                        closest_i = node_i
                        min_r = r
                        min_i = i
                        min_o = o
#            print "\nfirst nodes", closest_i, closest_o, r
            new_inner = shgm.polygon.LinearRing(np.roll(np.array(inner.coords)[:-1], -min_i, axis=0))
            new_inner_rings_list.append(new_inner)
            self.outer_nodes_closest.append(min_o)
            outer_nodes_avail.remove(min_o)
#            print self.outer_nodes_closest
#        print "---\n\n"
        # -- sort inner rings by index of closest outer node
        yx = sorted(zip(self.outer_nodes_closest, new_inner_rings_list))
        self.inner_rings_list = [x for (y, x) in yx]
        self.outer_nodes_closest = [y for (y, x) in yx]
        self.set_polygon(self.polygon.exterior, self.inner_rings_list)
#        for o in self.outer_nodes_closest:
#            assert(o < len(outer_ring.coords) - 1)

    def simplify(self, tolerance):
        original_nodes = self.nnodes_outer + len(self.X_inner)
        #print ">> outer nodes", b.nnodes_outer
        #print ">> inner nodes", len(b.X_inner)
        #print "total", total_nodes
        #print "now simply"
        self.polygon = self.polygon.simplify(tolerance)
        #print ">> outer nodes", b.nnodes_outer
        #print ">> inner nodes", len(b.X_inner)
        nnodes_simplified = original_nodes - (self.nnodes_outer + len(self.X_inner))
        # FIXME: simplifiy interiors
        #print "now", simple_nodes
        #print "--------------------"
        return nnodes_simplified

    def set_polygon(self, outer, inner=[]):
        #ring = shg.polygon.LinearRing(list(outer))
        # make linear rings for inner(s)
        #inner_rings = [shg.polygon.LinearRing(list(i)) for i in inner]
        #if inner_rings:
        #    print "inner!", inner_rings
        self.polygon = shgm.Polygon(outer, inner)
        
    def set_X(self):
        self.X = np.array(self.X_outer + self.X_inner)
        for i in range(self._nnodes_ground):
            self.X[i, 0] -= offset.x  # -- cluster coordinates. NB: this changes building coordinates!
            self.X[i, 1] -= offset.y

    def set_ground_elev(self, elev, tile_elev, min_elev=None, flag='local'):

        def local_elev(p):
            return elev(p + offset) - tile_elev

        self.set_X()
        
        elevs = [local_elev(v.vec2d(self.X[i])) for i in range(self._nnodes_ground)]
        
        self.ground_elev_min = min(elevs)
        self.ground_elev_max = max(elevs)
        self.ground_elev = self.ground_elev_min

    @property
    def X_outer(self):
        return list(self.polygon.exterior.coords)[:-1]

    @property
    def X_inner(self):
        return [coord for interior in self.polygon.interiors for coord in list(interior.coords)[:-1]]

    @property
    def _nnodes_ground(self):  # FIXME: changed behavior. Keep _ until all bugs found
        n = len(self.polygon.exterior.coords) - 1
        for item in self.polygon.interiors:
            n += len(item.coords) - 1
        return n

    @property
    def nnodes_outer(self):
        return len(self.polygon.exterior.coords) - 1

    @property
    def area(self):
        return self.polygon.area

class Buildings(object):
    """Holds buildings list. Interfaces with OSM handler"""
    valid_node_keys = []
    req_way_keys = ["building", "building:part"]
    valid_relation_keys = ["building", "building:part"]
    req_relation_keys = ["building", "building:part"]

    def __init__(self):
        self.buildings = []
        self.buildings_with_parts = []
        self.remove_buildings = []
        self.remove_buildings_parts = []
        self.nodes_dict = {}
        self.node_way_dict = {}
        self.way_list = []
        self.minlon = 181.
        self.maxlon = -181.
        self.minlat = 91.
        self.maxlat = -91.

    def register_callbacks_with(self, handler):
        handler.register_way_callback(self.process_way, self.req_way_keys)
        handler.register_uncategorized_way_callback(self.store_uncategorzied_way)
        handler.register_relation_callback(self.process_relation, self.req_relation_keys)

    def _refs_to_ring(self, refs, inner=False):
        """accept a list of OSM refs, return a linear ring. Also
           fixes face orientation, depending on inner/outer.
        """
        coords = []
        for ref in refs:
                c = self.nodes_dict[ref]
                coords.append(tools.transform.toLocal((c.lon, c.lat)))

        ring = shgm.polygon.LinearRing(coords)
        # -- outer -> CCW, inner -> not CCW
        if ring.is_ccw == inner:
            ring.coords = list(ring.coords)[::-1]
        return ring

    def make_way_buildings(self):
        """Converts all the ways into buildings"""
        def tag_matches(tags, req_tags):
            for tag in tags:
                if tag in req_tags:
                    return True
            return False

        for way in self.way_list:
            if tag_matches(way.tags, self.req_way_keys) and len(way.refs) > 3:
                self._make_building_from_way(way.osm_id, way.tags, way.refs)

    def _make_building_from_way(self, osm_id, tags, refs, inner_ways=[]):
        """Creates a building object from a way"""
        if refs[0] == refs[-1]:
            refs = refs[0:-1]  # -- kick last ref if it coincides with first

        name = ""
        height = 0.
        levels = 0
        layer = 99

        # -- funny things might happen while parsing OSM
        try:
            #if osm_id in parameters.SKIP_LIST :
            #    try : 
            #        if tags['building'] != 'no' :
            #            logging.info("SKIPPING OSM_ID %i" % osm_id)
            #            return False
            #    except :
            #        pass
            if 'name' in tags:
                name = tags['name']
                if name in parameters.SKIP_LIST:
                    logging.info("SKIPPING " + name)
                    return False
            if 'height' in tags:
                height = osmparser.parse_length(tags['height'])
            elif 'building:height' in tags:
                height = osmparser.parse_length(tags['building:height'])
            if 'building:levels' in tags:
                levels = float(tags['building:levels'])
            if 'levels' in tags:
                levels = float(tags['levels'])
            if 'layer' in tags:
                layer = int(tags['layer'])
            if 'roof:shape' in tags:
                _roof_type = tags['roof:shape']
            else:
                _roof_type = parameters.BUILDING_UNKNOWN_ROOF_TYPE

            _roof_height = 0
            if 'roof:height' in tags:
                try:
                    _roof_height = float(tags['roof:height'])
                except:
                    _roof_height = 0

            _building_type = building_lib.mapType(tags)

            # -- simple (silly?) heuristics to 'respect' layers
            if layer == 0:
                return False
            if layer < 99 and height == 0 and levels == 0:
                levels = layer + 2

        #        if len(refs) != 4: return False# -- testing, 4 corner buildings only

            # -- all checks OK: accept building

            # -- make outer and inner rings from refs
            outer_ring = self._refs_to_ring(refs)
            inner_rings_list = []
            for _way in inner_ways:
                inner_rings_list.append(self._refs_to_ring(_way.refs, inner=True))
        except KeyError as reason:
            logging.error("Failed to parse building referenced node missing clipped?(%s) WayID %d %s Refs %s" % (reason, osm_id, tags, refs))
            tools.stats.parse_errors += 1
            return False
        except Exception as reason:
            logging.error("Failed to parse building (%s)  WayID %d %s Refs %s" % (reason, osm_id, tags, refs))
            tools.stats.parse_errors += 1
            return False

        building = Building(osm_id, tags, outer_ring, name, height, levels, inner_rings_list=inner_rings_list, building_type=_building_type, roof_type=_roof_type, roof_height=_roof_height, refs=refs)
        self.buildings.append(building)

        tools.stats.objects += 1
        # show progress here?
        # if tools.stats.objects % 50 == 0:
        #    logging.info(tools.stats.objects)
        return True

    def store_uncategorzied_way(self, way, nodes_dict):
        """We need uncategorized ways (those without tags) too. They could
           be part of a relation building."""
        self.way_list.append(way)

    def process_way(self, way, nodes_dict):
        """Store ways. These simple buildings will be created only after
           relations have been parsed, to prevent double buildings. Our way
           could be part of a relation building and still have a 'building' tag attached.
        """
        if not self.nodes_dict:
            self.nodes_dict = nodes_dict
        if tools.stats.objects >= parameters.MAX_OBJECTS:
            return
        self.way_list.append(way)

    def process_relation(self, relation):
        """Build relation buildings right after parsing."""
#        print "__________- got relation", relation
#        bla = 0
#        if int(relation.osm_id) == 5789:
#            print "::::::::::::: name", relation.tags['name']
#            bla = 1
        if tools.stats.objects >= parameters.MAX_OBJECTS:
            return

        if 'building' in relation.tags or 'building:part' in relation.tags :
            outer_ways = []
            inner_ways = []
            outer_multipolygons = []
            for m in relation.members:
                if m.type_ == 'way':
                    if m.role == 'outer':
                        for way in self.way_list:
                            if way.osm_id == m.ref:
                                if way.refs[0] == way.refs[-1] :
                                    outer_multipolygons.append(way)
                                    logging.verbose("add way outer multipolygon " + str(way.osm_id))                                    
                                else :
                                    outer_ways.append(way)
                                    logging.verbose("add way outer " + str(way.osm_id))

                    elif m.role == 'inner':
                        for way in self.way_list:
                            if way.osm_id == m.ref: inner_ways.append(way)

                #elif m.type_ == 'multipolygon':
                #    if m.role == 'outer' :
                #        for way in self.way_list:
                #            if way.osm_id == m.ref:
                #                outer_multipolygons.append(way)

            if outer_multipolygons:
                all_tags = relation.tags
                for way in outer_multipolygons:
                    logging.debug("Multipolygon " + str(way.osm_id))
                    all_tags = dict(list(way.tags.items()) + list(all_tags.items()))
                    res=False
                    try:
                        if not parameters.EXPERIMENTAL_INNER and len(inner_ways) > 1:
                            res = self._make_building_from_way(way.osm_id,
                                                               all_tags,
                                                               way.refs, [inner_ways[0]])
                        else:
                            res = self._make_building_from_way(way.osm_id, 
                                                               all_tags,
                                                               way.refs, inner_ways)
                    except:
                        res = self._make_building_from_way(way.osm_id, 
                                                                   all_tags,
                                                                   way.refs)

            if outer_ways:
                #all_outer_refs = [ref for way in outer_ways for ref in way.refs]
                # build all_outer_refs
                list_outer_refs = [way.refs for way in outer_ways[1:]]
                # get some order :
                all_outer_refs = []
                all_outer_refs.extend( outer_ways[0].refs )

                for i in range(1, len(outer_ways)):
                    for way_refs in list_outer_refs :
                        if way_refs[0] == all_outer_refs[-1]:
                            #first node of way is last of previous
                            all_outer_refs.extend(way_refs[0:])
                            continue
                        elif way_refs[-1] == all_outer_refs[-1]:
                            #last node of way is last of previous 
                            all_outer_refs.extend(way_refs[::-1])
                            continue
                    list_outer_refs.remove(way_refs)

                all_tags = relation.tags
                for way in outer_ways:
                    #print "TAG", way.tags
                    all_tags = dict(list(way.tags.items()) + list(all_tags.items()))
                #print "all tags", all_tags
                #all_tags = dict([way.tags for way in outer_ways]) # + tags.items())
                #print "all outer refs", all_outer_refs
                #dict(outer.tags.items() + tags.items())
                if not parameters.EXPERIMENTAL_INNER and len(inner_ways) > 1:
                    print("FIXME: ignoring all but first inner way (%i total) of ID %i" % (len(inner_ways), relation.osm_id))
                    res = self._make_building_from_way(relation.osm_id,
                                                       all_tags,
                                                       all_outer_refs, [inner_ways[0]])
                else:
                    res = self._make_building_from_way(relation.osm_id,
                                                       all_tags,
                                                       all_outer_refs, inner_ways)
#                print ":::::mk_build returns", res,
#                if bla:
#                    print relation.tags['name']
                # -- way could have a 'building' tag, too. Prevent processing this twice.

            if not outer_multipolygons and not outer_ways:
                logging.info("Skipping relation %i: no outer way." % relation.osm_id)
                
            for _way in outer_ways:
                    if _way in self.way_list:
                        logging.info("removing ways" + str(_way.osm_id))
                        # keep way if not closed, might be used elsewhere
                        if _way.refs[0] == _way.refs[-1]:
                            self.way_list.remove(_way)
                    else:
                        logging.error("Outer way (%d) not in list of ways. Building type missing?" % _way.osm_id)

    def _get_min_max_coords(self):
        for node in list(self.nodes_dict.values()):
            if node.lon > self.maxlon:
                self.maxlon = node.lon
            if node.lon < self.minlon:
                self.minlon = node.lon
            if node.lat > self.maxlat:
                self.maxlat = node.lat
            if node.lat < self.minlat:
                self.minlat = node.lat

#        cmin = vec2d(self.minlon, self.minlat)
#        cmax = vec2d(self.maxlon, self.maxlat)
#        logging.info("min/max coord" + str(cmin) + " " + str(cmax))

# -----------------------------------------------------------------------------
# -- write xml


def write_xml(path, fname, buildings):
    #  -- LOD animation
    xml = open(path + fname + ".xml", "w")
    xml.write("""<?xml version="1.0"?>\n<PropertyList>\n""")
    xml.write("<path>%s.ac</path>" % fname)

    has_lod_bare = False
    has_lod_rough = False
    has_lod_detail = False

    # -- lightmap
    # FIXME: use Effect/Building? What's the difference?
    #                <lightmap-factor type="float" n="0"><use>/scenery/LOWI/garage[0]/door[0]/position-norm</use></lightmap-factor>
    if parameters.LIGHTMAP_ENABLE:
        xml.write(textwrap.dedent("""
        <effect>
          <inherits-from>cityLM</inherits-from>
          """))
        xml.write("  <object-name>LOD_detail</object-name>\n")
        xml.write("  <object-name>LOD_rough</object-name>\n")
        xml.write("</effect>\n")

    # -- put obstruction lights on hi-rise buildings
    for b in buildings:
        if b.levels >= parameters.OBSTRUCTION_LIGHT_MIN_LEVELS:
            Xo = np.array(b.X_outer)
            for i in np.arange(0, b.nnodes_outer, b.nnodes_outer/4.):
                xo = Xo[int(i+0.5), 0] - offset.x
                yo = Xo[int(i+0.5), 1] - offset.y
                zo = b.ceiling + 1.5
                # <path>cursor.ac</path>
                xml.write(textwrap.dedent("""
                <model>
                  <path>Models/Effects/pos_lamp_red_light_2st.xml</path>
                  <offsets>
                    <x-m>%g</x-m>
                    <y-m>%g</y-m>
                    <z-m>%g</z-m>
                    <pitch-deg> 0.00</pitch-deg>
                    <heading-deg>0.0 </heading-deg>
                  </offsets>
                </model>""" % (-yo, xo, zo)))  # -- I just don't get those coordinate systems.

        if b.LOD is not None:
            if b.LOD == Building.LOD_BARE:
                has_lod_bare = True
            elif b.LOD == Building.LOD_ROUGH:
                has_lod_rough = True
            elif b.LOD == Building.LOD_DETAIL:
                has_lod_detail = True
            else:
                logging.warning("Building %s with unknown LOD level %i", b.osm_id, b.LOD)

    # -- LOD animation
    #    no longer use bare (reserved for terrain)
    #    instead use rough, detail, roof
    if has_lod_bare:
        xml.write(textwrap.dedent("""
        <animation>
          <type>range</type>
          <min-m>0</min-m>
          <max-property>/sim/rendering/static-lod/bare</max-property>
          <object-name>LOD_bare</object-name>
        </animation>
        """))
    if has_lod_rough:
        xml.write(textwrap.dedent("""
        <animation>
          <type>range</type>
          <min-m>0</min-m>
          <max-property>/sim/rendering/static-lod/rough</max-property>
          <object-name>LOD_rough</object-name>
        </animation>
        """))
    if has_lod_detail:
        xml.write(textwrap.dedent("""
        <animation>
          <type>range</type>
          <min-m>0</min-m>
          <max-property>/sim/rendering/static-lod/detailed</max-property>
          <object-name>LOD_detail</object-name>
        </animation>
        """))
    xml.write(textwrap.dedent("""

    </PropertyList>
    """))
    xml.close()


# -----------------------------------------------------------------------------
# here we go!
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    random.seed(42)
    # -- Parse arguments. Command line overrides config file.
    parser = argparse.ArgumentParser(description="osm2city reads OSM data and creates buildings for use with FlightGear")
    parser.add_argument("-f", "--file", dest="filename",
                        help="read parameters from FILE (e.g. params.ini)", metavar="FILE", required=True)
    parser.add_argument("-e", dest="e", action="store_true",
                        help="skip elevation interpolation", required=False)
    parser.add_argument("-c", dest="c", action="store_true",
                        help="do not check for overlapping with static objects", required=False)
    parser.add_argument("-a", "--create-atlas", action="store_true",
                        help="create texture atlas", required=False)
    parser.add_argument("-u", dest="uninstall", action="store_true",
                        help="uninstall ours from .stg", required=False)
    parser.add_argument("-l", "--loglevel",
                        help="set loglevel. Valid levels are VERBOSE, DEBUG, INFO, WARNING, ERROR, CRITICAL", required=False)
    args = parser.parse_args()

    # -- command line args override paramters

    if args.filename is not None:
        parameters.read_from_file(args.filename)
    parameters.set_loglevel(args.loglevel)  # -- must go after reading params file
    
    if args.e:
        parameters.NO_ELEV = True
    if args.c:
        parameters.OVERLAP_CHECK = False

    if args.uninstall:
        logging.info("Uninstalling.")
        files_to_remove = []
        parameters.NO_ELEV = True
        parameters.OVERLAP_CHECK = False

    parameters.show()

    # -- initialize modules

    # -- prepare transformation to local coordinates
    cmin, cmax = parameters.get_extent_global()
    center = parameters.get_center_global()

    tools.init(coordinates.Transformation(center, hdg=0))

    tex_manager.init(tools.get_osm2city_directory(), args.create_atlas)

    logging.info("reading elevation data")
    elev = tools.get_interpolator(fake=parameters.NO_ELEV)
    logging.debug("height at origin" + str(elev(v.vec2d(0, 0))))
    logging.debug("origin at " + str(tools.transform.toGlobal((0, 0))))

    # -- now read OSM data. Either parse OSM xml, or read a previously cached .pkl file
    #    End result is 'buildings', a list of building objects
    pkl_fname = parameters.PREFIX + os.sep + parameters.OSM_FILE + '.pkl'
    osm_fname = parameters.PREFIX + os.sep + parameters.OSM_FILE

    if parameters.USE_PKL and not os.path.exists(pkl_fname):
        logging.warning("pkl file %s not found, will parse OSM file %s instead." % (pkl_fname, osm_fname))
        parameters.USE_PKL = False

    if not parameters.USE_PKL:
        # -- parse OSM, return
        if not parameters.IGNORE_PKL_OVERWRITE and os.path.exists(pkl_fname):
            print("Existing cache file %s will be overwritten. Continue? (y/n)" % pkl_fname)
            if input().lower() != 'y':
                sys.exit(-1)

        if parameters.BOUNDARY_CLIPPING:
            border = shgm.Polygon(parameters.get_clipping_extent())
        else:
            border = None
        handler = osmparser.OSMContentHandler(valid_node_keys=[], border=border)
        buildings = Buildings()
        buildings.register_callbacks_with(handler)
        source = open(osm_fname, encoding="utf8")
        logging.info("Reading the OSM file might take some time ...")
        handler.parse(source)

        # tools.stats.print_summary()
        buildings.make_way_buildings()
        buildings._get_min_max_coords()
        cmin = v.vec2d(buildings.minlon, buildings.minlat)
        cmax = v.vec2d(buildings.maxlon, buildings.maxlat)
        logging.info("min/max " + str(cmin) + " " + str(cmax))
        
        # Search parents
        if parameters.BUILDING_REMOVE_WITH_PARTS:  # and 'building' not in building.tags :
            # Build neighbours
            def add_candidates(building, b_cands=[], used_refs=[], flag_init=True, recurs=0):
                """Build list of parent candidates for building, return parent if one of the candidates already parsed"""
                
                if recurs > 20:
                    return False

                if flag_init is True:
                    used_refs = []
                    b_cands = []
                
                if building not in b_cands:
                    b_cands.append(building)
                    
                process_refs = []
                process_refs.extend(building.refs)
                for ref in used_refs:
                    try:
                        process_refs.remove(ref)
                    except:
                        pass
                
                for ref in process_refs:
                    # Store used references
                    #if ref in used_refs :
                    #    continue
                    # 
                    #if ref in self.node_way_dict :
                    #print(" ref", ref)
                    
                    #if ref not in buildings.node_way_dict :
                    #     buildings.node_way_dict=[]
                        
                    tmp_b_cands = list({ b_cand for b_cand in buildings.node_way_dict[ref] if ((b_cand not in b_cands) and (b_cand.osm_id != building.osm_id))})
                    b_cands.extend(tmp_b_cands)
                    
                    if ref not in used_refs:
                        used_refs.append(ref) ; used_refs = list(set(used_refs))
                        for cand_building in tmp_b_cands:
                            #if cand_building.cand_buildings and flag_init==False:
                            #    building.cand_buildings =  cand_building.cand_buildings
                            #    return True
                            #else :                                
                            add_candidates(cand_building, b_cands, used_refs, flag_init=False, recurs=recurs+1) 
                            #        return True
                    
                #for b_cand in b_cands :
                #    if b_cand not in building.cand_buildings :
                #        building.cand_buildings.append(b_cand)
                
                building.cand_buildings = b_cands

                return False
        
            def check_and_set_parent(building, cand_building, flag_search='equal'):
                try:
                    if building.osm_id == cand_building.osm_id:
                        try:
                            if cand_building.tags['building'] != 'no':
                                building.parent = building
                        except:
                            return False
                            
                    cand_valid = False
                    
                    if flag_search == 'equal':
                        if cand_building.polygon.intersection(building.polygon).equals(building.polygon):
                            cand_valid = True
                    if flag_search == 'intersects':
                        #
                        # Set parent if intersection assuming that building is 0.8 % in candidate
                        #
                        if cand_building.polygon.intersection(building.polygon).intersects(building.polygon):
                            ratio_area = cand_building.polygon.intersection(building.polygon).area / building.area
                            if ratio_area > 0.8:
                                cand_valid = True

                    if cand_valid:
                        #
                        # Our building:part belongs to the building
                        #
                        if((cand_building in buildings.buildings) or (cand_building in buildings.buildings_with_parts)):
                            #
                            # set temporary building:part as parent
                            #
                            try:
                                if cand_building.tags['building:part'] != 'no':
                                    #
                                    #  area of cand_building is greater than building
                                    #  if building:height <= cand_building and building:height 
                                    #  building will not be visible
                                    #
                                    try:
                                        cand_min_height = float(cand_building.tags['building:min_height'])
                                    except:
                                        cand_min_height = 0.
                                        
                                    try:
                                        min_height = float(building.tags['building:min_height'])
                                    except:
                                        min_height = 0.
                                
                                    if (cand_building.height - cand_building.roof_height) >= building.height and min_height > cand_min_height:
                                        buildings.remove_buildings_parts.append(building)
                                        logging.info(" removed 'invisible' building:part " + str(building.osm_id))
                                        return
                                    else:
                                        # store parent that is itset a building:part
                                        logging.verbose("    found possible " + str(cand_building.osm_id))
                                        building.parents_parts.append(cand_building)
                                        #building.parent_part.cand_building 
                                        return
                            except KeyError:
                                pass

                            try:
                                if cand_building.tags['building'] != 'no':
                                    #
                                    # found building parent
                                    #
                                    if cand_building not in buildings.remove_buildings:
                                        buildings.remove_buildings.append(cand_building)
                                        logging.info('Found Building for removing %d' % cand_building.osm_id)

                                    if cand_building not in buildings.buildings_with_parts:
                                        buildings.buildings_with_parts.append(cand_building)   
                                        logging.info('Found Building for removing %d' % cand_building.osm_id)

                                    building.parent = cand_building
                                    return
                            except KeyError:
                                pass

                        else:
                            logging.verbose(" cand %i not in cand_buildings nor buildings_with_parts" % cand_building.osm_id)
                            
                    else:
                        logging.verbose("   cand %i doesn't contains  %i" % (cand_building.osm_id,  building.osm_id))
                                
                except shgs.TopologicalError as reason:
                    logging.warning("Error while checking for intersection %s. This might lead to double buildings ID1 : %d ID2 : %d " % (reason, building.osm_id, cand_building.osm_id))
                except shgs.PredicateError as reason:
                    logging.warning("Error while checking for intersection %s. This might lead to double buildings ID1 : %d ID2 : %d " % (reason, building.osm_id, cand_building.osm_id))
    
                return False
               
            #
            # Build index of buildings by ref
            #
            logging.verbose("\nBuilding index of way by ref\n")
            for building in buildings.buildings :

                for ref in building.refs :
                    if ref not in buildings.node_way_dict:
                        way_list_by_ref=[]
                    else:
                        way_list_by_ref=buildings.node_way_dict[ref]
                        
                    way_list_by_ref.append(building)
                    way_list_by_ref=list(set(way_list_by_ref))
                    
                    buildings.node_way_dict[ref]=way_list_by_ref

            #
            # First Pass search parent with buildings sharing points
            #               add possible parents parts
            logging.verbose("\nFirst pass of parent search\n")  
            buildings.remove_buildings = []
            buildings.remove_buildings_parts = []
            for building in buildings.buildings:
                logging.verbose("   search parent for %i" % building.osm_id)
                
                # Set actual building parent to itself
                try:
                    if building.tag['building'] != 'no':
                        building.parent = building
                        continue
                except:
                    pass
                    
                # Search and set parent for building:part
                cand_buildings = list({b_cand for ref in building.refs for b_cand in buildings.node_way_dict[ref] if ((b_cand.osm_id != building.osm_id ))})
                for b_cand in cand_buildings:
                    logging.verbose("      trying %i"%b_cand.osm_id )
                    check_and_set_parent(building, b_cand)

            #
            # Search for candidates buildings recursively
            #
            for building in buildings.buildings:
                if not building.parent:
                    cand_buildings = building.cand_buildings
                    add_candidates(building, cand_buildings)

            #
            # Search parents for still orphans buildings - on buildings sharing points
            #
            for building in buildings.buildings:
                if building.parent:
                    continue
                
                logging.verbose("search parent for %i" % building.osm_id)
                #
                # Skip building:part=no and building!=no
                #
                if 'building:part' in building.tags:
                    if building.tags['building:part'] == 'no':
                        logging.verbose(" skip building:part = no for %i" % building.osm_id)
                        continue
                        
                if 'building' in building.tags:
                    if building.tags['building'] != 'no':
                        logging.verbose(" skip building != no for %i" % building.osm_id)
                        building.parent = building
                        continue
                
                cand_buildings = building.cand_buildings
                # Loop on neighbours buildings sharing a point with target building
                for cand_building in cand_buildings:
                    logging.verbose(" trying candidate : %i " % cand_building.osm_id)
                    check_and_set_parent(building, cand_building)

            #
            # Search parents for buildings that are still orphan and do not "share" points
            #
            orphans = 0
            for building in buildings.buildings:
                if not building.parent:
                    process = False 
                    #
                    # Check if isolated 
                    #
                    
                    # obvious 
                    #if len(building.cand_buildings) < 2 : 
                    #    process = True
                    #else 
                    # less obvious superposition
                    #    bc_ids = [ bc.osm_id for bc in building.cand_buildings ]
                    #    bc_ids.sort()
                    
                    orphans += 1
                    for cand_building in buildings.remove_buildings:
                        check_and_set_parent(building, cand_building)
                        
                        if building.parent:
                            break

            #
            # build children
            #
            for building in buildings.buildings:
                if building.parent and (building.parent != building):
                    if building not in building.parent.children:
                        building.parent.children.append(building)
                
                if building.parent_part and ( building.parent_part != building):
                    if building not in building.parent_part.children:
                        building.parent_part.children.append(building)

            #
            # Search parents in children parents 
            #
            tools.stats.objects = 0 
            tools.stats.orphans = 0
            
            for building in buildings.buildings:
                if not building.parent:
                    #
                    # Search in parent of childrens
                    #
                    possible_parents = [child.parent for child in building.children if child.parent]
                    possible_parents = list(set(possible_parents))
                    try:
                        possible_parents.remove(None)
                    except:
                        pass
                    if len(possible_parents) == 1:
                        building.parent = possible_parents[0]
                    elif len(possible_parents) > 1:
                        most_probable_parent = possible_parents[0]
                        area=most_probable_parent.area
                        #print("area", area)
                        #
                        # search biggest building
                        #
                        for possible_parent in set(possible_parents):
                            #area_tmp=possible_parent.area
                            #building.parent=possible_parent
                            #if area_tmp > area :
                            #    building.parent=possible_parent
                            #    area=area_tmp
                            check_and_set_parent(building, cand_building, flag_search='intersects')
                            
                            if building.parent and (building.parent != building):
                                if building not in building.parent.children:
                                    building.parent.children.append(building)
                                break
                    else:
                        for cand_building in buildings.remove_buildings:
                            
                            check_and_set_parent(building, cand_building, flag_search='intersects')
                            
                            if building.parent and ( building.parent != building):
                                if building not in building.parent.children:
                                    building.parent.children.append(building)                                
                                break
                                
                if not building.parent:
                    tools.stats.orphans += 1

            if parameters.LOGLEVEL == 'VERBOSE':
                for building in buildings.buildings:
                    if building.parent:
                        logging.verbose('building %i found parent %i' % (building.osm_id, building.parent.osm_id))
                    else:
                        logging.verbose('building %i without parent' % building.osm_id)

            #
            # remove tagged buildings
            #
            for building in buildings.remove_buildings:
                logging.verbose(" Removing buildings")
                try:
                    buildings.buildings.remove(building)
                    logging.verbose("Removing building %i" % building.osm_id)
                    tools.stats.objects -= 1
                except:
                    pass

            # Custom inject tmp
                if building.osm_id == 263644296:
                    for child in building.children:
                            child.correct_ground = 3.5

                            child.tags['building:colour'] = 'red'
                            try:
                                if 'roof:colour' not in child.tags:
                                    if 'roof:material' in child.tags :
                                        if child.tags['roof:material'] != 'stone':
                                            continue
                                        else:
                                            child.tags['roof:colour'] = 'red'

                                    if child.tags['building:material'] == 'stone':
                                        child.tags['roof:material'] = 'stone'
                                        child.tags['roof:colour'] = 'red'
                            except:
                                pass

            #
            # remove tagged buildings:part
            #
            #for building in buildings.remove_buildings_parts :
            #    try :
            #        buildings.buildings.remove(building)
            ##        print("Removing building part", building.osm_id)
            #        tools.stats.objects -= 1
            #    except :
            #        pass       
            keep_buildings = []
            keeped = 0
            if parameters.KEEP_LIST:
                logging.verbose(" KEEP only buildings ")
                logging.verbose("len buildings.buildings %i"%len(buildings.buildings))
                # keep explicitely given buildings by keep_list
                for building in buildings.buildings:
                    logging.verbose("TEST %i " % building.osm_id)
                    if building.osm_id in parameters.KEEP_LIST:
                        if building not in keep_buildings:
                            keep_buildings.append(building)
                            logging.verbose("    keep %i" % building.osm_id)
                            keeped += 1
                        
                    if keeped == len(parameters.KEEP_LIST):
                        break
                
                # keep only parts of buildings with parts
                for building in buildings.remove_buildings:
                    logging.verbose("keeping childs of building %i" % building.osm_id)

                    if building.osm_id in parameters.KEEP_LIST:
                        for child in building.children:
                            if (child not in keep_buildings) and (child.osm_id not in parameters.SKIP_LIST):
                                logging.verbose("    keep child %i" % child.osm_id)
                                keep_buildings.append(child)
                        keeped += 1
                            
                    if keeped == len(parameters.KEEP_LIST):
                        break

                keep_buildings = list(set(keep_buildings))
                buildings.buildings = keep_buildings
            
            #
            # REMOVE BUILDINGS + children in SKIP_LIST
            #
            if parameters.SKIP_LIST:
                # Add children of buildings to remove
                for building in buildings.remove_buildings:
                    for child in building.children:
                        parameters.SKIP_LIST.append(child.osm_id)
                        try:
                            buildings.buildings.remove(child)
                        except:
                            pass                       

                parameters.SKIP_LIST = list(set(parameters.SKIP_LIST))

                for building in buildings.buildings:
                    if building.osm_id in parameters.SKIP_LIST:
                        for child in building.children:
                            try:
                                buildings.buildings.remove(child)
                                parameters.SKIP_LIST.append(child.osm_id)
                            except:
                                pass  
                        try:
                            buildings.buildings.remove(building)
                        except:
                            pass
                            
            #
            # Clean parent
            #
            for building in buildings.buildings:
                if building.parent == building:
                    building.parent = None
            
        #self.buildings.append(building)

        #tools.stats.objects += 1
        # show progress here?
        # if tools.stats.objects % 50 == 0:
        #    logging.info(tools.stats.objects)
        
        #    #if building.parent : 
        #            print("building ", str(building.osm_id), " found parent", str(building.parent.osm_id))

        buildings_with_parts = buildings.buildings_with_parts
        buildings = buildings.buildings
        logging.info("parsed %i buildings." % len(buildings))

        # -- cache parsed data. To prevent accidentally overwriting,
        #    write to local dir, while we later read from $PREFIX/buildings.pkl
        fpickle = open(pkl_fname, 'wb')
        pickle.dump(buildings, fpickle, -1)
        fpickle.close()
    else:
        # -- load list of building objects from previously cached file
        logging.info("Loading %s", pkl_fname)
        fpickle = open(pkl_fname, 'rb')
        buildings = pickle.load(fpickle)[:parameters.MAX_OBJECTS]
        fpickle.close()

#        newbuildings = []

        logging.info("Unpickled %g buildings ", len(buildings))
        tools.stats.objects = len(buildings)

    # -- debug filter
#    for b in buildings:
#        if b.osm_id == 35336:
#            new_buildings = [b]
#            break
#    buildings = new_buildings

    # -- create (empty) clusters
    lmin = v.vec2d(tools.transform.toLocal(cmin))
    lmax = v.vec2d(tools.transform.toLocal(cmax))
    clusters = cluster.Clusters(lmin, lmax, parameters.TILE_SIZE, parameters.PREFIX)

    if parameters.OVERLAP_CHECK:
        # -- read static/shared objects in our area from .stg(s)
        #    FG tiles are assumed to be much larger than our clusters.
        #    Loop all clusters, find relevant tile by checking tile_index at center of each cluster.
        #    Then read objects from .stg.
        stgs = []
        static_objects = []
        for cl in clusters:
            center_global = tools.transform.toGlobal(cl.center)
            path = calc_tile.construct_path_to_stg(parameters.PATH_TO_SCENERY, center_global)
            stg_fname = calc_tile.construct_stg_file_name(center_global)

            if stg_fname not in stgs:
                stgs.append(stg_fname)
                static_objects.extend(stg_io2.read(path, stg_fname, OUR_MAGIC))

        logging.info("read %i objects from %i tiles", len(static_objects), len(stgs))
    else:
        static_objects = None


    # - analyze buildings
    #   - calculate area
    #   - location clash with stg static models? drop building
    #   - TODO: analyze surrounding: similar shaped buildings nearby? will get same texture
    #   - set building type, roof type etc
    buildings = building_lib.analyse(buildings, static_objects, tools.transform, elev,
                                     tex_manager.facades, tex_manager.roofs)

    # -- initialize STG_Manager
    path_to_output = parameters.get_output_path()
    replacement_prefix = parameters.get_repl_prefix()
    stg_manager = stg_io2.STG_Manager(path_to_output, OUR_MAGIC, replacement_prefix, overwrite=True)
#     for node in ac_nodes:
#         print node
#         lon, lat = tools.transform.toGlobal(node)
#         e = elev((lon,lat), is_global=True)
#         stg_manager.add_object_shared("Models/Communications/cell-monopole1-75m.xml", vec2d(lon, lat), e, 0)

    #tools.write_gp(buildings)

    # -- put buildings into clusters, decide LOD, shuffle to hide LOD borders
    for b in buildings:
        clusters.append(b.anchor, b)
    building_lib.decide_LOD(buildings)
    clusters.transfer_buildings()

    # -- write clusters
    clusters.write_stats()
    stg_fp_dict = {}    # -- dictionary of stg file pointers
    stg = None  # stg-file object

    for ic, cl in enumerate(clusters):
        nb = len(cl.objects)
        if nb < parameters.CLUSTER_MIN_OBJECTS:
            continue  # skip almost empty clusters

        # -- get cluster center
        offset = cl.center

        # -- count roofs == separate objects
        nroofs = 0
        for b in cl.objects:
            if b.roof_complex:
                nroofs += 2  # we have 2 different LOD models for each roof

        tile_elev = elev(cl.center)
        center_global = v.vec2d(tools.transform.toGlobal(cl.center))
        if tile_elev == -9999:
            logging.warning("Skipping tile elev = -9999 at lat %.3f and lon %.3f", center_global.lat, center_global.lon)
            continue  # skip tile with improper elev

        #LOD_lists = []
        #LOD_lists.append([])  # bare
        #LOD_lists.append([])  # rough
        #LOD_lists.append([])  # detail
        #LOD_lists.append([])  # roof
        #LOD_lists.append([])  # roof-flat

        # -- incase PREFIX is a path (batch processing)
        file_name = replacement_prefix + "city%02i%02i" % (cl.I.x, cl.I.y)
        logging.info("writing cluster %s (%i/%i)" % (file_name, ic, len(clusters)))

        path_to_stg = stg_manager.add_object_static(file_name + '.xml', center_global, tile_elev, 0)

#        if cl.I.x == 0 and cl.I.y == 0:
        stg_manager.add_object_static('lightmap-switch.xml', center_global, tile_elev, 0, once=True)

        if args.uninstall:
            files_to_remove.append(path_to_stg + file_name + ".ac")
            files_to_remove.append(path_to_stg + file_name + ".xml")
        else:
            # -- write .ac and .xml
            building_lib.write(path_to_stg + file_name + ".ac", cl.objects, elev, tile_elev, tools.transform, offset)
            write_xml(path_to_stg, file_name, cl.objects)
            tools.install_files(['cityLM.eff', 'lightmap-switch.xml'], path_to_stg, True)

    if args.uninstall:
        for f in files_to_remove:
            try:
                os.remove(f)
            except:
                pass
        stg_manager.drop_ours()
        stg_manager.write()
        logging.info("uninstall done.")
        sys.exit(0)

    elev.save_cache()
    stg_manager.write()
    tools.stats.print_summary()
    troubleshoot.troubleshoot(tools.stats)
    logging.info("done.")
    sys.exit(0)
