"""Holds string constants for OSM keys and values."""

# ======================= KEYS ====================================
K_AERIALWAY = 'aerialway'
K_AEROWAY = 'aeroway'
K_AMENITY = 'amenity'
K_AREA = 'area'
K_BRIDGE = 'bridge'
K_BUILDING = 'building'
K_BUILDING_COLOUR = 'building:colour'
K_BUILDING_HEIGHT = 'building:height'
K_BUILDING_LEVELS = 'building:levels'
K_BUILDING_MATERIAL = 'building:material'
K_BUILDING_PART = 'building:part'
K_CABLES = 'cables'
K_CONTENT = 'content'
K_DENOMINATION = 'denomination'
K_ELECTRIFIED = 'electrified'
K_GAUGE = 'gauge'
K_GENERATOR_TYPE = 'generator:type'
K_HEIGHT = 'height'
K_HIGHWAY = 'highway'
K_INDOOR = 'indoor'
K_JUNCTION = 'junction'
K_LANDUSE = 'landuse'
K_LANES = 'lanes'
K_LAYER = 'layer'
K_LEISURE = 'leisure'
K_LEVEL = 'level'
K_LEVELS = 'levels'
K_LIT = 'lit'
K_LOCATION = 'location'
K_MAN_MADE = 'man_made'
K_MANUFACTURER = 'manufacturer'
K_MANUFACTURER_TYPE = 'manufacturer_type'
K_MATERIAL = 'material'
K_MILITARY = 'military'
K_MIN_HEIGHT = 'min_height'
K_MIN_HEIGHT_COLON = 'min:height'  # Incorrect value, but sometimes used
K_NAME = 'name'
K_NATURAL = 'natural'
K_OFFSHORE = 'offshore'
K_ONEWAY = 'oneway'
K_PARKING = 'parking'
K_PLACE = 'place'
K_PLACE_NAME = 'place_name'
K_POPULATION = 'population'
K_POWER = 'power'
K_PUBLIC_TRANSPORT = 'public_transport'
K_RAILWAY = 'railway'
K_RELIGION = 'religion'
K_ROOF_ANGLE = 'roof:angle'
K_ROOF_COLOUR = 'roof:colour'
K_ROOF_HEIGHT = 'roof:height'
K_ROOF_MATERIAL = 'roof:material'
K_ROOF_ORIENTATION = 'roof:orientation'
K_ROOF_SHAPE = 'roof:shape'
K_ROOF_SLOPE_DIRECTION = 'roof:slope:direction'
K_ROTOR_DIAMETER = 'rotor_diameter'
K_ROUTE = 'route'
K_SEAMARK_LANDMARK_HEIGHT = 'seamark:landmark:height'
K_SEAMARK_LANDMARK_STATUS = 'seamark:landmark:status'
K_SEAMARK_STATUS = 'seamark:status'
K_SERVICE = 'service'
K_STRUCTURE = 'structure'
K_TOURISM = 'tourism'
K_TRACKS = 'tracks'
K_TUNNEL = 'tunnel'
K_TYPE = 'type'
K_VOLTAGE = 'voltage'
K_WATERWAY = 'waterway'
K_WIKIDATA = 'wikidata'
K_WIRES = 'wires'

# ======================= VALUES ==================================
V_ABANDONED = 'abandoned'
V_ACROSS = 'across'
V_AERODROME = 'aerodrome'
V_AERO_OTHER = 'aero_other'  # does not exist in OSM - used when it is unsure whether terminal, hangar or different
V_ALONG = 'along'
V_APARTMENTS = 'apartments'
V_APRON = 'apron'
V_ATTACHED = 'attached'  # does not exist in OSM - used as a proxy for apartment buildings attached e.g. in cities
V_BOROUGH = 'borough'
V_BUNKER = 'bunker'
V_BRIDGE = 'bridge'
V_BUFFER_STOP = 'buffer_stop'
V_BUILDING = 'building'
V_CANAL = 'canal'
V_CATHEDRAL = 'cathedral'
V_CIRCULAR = 'circular'
V_CITY = 'city'
V_CHECKPOINT = 'checkpoint'
V_CHRISTIAN = 'christian'
V_CHURCH = 'church'
V_COASTLINE = 'coastline'
V_COMMERCIAL = 'commercial'
V_COMMUNICATIONS_TOWER = 'communications_tower'
V_CONSTRUCTION = 'construction'
V_CONTACT_LINE = 'contact_line'
V_DAM = 'dam'
V_DANGER_AREA = 'danger_area'
V_DETACHED = 'detached'
V_DISUSED = 'disused'
V_DOME = 'dome'
V_DYKE = 'dyke'
V_FLAT = 'flat'
V_FERRY = 'ferry'
V_FUEL_STORAGE_TANK = 'fuel_storage_tank'  # deprecated tag in OSM
V_FUNICULAR = 'funicular'
V_GABLED = 'gabled'
V_GAMBREL = 'gambrel'
V_GLASSHOUSE = 'glasshouse'
V_GREENHOUSE = 'greenhouse'
V_HALF_HIPPED = 'half-hipped'
V_HAMLET = 'hamlet'
V_HANGAR = 'hangar'
V_HELIPAD = 'helipad'
V_HELIPORT = 'heliport'
V_HIPPED = 'hipped'
V_HOSPITAL = 'hospital'
V_HOUSE = 'house'
V_INDOOR = 'indoor'
V_INDUSTRIAL = 'industrial'
V_INNER = 'inner'
V_ISOLATED_DWELLING = 'isolated_dwelling'
V_LEAN_TO = 'lean_to'
V_LIGHT_RAIL = 'light_rail'
V_LIGHTHOUSE = 'lighthouse'
V_MANSARD = 'mansard'
V_MARINA = 'marina'
V_MONORAIL = 'monorail'
V_MOTORWAY = 'motorway'
V_MULTIPOLYGON = 'multipolygon'
V_MULTISTOREY = 'multi-storey'
V_NARROW_GAUGE = 'narrow_gauge'
V_NAVAL_BASE = 'naval_base'
V_NO = 'no'
V_OFFSHORE_PLATFORM = 'offshore_platform'
V_OIL_TANK = 'oil_tank'  # deprecated tag in OSM
V_ONION = 'onion'
V_ORTHODOX = 'orthodox'
V_OUTER = 'outer'
V_OUTLINE = 'outline'
V_PARK = 'park'
V_PIER = 'pier'
V_PITCHED = 'pitched'
V_PLACE_OF_WORSHIP = 'place_of_worship'
V_PLANT = 'plant'
V_PLATFORM = 'platform'
V_PRESERVED = 'preserved'
V_PRIMARY = 'primary'
V_PYRAMIDAL = 'pyramidal'
V_RAIL = 'rail'
V_RAILWAY = 'railway'
V_RANGE = 'range'
V_RESIDENTIAL = 'residential'
V_RETAIL = 'retail'
V_RIVER = 'river'
V_ROAD = 'road'
V_ROUND = 'round'
V_ROUNDABOUT = 'roundabout'
V_SALTBOX = 'saltbox'
V_SECONDARY = 'secondary'
V_SHED = 'shed'
V_SKILLION = 'skillion'
V_SPUR = 'spur'
V_STADIUM = 'stadium'
V_STATION = 'station'
V_STORAGE_TANK = 'storage_tank'
V_STREAM = 'stream'
V_SUBURB = 'suburb'
V_SUBWAY = 'subway'
V_SWITCH = 'switch'
V_TANK = 'tank'  # deprecated tag in OSM
V_TERMINAL = 'terminal'
V_TERRACE = 'terrace'
V_TERTIARY = 'tertiary'
V_TOWER = 'tower'
V_TOWN = 'town'
V_TRACK = 'track'
V_TRAINING_AREA = 'training_area'
V_TRAM = 'tram'
V_TRUNK = 'trunk'
V_UNCLASSIFIED = 'unclassified'
V_UNDERGROUND = 'underground'
V_VILLAGE = 'village'
V_WATER_TOWER = 'water_tower'
V_WAY = 'way'
V_YES = 'yes'
V_ZOO = 'zoo'


# ======================= LISTS ===================================
L_STORAGE_TANK = [V_STORAGE_TANK, V_TANK, V_OIL_TANK, V_FUEL_STORAGE_TANK]

# ======================= KEY-VALUE PAIRS ==================================
KV_MAN_MADE_CHIMNEY = 'man_made=>chimney'
KV_ROUTE_FERRY = 'route=>ferry'


# ========================= NON OSM KEYS AND VALUES ===============
K_OWBB_GENERATED = 'owbb_generated'

V_GEN = 'gen'
