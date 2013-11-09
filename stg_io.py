#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Created on Sat Mar 23 18:32:18 2013

@author: tom
"""

import os
import string
#from osm2city import Building, Coords
import osm2city
import osmparser
import shapely.geometry as shg
import tools
#, transform

#    def __str__(self):
#        return "%s %s %g %g %g %g" % (self.typ, self.path, self.lon, self.lat, self.alt, self.hdg)

#our_magic_start = "# osm2city"

def read(path, stg, prefix, fgscenery, our_magic):
    """Accepts a scenery sub-path, as in 'w010n40/w005n48/', plus an .stg file name.
       In the future, take care of multiple scenery paths here.
       Returns list of buildings representing static/shared objects in .stg, with full path.
    """
    objs = []
    path = fgscenery + os.sep + 'Objects' + os.sep + path + os.sep
    print "stg: reading", path + stg

    our_magic_start = '# ' + our_magic
    our_magic_end = '# END ' + our_magic

    ours = False
    try:
        f = open(path + stg)
        for line in f.readlines():
            if line.startswith(our_magic_start):
                ours = True
                continue
            if line.startswith(our_magic_end):
                ours = False
            if ours: continue

            if line.startswith('#') or line.lstrip() == "": continue
            splitted = line.split()
            typ, ac_path  = splitted[0:2]
            lon = float(splitted[2])
            lat = float(splitted[3])
            alt = float(splitted[4])
            r = osmparser.Nodey(lon, lat)
            point = shg.Point(tools.transform.toLocal((r.lon, r.lat)))
            hdg = float(splitted[5])
                #print "stg:", typ, path + ac_path
            objs.append(osm2city.Building(osm_id=-1, tags=-1, outer_ring = point, name=path + ac_path, height=0, levels=0, stg_typ = typ, stg_hdg = hdg))
        f.close()
    except IOError, reason:
        print "stg_io:read: Ignoring unreadable file %s" % reason
        return []

    return objs

def uninstall_ours(stg_fname, our_magic):
    """Uninstall previous osm2city data from .stg.
       Read full .stg to memory, write everything except ours back to .stg, sync.
    """
    our_magic_start = '# ' + our_magic
    our_magic_end = '# END ' + our_magic
    
    try:
        stg = open(stg_fname, "r")
        lines = stg.readlines()
        stg.close()
        stg = open(stg_fname, "w")
        ours = False
        for line in lines:
            if line.startswith(our_magic_start):
                ours = True
                continue
            if line.startswith(our_magic_end):
                ours = False
            if ours: continue
            
            stg.write(line)
        stg.flush()
        stg.close()
    except IOError, reason:
        print "error uninstalling %s: %s" % (stg_fname, reason)


#class Stg:
#    def __init__(self, stgs_with_path):
#        self.objs = []
#        for path, stg in stgs_with_path:
#            #print "stg read", path, stg
#            self.objs += self.read(fgscenery + os.sep + "Objects" + os.sep + path, stg)
#
#    def read(self, path, stg):
#        objs = []
#        print "stg read", path + stg
#
#        f = open(path + stg)
#        for line in f.readlines():
#            if line.startswith('#') or line.lstrip() == "": continue
#            splitted = line.split()
#            typ, ac_path  = splitted[0:2]
#            print "stg:", typ, path + ac_path
#            lon = float(splitted[2])
#            lat = float(splitted[3])
#            alt = float(splitted[4])
#            r = Coords(-1, lon, lat)
#            hdg = float(splitted[5])
#            objs.append(Building(osm_id=-1, tags=-1, refs=[r], name=path + ac_path, height=0, levels=0, stg_typ = typ, stg_hdg = hdg))
#        f.close()
#        return objs
#



#a = stg(inf)
#for o in a.objs:
#    print o
