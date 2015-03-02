#!/usr/bin/env python
import string
import matplotlib.pyplot as plt
import logging
from pdb import pm

from pyparsing import Literal, Word, quotedString, alphas, Optional, OneOrMore, \
    Group, ParseException, nums, Combine, Regex, alphanums, LineEnd

fmt_node = '%1.6f'

class Node(object):
    def __init__(self, x, y, z):
        self.x = x
        self.y = y
        self.z = z
    def __str__(self):
        return (fmt_node + ' ' + fmt_node + ' ' + fmt_node + '\n') % (self.x, self.y, self.z)

class Face(object):
    """if our texture is rotated in texture_atlas, set swap_uv=True"""
    def __init__(self, nodes_uv_list, typ, mat, swap_uv):
        assert len(nodes_uv_list) >= 2
        for n in nodes_uv_list:
            assert len(n) == 3
        if swap_uv:
            nodes_uv_list = [(n[0], n[2], n[1]) for n in nodes_uv_list]
        self.nodes_uv_list = nodes_uv_list
        self.typ = typ
        self.mat = mat

    def __str__(self):
        s = "SURF %s\n" % self.typ
        s += "mat %i\n" % self.mat
        s += "refs %i\n" % len(self.nodes_uv_list)
        s += string.join(["%i %1.4g %1.4g\n" % (n[0], n[1], n[2]) for n in self.nodes_uv_list], '')
        return s


class Object(object):
    """An object (3D) in a AC3D filed with faces and nodes"""
    def __init__(self, name, stats=None, texture=None, default_type=0x0, default_mat=0, default_swap_uv=False):
        self._nodes = []
        self._faces = []
        self.name = str(name)
        assert name != ""
        self.stats = stats
        self.texture = texture
        self.default_type = default_type
        self.default_mat = default_mat
        self.default_swap_uv = default_swap_uv

    def close(self):
        pass

    def node(self, x, y, z):
        """Add new node. Return its index."""
        self._nodes.append(Node(x, y, z))
        if self.stats:
            self.stats.vertices += 1
        return len(self._nodes) - 1

    def next_node_index(self):
        return len(self._nodes)

    def face(self, nodes_uv_list, typ=None, mat=None, swap_uv=None):
        """Add new face. Return its index."""
        if not typ:
            typ = self.default_type
        if not mat:
            mat = self.default_mat
        if not swap_uv:
            swap_uv = self.default_swap_uv
        self._faces.append(Face(nodes_uv_list, typ, mat, swap_uv))
        if self.stats:
            self.stats.surfaces += 1
        return len(self._faces) - 1

    def is_empty(self):
        return not self._nodes

    def __str__(self):
        s = 'OBJECT poly\n'
        s += 'name "%s"\n' % self.name
        if self.texture:
            s += 'texture "%s"\n' %self.texture
        s += 'numvert %i\n' % len(self._nodes)
        s += string.join([str(n) for n in self._nodes], '')
        s += 'numsurf %i\n' % len(self._faces)
        s += string.join([str(f) for f in self._faces], '')
        s += 'kids 0\n'
        return s

    def plot(self):
        """note: here, Z is height."""
        for f in self._faces:
            X = [self._nodes[n[0]].x for n in f.nodes_uv_list]
            Y = [self._nodes[n[0]].z for n in f.nodes_uv_list]
            Z = [self._nodes[n[0]].y for n in f.nodes_uv_list]
            X.append(self._nodes[f.nodes_uv_list[0][0]].x)
            Y.append(self._nodes[f.nodes_uv_list[0][0]].z)
            #Z.append(self._nodes[f.nodes_uv_list[0][0]].y)
            #if max(Z) > 1.: break
            #print "MAX", max(Z)
            plt.plot(X, Y, '-o')
            for i in range(len(X)-1):
                x = 0.5*(X[i] + X[i+1])
                y = 0.5*(Y[i] + Y[i+1])
                plt.text(x+Z[i], y+Z[i], "%i" % i)

class Label(Object):
    def __init__(self):
        super(Label, self).__init__('label', texture='tex/ascii.png')
        self.char_w = 1.
        self.char_h = 1.

    def add(self, text, x, y, z, orientation=0, scale=1.):
        h = self.char_h * scale
        w = self.char_w * scale
        for c in str(text):
            code = ord(c) - 32
            if code < 0 or code > 126-32:
                logging.warning('Ignoring character %s' % c)
                continue
            cw = 1/95.
            u0 = code * cw - cw*0.05
            u1 = u0 + cw
            v0 = 0
            v1 = 1
            if 1 or orientation == 0:
                o = self.next_node_index()
                self.node(x, y, z)
                self.node(x, y, z+w)
                self.node(x+h, y, z+w)
                self.node(x+h, y, z)
                self.face([(o,  u0,v0),
                           (o+1,u1,v0),
                           (o+2,u1,v1),
                           (o+3,u0,v1)])
                z += w

class Writer(object):
    """
    Hold a number of objects. Each object holds nodes and faces.
    Count nodes/surfaces etc internally, thereby eliminating a common source of bugs.
    Can also add 3d labels (useful for debugging, disabled by default)
    """
    def __init__(self, stats, show_labels = False):
        self.objects = []
        self.show_labels = show_labels
        self.stats = stats
        self._current_object = None
        self.label_object = None

    def new_object(self, name, texture, **kwargs):
        o = Object(name, self.stats, texture, **kwargs)
        self.objects.append(o)
        self._current_object = o
        return o
        
    def add_label(self, text, x, y, z, orientation=0, scale=1.):
        if not self.label_object:
            self.label_object = Label()
            if self.show_labels: self.objects.append(self.label_object)
        self.label_object.add(text, x, y, z, orientation, scale)
        return self.label_object

    def close_object(self):
        self._current_object.close()
        self._current_object = None

    def node(self, *args):
        return self._current_object.node(*args)

    def next_node_index(self):
        return self._current_object.next_node_index()

    def face(self, *args):
        return self._current_object.face(*args)

    def center(self):
        """translate all nodes such that the average is zero"""
        sum_x = sum_y = sum_z = n = 0
        for obj in self.objects:
            for node in obj._nodes:
                sum_x += node.x
                sum_y += node.y
                sum_z += node.z
                n += 1

        cx = float(sum_x) / n
        cy = float(sum_y) / n
        cz = float(sum_z) / n
        for obj in self.objects:
            for node in obj._nodes:
                node.x -= cx
                node.y -= cy
                node.z -= cz

    def __str__(self):
        s = 'AC3Db\n'
        s += 'MATERIAL "" rgb 1 1 1 amb 1 1 1 emis 0 0 0 spec 0.5 0.5 0.5 shi 64 trans 0\n'
#        s += 'MATERIAL "" rgb 1 1 1 amb 0.5 0.5 0.5 emis 1 1 1 spec 0.5 0.5 0.5 shi 64 trans 0\n'
        non_empty = [o for o in self.objects if not o.is_empty()]
        s += 'OBJECT world\nkids %i\n' % len(non_empty)
        s += string.join([str(o) for o in non_empty])
        return s

    def write_to_file(self, file_name):
        f = open(file_name + '.ac', 'w')
        f.write(str(self))
        f.close()

    def plot(self):
        non_empty = [o for o in self.objects if not o.is_empty()]
        for o in non_empty:
            o.plot()
    
    def parse(self):
        def convertObject(tokens):
            print "got tokens!", tokens
            print "--------"
            #bla
            #o = Object(name, self.stats, texture, **kwargs)
            #self.objects.append(o)
            #self._current_object = o
            #return o
        def convertLObj(tokens):
            #print "got LObj", tokens
            self.new_object(None, None)

        def convertLName(tokens):
            #print "got LName", tokens
            self._current_object.name = tokens[1].strip('"\'')

        def convertLTexture(tokens):
            #print "got LText", tokens
            self._current_object.texture = tokens[1].strip('"\'')

        def convertLTexrep(tokens):
            self._current_object.texrep = (tokens[0], tokens[1])

        def convertLRot(tokens):
            self._current_object.rot = tokens

        def convertLLoc(tokens):
            self._current_object.loc = (tokens[0], tokens[1], tokens[2])

        def convertLUrl(tokens):
            self._current_object.url = (tokens[0])

        def convertLVertex(tokens):
            #print "got LVert", tokens
            self._current_object.node(tokens[0], tokens[1], tokens[2])

        def convertSurf(tokens):
            #print "got Surf", tokens
            assert(tokens[0] == 'SURF')
            assert(tokens[2] == 'mat')
            assert(tokens[4] == 'refs')
            
            self._current_object.face(nodes_uv_list = tokens[6], typ = tokens[1], mat = tokens[3])

        def convertIntegers(tokens):
            return int(tokens[0])
        
        def convertFloats(tokens):
            return float(tokens[0])
            
        integer = Word( nums ).setParseAction( convertIntegers ) 
        floatNumber = Regex(r'[+-]?\d+(\.\d*)?([eE][+-]\d+)?').setParseAction( convertFloats )
        
        anything = Regex(r'.*')
        
        lHeader = Literal('AC3Db') + LineEnd()
        lObject = (Literal('OBJECT') + Word(alphas)).setParseAction(convertLObj)
        lKids = (Literal('kids') + integer).setResultsName('kids')
        lName = (Literal('name') + anything + LineEnd()).setParseAction(convertLName)
#        lData = (Literal('data') + anything + LineEnd()).setParseAction(convertLName)
        lTexture = (Literal('texture') + anything + LineEnd()).setParseAction(convertLTexture)
        lTexrep = (Literal('texrep') + floatNumber + floatNumber).setParseAction(convertLTexrep)
        lRot = (Literal('rot') + floatNumber + floatNumber + floatNumber + floatNumber + floatNumber + floatNumber + floatNumber + floatNumber + floatNumber).setParseAction(convertLRot)
        lLoc = (Literal('loc') + floatNumber + floatNumber + floatNumber).setParseAction(convertLLoc)
        lUrl = (Literal('url') + anything + LineEnd()).setParseAction(convertLUrl)
        lNumvert = Literal('numvert') + Word(nums)
        lVertex = (floatNumber + floatNumber + floatNumber).setParseAction(convertLVertex)
        lMaterial = Literal('MATERIAL') + anything + LineEnd()
        lNumsurf = Literal('numsurf') + Word(nums)
        lSurf = Literal('SURF') + Word(alphanums)
        lMat = Literal('mat') + integer
        lRefs = Literal('refs') + integer
        lNodes = Group(integer + floatNumber + floatNumber)
        
        pObjectWorld = Group(lObject + lKids)
        pSurf = (lSurf + Optional(lMat) + lRefs + Group(OneOrMore(lNodes))).setParseAction( convertSurf )
        pObject = Group(lObject + lName + Optional(lTexture) + Optional(lTexrep) \
          + Optional(lRot) + Optional(lLoc) + Optional(lUrl) \
          + lNumvert + Group(OneOrMore(lVertex)) \
          + Optional(lNumsurf + Group(OneOrMore(pSurf))) + lKids).setParseAction( convertObject ) 

        pFile = lHeader + Group(OneOrMore(lMaterial)) + pObjectWorld \
          + Group(OneOrMore(pObject))
        
        self.p = pFile.parseFile('big-hangar.ac')
    
        # todo: texrep rot loc url data
        # groups -- how do they work?
    
    
if __name__ == "__main__":
    a = Writer(None)
    a.parse()
    
    print "print\n", a

    if 0:
        a = Writer(None)
        a.new_object('bla', '')
        a.node(0,0,0)
        a.node(0,1,0)
        a.node(1,1,0)
        a.node(1,0,0)
        a.face([(0,0,0), (1,0,0), (2,0,0), (3,0,0)])
        print a

