"""Assemble the dashboard.

  python build.py <pipeline folder> [site folder]

The pipeline folder holds template.html and build/ (inputs). Without a site folder the site is written to
"basinscope-alps-site" next to the pipeline folder, and a single-file copy is written beside it.

Outputs
  build/basinscope-alps.html                      page published on claude.ai (no outside calls allowed there)
  <site>/                                         self-hosted site: index.html + assets + data/dataset.json + api/, pulls live federal data
  <site>/../BasinScope_Alps_Dashboard.html        single-file copy of the self-hosted page (default layout only)
  build/seed/                                     database seed files for the claude.ai version
"""
import json, base64, hashlib, sys, os, shutil

SP = sys.argv[1]
B = SP + "/build/"
HOME = os.path.dirname(os.path.abspath(SP))
SITE = (sys.argv[2] if len(sys.argv) > 2 else os.path.join(HOME, "basinscope-alps-site")).replace("\\", "/").rstrip("/") + "/"
t = open(SP + "/template.html", encoding="utf-8").read()
geo = json.load(open(B + "geo.json"))
hyd = json.load(open(B + "hydro.json", encoding="cp1252"))
base = json.load(open(B + "base.json", encoding="utf-8"))
raw = json.load(open(B + "checks_raw.json", encoding="utf-8"))
# hazard process areas, hydropower plants, dams and reservoir storage: written by fetch_federal.py
federal = json.load(open(B + "federal.json", encoding="utf-8")) if os.path.exists(B + "federal.json") else None
# snow and ice per year, the then/now scene pair and glacier thinning: written by fetch_satellite_series.py
satellite = json.load(open(B + "satellite.json", encoding="utf-8")) if os.path.exists(B + "satellite.json") else None
# optional inputs of the Energy sheet, the test of the risk rule and the Glacier size control: written by fetch_energy.py,
# fetch_hindcast.py and fetch_glacier_path.py
opt = lambda f: json.load(open(B + f, encoding="utf-8")) if os.path.exists(B + f) else None
energy, hindcast, glacier_path = opt("energy.json"), opt("hindcast.json"), opt("glacier_path.json")
# the projects of the 2024 Federal Council report that lie in the study area, entered by hand from its appendix
fed_report = opt("federal_report.json")
# hazard process areas around the hydropower plants and dams: written by fetch_infra_hazard.py
infra = opt("infra_hazard.json")

# ---- protected-area hits from the federal geodata API (queried 3 Oct 2026, 250 m around each point)
KEY = {
    "ch.bafu.bundesinventare-auen": "floodplain", "ch.bafu.bundesinventare-moorlandschaften": "mire_landscape",
    "ch.bafu.bundesinventare-flachmoore": "fen", "ch.bafu.bundesinventare-hochmoore": "bog",
    "ch.bfe.abgeltung-wasserkraftnutzung": "hydro_waiver", "ch.bafu.unesco-weltnaturerbe": "unesco",
    "ch.bafu.bundesinventare-bln": "bln", "ch.bafu.bundesinventare-jagdbanngebiete": "game_reserve",
}
AUEN = {"Gletschervorfeld": "glacier forefield", "Alpine Schwemmebene": "alpine alluvial plain"}


def hit_name(lid, a):
    if lid.endswith("-auen"):
        return f'{a.get("name")}, object {a.get("objnummer")}, {AUEN.get(a.get("auen_type_de"), a.get("auen_type_de"))}'
    if lid.endswith("-bln"):
        return f'{str(a.get("bln_name")).strip()}, object {a.get("bln_obj")}'
    if lid.endswith("-jagdbanngebiete"):
        kind = "integral protection" if "integral" in str(a.get("typ_de")) else "partial protection"
        return f'{a.get("gebietsname")}, {kind}'
    if lid.endswith("wasserkraftnutzung"):
        return f'{a.get("name")}, since {str(a.get("startprotectioncommitment"))[:4]}'
    return str(a.get("name") or a.get("label") or "")


def prot(sid):
    out, seen = [], set()
    for r in raw[str(sid)]:
        k = KEY.get(r["layerBodId"])
        if not k:
            continue
        h = (k, hit_name(r["layerBodId"], r.get("attributes", {})))
        if h not in seen:
            seen.add(h)
            out.append({"k": h[0], "name": h[1]})
    return out


sites = []
for s in base["sites"]:
    s = dict(s)
    s["prot"] = prot(s["id"])
    sites.append(s)
cands = []
for i, c in enumerate([c for c in geo["cands"] if not c["rank"]]):
    cands.append({"x": c["x"], "y": c["y"], "E": c["E"], "N": c["N"], "prot": prot(f"c{i + 1}")})
catch = {str(k): {**v, "id": int(k)} for k, v in hyd.items()}
snap = {"sites": sites, "candidates": cands, "catchments": catch, "exits": base["exits"], "glaciers": base["glaciers"], "bands": base["bands"]}
if federal:
    snap["federal"] = federal
if satellite:
    snap["satellite"] = satellite
for key, val in (("energy", energy), ("hindcast", hindcast), ("glacierPath", glacier_path), ("fedReport", fed_report), ("infra", infra)):
    if val:
        snap[key] = val
geo_small = {k: geo[k] for k in ("W", "H", "cE", "cN", "poly")}
dump = lambda o: json.dumps(o, separators=(",", ":"), ensure_ascii=False)
IMG = {"__RELIEF__": "base_relief.webp", "__DEM__": "base_dem.webp", "__LOGO__": "logo.webp"}
# optional map layers, loaded only when a visitor switches them on; left out of the claude.ai page, which may not load outside pictures
LAYERS = {"__OV_PERMAFROST__": "ov_permafrost.webp", "__OV_DEBRIS__": "ov_debris.webp", "__OV_ROCKFALL__": "ov_rockfall.webp", "__SAT__": "base_s2.webp"}
PUBLIC = "https://gopalinternship-unibasel.github.io/basinscope-alps/"
SAT_DATE = json.load(open(B + "base_s2.json"))["date"] if os.path.exists(B + "base_s2.json") else ""
if SAT_DATE:  # shown on the page as "13 August 2026"
    y, m, d = SAT_DATE.split("-")
    SAT_DATE = f"{int(d)} {['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'][int(m) - 1]} {y}"
# pictures of the Satellite sheet: a folder of their own, fetched when that sheet is opened. Like the layers they are kept in build/ and
# exist in the site repo only as published assets.
SPACE = B + "sat/" if os.path.isdir(B + "sat") else SITE + "assets/sat/"
SPACE_PICS = sorted(f for f in os.listdir(SPACE) if f.endswith(".webp")) if os.path.isdir(SPACE) else []
SPACE_V = hashlib.sha1(b"".join(open(SPACE + f, "rb").read() for f in SPACE_PICS)).hexdigest()[:8]
TITLE = "<title>BasinScope Alps</title>\n"
# fonts and the geotiff.js library: the self-hosted site serves its own copies (fetch_vendor.py), so that a visitor's browser calls no
# third party for them. The page on claude.ai and the single-file copy keep the Google Fonts link.
GOOGLE_FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">\n<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Semi+Condensed:wght@500;600;700'
                '&family=IBM+Plex+Mono:wght@400;500&family=Source+Sans+3:wght@400;500;600;700&display=swap">')
OWN = {"fonts": "fonts/fonts.css", "lib": "vendor/geotiff.js"}


def src(f):
    # pictures are kept in build/; in the site repo they exist only as published assets
    return B + f if os.path.exists(B + f) else SITE + "assets/" + f


def uri(f):
    return "data:image/webp;base64," + base64.b64encode(open(src(f), "rb").read()).decode()


def versioned(f):
    # the address changes with the file, so a replaced image is never served from a browser cache
    return "assets/" + f + "?v=" + hashlib.sha1(open(src(f), "rb").read()).hexdigest()[:8]


def page(mode, inline_images):
    out = t.replace('"__MODE__"', '"' + mode + '"').replace("/*__GEO__*/null", dump(geo_small)).replace("/*__SNAP__*/null", dump(snap))
    for k, f in IMG.items():
        out = out.replace(k, uri(f) if inline_images else versioned(f))
    for k, f in LAYERS.items():
        have = mode == "site" and os.path.exists(src(f))
        out = out.replace(k, ((PUBLIC if inline_images else "") + versioned(f)) if have else "")
    out = out.replace("__SAT_DATE__", SAT_DATE)
    own = mode == "site" and not inline_images
    out = out.replace("__FONTS__", f'<link rel="stylesheet" href="{versioned(OWN["fonts"])}">' if own and os.path.exists(src(OWN["fonts"])) else GOOGLE_FONTS)
    out = out.replace("__GEOTIFF__", ((PUBLIC if inline_images else "") + versioned(OWN["lib"])) if mode == "site" and os.path.exists(src(OWN["lib"])) else "https://cdn.jsdelivr.net/npm/geotiff@2.1.3/dist-browser/geotiff.js")
    out = out.replace("__SPACE_DIR__", ((PUBLIC if inline_images else "") + "assets/sat/") if mode == "site" and satellite and SPACE_PICS else "").replace("__SPACE_V__", SPACE_V)
    assert "/*__" not in out and not any(k in out for k in list(IMG) + list(LAYERS) + ["__MODE__", "__SAT_DATE__", "__SPACE_DIR__", "__SPACE_V__", "__FONTS__", "__GEOTIFF__"]), "placeholder left"
    return out


def document(body):
    assert body.startswith(TITLE)  # in a full document the title belongs in the head
    return ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n' + TITLE +
            '<meta name="description" content="BasinScope Alps: a digital twin of the Jungfrau-Aletsch glacier region. Where glacier meltwater could be stored, with live federal river and weather data, a five-day risk outlook, a hydropower stress test and an open data API.">\n'
            '<style>[hidden]{display:none!important}img{max-width:100%}</style>\n</head>\n<body>\n' + body[len(TITLE):] + '\n</body>\n</html>\n')


# 1. claude.ai artifact
art = page("artifact", True)
open(B + "basinscope-alps.html", "w", encoding="utf-8").write(art)

# 2. self-hosted site
os.makedirs(SITE + "assets", exist_ok=True)
os.makedirs(SITE + "data", exist_ok=True)
open(SITE + "index.html", "w", encoding="utf-8").write(document(page("site", False)))
for f in list(IMG.values()) + list(LAYERS.values()):
    if os.path.exists(B + f):
        shutil.copyfile(B + f, SITE + "assets/" + f)
for folder in ("fonts", "vendor"):  # the site's own copies of the fonts and of geotiff.js
    if os.path.isdir(B + folder):
        os.makedirs(SITE + "assets/" + folder, exist_ok=True)
        for f in os.listdir(B + folder):
            shutil.copyfile(B + folder + "/" + f, SITE + "assets/" + folder + "/" + f)
if SPACE_PICS and os.path.abspath(SPACE) != os.path.abspath(SITE + "assets/sat"):
    os.makedirs(SITE + "assets/sat", exist_ok=True)
    for f in SPACE_PICS:
        shutil.copyfile(SPACE + f, SITE + "assets/sat/" + f)
json.dump(snap, open(SITE + "data/dataset.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
open(SITE + ".nojekyll", "w").write("")

# 3. single-file copy (same live behaviour, images built in)
single = document(page("site", True))
if len(sys.argv) <= 2:
    open(os.path.join(HOME, "BasinScope_Alps_Dashboard.html"), "w", encoding="utf-8").write(single)

# 4. database seed for the claude.ai version
seed = B + "seed/"
writes = []


def doc(coll, did, body):
    d = seed + coll
    os.makedirs(d, exist_ok=True)
    f = f"{d}/{did}.json"
    json.dump(body, open(f, "w", encoding="utf-8"), ensure_ascii=False)
    writes.append({"op": "set", "collection": coll, "doc_id": str(did), "file_path": os.path.abspath(f)})


for s in sites:
    doc("sites", s["id"], s)
for k, c in catch.items():
    doc("catchments", k, c)
doc("context", "main", {"exits": base["exits"], "glaciers": base["glaciers"], "bands": base["bands"],
                        "meta": {"analysisAsOf": "2026-10-02", "protectionCheckedAt": "2026-10-03", "studyArea": "Jungfrau-Aletsch",
                                 "sources": "Team terrain analysis (swissALTI3D, SGI 2016); Hydro-CH2018 L03 (FOEN); federal inventories via geo.admin.ch"}})
doc("context", "candidates", {"points": cands})
json.dump(writes, open(B + "seed_writes.json", "w", encoding="utf-8"), indent=0)

size = lambda p: os.path.getsize(p)
print("artifact bytes:", len(art.encode("utf-8")), "| site index.html:", size(SITE + "index.html"), "| dataset.json:", size(SITE + "data/dataset.json"), "| single file:", len(single.encode("utf-8")))

# 5. read-only data API of the self-hosted site (api/v1/*.json, OpenAPI description, docs page)
import build_api
build_api.main(SITE)
