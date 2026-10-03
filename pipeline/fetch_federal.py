"""Federal layers that are fetched when the site is built, not from the visitor's browser.

  python fetch_federal.py <build folder>

Writes
  build/federal.json        hydropower plants and dams in the map extent (SFOE), hazard process areas around each
                            ranked site (FOEN indicative maps), Swiss reservoir storage (SFOE, weekly)
  build/ov_<layer>.webp     the same hazard maps as transparent pictures laid over the dashboard map

Why at build time: the hazard maps are served as pictures only (no feature query), and the SFOE storage file
does not allow calls from other web origins.
"""
import csv, datetime, io, json, sys, time, urllib.parse, urllib.request
from PIL import Image

SP = sys.argv[1]
B = SP + "/build/"
geo = json.load(open(B + "geo.json"))
base = json.load(open(B + "base.json", encoding="utf-8"))
W, H = geo["W"], geo["H"]
a, b, c0 = geo["cE"]
d, e, f0 = geo["cN"]
# axis-aligned box of the base map. The fitted georeference is rotated by about 0.1 degree (under 2 px), which is ignored here.
E0, E1 = c0 + b * H / 2, c0 + a * W + b * H / 2
N1, N0 = f0 + d * W / 2, f0 + d * W / 2 + e * H
BOX = (round(E0, 1), round(N0, 1), round(E1, 1), round(N1, 1))
WMS = "https://wms.geo.admin.ch/"
API = "https://api3.geo.admin.ch/rest/services/all/MapServer/identify"
UA = {"User-Agent": "basinscope-alps-build/1.0"}


def get(url, tries=3):
    for i in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90).read()
        except Exception as err:  # the federal services drop a request now and then
            if i == tries - 1:
                raise
            time.sleep(2 + 2 * i)


def wms(layer, box, w, h):
    q = {"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap", "LAYERS": layer, "STYLES": "", "CRS": "EPSG:2056",
         "BBOX": ",".join(str(v) for v in box), "WIDTH": w, "HEIGHT": h, "FORMAT": "image/png", "TRANSPARENT": "true"}
    return Image.open(io.BytesIO(get(WMS + "?" + urllib.parse.urlencode(q)))).convert("RGBA")


# ---- 1. hazard process areas: FOEN indicative maps, nationwide models
# The SilvaProtect avalanche layer is left out: it only models avalanches that start in forest, which says nothing above the tree line.
HAZ = {"permafrost": "ch.bafu.permafrost", "debris": "ch.bafu.silvaprotect-murgang", "rockfall": "ch.bafu.silvaprotect-sturz",
       "landslide": "ch.bafu.silvaprotect-hangmuren"}
R = 250  # metres around each site, the same square as the protected-area check
haz = {}
for s in base["sites"]:
    row = {}
    for k, layer in HAZ.items():
        im = wms(layer, (s["E"] - R, s["N"] - R, s["E"] + R, s["N"] + R), 100, 100)
        alpha = im.getchannel("A")
        row[k] = round(sum(1 for v in alpha.getdata() if v > 40) / (100 * 100) * 100)
    haz[str(s["id"])] = row
    print("hazard", s["id"], s["name"], row)

for k in ("permafrost", "debris", "rockfall"):
    im = wms(HAZ[k], BOX, W * 2, H * 2).resize((int(W * 1.5), int(H * 1.5)), Image.LANCZOS)
    im.save(B + f"ov_{k}.webp", "WEBP", quality=62, alpha_quality=80, method=6)
    print("overlay", k, im.size)


# ---- 2. hydropower plants and dams in the map extent (SFOE)
def identify(layer):
    q = {"geometryType": "esriGeometryEnvelope", "geometry": ",".join(str(v) for v in BOX), "imageDisplay": "0,0,0", "mapExtent": "0,0,0,0",
         "tolerance": 0, "layers": "all:" + layer, "sr": 2056, "returnGeometry": "true", "lang": "en", "limit": 200}
    return json.loads(get(API + "?" + urllib.parse.urlencode(q)))["results"]


def point(g):
    if "points" in g:
        return g["points"][0]
    return [g["x"], g["y"]]


PTYPE = {"Speicherkraftwerk": "storage plant", "Laufkraftwerk": "run-of-river plant", "Pumpspeicherkraftwerk": "pumped-storage plant", "reines Umwälzwerk": "pure pumped-storage plant"}
PSTAT = {"im Normalbetrieb": "in operation", "ausser Betrieb/reduzierter Betrieb": "out of service or reduced", "im Bau": "under construction", "im Umbau": "being rebuilt", "stillgelegt": "shut down"}
num = lambda v: float(v) if isinstance(v, (int, float)) else None
plants, stat_date = [], ""
for x in identify("ch.bfe.statistik-wasserkraftanlagen"):
    p, (E, N) = x["attributes"], point(x["geometry"])
    stat_date = max(stat_date, str(p.get("dateofstatistic") or ""))
    plants.append({"n": p.get("name"), "loc": p.get("location"), "type": PTYPE.get(p.get("hydropowerplanttype_de"), p.get("hydropowerplanttype_de")),
                   "st": PSTAT.get(p.get("hydropowerplantoperationalstatus_de"), p.get("hydropowerplantoperationalstatus_de")),
                   "mw": num(p.get("performanceturbinemaximum")), "gwh": num(p.get("productionexpected")), "y": p.get("beginningofoperation"), "E": round(E), "N": round(N)})
dams = []
for x in identify("ch.bfe.stauanlagen-bundesaufsicht"):
    p, (E, N) = x["attributes"], point(x["geometry"])
    dams.append({"n": p.get("damname"), "res": p.get("reservoirname"), "type": p.get("damtype_en"), "h": num(p.get("damheight")), "crest": num(p.get("crestlength")),
                 "vol": float(p["impoundmentvolume"]) if p.get("impoundmentvolume") not in (None, "") else None, "y": p.get("baujahr"), "aim": p.get("facaim_en"), "E": round(E), "N": round(N)})
plants.sort(key=lambda p: -(p["mw"] or 0))
dams.sort(key=lambda p: -(p["h"] or 0))
print("plants", len(plants), "dams", len(dams), "statistics of", stat_date)

# ---- 3. energy held in Swiss reservoirs, weekly (SFOE)
rows = list(csv.DictReader(io.StringIO(get("https://www.uvek-gis.admin.ch/BFE/ogd/17/ogd17_fuellungsgrad_speicherseen.csv").decode("utf-8-sig"))))
rows = [r for r in rows if r.get("TotalCH_speicherinhalt_gwh")]
last = rows[-1]
storage = {"date": last["Datum"], "gwh": float(last["TotalCH_speicherinhalt_gwh"]), "max": float(last["TotalCH_max_speicherinhalt_gwh"]),
           "year": [[r["Datum"], float(r["TotalCH_speicherinhalt_gwh"])] for r in rows[-53:]]}
print("storage", storage["date"], storage["gwh"], "of", storage["max"])

out = {"at": datetime.date.today().isoformat(), "box": BOX, "haz": haz, "plants": plants, "dams": dams, "plantsAsOf": stat_date, "storage": storage}
json.dump(out, open(B + "federal.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print("wrote federal.json")
