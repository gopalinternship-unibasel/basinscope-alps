"""Satellite base map: the clearest recent Sentinel-2 mosaic of the map extent, from swisstopo's swissEO S2-SR.

  python fetch_satellite.py <build folder> [first day] [last day]

Looks at every mosaic between the two days (default: 1 August to 30 September 2026), reads its cloud mask over the
dashboard's map extent, keeps the one with full coverage and the least cloud, and writes
  build/base_s2.webp   true-colour picture at 1.5 times the base map's size
  build/base_s2.json   its acquisition date and cloud share

The federal map service only serves the newest mosaic, whatever its weather, so the picture is read from the
cloud-optimised files of the federal data catalogue instead. Needs rasterio and Pillow.
"""
import json, os, sys, urllib.request
import numpy as np
import rasterio
from rasterio.windows import from_bounds
from PIL import Image

SP = sys.argv[1]
B = SP + "/build/"
D0 = sys.argv[2] if len(sys.argv) > 2 else "2026-08-01"
D1 = sys.argv[3] if len(sys.argv) > 3 else "2026-09-30"
BOX = json.load(open(B + "federal.json", encoding="utf-8"))["box"]  # LV95, same box as the hazard overlays
geo = json.load(open(B + "geo.json"))
W, H = int(geo["W"] * 1.5), int(geo["H"] * 1.5)
STAC = "https://data.geo.admin.ch/api/stac/v0.9/collections/ch.swisstopo.swisseo_s2-sr_v200/items"
os.environ.update({"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif", "GDAL_HTTP_MAX_RETRY": "3"})


def read(url, shape, bands=None):
    with rasterio.open("/vsicurl/" + url) as src:
        win = from_bounds(*BOX, transform=src.transform)
        return src.read(bands, window=win, out_shape=shape), src.nodata  # a reduced out_shape is read from the file's overviews


url = f"{STAC}?limit=100&datetime={D0}T00:00:00Z/{D1}T23:59:59Z"
items = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "basinscope-alps-build/1.0"}), timeout=90))["features"]
found = []
for it in sorted(items, key=lambda x: x["properties"]["datetime"]):
    w, s, e, n = it["bbox"]
    if not (w < 7.6 and e > 8.6):  # the flight path has to span the study area
        continue
    asset = lambda tag: next(v["href"] for k, v in it["assets"].items() if k.endswith(tag))
    try:
        mask, _ = read(asset("_cloudmask_10m.tif"), (1, H // 8, W // 8))
        rgb, _ = read(asset("_tci_10m.tif"), (3, H // 8, W // 8))
    except Exception as err:
        print(it["id"], "not readable:", str(err)[:80])
        continue
    data = rgb.sum(axis=0) > 0
    cover, cloud = float(data.mean()), float((mask[0][data] > 0).mean()) if data.any() else 1.0
    print(it["id"], f"coverage {cover:.0%}, cloud or shadow {cloud:.0%}")
    found.append((it, cover, cloud, asset))
full = [f for f in found if f[1] > 0.93]
assert full, "no mosaic covers the map extent in this period"
it, cover, cloud, asset = min(full, key=lambda f: f[2])
print("picked", it["id"], f"coverage {cover:.0%}, cloud {cloud:.0%}")
rgb, _ = read(asset("_tci_10m.tif"), (3, H, W))
img = Image.fromarray(np.transpose(rgb, (1, 2, 0)).astype("uint8"), "RGB")
img.save(B + "base_s2.webp", "WEBP", quality=74, method=6)
json.dump({"date": it["properties"]["datetime"][:10], "id": it["id"], "cloud_percent": round(cloud * 100), "coverage_percent": round(cover * 100)}, open(B + "base_s2.json", "w"))
print("wrote base_s2.webp", img.size, os.path.getsize(B + "base_s2.webp"), "bytes")
