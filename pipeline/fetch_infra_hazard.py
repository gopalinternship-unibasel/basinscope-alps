"""Hazard process areas around the hydropower plants and dams, for the Risk outlook sheet.

  python fetch_infra_hazard.py <pipeline folder>

Reads   build/base.json, build/federal.json (fetch_federal.py), build/energy.json (fetch_energy.py)
Writes  build/infra_hazard.json

Which points: the plants of the stress test on the Energy sheet (the plants matched to the nine catchments) and the dams under federal
supervision within 5 km of a ranked site. For each one the share of the square reaching 250 m from it that the FOEN index maps mark,
measured by hazard_share.py exactly as for the ranked sites, and the ground height from the swisstopo height service, which the
dashboard needs to tell rain from snow in the forecast.
"""
import datetime, json, math, sys, time, urllib.parse, urllib.request
import hazard_share

SP = sys.argv[1]
B = SP + "/build/"
base = json.load(open(B + "base.json", encoding="utf-8"))
federal = json.load(open(B + "federal.json", encoding="utf-8"))
energy = json.load(open(B + "energy.json", encoding="utf-8"))
HEIGHT = "https://api3.geo.admin.ch/rest/services/height"
UA = {"User-Agent": "basinscope-alps-build/1.0"}
R = 250       # metres from each point to the sides of the square, as for the ranked sites
NEAR_KM = 5   # dams this close to a ranked site are included


def get(url, tries=3):
    for i in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90).read()
        except Exception:  # the federal services drop a request now and then
            if i == tries - 1:
                raise
            time.sleep(2 + 2 * i)


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
    it["haz"] = hazard_share.shares(B, it["E"], it["N"], R)
    print(it["k"], it["n"], it["z"], "m", it["haz"])

out = {"at": datetime.date.today().isoformat(), "r": R, "nearKm": NEAR_KM, "items": items}
json.dump(out, open(B + "infra_hazard.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print("wrote infra_hazard.json:", sum(1 for i in items if i["k"] == "plant"), "plants,", sum(1 for i in items if i["k"] == "dam"), "dams")
