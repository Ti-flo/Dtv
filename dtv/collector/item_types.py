# Item type GIDs for superTypeId=9 (RESOURCE) — extracted live from
# window.gui.databases.ItemTypes via DevTools console (session 5, June 2026).
#
# Usage: filter buyerDescriptor.types to only collect these.

RESOURCE_TYPES: dict[int, str] = {
    15: "Miscellaneous",
    26: "Smithmagic potion",
    34: "Cereal",
    35: "Flower",
    36: "Plant",
    38: "Wood",
    39: "Ore",
    40: "Alloy",
    41: "Fish",
    46: "Fruit",
    47: "Bone",
    48: "Powder",
    50: "Precious stone",
    51: "Stone",
    52: "Flour",
    53: "Feather",
    54: "Hair",
    55: "Fabric",
    56: "Leather",
    57: "Wool",
    58: "Seed",
    59: "Skin",
    60: "Oil",
    61: "Stuffed toy",
    62: "Gutted fish",
    63: "Meat",
    64: "Preserved meat",
    65: "Tail",
    66: "Metaria",
    68: "Vegetable",
    70: "Dye",
    71: "Alchemy equipment",
    78: "Smithmagic rune",
    84: "Key",
    90: "Pet ghost",
    95: "Plank",
    96: "Bark",
    98: "Root",
    103: "Leg",
    104: "Wing",
    105: "Egg",
    106: "Ear",
    107: "Carapace",
    108: "Bud",
    109: "Eye",
    110: "Jelly",
    111: "Shell",
    119: "Mushroom",
    124: "Petsmount ghost",
    125: "Souvenir",
    152: "Pebble",
    153: "Kwismas",
    154: "Wrapping paper",
    158: "Caramel Rabmajoke",
    159: "Strawberry Rabmajoke",
    160: "Lemon Rabmajoke",
    161: "Orange Rabmajoke",
    162: "Kola Rabmajoke",
    163: "Nougat Rabmajoke",
    164: "Garment",
    168: "Badge",
    175: "Dungeon keeper essence",
    211: "Awakening Material",
    241: "Vouchers",
}

RESOURCE_TYPE_IDS: list[int] = list(RESOURCE_TYPES.keys())

# Core crafting resources — exclude seasonal/event/niche types.
# Use this for daily collection to keep runs short.
CORE_RESOURCE_TYPE_IDS: list[int] = [
    34,   # Cereal
    35,   # Flower
    36,   # Plant
    38,   # Wood
    39,   # Ore
    40,   # Alloy
    41,   # Fish
    46,   # Fruit
    47,   # Bone
    48,   # Powder
    50,   # Precious stone
    51,   # Stone
    52,   # Flour
    53,   # Feather
    54,   # Hair
    55,   # Fabric
    56,   # Leather
    57,   # Wool
    58,   # Seed
    59,   # Skin
    60,   # Oil
    62,   # Gutted fish
    63,   # Meat
    64,   # Preserved meat
    65,   # Tail
    66,   # Metaria
    68,   # Vegetable
    78,   # Smithmagic rune
    95,   # Plank
    96,   # Bark
    98,   # Root
    103,  # Leg
    104,  # Wing
    105,  # Egg
    106,  # Ear
    107,  # Carapace
    108,  # Bud
    109,  # Eye
    110,  # Jelly
    111,  # Shell
    119,  # Mushroom
]
