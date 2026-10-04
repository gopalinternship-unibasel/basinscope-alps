"""A time axis for the Glacier size control: how much glacier area a published glacier model leaves, year by year.

  python fetch_glacier_path.py <pipeline folder>

Writes
  build/glacier_path.json    per emission path (RCP2.6, 4.5, 8.5) and year from this year to 2100: glacier area as a share of
                             this year's, median and range over the climate models

Source: OGGM standard projections v1.6.1 (Open Global Glacier Model, Maussion et al. 2019), CMIP5 runs, glacier area summed over Randolph Glacier Inventory region 11 (Central Europe: the Alps and the Pyrenees).
The files hold one column per climate model, in square metres. The share is for the whole region, not for Jungfrau-Aletsch.
"""
import csv, datetime, io, json, statistics as st, sys, urllib.request

SP = sys.argv[1]
B = SP + "/build/"
URL = "https://cluster.klima.uni-bremen.de/~oggm/oggm-standard-projections/oggm-standard-projections-csv-files/1.6.1/common_running_2100/area/CMIP5/2100/RGI11/{r}.csv"
NOW = datetime.date.today().year
out = {"at": datetime.date.today().isoformat(), "base": NOW, "years": list(range(NOW, 2101)), "rcp": {}}
for key, name in (("RCP26", "rcp26"), ("RCP45", "rcp45"), ("RCP85", "rcp85")):
    txt = urllib.request.urlopen(urllib.request.Request(URL.format(r=name), headers={"User-Agent": "basinscope-alps-build/1.0"}), timeout=90).read().decode()
    rows = list(csv.reader(io.StringIO(txt)))
    models = rows[0][1:]
    area = {int(float(r[0])): [float(v) for v in r[1:]] for r in rows[1:]}
    share = {y: [a / b * 100 for a, b in zip(area[y], area[NOW])] for y in out["years"]}  # each model against its own area this year
    out["rcp"][key] = {"n": len(models), "med": [round(st.median(share[y]), 1) for y in out["years"]], "lo": [round(min(share[y]), 1) for y in out["years"]],
                       "hi": [round(max(share[y]), 1) for y in out["years"]]}
    print(key, len(models), "models |", {y: out["rcp"][key]["med"][y - NOW] for y in (2035, 2060, 2085, 2100)})
json.dump(out, open(B + "glacier_path.json", "w", encoding="utf-8"), separators=(",", ":"))
print("wrote glacier_path.json")
