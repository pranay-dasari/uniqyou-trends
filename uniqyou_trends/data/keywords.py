"""Curated fashion keyword seed list (40 keywords, 6 categories)."""

FASHION_KEYWORDS = {
    "silhouettes": [
        "maxi dress", "mini skirt", "balloon sleeve", "wide leg pants",
        "co-ord set", "shirt dress", "bodycon dress", "wrap dress",
    ],
    "fabrics_textures": [
        "linen co-ord", "crochet top", "mesh fabric", "sheer blouse",
        "satin dress", "denim jacket", "knit cardigan", "velvet dress",
    ],
    "aesthetics": [
        "dark academia outfit", "coastal grandmother", "quiet luxury fashion",
        "Y2K fashion", "cottagecore dress", "indie sleaze", "mob wife aesthetic",
        "clean girl aesthetic",
    ],
    "footwear": [
        "ballet flats", "mary jane shoes", "chunky loafers", "platform boots",
    ],
    "accessories": [
        "mini bag", "claw clip", "pearl jewelry", "layered necklaces",
    ],
    "occasions": [
        "workwear women", "wedding guest dress", "festival outfit women",
    ],
}

# Flat list for API calls
ALL_KEYWORDS = [kw for kws in FASHION_KEYWORDS.values() for kw in kws]

KEYWORD_CATEGORY = {kw: cat for cat, kws in FASHION_KEYWORDS.items() for kw in kws}
