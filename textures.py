#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Created on Wed Mar 13 22:22:05 2013

@author: tom
"""
import numpy as np
import random
from pdb import pm
import logging
import Image
import math
import cPickle
import string

def next_pow2(value):
    return 2**(int(math.log(value) / math.log(2)) + 1)

def make_texture_atlas(texture_list, filename, size_x = 256, pad_y = 0):
    """
    create texture atlas from all textures. Update all our item coordinates.
    """
    logging.debug("Making texture atlas")

    atlas_sx = size_x
    keep_aspect = True # FIXME: False won't work -- im.thumbnail seems to keep aspect no matter what

    atlas_sy = 0
    next_y = 0

    # -- load and rotate images
    for l in texture_list:
        l.im = Image.open(l.filename)
        logging.debug("name %s size " % l.filename + str(l.im.size))
        assert (l.v_can_repeat + l.h_can_repeat < 2)
        if l.v_can_repeat:
            l.rotated = True
            l.im = l.im.transpose(Image.ROTATE_270)

    # FIXME: maybe auto-calc x-size here

    # -- scale
    for l in texture_list:
        scale_x = 1. * atlas_sx / l.im.size[0]
        if keep_aspect:
            scale_y = scale_x
        else:
            scale_y = 1.
        org_size = l.im.size
        nx = int(org_size[0] * scale_x)
        ny = int(org_size[1] * scale_y)
        l.im = l.im.resize((nx, ny), Image.ANTIALIAS)
        logging.debug("scale:" + str(org_size) + str(l.im.size))
        atlas_sy += l.im.size[1] + pad_y

    # -- create atlas image
    atlas_sy = next_pow2(atlas_sy)
    atlas = Image.new("RGBA", (atlas_sx, atlas_sy))

    # -- paste, compute atlas coords
    #    lower left corner of texture is x0, y0
    for l in texture_list:
        atlas.paste(l.im, (0, next_y))
        sx, sy = l.im.size
        l.x0 = 0
        l.x1 = float(sx) / atlas_sx
        l.y1 = 1 - float(next_y) / atlas_sy
        l.y0 = 1 - float(next_y + sy) / atlas_sy
        l.sy = float(sy) / atlas_sy
        l.sx = 1.

        next_y += sy + pad_y

    atlas.save(filename, optimize=True)

    for l in texture_list:
        logging.debug('%s (%4.2f, %4.2f) (%4.2f, %4.2f)' % (l.filename, l.x0, l.y0, l.x1, l.y1))
        del l.im

class TextureManager(object):
    def __init__(self,cls):
        self.__l = []
        self.__cls = cls # -- class (roof, facade, ...)

    def append(self, t):
        # -- prepend each item in t.provides with class name,
        #    except for class-independent keywords: age,region,compat
        new_provides = []
        for item in t.provides:
            if item.split(':')[0] in ('age', 'region', 'compat'):
                new_provides.append(item)
            else:
                new_provides.append(self.__cls + ':' + item)
        #t.provides = [self.__cls + ':' + i for i in t.provides]
        t.provides = new_provides
        self.__l.append(t)

    def find_matching(self, requires = []):
        candidates = self.find_candidates(requires)
        logging.debug("looking for texture" + str(requires))
        for c in candidates:
            logging.debug("  candidate " + c.filename + " provides " + str(c.provides))
        if len(candidates) == 0:
            logging.warn("WARNING: no matching texture for <%s>" + str(requires))
            return None
        #print "cands are\n", string.join(["  " + str(c) for c in candidates], '\n')
        #return candidates[3]
        return candidates[random.randint(0, len(candidates)-1)]

    def find_candidates(self, requires = []):
        #return [self.__l[0]]
        candidates = []
        for cand in self.__l:
            if set(requires).issubset(cand.provides):
                candidates.append(cand)
        return candidates

    def __str__(self):
        return string.join([str(t) + '\n' for t in self.__l])

    def __getitem__(self, i):
        return self.__l[i]

    def get_list(self):
        return self.__l


class FacadeManager(TextureManager):
    def find_matching(self, requires, building_height):
        candidates = self.find_candidates(requires, building_height)
        if len(candidates) == 0:
            print "WARNING: no matching texture for <%s>", requires
            return None
        return candidates[random.randint(0, len(candidates)-1)]

    def find_candidates(self, requires, building_height):
        candidates = TextureManager.find_candidates(self, requires)
#        print "\ncands", [str(t.filename) for t in candidates]
        # -- check height
#        print " Candidates:"
        new_candidates = []
        for t in candidates:
#            print "  <<<", t.filename
#            print "     building_height", building_height
#            print "     min/max", t.height_min, t.height_max
            if building_height < t.height_min or building_height > t.height_max:
#                print "  KICKED"
                continue
            new_candidates.append(t)

#                candidates.remove(t)
#        print "remaining cands", [str(t.filename) for t in new_candidates]
        return new_candidates


#
#
#tex_facade = facades.find_matching(building_height, ["shape:residential", "age:modern"])
#tex_roof = roofs.find_matching(tex_facade.requires+["shape:flat"])



def find_matching_texture(cls, textures):
    candidates = []
    for t in textures:
        if t.cls == cls: candidates.append(t)
    if len(candidates) == 0: return None
    return candidates[random.randint(0, len(candidates)-1)]

class Texture(object):
#    def __init__(self, filename, h_min, h_max, h_size, h_splits, \
#                                 v_min, v_max, v_size, v_splits, \
#                                 has_roof_section):
    """
    possible texture types:
        - facade
        - roof

    facade:
      provides
        - shape:skyscraper
        - shape:residential
        - shape:commercial/business
        - shape:industrial
        - age:modern/old
        - color: white
        - region: europe-middle
        - region: europe-north
        - minlevels: 2
        - maxlevels: 4
      requires
        - roof:shape:flat
        - roof:color:red|black

    roof:
      provides
        - color:black (red, ..)
        - shape:flat  (pitched, ..)

    """
    def __init__(self, filename,
                 h_size_meters, h_splits, h_can_repeat, \
                 v_size_meters, v_splits, v_can_repeat, \
                 has_roof_section = False, \
                 height_min = 0, height_max = 9999, \
                 v_split_from_bottom = False, \
                 provides = [], requires = []):
        self.filename = filename
        self.x0 = self.x1 = self.y0 = self.y1 = 0
        self.sy = self.sx = 0
        self.rotated = False
        self.provides = provides
        self.requires = requires
        self.has_roof_section = has_roof_section
        self.height_min = height_min
        self.height_max = height_max
        self.v_split_from_bottom = v_split_from_bottom
        # roof type, color
#        self.v_min = v_min
#        self.v_max = v_max
        self.v_size_meters = v_size_meters
        if v_splits != None:
            v_splits.insert(0,0)
            self.v_splits = np.array(v_splits, dtype=np.float)
            if len(self.v_splits) > 1:
                # FIXME            test for not type list
                self.v_splits /= self.v_splits[-1]
#                print self.v_splits
                # -- Gimp origin is upper left, convert to OpenGL lower left
                self.v_splits = (1. - self.v_splits)[::-1]
#                print self.v_splits
        else:
            self.v_splits = 1.
        self.v_splits_meters = self.v_splits * self.v_size_meters

        self.v_can_repeat = v_can_repeat

        if not self.v_can_repeat:
            self.height_min = self.v_splits_meters[0]
            self.height_max = self.v_size_meters

#        self.h_min = h_min
#        self.h_max = h_max
        self.h_size_meters = h_size_meters
        self.h_splits = np.array(h_splits, dtype=np.float)
        print "h1", self.h_splits
        print "h2", h_splits

        if h_splits == None or h_splits == []:
            self.h_splits = np.array([1.])
        elif len(self.h_splits) > 1:
            self.h_splits /= self.h_splits[-1]
        self.h_splits_meters = self.h_splits * self.h_size_meters
        self.h_can_repeat = h_can_repeat

        if self.h_can_repeat + self.v_can_repeat > 1:
            raise ValueError('%s: Textures can repeat in one direction only. '\
              'Please set either h_can_repeat or v_can_repeat to False.' % self.filename)

    def x(self, x):
        """given non-dimensional texture coord, return position in atlas"""
        #print "xx==", (self.x0 + x*self.sx)
        return self.x0 + x * self.sx

    def y(self, y):
        """given non-dimensional texture coord, return position in atlas"""
        #print "yy==", (self.y0 + y*self.sy)
        return self.y0 + y * self.sy

    def __str__(self):
        return "<%s> x0,1 %4.2f %4.2f  y0,1 %4.2f %4.2f  sh,v %4.2fm %4.2fm" % \
                (self.filename, self.x0, self.x1, self.y0, self.y1, \
                 self.h_size_meters, self.v_size_meters)
        # self.type = type
        # commercial-
        # - warehouse
        # - skyscraper
        # industrial
        # residential
        # - old
        # - modern
        # european, north_american, south_american, mediterreanian, african, asian
    def closest_h_match(self, frac):
        return self.h_splits[np.abs(self.h_splits - frac).argmin()]
        #self.h_splits[np.abs(self.h_splits - frac).argmin()]
        #bla

# pitched roof: requires = facade:age:old

def init():
    print "textures: init"
    global facades
    global roofs
    facades = FacadeManager('facade')
    roofs = TextureManager('roof')

    if True:
#        facades.append(Texture('tex/DSCF9495_pow2',
#                                14, [585, 873, 1179, 1480, 2048], True,
#                                19.4, [274, 676, 1114, 1542, 2048], False, True,
#                                requires=['roof:color:black'],
#                                provides=['shape:residential','age:old','compat:roof-flat','compat:roof-pitched']))

#                                19.4, [1094, 1531, 2048], False, True,

        facades.append(Texture('tex/DSCF9495_pow2.png',
                                14, [585, 873, 1179, 1480, 2048], True,
                                19.4, [274, 676, 1114, 1542, 2048], False, True,
                                height_max = 13.,
                                v_split_from_bottom = True,
                                requires=['roof:color:red'],
                                provides=['shape:residential','age:old','compat:roof-flat','compat:roof-pitched']))
    if True:

        # -- just two windows. Looks rather boring. But maybe we need a very narrow texture?
    #    facades.append(Texture('tex/DSCF9496_pow2',
    #                            4.44, None, True,
    #                            17.93, (1099, 1521, 2048), False, True,
    #                            requires=['roof:color:black'],
    #                            provides=['shape:residential','age:old','compat:roof-flat','compat:roof-pitched']))

        facades.append(Texture('tex/LZ_old_bright_bc2.png',
                                17.9, [345,807,1023,1236,1452,1686,2048], True,
                                14.8, [558,1005,1446,2048], False, True,
                                provides=['shape:residential','age:old','compat:roof-flat','compat:roof-pitched']))

        facades.append(Texture('tex/facade_modern_21x42m.jpg',
            43., [40, 79, 115, 156, 196, 235, 273, 312, 351, 389, 428, 468, 507, 545, 584, 624, 662], True,
            88., [667, 597, 530, 460, 391, 322, 254, 185, 117, 48, 736, 804, 873, 943, 1012, 1080, 1151, 1218, 1288, 1350], False, True,
            v_split_from_bottom = True,
            requires=[],
            provides=['shape:urban','age:modern', 'compat:roof-flat']))

        facades.append(Texture('tex/facade_modern_black_46x60m.jpg',
            45.9, [167, 345, 521, 700, 873, 944], True,
            60.5, [144, 229, 311, 393, 480, 562, 645, 732, 818, 901, 983, 1067, 1154, 1245], False, True,
            v_split_from_bottom = True,
            requires=[],
            provides=['shape:urban','age:modern', 'compat:roof-flat']))

        facades.append(Texture('tex/facade_modern36x36_12.png',
                                36., [], True,
                                36., [158, 234, 312, 388, 465, 542, 619, 697, 773, 870, 1024], False, True,
                                provides=['shape:urban','shape:residential','age:modern',
                                         'compat:roof-flat']))

    #    facades.append(Texture('tex/DSCF9503_pow2',
    #                            12.85, None, True,
    #                            17.66, (1168, 1560, 2048), False, True,
    #                            requires=['roof:color:black'],
    #                            provides=['shape:residential','age:old','compat:roof-flat','compat:roof-pitched']))
        facades.append(Texture('tex/DSCF9503_noroofsec_pow2.png',
                                12.85, [360, 708, 1044, 1392, 2048], True,
                                17.66, [556,1015,1474,2048], False, True,
                                requires=['roof:color:black'],
                                provides=['shape:residential','age:old','compat:roof-flat','compat:roof-pitched']))

    # -- this just looks ugly
    #    facades.append(Texture('tex/facade_modern1',
    #                           2.5, None, True,
    #                           2.8, None, True,
    #                           height_min = 15.,
    #                           provides=['shape:urban','shape:residential','age:modern',
    #                                     'compat:roof-flat']))

    #    facades.append(Texture('tex/DSCF9710_pow2',
    #                           29.9, (284,556,874,1180,1512,1780,2048), True,
    #                           19.8, (173,329,490,645,791,1024), False, True,
    #                           provides=['shape:residential','age:old','compat:roof-flat','compat:roof-pitched']))

        facades.append(Texture('tex/DSCF9710.png',
                               29.9, [142,278,437,590,756,890,1024], True,
                               19.8, [130,216,297,387,512], False, True,
                               provides=['shape:residential','age:old','compat:roof-flat','compat:roof-pitched']))


        facades.append(Texture('tex/DSCF9678_pow2.png',
                               10.4, [97,152,210,299,355,411,512], True,
                               15.5, [132,211,310,512], False, True,
                               provides=['shape:residential','shape:commercial','age:modern','compat:roof-flat']))

        facades.append(Texture('tex/DSCF9726_noroofsec_pow2.png',
                               15.1, [321,703,1024], True,
                               9.6, [227,512], False, True,
                               provides=['shape:residential','age:old','compat:roof-flat','compat:roof-pitched']))

        facades.append(Texture('tex/wohnheime_petersburger.png',
                                15.6, [215, 414, 614, 814, 1024], False,
                                15.6, [112, 295, 477, 660, 843, 1024], True, True,
                                height_min = 15.,
                                provides=['shape:urban','shape:residential','age:modern',
                                         'compat:roof-flat']))
    #                            provides=['shape:urban','shape:residential','age:modern','age:old',
    #                                     'compat:roof-flat','compat:roof-pitched']))


#    roofs.append(Texture('tex/roof_tiled_black',
#                         1., [], True, 1., [], False, provides=['color:black']))
#    roofs.append(Texture('tex/roof_tiled_red',
#                         1., [], True, 1., [], False, provides=['color:red']))
    roofs.append(Texture('tex/roof_red_1.png',
                         31.8, [], True, 16.1, [], False, provides=['color:red', 'compat:roof-pitched']))
    roofs.append(Texture('tex/roof_black_1.png',
                         31.8, [], True, 16.1, [], False, provides=['color:black', 'compat:roof-pitched']))
    roofs.append(Texture('tex/roof_black4.jpg',
                         6., [], True, 3.5, [], False, provides=['color:black', 'compat:roof-pitched']))
    roofs.append(Texture('tex/roof_gen_black_1.png',
                         100., [], True, 100., [], False, provides=['color:red', 'compat:roof-flat']))
    roofs.append(Texture('tex/roof_gen_black_1.png',
                         100., [], True, 100., [], False, provides=['color:black', 'compat:roof-flat']))

#    roofs.append(Texture('tex/roof_black2',
#                             1.39, [], True, 0.89, [], True, provides=['color:black']))
#    roofs.append(Texture('tex/roof_black3',
#                             0.6, [], True, 0.41, [], True, provides=['color:black']))

#    roofs.append(Texture('tex/roof_black3_small_256x128',
#                             0.25, [], True, 0.12, [], True, provides=['color:black']))

    if False:
        print roofs[0].provides
        print "black roofs: ", [str(i) for i in roofs.find_candidates(['roof:color:black'])]
        print "red   roofs: ", [str(i) for i in roofs.find_candidates(['roof:color:red'])]
        print "old facades: "
        for i in facades.find_candidates(['facade:shape:residential','age:old'], 10):
            print i, i.v_splits * i.v_size_meters
    #print facades[0].provides

    if False:
        facades = FacadeManager('facade')
        roofs = TextureManager('roof')
        facades.append(Texture('tex/test.png',
                               10, [142,278,437,590,756,890,1024], True,
                               10, [130,216,297,387,512], True, True,
                               provides=['shape:urban','shape:residential','age:modern','age:old','compat:roof-flat','compat:roof-pitched']))
        roofs.append(Texture('tex/test.png',
                             10., [], True, 10., [], True, provides=['color:black', 'color:red']))

    # -- make texture atlas (or unpickle)
    filename = 'atlas_facades'
    pkl_fname = filename + '.pkl'
    if 1:
#        facades.make_texture_atlas(filename + '.png')
        texture_list = facades.get_list() + roofs.get_list()
        make_texture_atlas(texture_list, filename + '.png')

        logging.info("Saving %s", pkl_fname)
        fpickle = open(pkl_fname, 'wb')
        cPickle.dump(facades, fpickle, -1)
        fpickle.close()
    else:
        logging.info("Loading %s", pkl_fname)
        fpickle = open(pkl_fname, 'rb')
        facades = cPickle.load(fpickle)
        fpickle.close()

    logging.info(facades)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    init()

    cands = facades.find_candidates([], 14)
    print "cands are", cands
    for t in cands:
        #print "%5.2g  %s" % (t.height_min, t.filename)
        logging.debug('%s (%4.2f, %4.2f) (%4.2f, %4.2f)' % (t.filename, t.x0, t.y0, t.x1, t.y1))

