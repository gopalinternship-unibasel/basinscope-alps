"""Satellite evidence for the Satellite sheet: what Sentinel-2 saw of the study area since 2015, and how fast
satellites measured the glaciers thinning.

  python fetch_satellite_series.py <build folder> [then scene id] [now scene id]

Writes
  build/satellite.json        snow and ice left at the end of each summer, the then/now scene pair, glacier thinning
  build/sat/area_*.webp       true-colour pictures of the study area for the two scenes of the pair, 30 m per pixel
  build/sat/s<id>_*.webp      the same two scenes around each ranked site, 4 km square at 10 m per pixel
  build/sat_cache/            per-scene results, so a re-run only reads scenes it has not seen

Sources
  swissEO S2-SR v200, swisstopo (Copernicus Sentinel-2 L2A, 10 m, mosaics per flight path, LV95), read from the
  cloud-optimised files of the federal data catalogue.
  Hugonnet et al. 2021, Nature 592: elevation change per glacier 2000-2019 from ASTER satellite stereo images,
  on Randolph Glacier Inventory 6.0 outlines. Both tables are read from the OGGM mirror with range requests.

Snow and ice rule: NDSI = (green - shortwave infrared) / (green + shortwave infrared) >= 0.4 on a 40 m grid, inside
the study-area polygon, on pixels the cloud mask calls clear. Lakes also pass that test, so pixels that the scene
classification calls water in most clear scenes are taken out (turbid lakes are not all caught). Debris-covered ice
and ice in deep shadow are missed.
Year value: the clear scene with the least snow and ice whose extent a second scene of the same late summer confirms
within 5 per cent. The cloud mask misses haze now and then, and a hazy scene reads too low; a scene nothing confirms is
only used when the year has no confirmed one, and is then marked.
Needs rasterio and Pillow.
"""
import concurrent.futures as cf, csv, datetime, io, json, os, sys, time, urllib.parse, urllib.request

os.environ.update({"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif", "GDAL_HTTP_MAX_RETRY": "4",
                   "GDAL_HTTP_RETRY_DELAY": "2", "GDAL_HTTP_MULTIRANGE": "YES", "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES", "VSI_CACHE": "TRUE"})
import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.transform import from_origin
from rasterio.windows import from_bounds
from PIL import Image

SP = sys.argv[1]
B = SP + "/build/"
THEN = sys.argv[2] if len(sys.argv) > 2 else "2016-09-29t102022"
NOW = sys.argv[3] if len(sys.argv) > 3 else "2026-09-27t101801"
Y0, Y1 = 2015, datetime.date.today().year
WINDOW = ("08-10", "10-05")  # late summer: the seasonal snow is at its smallest
CLEAR, PARTLY = 1.0, 3.0  # per cent of the study area under cloud or cloud shadow
CONFIRM = 0.05  # a second scene within 5 per cent confirms an extent
NDSI_MIN, RES, RES_SCREEN = 0.4, 40, 80
UA = {"User-Agent": "basinscope-alps-build/1.0"}
COLL = "ch.swisstopo.swisseo_s2-sr_v200"
STAC = f"https://data.geo.admin.ch/api/stac/v1/collections/{COLL}/items"
FILES = f"https://data.geo.admin.ch/{COLL}/"
OGGM = "https://cluster.klima.uni-bremen.de/~oggm/"
os.makedirs(B + "sat", exist_ok=True)
os.makedirs(B + "sat_cache", exist_ok=True)

geo = json.load(open(B + "geo.json"))
base = json.load(open(B + "base.json", encoding="utf-8"))
a, b, c0 = geo["cE"]
d, e, f0 = geo["cN"]
POLY = [(a * x + b * y + c0, d * x + e * y + f0) for x, y in geo["poly"]]  # study area in LV95
E0, E1 = min(p[0] for p in POLY) // 1000 * 1000, -(-max(p[0] for p in POLY) // 1000) * 1000
N0, N1 = min(p[1] for p in POLY) // 1000 * 1000, -(-max(p[1] for p in POLY) // 1000) * 1000
BOX = (E0, N0, E1, N1)


def inside(res):
    h, w = int((N1 - N0) / res), int((E1 - E0) / res)
    return ~geometry_mask([{"type": "Polygon", "coordinates": [POLY + [POLY[0]]]}], out_shape=(h, w), transform=from_origin(E0, N1, res, res))


def read(sid, asset, box, shape, bands=1):
    with rasterio.open(f"{FILES}{sid}/swisseo_s2-sr_v200_mosaic_{sid}_{asset}.tif") as src:
        return src.read(bands, window=from_bounds(*box, transform=src.transform), out_shape=shape)  # a reduced shape is read from the overviews; boundless=True would skip them


def grid(sid, asset, res):
    return read(sid, asset, BOX, (int((N1 - N0) / res), int((E1 - E0) / res)))


def wgs(E, N):  # swisstopo approximation, good to a metre
    y, x = (E - 2600000) / 1e6, (N - 1200000) / 1e6
    lon = 2.6779094 + 4.728982 * y + 0.791484 * y * x + 0.1306 * y * x * x - 0.0436 * y ** 3
    lat = 16.9023892 + 3.238272 * x - 0.270978 * y * y - 0.002528 * x * x - 0.0447 * y * y * x - 0.0140 * x ** 3
    return lon * 100 / 36, lat * 100 / 36


def lv95(lon, lat):
    p, l = (lat * 3600 - 169028.66) / 10000, (lon * 3600 - 26782.5) / 10000
    return (2600072.37 + 211455.93 * l - 10938.51 * l * p - 0.36 * l * p * p - 44.54 * l ** 3,
            1200147.07 + 308807.95 * p + 3745.25 * l * l + 76.63 * p * p - 194.56 * l * l * p + 119.79 * p ** 3)


def in_poly(x, y):
    hit = False
    for i in range(len(POLY)):
        (x1, y1), (x2, y2) = POLY[i], POLY[(i + 1) % len(POLY)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


def get(url, headers=None, tries=4):
    for i in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers={**UA, **(headers or {})}), timeout=120).read()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 + 2 * i)


# ---- 1. every late-summer mosaic over the study area, screened for cloud at 80 m
w_, s_ = wgs(E0, N0)
e_, n_ = wgs(E1, N1)
ids = []
for y in range(Y0, Y1 + 1):
    q = {"bbox": f"{w_},{s_},{e_},{n_}", "datetime": f"{y}-{WINDOW[0]}T00:00:00Z/{y}-{WINDOW[1]}T23:59:59Z", "limit": 100}
    ids += [f["id"] for f in json.loads(get(STAC + "?" + urllib.parse.urlencode(q)))["features"] if f["id"][:2] == "20"]
M_S = inside(RES_SCREEN)
SCREEN = B + "sat_cache/screen.json"
seen = json.load(open(SCREEN)) if os.path.exists(SCREEN) else {}


def screen(sid):
    if sid in seen:
        return sid, seen[sid]
    try:
        cm, scl = grid(sid, "cloudmask_10m", RES_SCREEN), grid(sid, "scl_20m", RES_SCREEN)
    except Exception as err:
        print(sid, "not readable:", str(err)[:80])
        return sid, None
    n = M_S.sum()  # cloud mask: 0 clear, 1 thick cloud, 2 thin cloud, 3 cloud shadow; scene classification 0 = no data
    return sid, {"nodata": round(float((scl == 0)[M_S].sum() / n * 100), 2), "cloud": round(float((cm > 0)[M_S].sum() / n * 100), 2)}


with cf.ThreadPoolExecutor(8) as ex:
    for sid, o in ex.map(screen, ids):
        if o:
            seen[sid] = o
json.dump(seen, open(SCREEN, "w"), indent=0)
usable = sorted(k for k in ids if k in seen and seen[k]["nodata"] < 0.5 and seen[k]["cloud"] <= PARTLY)
print(len(ids), "mosaics,", len(usable), "with at most", PARTLY, "% cloud over the study area")

# ---- 2. snow and ice in each usable mosaic, on a 40 m grid
M = inside(RES)
PX = RES * RES / 1e6


def classify(sid):
    f = B + f"sat_cache/{sid}.npz"
    if os.path.exists(f):
        z = np.load(f)
        return sid, {k: np.unpackbits(z[k])[:M.size].reshape(M.shape).astype(bool) for k in ("snow", "water", "ok")}
    try:
        g, s = grid(sid, "b03_10m", RES), grid(sid, "b11_20m", RES)
        cm, scl = grid(sid, "cloudmask_10m", RES), grid(sid, "scl_20m", RES)
    except Exception as err:
        print(sid, "not readable:", str(err)[:80])
        return sid, None
    ok = M & (cm == 0) & (g > 0) & (s > 0) & (scl != 0)  # a band that is 0 has no data
    gr, sr = np.clip((g.astype("f4") - 1000) / 1e4, 1e-4, None), np.clip((s.astype("f4") - 1000) / 1e4, 1e-4, None)  # reflectance: the files carry an offset of 1000
    o = {"snow": ok & ((gr - sr) / (gr + sr) >= NDSI_MIN), "water": ok & (scl == 6), "ok": ok}
    np.savez_compressed(f, **{k: np.packbits(v) for k, v in o.items()})
    return sid, o


masks = {}
with cf.ThreadPoolExecutor(4) as ex:
    for i, (sid, o) in enumerate(ex.map(classify, usable)):
        if o is not None:
            masks[sid] = o
        if i % 10 == 9:
            print("  read", i + 1, "of", len(usable), flush=True)
# lakes: water in more than half of the scenes that saw the pixel clearly
seen_n = sum(m["ok"].astype("u2") for m in masks.values())
water_n = sum(m["water"].astype("u2") for m in masks.values())
LAKE = (water_n * 2 > seen_n) & (seen_n >= 5)
print("lakes taken out:", round(float(LAKE.sum() * PX), 1), "km2")
AREA_KM2 = float(M.sum() * PX)
scenes = {}
for sid, m in masks.items():
    unknown = float((M & ~m["ok"]).sum() * PX)
    scenes[sid] = {"km2": round(float((m["snow"] & ~LAKE).sum() * PX), 1), "unknown": round(unknown, 1), "cloud": seen[sid]["cloud"]}
years = []
for y in range(Y0, Y1 + 1):
    mine = {k: v for k, v in scenes.items() if k.startswith(str(y))}
    passes = sum(1 for k in ids if k.startswith(str(y)))
    best = {k: v for k, v in mine.items() if v["unknown"] <= AREA_KM2 * CLEAR / 100}
    pool = best or mine
    if not pool:
        years.append({"y": y, "passes": passes, "clear": 0})
        continue
    order = sorted(pool, key=lambda k: pool[k]["km2"])
    confirmed = [k for k in order if any(o != k and abs(mine[o]["km2"] - pool[k]["km2"]) <= CONFIRM * pool[k]["km2"] for o in mine)]
    sid = (confirmed or order)[0]
    years.append({"y": y, "id": sid, "date": sid[:10], "km2": pool[sid]["km2"], "unknown": pool[sid]["unknown"], "passes": passes, "clear": len(best), "partly": not best, "confirmed": bool(confirmed)})
    print(y, sid, pool[sid], "| clear scenes", len(best), "of", passes, "" if confirmed else "| not confirmed by a second scene")

# ---- 3. pictures of the two scenes of the pair
AW, AH = int((E1 - E0) / 30), int((N1 - N0) / 30)
HALF, SPX = 2000, 400


def picture(sid, box, w, h, f, q):
    if DONE and os.path.exists(B + "sat/" + f):
        return os.path.getsize(B + "sat/" + f)
    rgb = read(sid, "tci_10m", box, (3, h, w), [1, 2, 3])
    alpha = np.where(rgb.sum(axis=0) > 0, 255, 0).astype("uint8")  # outside the flight path
    img = Image.fromarray(np.dstack([np.transpose(rgb, (1, 2, 0)).astype("uint8"), alpha]), "RGBA") if (alpha == 0).any() else Image.fromarray(np.transpose(rgb, (1, 2, 0)).astype("uint8"), "RGB")
    img.save(B + "sat/" + f, "WEBP", quality=q, method=6)
    return os.path.getsize(B + "sat/" + f)


PAIR = B + "sat_cache/pair.json"  # the scenes the pictures on disk were made from
DONE = os.path.exists(PAIR) and json.load(open(PAIR)) == [THEN, NOW]
total = 0
for tag, sid in (("then", THEN), ("now", NOW)):
    total += picture(sid, BOX, AW, AH, f"area_{tag}.webp", 72)
    for s in base["sites"]:
        total += picture(sid, (s["E"] - HALF, s["N"] - HALF, s["E"] + HALF, s["N"] + HALF), SPX, SPX, f"s{s['id']}_{tag}.webp", 76)
    print("pictures of", sid, "written")
json.dump([THEN, NOW], open(PAIR, "w"))
print("pictures:", round(total / 1e6, 2), "MB in", 2 * (1 + len(base["sites"])), "files")


def pair(sid):
    if sid not in masks:
        _, masks[sid] = classify(sid)
    m = masks[sid]
    return {"id": sid, "date": sid[:10], "km2": round(float((m["snow"] & ~LAKE).sum() * PX), 1), "unknown": round(float((M & ~m["ok"]).sum() * PX), 1)}


# ---- 4. glacier thinning measured from space (Hugonnet et al. 2021), for the glaciers whose centre lies in the study area
def rng(url, lo, hi):
    return get(url, {"Range": f"bytes={lo}-{hi}"}).decode("utf-8", "replace")


def size(url):
    return int(urllib.request.urlopen(urllib.request.Request(url, method="HEAD", headers=UA), timeout=60).headers["Content-Length"])


def region_rows(url, region, key):
    """The rows of one RGI region from a large CSV that is sorted by region, without downloading the rest."""
    n = size(url)

    def first(target):
        lo, hi = 0, n - 1
        while hi - lo > 6000:
            mid = (lo + hi) // 2
            if key(rng(url, mid, min(mid + 4000, n - 1)).split("\n")[1]) >= target:
                hi = mid
            else:
                lo = mid
        return lo

    keep = B + "sat_cache/" + url.rsplit("/", 1)[1].replace(".csv", f"_region{region}.csv")  # the tables do not change
    if not os.path.exists(keep):
        head = rng(url, 0, 3000).split("\n")[0].strip()
        body = rng(url, first(region), first(region + 1) + 8000).split("\n")
        rows = [l.strip() for l in body if l.startswith(f"RGI60-{region:02d}.") and l.count(",") >= head.count(",")]
        open(keep, "w", encoding="utf-8", newline="\n").write(head + "\n" + "\n".join(rows) + "\n")
    return list(csv.DictReader(open(keep, encoding="utf-8")))


rgi = {r["RGIId"]: r for r in region_rows(OGGM + "rgi/rgi62_stats.csv", 11, lambda l: int(l.split(",")[0][6:8]))}
hug = {}
for r in region_rows(OGGM + "geodetic_ref_mb/hugonnet_2021_ds_rgi60_pergla_rates_10_20_worldwide.csv", 11, lambda l: int(l.split(",")[-1])):
    hug.setdefault(r["rgiid"], {})[r["period"][:4] + "-" + r["period"][11:15]] = r
assert len(rgi) == 3927 and len(hug) == 3927, (len(rgi), len(hug))
num = lambda v: float(v) if v not in ("", "nan") else None
inside_ids = [k for k, r in rgi.items() if in_poly(*lv95(float(r["CenLon"]), float(r["CenLat"])))]
periods = {}
for per in ("2000-2010", "2010-2020", "2000-2020"):
    ok = [k for k in inside_ids if num(hug[k][per]["dmdt"]) is not None]
    area = sum(num(hug[k][per]["area"]) for k in ok)
    periods[per] = {"measured": len(ok), "area": round(area / 1e6, 1),
                    "mwe": round(sum(num(hug[k][per]["dmdtda"]) * num(hug[k][per]["area"]) for k in ok) / area, 2),  # metres of water a year, area-weighted
                    "dh": round(sum(num(hug[k][per]["dhdt"]) * num(hug[k][per]["area"]) for k in ok) / area, 2),  # metres of surface lowering a year
                    "water": round(-sum(num(hug[k][per]["dmdt"]) for k in ok) * 1000)}  # Mio m3 of water a year (1 Gt = 1000 Mio m3)
    print("thinning", per, periods[per])
# the dashboard's ten largest glaciers, matched to RGI outlines by position, area and elevation range (3 Oct 2026).
# RGI 6.0 maps the Unterer Grindelwaldgletscher and the Ischmeer as one glacier.
MATCH = {"Grosser Aletschgletscher": "RGI60-11.01450", "Fieschergletscher E": "RGI60-11.01478", "Unteraargletscher": "RGI60-11.01328", "Oberaletschgletscher": "RGI60-11.01827",
         "Kanderfirn N": "RGI60-11.01702", "Gauligletscher": "RGI60-11.01275", "Unterer Grindelwaldgletscher": "RGI60-11.01346", "Oberer Grindelwaldgletscher": "RGI60-11.01270",
         "Langgletscher": "RGI60-11.01698", "Obers Ischmeer E": "RGI60-11.01346"}
glaciers = []
for gl in base["glaciers"]:
    k = MATCH.get(gl["n"])
    if not k:
        continue
    h = hug[k]
    glaciers.append({"n": gl["n"], "rgi": k, "area": round(float(rgi[k]["Area"]), 1), "dh": round(num(h["2000-2020"]["dhdt"]), 2), "err": round(num(h["2000-2020"]["err_dhdt"]), 2),
                     "mwe": round(num(h["2000-2020"]["dmdtda"]), 2), "errm": round(num(h["2000-2020"]["err_dmdtda"]), 2),
                     "dh1": round(num(h["2000-2010"]["dhdt"]), 2), "dh2": round(num(h["2010-2020"]["dhdt"]), 2), "shared": list(MATCH.values()).count(k) > 1})

out = {"at": datetime.date.today().isoformat(), "product": "swissEO S2-SR v200", "grid": RES, "ndsi": NDSI_MIN, "window": WINDOW, "area": round(AREA_KM2, 1),
       "lakes": round(float(LAKE.sum() * PX), 1), "mosaics": len(ids), "used": len(masks), "confirm": CONFIRM, "years": years, "pair": {"then": pair(THEN), "now": pair(NOW)},
       "frames": {"box": BOX, "w": AW, "h": AH, "half": HALF, "px": SPX},
       "thin": {"n": len(inside_ids), "outlines": 2003, "periods": periods, "glaciers": glaciers}}
json.dump(out, open(B + "satellite.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print("wrote satellite.json", os.path.getsize(B + "satellite.json"), "bytes")
