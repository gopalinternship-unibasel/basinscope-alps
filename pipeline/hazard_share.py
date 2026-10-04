"""Share of the square around a point that the FOEN hazard index maps mark, in per cent.

  python hazard_share.py <pipeline folder>

recomputes the shares in build/federal.json (ranked sites) and build/infra_hazard.json (plants and dams) and leaves everything else in
those files as it is. fetch_federal.py and fetch_infra_hazard.py use the same function, so a full run gives the same figures.

The square reaches R metres from the point in each direction (500 m across), the same reach as the protected-area check.

Debris flow, shallow landslide, rockfall: the SilvaProtect-CH process areas are polygons. The federal map service draws them as hatching,
so counting the drawn pixels of a map picture counts hatch lines and not area: about a fifth of the area at 5 m per pixel, and less at a
finer resolution. The shares are therefore measured on the polygons themselves, from the File Geodatabases of the federal data catalogue
(data.geo.admin.ch). They are downloaded once into build/haz_cache/ (33 MB, not kept in the site repo).
Permafrost: the map of potential permafrost distribution is drawn as a solid fill, so its share is counted on a map picture.

Needs pyogrio, shapely and Pillow.
"""
import datetime, io, json, os, sys, time, urllib.parse, urllib.request, zipfile

# The largest process areas are single features with several hundred thousand points. In a File Geodatabase the outline of a hole runs
# counter-clockwise, so the reader only has to sort those; its default check of every ring against every other takes minutes.
os.environ.setdefault("OGR_ORGANIZE_POLYGONS", "ONLY_CCW")
import pyogrio
import shapely
from PIL import Image

R = 250  # metres from the point to each side of the square
UA = {"User-Agent": "basinscope-alps-build/1.0"}
WMS = "https://wms.geo.admin.ch/"
CATALOGUE = "https://data.geo.admin.ch/ch.bafu.silvaprotect-{n}/silvaprotect-{n}/silvaprotect-{n}_2056.gdb.zip"
AREAS = {"debris": "murgang", "landslide": "hangmuren", "rockfall": "sturz"}  # polygon datasets of SilvaProtect-CH
PICTURES = {"permafrost": "ch.bafu.permafrost"}  # solid fill on the map service
_layers = {}


def get(url, tries=3):
    for i in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180).read()
        except Exception:  # the federal services drop a request now and then
            if i == tries - 1:
                raise
            time.sleep(2 + 2 * i)


def layer(B, k):
    """Path and layer name of one polygon dataset, downloaded on first use."""
    if k not in _layers:
        folder = B + "haz_cache/" + AREAS[k]
        if not os.path.isdir(folder):
            zipfile.ZipFile(io.BytesIO(get(CATALOGUE.format(n=AREAS[k])))).extractall(folder)
        gdb = folder + "/" + next(f for f in os.listdir(folder) if f.lower().endswith(".gdb"))
        _layers[k] = (gdb, pyogrio.list_layers(gdb)[0][0])
    return _layers[k]


def area_share(B, k, box):
    gdb, name = layer(B, k)
    geom = pyogrio.raw.read(gdb, layer=name, bbox=box, columns=[])[2]
    if geom is None or not len(geom):
        return 0.0
    # cut every feature to the square first: repairing a whole feature of 800,000 points does not finish
    parts = [shapely.make_valid(shapely.clip_by_rect(g, *box)) for g in shapely.from_wkb(geom)]
    return shapely.union_all(parts).area / ((box[2] - box[0]) * (box[3] - box[1])) * 100


def picture_share(k, box, px=100):
    q = {"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap", "LAYERS": PICTURES[k], "STYLES": "", "CRS": "EPSG:2056",
         "BBOX": ",".join(str(v) for v in box), "WIDTH": px, "HEIGHT": px, "FORMAT": "image/png", "TRANSPARENT": "true"}
    alpha = Image.open(io.BytesIO(get(WMS + "?" + urllib.parse.urlencode(q)))).convert("RGBA").getchannel("A")
    return sum(1 for v in alpha.getdata() if v > 40) / (px * px) * 100


def shares(B, E, N, r=R):
    """Per cent of the square around E, N (LV95) that each index map marks, as whole numbers."""
    box = (E - r, N - r, E + r, N + r)
    row = {k: round(picture_share(k, box)) for k in PICTURES}
    row.update({k: round(area_share(B, k, box)) for k in AREAS})
    return row


if __name__ == "__main__":
    B = sys.argv[1] + "/build/"
    today = datetime.date.today().isoformat()
    base = json.load(open(B + "base.json", encoding="utf-8"))
    federal = json.load(open(B + "federal.json", encoding="utf-8"))
    for s in base["sites"]:
        federal["haz"][str(s["id"])] = shares(B, s["E"], s["N"])
        print("hazard", s["id"], s["name"], federal["haz"][str(s["id"])])
    federal["hazAt"] = today
    json.dump(federal, open(B + "federal.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    if os.path.exists(B + "infra_hazard.json"):
        infra = json.load(open(B + "infra_hazard.json", encoding="utf-8"))
        for it in infra["items"]:
            it["haz"] = shares(B, it["E"], it["N"], infra["r"])
            print(it["k"], it["n"], it["haz"])
        infra["at"] = today
        json.dump(infra, open(B + "infra_hazard.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("hazard shares recomputed on", today)
