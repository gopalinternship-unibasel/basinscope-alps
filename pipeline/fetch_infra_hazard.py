"""Hazard process areas around the hydropower plants and dams, for the Risk outlook sheet.

  python fetch_infra_hazard.py <pipeline folder>

Reads   build/base.json, build/federal.json (fetch_federal.py), build/energy.json (fetch_energy.py)
Writes  build/infra_hazard.json

Which points: the plants of the stress test on the Energy sheet (the plants matched to the nine catchments) and the dams under federal
supervision within 5 km of a ranked site. For each one the share of a 250 m square that the FOEN index maps mark, read from the federal
map service exactly as fetch_federal.py does for the ranked sites, and the ground height from the swisstopo height service, which the
dashboard needs to tell rain from snow in the forecast.
"""
import datetime, io, json, math, sys, time, urllib.parse, urllib.request
from PIL import Image

SP = sys.argv[1]
B = SP + "/build/"
base = json.load(open(B + "base.json", encoding="utf-8"))
federal = json.load(open(B + "federal.json", encoding="utf-8"))
energy = json.load(open(B + "energy.json", encoding="utf-8"))
WMS = "https://wms.geo.admin.ch/"
HEIGHT = "https://api3.geo.admin.ch/rest/services/height"
UA = {"User-Agent": "basinscope-alps-build/1.0"}
HAZ = {"permafrost": "ch.bafu.permafrost", "debris": "ch.bafu.silvaprotect-murgang", "rockfall": "ch.bafu.silvaprotect-sturz",
       "landslide": "ch.bafu.silvaprotect-hangmuren"}
R = 250       # metres around each point, the same square as for the ranked sites
NEAR_KM = 5   # dams this close to a ranked site are included


def get(url, tries=3):
    for i in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90).read()
        except Exception:  # the federal services drop a request now and then
            if i == tries - 1:
                raise
            time.sleep(2 + 2 * i)


def hazard(E, N):
    row = {}
    for k, layer in HAZ.items():
        q = {"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap", "LAYERS": layer, "STYLES": "", "CRS": "EPSG:2056",
             "BBOX": ",".join(str(v) for v in (E - R, N - R, E + R, N + R)), "WIDTH": 100, "HEIGHT": 100, "FORMAT": "image/png", "TRANSPARENT": "true"}
        alpha = Image.open(io.BytesIO(get(WMS + "?" + urllib.parse.urlencode(q)))).convert("RGBA").getchannel("A")
        row[k] = round(sum(1 for v in alpha.getdata() if v > 40) / (100 * 100) * 100)
    return row


def height(E, N):
    return round(float(json.loads(get(HEIGHT + "?" + urllib.parse.urlencode({"easting": E, "northing": N, "sr": 2056})))["height"]))


by_name = {p["n"]: p for p in federal["plants"]}
items = []
for hc, chain in energy["chain"].items():
    for c in chain:
        p = by_name[c["n"]]
        items.append({"k": "plant", "n": p["n"], "type": p["type"], "gwh": p["gwh"], "mw": p["mw"], "hc": int(hc), "E": p["E"], "N": p["N"]})
for d in federal["dams"]:
    km = min(math.hypot(d["E"] - s["E"], d["N"] - s["N"]) / 1000 for s in base["sites"])
    if km <= NEAR_KM:
        items.append({"k": "dam", "n": d["n"], "type": d["type"], "h": d["h"], "vol": d["vol"], "y": d["y"], "E": d["E"], "N": d["N"]})
for it in items:
    it["z"] = height(it["E"], it["N"])
    it["haz"] = hazard(it["E"], it["N"])
    print(it["k"], it["n"], it["z"], "m", it["haz"])

out = {"at": datetime.date.today().isoformat(), "r": R, "nearKm": NEAR_KM, "items": items}
json.dump(out, open(B + "infra_hazard.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print("wrote infra_hazard.json:", sum(1 for i in items if i["k"] == "plant"), "plants,", sum(1 for i in items if i["k"] == "dam"), "dams")
