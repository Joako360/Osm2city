'''
Created on 25.04.2014

@author: keith.paterson
'''
import logging
import argparse
import sys
import calc_tile
import re
import os
from _io import open

def getFile(name, tilename, lon, lat):
    if "nt" in os.name:
        name = name + tilename + ".cmd"
    else:
        name = name + tilename
    return open(calc_tile.root_directory_name((lon, lat)) + os.sep + name, "wb")

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="build-tiles generates a directory structure capable of generating complete tiles of scenery")
    parser.add_argument("-t", "--tile", dest="tilename",
                      help="The name of the tile")
    parser.add_argument("-f", "--properties", dest="properties",
                      help="The name of the property file to be copied")
    parser.add_argument("-o", "--out", dest="out",
                      help="The name of the property file to be copied")
    args = parser.parse_args()
    
    if( args.tilename is None):
        logging.error("Tilename is required")
        parser.print_usage()
        exit(1)
    if( args.properties is None):
        logging.error("Properties is required")
        parser.print_usage()
        exit(1)
    logging.info( 'Generating directory structure for %s ', args.tilename)
    matched = re.match("([ew])([0-9]{3})([ns])([0-9]{2})", args.tilename)
    lon = int(matched.group(2))
    lat = int(matched.group(4))
    if( matched.group(1) == 'w' ):
        lon *= -1
    if( matched.group(3) == 's' ):
        lat *= -1
    if( calc_tile.bucket_span(lat) > 1):
        num_rows = 1
    else:    
        num_rows = int(1 / calc_tile.bucket_span(lat))
    #int(1/calc_tile.bucket_span(lat))
    num_cols = 8
    try:
        os.makedirs(calc_tile.root_directory_name((lon, lat)))
    except OSError, e:
        if e.errno != 17:
            logging.exception("Unable to create path to output")
            
    downloadfile = getFile("download", args.tilename ,lon, lat) 
    osm2city = getFile("osm2city_", args.tilename ,lon, lat)
    osm2pylon = getFile("osm2pylon_", args.tilename ,lon, lat)
    tools = getFile("tools_", args.tilename ,lon, lat) 
    platformsfile = getFile("osm2platform_", args.tilename ,lon, lat) 
    roads = getFile("roads_", args.tilename ,lon, lat) 
    for dy in range(0, num_cols):
        for dx in range(0, num_rows):
            index = calc_tile.tile_index((lon, lat), dx, dy)
            path =("%s%s%s" % (calc_tile.directory_name((lon, lat)), os.sep,  index ) )
            logging.info ( path)
            try:
                os.makedirs(path)
            except OSError, e:
                if e.errno != 17:
                    logging.exception("Unable to create path to output")
            if( path.count('\\') ):
                replacement_path = re.sub('\\\\','/', path)
            with open(args.properties, "r") as sources:
                lines = sources.readlines()
            with open(path + os.sep + args.out, "w") as sources:
                replacement = '\\1 ' + replacement_path
                for line in lines:
                    line = re.sub('^\s*(PREFIX\s*=)([ A-Za-z0-9]*)', replacement, line)
                    line = re.sub('^\s*(BOUNDARY_EAST\s*=)([ A-Za-z0-9.,]*)', '\\1 %f' % (calc_tile.get_east_lon(lon, lat, dx)), line)
                    line = re.sub('^\s*(BOUNDARY_WEST\s*=)([ A-Za-z0-9.,]*)', '\\1 %f' % (calc_tile.get_west_lon(lon, lat, dx)), line)
                    line = re.sub('^\s*(BOUNDARY_NORTH\s*=)([ A-Za-z0-9.,]*)', '\\1 %f' % (calc_tile.get_north_lat(lat, dy)), line)
                    line = re.sub('^\s*(BOUNDARY_SOUTH\s*=)([ A-Za-z0-9.,]*)', '\\1 %f' % (calc_tile.get_south_lat(lat, dy)), line)
                    sources.write(line)            
            download_command = 'wget -O %s/buildings.osm http://overpass-api.de/api/map?bbox=%f,%f,%f,%f   ' + os.linesep
            #wget -O FT_WILLIAM/buildings.osm http://overpass-api.de/api/map?bbox=-5.2,56.8,-5.,56.9
            downloadfile.write(download_command%(replacement_path,calc_tile.get_west_lon(lon, lat, dx),calc_tile.get_south_lat(lat, dy),calc_tile.get_east_lon(lon, lat, dx),calc_tile.get_north_lat(lat, dy)))
            osm2city.write('python osm2city.py -f %s/params.ini' % (replacement_path) + os.linesep)
            osm2pylon.write('python osm2pylon.py -f %s/params.ini' % (replacement_path) + os.linesep)
            tools.write('python tools.py -f %s/params.ini' % (replacement_path) + os.linesep)
            platformsfile.write('python platforms.py -f %s/params.ini' % (replacement_path) + os.linesep)
            roads.write('python roads.py -f %s/params.ini' % (replacement_path) + os.linesep)
    downloadfile.close() 
    osm2city.close()
    osm2pylon.close()
    tools.close() 
    platformsfile.close() 
    roads.close() 

    sys.exit(0)