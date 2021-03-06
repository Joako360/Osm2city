import logging
import os
from PIL import Image
import random
import re
from typing import Dict, List, Optional

import numpy as np

from osm2city import parameters
from osm2city.textures.materials import screen_texture_tags_for_colour_spelling, map_hex_colour
from osm2city.static_types import osmstrings as s
from osm2city.utils.utilities import replace_with_os_separator, Stats


class Texture(object):

    tex_prefix = ''  # static variable to reduce the dynamic path info the texture registrations. Needs to be set first.
    """
    spelling used internally in osm2city and in many cases automatically converted:
        - colour (instead of color)
        - gray (instead of grey)

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
        - roof:colour:red|black

    roof: http://wiki.openstreetmap.org/wiki/Simple_3D_buildings#Roof
      provides
        - colour:black (red, ..)
        - shape:flat  (pitched, ..)

    """
    def __init__(self, filename: str,
                 h_size_meters=None, h_cuts=None, h_can_repeat=False,
                 v_size_meters=None, v_cuts=None, v_can_repeat=False,
                 height_min=0, height_max=9999,
                 v_align_bottom: bool = False,
                 provides=None, requires=None, levels=None) -> None:
        # assert lists if None
        if h_cuts is None:
            h_cuts = list()
        if v_cuts is None:
            v_cuts = list()
        if provides is None:
            provides = list()
        if requires is None:
            requires = list()
        self.filename = os.path.join(Texture.tex_prefix, replace_with_os_separator(filename))
        self.x0 = self.x1 = self.y0 = self.y1 = 0
        self.sy = self.sx = 0
        self.rotated = False
        self.provides = provides
        self._parse_region()
        self.requires = requires
        self.height_min = height_min
        self.height_max = height_max
        self.width_min = 0
        self.width_max = 9999
        self.v_align_bottom = v_align_bottom
        h_cuts.sort()
        v_cuts.sort()
        self.ax = 0  # coordinate in atlas (int)
        self.ay = 0
        self.validation_message = None
        self.registered_in = None  # filename of the .py file, where this texture has been referenced
        self.cls = ''  # The class of the texture depends on the manager: 'roof' or 'facade'

        self.im = None
        self.im_LM = None  # is only set when processing texture atlas
        try:
            self.im = Image.open(self.filename)
        except IOError:
            self.validation_message = "Skipping non-existing texture %s" % self.filename
            return
        self.width_px, self.height_px = self.im.size
        image_aspect = self.height_px / float(self.width_px)

        if v_size_meters:
            if levels:
                logging.warning("Ignoring levels=%g because v_size_meters=%g is given for texture %s."
                                % (levels, v_size_meters, filename))
            self.v_size_meters = v_size_meters
        else:
            if not levels:
                logging.warning("Ignoring texture %s because neither v_size_meters nor levels is given"
                                % filename)
                # Set filename to "" to make TextureManger reject us. Bad style, but raising
                # an exception instead would prohibit the nice, simple structure of catalog.py
                self.filename = "" 
                return
            else:
                self.v_size_meters = levels * 3.3  # FIXME: this should be configurable
            
        if h_size_meters: 
            self.h_size_meters = h_size_meters
        else:
            self.h_size_meters = self.v_size_meters / image_aspect
            logging.debug("No hsize, using image aspect %i x %i = %g. h_size = %g v_size = %g" %
                          (self.width_px, self.height_px, image_aspect, self.h_size_meters, self.v_size_meters))
            
        # aspect = v / h
        if len(v_cuts) == 0:
            v_cuts = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
            
        if v_cuts is not None:
            v_cuts.insert(0, 0)
            self.v_cuts = np.array(v_cuts, dtype=np.float)
            if len(self.v_cuts) > 1:
                # FIXME: test for not type list
                self.v_cuts /= self.v_cuts[-1]
                # -- Gimp origin is upper left, convert to OpenGL lower left
                self.v_cuts = (1. - self.v_cuts)[::-1]
        else:
            self.v_cuts = 1.
        self.v_cuts_meters = self.v_cuts * self.v_size_meters

        self.v_can_repeat = v_can_repeat

        if not self.v_can_repeat:
            self.height_min = self.v_cuts_meters[0]
            self.height_max = self.v_size_meters

        if len(h_cuts) == 0:
            h_cuts = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

        self.h_cuts = np.array(h_cuts, dtype=np.float)

        if h_cuts is None:
            self.h_cuts = np.array([1.])
        elif len(self.h_cuts) > 1:
            self.h_cuts /= self.h_cuts[-1]
        self.h_cuts_meters = self.h_cuts * self.h_size_meters
        self.h_can_repeat = h_can_repeat

        if not self.h_can_repeat:
            self.width_min = self.h_cuts_meters[0]
            self.width_max = self.h_size_meters

        if self.h_can_repeat + self.v_can_repeat > 1:
            self.validation_message = '%s: Textures can repeat in one direction only. \
Please set either h_can_repeat or v_can_repeat to False.' % self.filename

    def x(self, x):
        """given non-dimensional texture coord, return position in atlas"""
        if self.rotated:
            return self.y0 + x * self.sy
        else:
            return self.x0 + x * self.sx

    def y(self, y):
        """given non-dimensional texture coord, return position in atlas"""
        if self.rotated:
            return self.x0 + y * self.sx
        else:
            return self.y0 + y * self.sy

    def __str__(self):
        return '<%s> x0=%4.2f x1=%4.2f - y0=%4.3f y1=%4.3f - sh=%4.2fm sv=%4.2fm - ax=%d ay=%d' % \
               (self.filename,
                self.x0, self.x1,
                self.y0, self.y1,
                self.h_size_meters, self.v_size_meters,
                self.ax, self.ay)
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
        return self.h_cuts[np.abs(self.h_cuts - frac).argmin()]

    def _parse_region(self) -> None:
        """Parses its filename to find out, which region it is and then adds it to self.provides."""
        my_region = "generic"
        specific_name = self.filename[len(Texture.tex_prefix) + 1:]
        index = specific_name.find(os.sep)
        if index > 0:
            my_region = specific_name[:index]
        self.provides.append("region:" + my_region)


class RoofManager(object):
    def __init__(self, cls: str, stats: Stats):
        self.__l = []
        self.__cls = cls  # -- class (roof, facade, ...)
        self.stats = stats
        self.current_registered_in = ""
        self.available_materials = set()

    def append(self, texture: Texture) -> None:
        """Appends a texture to the catalog if the referenced file exists and other tests pass.
        

        Prepend each item in t.provides with class name, except for class-independent keywords: age, region, compat
        """
        # check whether already during initialization an error occurred
        if texture.validation_message:
            logging.warning("Error during initialization. Defined in registration file %s: %s",
                            self.current_registered_in, texture.validation_message)
            return

        texture.registered_in = self.current_registered_in

        # check whether the texture should be excluded based on parameter for name
        if not self._screen_exclude_texture_by_name(texture):
            return

        if not self._screen_exclude_texture_by_region(texture):
            return

        # check whether the same texture already has been referenced in an existing entry
        for existing in self.__l:
            if existing.filename == texture.filename:
                logging.warning("Double registration. Defined in registration file %s: %s is already referenced in %s",
                                self.current_registered_in, texture.filename, existing.registered_in)
                return

        new_provides = list()
        my_available_materials = list()
        logging.debug("Based on registration file %s: added %s ", self.current_registered_in, texture.filename)
        for item in texture.provides:
            screened_item = screen_texture_tags_for_colour_spelling(item)
            if not self._screen_exclude_texture_by_provides(screened_item):
                return
            if screened_item.split(':')[0] in ('age', 'region', 'compat'):
                new_provides.append(screened_item)
            else:
                if screened_item.split(":")[0] == "material":
                    my_available_materials.append(screened_item.split(":")[1])
                new_provides.append(self.__cls + ':' + screened_item)
        texture.provides = new_provides
        new_requires = list()
        for item in texture.requires:
            new_requires.append(screen_texture_tags_for_colour_spelling(item))
        texture.requires = new_requires
        self.available_materials.update(my_available_materials)
        texture.cls = self.__cls

        self.stats.textures_total[texture.filename] = None
        self.__l.append(texture)
        return

    def find_by_file_name(self, file_name: str) -> Optional[Texture]:
        for candidate in self.__l:
            if file_name in candidate.filename:
                return candidate
        return None  # nothing found

    def _screen_exclude_texture_by_name(self, texture: Texture) -> bool:
        if isinstance(self, FacadeManager):
            if parameters.TEXTURES_FACADES_NAME_EXCLUDE:
                for a_facade_path in parameters.TEXTURES_FACADES_NAME_EXCLUDE:
                    if texture.filename.rfind(a_facade_path) >= 0:
                        return False
        else:
            if parameters.TEXTURES_ROOFS_NAME_EXCLUDE:
                for a_roof_path in parameters.TEXTURES_ROOFS_NAME_EXCLUDE:
                    if texture.filename.rfind(a_roof_path) >= 0:
                        return False
        return True

    def _screen_exclude_texture_by_provides(self, provided_feature: str) -> bool:
        if isinstance(self, FacadeManager):
            if parameters.TEXTURES_FACADES_PROVIDE_EXCLUDE:
                for a_feature in parameters.TEXTURES_FACADES_PROVIDE_EXCLUDE:
                    if screen_texture_tags_for_colour_spelling(a_feature) == provided_feature:
                        return False
        else:
            if parameters.TEXTURES_ROOFS_PROVIDE_EXCLUDE:
                for a_feature in parameters.TEXTURES_ROOFS_PROVIDE_EXCLUDE:
                    if screen_texture_tags_for_colour_spelling(a_feature) == provided_feature:
                        return False
        return True

    def _screen_exclude_texture_by_region(self, texture: Texture) -> bool:
        if isinstance(self, FacadeManager):
            if parameters.TEXTURES_REGIONS_EXPLICIT:
                for feature in texture.provides:
                    for region in parameters.TEXTURES_REGIONS_EXPLICIT:
                        if len(feature) > 7 and feature[7:] == region:  # [:7] because "region:gb" in texture.provides
                            return True
                return False
        return True

    def find_matching_roof(self, requires: List[str], max_dimension: float, stats: Stats):
        candidates = self.find_candidates(requires, list())
        if not candidates:
            logging.debug("WARNING: No matching texture found for %s with max_dim %d", str(requires), max_dimension)
            # Break down requirements to find something that matches
            for simple_req in requires:
                candidates = self.find_candidates([simple_req], list())
                self._screen_grass_and_glass(candidates, requires)
                if candidates:
                    break
                if not candidates:
                    # Now we're really desperate - just find something!
                    candidates = self.find_candidates(['compat:roof-large'], list())
        if "compat:roof-flat" not in requires:
            the_texture = candidates[random.randint(0, len(candidates) - 1)]
        else:  # for flat roofs make sure that a candidate texture that can be found with enough length/width
            max_dim_candidates = list()
            for candidate in candidates:
                if not candidate.h_can_repeat and candidate.h_size_meters < max_dimension:
                    continue
                if not candidate.v_can_repeat and candidate.v_size_meters < max_dimension:
                    continue
                max_dim_candidates.append(candidate)
            if max_dim_candidates:
                the_texture = max_dim_candidates[random.randint(0, len(max_dim_candidates)-1)]
            else:
                # now we do not care about colour, material etc. Just pick a
                fallback_candidates = self.find_candidates(['compat:roof-large'], list())
                final_candidates = list()
                if not fallback_candidates:
                    logging.error("Large roof required, but no roof texture providing 'compat:roof-large' found.")
                    exit(1)
                for candidate in fallback_candidates:
                    if not candidate.h_can_repeat and candidate.h_size_meters < max_dimension:
                        continue
                    if not candidate.v_can_repeat and candidate.v_size_meters < max_dimension:
                        continue
                    final_candidates.append(candidate)
                if final_candidates:
                    the_texture = final_candidates[random.randint(0, len(final_candidates) - 1)]
                else:  # give up and live with some visual residuals instead of excluding the building
                    the_texture = fallback_candidates[random.randint(0, len(fallback_candidates) - 1)]
        stats.count_texture(the_texture)
        return the_texture

    @staticmethod
    def _screen_grass_and_glass(candidates: List[Texture], requires: List[str]) -> None:
        """Special case handling of grass and glass so they get excluded unless really requested.

        This does only work with the Spring 2020 atlas having specific roof textures that match this pattern!"""
        for candidate in reversed(candidates):
            if 'roof:roof:material:grass' in candidate.provides and 'roof:material:grass' not in requires:
                candidates.remove(candidate)
            elif 'roof:roof:material:glass' in candidate.provides and 'roof:material:glass' not in requires:
                candidates.remove(candidate)

    def find_candidates(self, requires: List[str], excludes: List[str]):
        candidates = []
        # replace known hex colour codes
        requires = list(map_hex_colour(value) for value in requires)
        can_use = True
        for candidate in self.__l:
            for ex in excludes:
                # check if we maybe have a tag that doesn't match a requires
                ex_material_key = 'XXX'
                ex_colour_key = 'XXX'
                ex_material = ''
                ex_colour = ''
                if re.match('^.*material:.*', ex):
                    ex_material_key = re.match('(^.*:material:)[^:]*', ex).group(1)
                    ex_material = re.match('^.*material:([^:]*)', ex).group(1)
                elif re.match('^.*:colour:.*', ex):
                    ex_colour_key = re.match('(^.*:colour:)[^:]*', ex).group(1)
                    ex_colour = re.match('^.*:colour:([^:]*)', ex).group(1)
                for req in candidate.requires:
                    if req.startswith(ex_colour_key) and ex_colour is not re.match('^.*:colour:(.*)', req).group(1):
                        can_use = False
                    if req.startswith(ex_material_key) and ex_material is not re.match('^.*:material:(.*)',
                                                                                       req).group(1):
                        can_use = False

            if set(requires).issubset(candidate.provides):
                # Check for "specific" texture in order they do not pollute everything
                if ('facade:specific' in candidate.provides) or ('roof:specific' in candidate.provides):
                    can_use = False
                    req_material = None
                    req_colour = None
                    for req in requires:
                        if re.match('^.*material:.*', req):
                            req_material = re.match('^.*material:(.*)', req).group(0)
                        elif re.match('^.*:colour:.*', req):
                            req_colour = re.match('^.*:colour:(.*)', req).group(0)

                    prov_materials = []
                    prov_colours = []
                    for prov in candidate.provides:
                        if re.match('^.*:material:.*', prov):
                            prov_material = re.match('^.*:material:(.*)', prov).group(0)
                            prov_materials.append(prov_material)
                        elif re.match('^.*:colour:.*', prov):
                            prov_colour = re.match('^.*:colour:(.*)', prov).group(0)
                            prov_colours.append(prov_colour)

                    # req_material and colour
                    can_material = False
                    if req_material is not None:
                        for prov_material in prov_materials:
                            logging.debug('Provides: %s; requires: %s', prov_material, requires)
                            if prov_material in requires:
                                can_material = True
                                break
                    else:
                        can_material = True

                    can_colour = False
                    if req_colour is not None:
                        for prov_colour in prov_colours:
                            if prov_colour in requires:
                                can_colour = True
                                break
                    else:
                        can_colour = True

                    if can_material and can_colour:
                        can_use = True

                if can_use:
                    candidates.append(candidate)
            else:
                logging.debug("  unmet requires %s req %s prov %s",
                              str(candidate.filename), str(requires), str(candidate.provides))
        return candidates

    def __str__(self):
        start = 'Textures of type %s with %d of elements:\n' % (self.__cls, len(self.__l))
        return start + "".join([str(t) + '\n' for t in self.__l])

    def __getitem__(self, i):
        return self.__l[i]

    def get_list(self):
        return self.__l


class FacadeManager(RoofManager):
    def find_matching_facade(self, requires: List[str], tags: Dict[str, str], height: float, width: float,
                             stats: Stats=None) -> Optional[Texture]:
        if s.K_AEROWAY in tags:
            return self._find_aeroway_facade(tags)

        exclusions = []
        # if 'roof:colour' in tags: FIXME why would we need this at all?
        # exclusions.append("%s:%s" % ('roof:colour', tags['roof:colour']))
        candidates = self.find_facade_candidates(requires, exclusions, height, width)
        if not candidates:
            # Break down requirements to something that matches
            for simple_req in requires:
                candidates = self.find_facade_candidates([simple_req], exclusions, height, width)
                if candidates:
                    break
            if not candidates:
                # Now we're really desperate - just find something!
                candidates = self.find_facade_candidates(['compat:roof-flat'], exclusions, height, width)
            if not candidates:
                logging.debug("WARNING: no matching facade texture for %1.f m x %1.1f m <%s>",
                              height, width, str(requires))
                return None
        ranked_list = _rank_candidates(candidates, tags)
        the_texture = ranked_list[random.randint(0, len(ranked_list) - 1)]
        if stats is not None:
            stats.count_texture(the_texture)
        return the_texture

    def find_facade_candidates(self, requires: List[str], excludes: List[str], height: float, width: float)\
            -> List[Texture]:
        candidates = RoofManager.find_candidates(self, requires, excludes)
        # -- check height
        new_candidates = []
        for t in candidates:
            if height < t.height_min or height > t.height_max:
                logging.debug("height %.2f (%.2f-%.2f) outside bounds : %s",
                              height, t.height_min, t.height_max, str(t.filename))
                continue
            if width < t.width_min or width > t.width_max:
                logging.debug("width %.2f (%.2f-%.2f) outside bounds : %s",
                              width, t.width_min, t.width_max, str(t.filename))
                continue

            new_candidates.append(t)
        return new_candidates

    TERMINAL_TEX = 'facade_modern_commercial_35x20m.jpg'
    HANGAR_TEX = 'facade_industrial_red_white_24x18m.jpg'
    OTHER_TEX = 'facade_modern_commercial_red_gray_20x14m.jpg'

    def _find_aeroway_facade(self, tags: Dict[str, str]) -> Optional[Texture]:
        """A little hack to get facades that match a bit an airport."""
        if s.V_HANGAR in tags:
            chosen_tex = self.HANGAR_TEX
        elif s.V_TERMINAL in tags:
            chosen_tex = self.TERMINAL_TEX
        else:
            if random.randint(0, 1) == 0:
                chosen_tex = self.TERMINAL_TEX
            else:
                chosen_tex = self.OTHER_TEX
        return RoofManager.find_by_file_name(self, chosen_tex)


class SpecialManager(RoofManager):
    """Manager for all those textures, which are specific for a given ac-file or so."""
    def find_matching(self, tex_path: str) -> Texture:
        pass


def _rank_candidates(candidates, tags):
    ranked_list = []
    for t in candidates:
        match = 0
        if 'building:material' in tags:
            val = tags['building:material']
            new_key = "facade:building:material:%s" % val
            if new_key in t.provides:
                match += 1
        ranked_list.append([match, t])
    ranked_list.sort(key=lambda tup: tup[0], reverse=True)
    max_val = ranked_list[0][0]
    if max_val > 0:
        logging.info("Max Rank %d" % max_val)
    return [t[1] for t in ranked_list if t[0] >= max_val]
