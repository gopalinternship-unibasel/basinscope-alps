"""Swiss grid records and the hydropower plants on the rivers of the nine catchments, for the Energy sheet.

  python fetch_energy.py <pipeline folder>      (after fetch_federal.py, which lists the plants)

Writes
  build/energy.json
    mix      mean electricity per calendar month, GWh: production by source, national consumption, net import
    hydro    per year: Swiss hydropower output, precipitation at Grimsel Hospiz in the hydrological year, summer temperature at Jungfraujoch
    winter   net import per winter half-year (October to March), GWh
    fill     filling of the Swiss storage lakes through the year since 2000, per cent of capacity: lowest, median, highest, and the latest two years
    chain    the plants that run on the water of each Hydro-CH2018 catchment (matched by name and location, see CHAIN)

Sources
  Swiss Federal Office of Energy, energy dashboard files (Swissgrid figures): production by source (daily), national consumption (daily),
  cross-border exchange (hourly), filling of the storage lakes (weekly). They only allow the origin map.geo.admin.ch, so they are read here.
  MeteoSwiss open data, daily station values: Grimsel Hospiz (precipitation), Jungfraujoch (air temperature).
"""
import csv, datetime, io, json, statistics as st, sys, time, urllib.request
from collections import defaultdict

SP = sys.argv[1]
B = SP + "/build/"
federal = json.load(open(B + "federal.json", encoding="utf-8"))
BFE = "https://www.uvek-gis.admin.ch/BFE/ogd/"
SMN = "https://data.geo.admin.ch/ch.meteoschweiz.ogd-smn/{a}/ogd-smn_{a}_d_historical.csv"
Y0, Y1 = 2017, 2024  # full calendar years that all three grid files cover


def get(url, tries=3):
    for i in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "basinscope-alps-build/1.0"}), timeout=120).read()
        except Exception as err:
            if i == tries - 1:
                raise
            time.sleep(3 + 3 * i)


def rows(url, enc="utf-8-sig", delim=","):
    return list(csv.DictReader(io.StringIO(get(url).decode(enc)), delimiter=delim))


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def corr(a, b):
    ma, mb = st.mean(a), st.mean(b)
    den = (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / den


# The files repeat some days (later corrections are appended), so every reading is keyed by its day or hour and the last one counts.
# ---- 1. production by source, daily -> per month
SRC = {"Flusskraft": "ror", "Speicherkraft": "sto", "Kernkraft": "nuc", "Photovoltaik": "pv", "Thermische": "oth", "Wind": "oth"}
day_p = {}
for r in rows(BFE + "104/ogd104_stromproduktion_swissgrid.csv"):
    v = num(r["Produktion_GWh"])
    if v is not None and r["Energietraeger"] in SRC:
        day_p[(r["Datum"], r["Energietraeger"])] = v
prod, pdays = defaultdict(float), defaultdict(set)
for (d, e), v in day_p.items():
    prod[(d[:7], SRC[e])] += v
    pdays[d[:7]].add(d)
prod_to = max(d for d, e in day_p)
# ---- 2. national consumption, daily -> per month
day_u = {}
for r in rows(BFE + "103/ogd103_stromverbrauch_swissgrid_lv_und_endv.csv"):
    v = num(r["Landesverbrauch_GWh"])
    if v is not None:
        day_u[r["Datum"]] = v
use, udays = defaultdict(float), defaultdict(set)
for d, v in day_u.items():
    use[d[:7]] += v
    udays[d[:7]].add(d)
use_to = max(day_u)
# ---- 3. cross-border exchange, hourly -> net import per month. A few months miss up to 6% of their hours: they are scaled up to the
# full month. The file thins out after September 2025; a month with less than 90% of its hours does not count.
hour_i = {}
for r in rows(BFE + "107/ogd107_strom_import_export.csv"):
    v = num(r["Nettoimport"])
    if v is not None:
        hour_i[r["Datetime"]] = v
imp, ihours = defaultdict(float), defaultdict(int)
for d, v in hour_i.items():
    imp[d[:7]] += v / 1000
    ihours[d[:7]] += 1


def mdays(ym):
    y, m = int(ym[:4]), int(ym[5:])
    return (datetime.date(y + (m == 12), m % 12 + 1, 1) - datetime.date(y, m, 1)).days


full_p = lambda ym: len(pdays[ym]) == mdays(ym)
full_u = lambda ym: len(udays[ym]) == mdays(ym)
full_i = lambda ym: ihours[ym] >= mdays(ym) * 24 * 0.9
for k in list(imp):
    if full_i(k):
        imp[k] *= max(1, mdays(k) * 24 / ihours[k])
months = [f"{y}-{m:02d}" for y in range(Y0, Y1 + 1) for m in range(1, 13)]
assert all(full_p(k) and full_u(k) and full_i(k) for k in months), "a month of the grid files is incomplete"
mean_m = lambda f: [round(st.mean(f(f"{y}-{m:02d}") for y in range(Y0, Y1 + 1))) for m in range(1, 13)]
mix = {"years": [Y0, Y1], "src": {k: mean_m(lambda ym, k=k: prod[(ym, k)]) for k in ("ror", "sto", "nuc", "pv", "oth")},
       "use": mean_m(lambda ym: use[ym]), "imp": mean_m(lambda ym: imp[ym])}
imp_to = max(k for k in imp if full_i(k))
winter = []
for y in range(2017, int(imp_to[:4]) + 1):
    ks = [f"{y}-{m:02d}" for m in (10, 11, 12)] + [f"{y + 1}-{m:02d}" for m in (1, 2, 3)]
    if all(k in imp and full_i(k) for k in ks):
        winter.append([f"{y}/{str(y + 1)[2:]}", round(sum(imp[k] for k in ks))])
print("mix", mix["src"]["ror"][:3], "... use", mix["use"][:3], "imp", mix["imp"], "| winters", winter)


# ---- 4. climate at two MeteoSwiss stations inside the area
def station(abbr, col):
    out = defaultdict(list)
    for r in rows(SMN.format(a=abbr), "latin-1", ";"):
        v, d = num(r[col]), r["reference_timestamp"][:10]
        if v is not None:
            out[d[6:10] + "-" + d[3:5]].append(v)
    return out


rain, temp = station("grh", "rre150d0"), station("jun", "tre200d0")
hydro = []
for y in range(2015, int(prod_to[:4]) + 1):
    ks = [f"{y}-{m:02d}" for m in range(1, 13)]
    hy = [f"{y - 1}-{m:02d}" for m in (10, 11, 12)] + [f"{y}-{m:02d}" for m in range(1, 10)]
    su = [f"{y}-{m:02d}" for m in (6, 7, 8)]
    if not all(full_p(k) for k in ks) or not all(len(rain[k]) >= mdays(k) - 2 for k in hy) or not all(len(temp[k]) >= mdays(k) - 2 for k in su):
        continue
    hydro.append([y, round(sum(prod[(k, "ror")] for k in ks)), round(sum(prod[(k, "sto")] for k in ks)), round(sum(sum(rain[k]) for k in hy)),
                  round(st.mean(v for k in su for v in temp[k]), 2)])
tot = [h[1] + h[2] for h in hydro]
r_rain, r_temp = round(corr(tot, [h[3] for h in hydro]), 2), round(corr(tot, [h[4] for h in hydro]), 2)
print("hydro years", hydro[0][0], "to", hydro[-1][0], "| r with precipitation", r_rain, "| r with summer temperature", r_temp)

# ---- 5. filling of the storage lakes through the year, per cent of capacity, by week of the year
fill_rows = [r for r in rows(BFE + "17/ogd17_fuellungsgrad_speicherseen.csv") if num(r.get("TotalCH_speicherinhalt_gwh")) is not None]
by_week, by_year = defaultdict(list), defaultdict(dict)
for r in fill_rows:
    d = datetime.date.fromisoformat(r["Datum"])
    w = min(51, (d.timetuple().tm_yday - 1) // 7)
    pc = round(float(r["TotalCH_speicherinhalt_gwh"]) / float(r["TotalCH_max_speicherinhalt_gwh"]) * 100, 1)
    by_year[d.year][w] = pc
    by_week[w].append((d.year, pc))
last_y = max(by_year)
past = lambda w: [pc for y, pc in by_week[w] if y < last_y]
fill = {"years": [min(by_year), last_y - 1], "lo": [min(past(w)) for w in range(52)], "hi": [max(past(w)) for w in range(52)], "med": [round(st.median(past(w)), 1) for w in range(52)],
        "now": [last_y, [by_year[last_y].get(w) for w in range(52)]], "prev": [last_y - 1, [by_year[last_y - 1].get(w) for w in range(52)]], "to": fill_rows[-1]["Datum"]}
while fill["now"][1] and fill["now"][1][-1] is None:
    fill["now"][1].pop()
print("fill", fill["years"], "weeks", len(fill["med"]), "this year up to week", len(fill["now"][1]))

# ---- 6. the plants on the water of each catchment. This match is ours, by plant name and location on the map; it has not been checked
# with the operators. Plants on side streams outside a catchment and plants out of service are left out.
CHAIN = {
    3004: ["Bitsch", "Moerel Aletsch"],                                           # Massa: Gebidem reservoir to Bitsch, and the Aletsch plant at Mörel
    3003: ["Loetschen", "Wiler Kippel", "Blatten 1 Runeja", "Blatten 2 Fuxloch", "Fafleralp", "Breithorn Fafleralp"],   # Lonza and its upper side streams
    4128: ["Grimsel 1 Oberaar", "Grimsel 1 Nachschubmaschine", "Handeck 2 und 2a", "Handeck 3", "Innertkirchen 1 und 1a"],  # Aare: the Grimsel chain of KWO
    4022: ["Innertkirchen 3"],                                                    # Urbachwasser
    3143: ["Fieschertal", "Wysswasser"],                                          # Wysswasser below the Fieschergletscher
    4006: ["Kandergrund"],                                                        # Kander below Kandersteg
    4134: ["Kandersteg Dorf"],                                                    # Öschibach
    4020: ["Stechelberg", "Sandweidli Sousbach"],                                 # Weisse Lütschine, Lauterbrunnen valley
    3124: ["Baltschieder"],                                                       # Baltschiederbach
}
by_name = {p["n"]: p for p in federal["plants"]}
chain = {}
for hc, names in CHAIN.items():
    ps = []
    for n in names:
        p = by_name[n]
        assert p["st"] == "in operation" and p["gwh"], n
        ps.append({"n": p["n"], "ror": p["type"] == "run-of-river plant", "mw": p["mw"], "gwh": p["gwh"]})
    chain[str(hc)] = ps
print("chain:", sum(len(v) for v in chain.values()), "plants,", round(sum(p["gwh"] for v in chain.values() for p in v)), "GWh a year expected")

out = {"at": datetime.date.today().isoformat(), "to": {"prod": prod_to, "use": use_to, "imp": imp_to, "fill": fill["to"]}, "mix": mix,
       "hydro": hydro, "r": {"rain": r_rain, "temp": r_temp}, "winter": winter, "fill": fill, "chain": chain}
json.dump(out, open(B + "energy.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print("wrote energy.json:", len(json.dumps(out, separators=(",", ":"))), "bytes")
