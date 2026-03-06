"""BioTrack inventory type id to user-friendly name. Used for display when product name is missing."""

INVENTORY_TYPE_NAMES = {
    6: "Flower",
    7: "Clone",
    9: "Other Material",
    10: "Seed",
    11: "Plant Tissue",
    12: "Mature Plant",
    13: "Flower Lot",
    14: "Other Material Lot",
    15: "Bubble Hash",
    16: "Hash",
    17: "Hydrocarbon Extract",
    19: "Food Grade Solvent Extract",
    20: "Infused Dairy Butter or Fat in Solid Form",
    21: "Infused Cooking Oil",
    22: "Solid Marijuana Infused Edible",
    23: "Liquid Marijuana Infused Edible",
    24: "Marijuana Extract for Inhalation",
    25: "Marijuana Infused Topicals",
    27: "Waste",
    28: "Usable Marijuana",
    29: "Wet Flower",
    30: "Marijuana Mix",
    31: "Marijuana Mix Packaged",
    32: "Marijuana Mix Infused",
    33: "Non-Mandatory QA Sample",
    34: "Capsule",
    35: "Tincture",
    36: "Transdermal Patch",
    38: "Lozenge",
    39: "Pill",
    40: "Non Smokable Infused Extract",
    42: "Ethanol/Alcohol Extract",
    45: "Liquid Marijuana RSO",
    46: "CO2 Extract",
    62: "Vape Cartridge",
}


def get_inventory_type_name(type_id):
    """Return user-friendly name for inventory type id, or None if unknown."""
    if type_id is None:
        return None
    if type_id in INVENTORY_TYPE_NAMES:
        return INVENTORY_TYPE_NAMES[type_id]
    try:
        return INVENTORY_TYPE_NAMES.get(int(type_id))
    except (TypeError, ValueError):
        return None


def get_product_display_name(item_info):
    """Return product name for display; when productname is missing use 'strain - inventory_type'."""
    productname = (item_info.get("productname") or "").strip()
    if productname:
        return productname
    strain = (item_info.get("strain") or "Unknown").strip()
    type_name = get_inventory_type_name(item_info.get("inventorytype"))
    if type_name:
        return strain + " - " + type_name
    return strain or "Unknown"
