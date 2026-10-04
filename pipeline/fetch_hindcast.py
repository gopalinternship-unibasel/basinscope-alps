"""Past forecasts for the Risk outlook: what the trigger rule would have said on every day since 2021.

  python fetch_hindcast.py <pipeline folder>

Writes
  build/hindcast.json    per day the two figures the Risk outlook works with (highest zero-degree level, precipitation),
                         per site the days with 10 mm of rain or more, and a short list of documented events

The page applies its own thresholds to these figures, so moving a threshold on the Risk outlook sheet re-runs the test.
The figures are worked out exactly as the page does for the live forecast (see outlook() in template.html):
  per hour  the median zero-degree level and the mean precipitation of the 15 site locations
  per day   the highest of those hourly levels, and the sum of the hourly precipitation
  per site  rain only: precipitation that falls while the zero-degree level is more than 300 m above the site

Source: Open-Meteo Historical Forecast API (CC BY 4.0), which keeps the first hours of every past model run. It serves the best
model it has for each date, so the model behind the figures changes over the years; the live outlook uses MeteoSwiss ICON-CH2.
"""
import datetime, json, sys, time, urllib.parse, urllib.request

SP = sys.argv[1]
B = SP + "/build/"
base = json.load(open(B + "base.json", encoding="utf-8"))
SITES = base["sites"]
SNOWLINE_M = 300   # as in template.html
MIN_MM = 10        # the lowest setting of the rain threshold on the page: a site day below it can never count
FIRST = datetime.date(2021, 1, 1)
LAST = datetime.date.today() - datetime.timedelta(days=1)
API = "https://historical-forecast-api.open-meteo.com/v1/forecast"


def wgs(E, N):  # LV95 to WGS84, the swisstopo approximation the page uses
    y, x = (E - 2600000) / 1e6, (N - 1200000) / 1e6
    lon = (2.6779094 + 4.728982 * y + 0.791484 * y * x + 0.1306 * y * x * x - 0.0436 * y * y * y) * 100 / 36
    lat = (16.9023892 + 3.238272 * x - 0.270978 * y * y - 0.002528 * x * x - 0.0447 * y * y * x - 0.0140 * x * x * x) * 100 / 36
    return lat, lon


def get(url, tries=4):
    for i in range(tries):
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "basinscope-alps-build/1.0"}), timeout=120).read())
        except Exception as err:
            if i == tries - 1:
                raise
            time.sleep(5 + 10 * i)


pts = [wgs(s["E"], s["N"]) for s in SITES]
zs = [s["z"] for s in SITES]
days = {}  # date -> {"z": highest hourly median level, "rain": sum of hourly means, "site": [rain per site]}
a = FIRST
while a <= LAST:
    b = min(datetime.date(a.year, 12, 31), LAST)
    q = {"latitude": ",".join(f"{p[0]:.4f}" for p in pts), "longitude": ",".join(f"{p[1]:.4f}" for p in pts), "elevation": ",".join(str(z) for z in zs),
         "hourly": "freezing_level_height,precipitation", "start_date": a.isoformat(), "end_date": b.isoformat(), "timezone": "Europe/Zurich"}
    j = get(API + "?" + urllib.parse.urlencode(q, safe=","))
    j = j if isinstance(j, list) else [j]
    assert len(j) == len(SITES), "one answer per site expected"
    time_ = j[0]["hourly"]["time"]
    fl = [o["hourly"]["freezing_level_height"] for o in j]
    pr = [o["hourly"]["precipitation"] for o in j]
    for i, t in enumerate(time_):
        d = days.setdefault(t[:10], {"z": None, "rain": 0.0, "site": [0.0] * len(SITES), "n": 0})
        lv = sorted(v[i] for v in fl if v[i] is not None)
        if lv:
            med = lv[len(lv) >> 1]
            d["z"] = med if d["z"] is None else max(d["z"], med)
        pv = [v[i] for v in pr if v[i] is not None]
        if pv:
            d["rain"] += sum(pv) / len(pv)
            d["n"] += 1
        for s in range(len(SITES)):
            p, z = pr[s][i], fl[s][i]
            if p is not None and z is not None and z > zs[s] + SNOWLINE_M:
                d["site"][s] += p
    print(a.year, len(time_) // 24, "days")
    a = b + datetime.timedelta(days=1)
    time.sleep(2)

keys = sorted(days)
assert keys[0] == FIRST.isoformat() and len(keys) == (LAST - FIRST).days + 1, "a gap in the days"
while days[keys[0]]["z"] is None:  # the archive starts in March 2021: drop the empty days before it
    keys.pop(0)
missing = [k for k in keys if days[k]["z"] is None or days[k]["n"] < 20]
print("days", len(keys), "from", keys[0], "| days without a usable forecast:", len(missing), missing[:5])

# Documented events in or next to the study area, to set the rule against. kind: what set the event off.
EVENTS = [
    {"from": "2021-07-12", "to": "2021-07-15", "name": "Days of rain in mid-July, Lake Thun at the highest flood danger level",
     "where": "Bernese Oberland, north of the study area", "kind": "long rain",
     "src": "https://www.plattformj.ch/artikel/195899/", "by": "Jungfrau Zeitung, review of 2021"},
    {"from": "2024-06-29", "to": "2024-06-30", "name": "Storms in Valais: debris flows, the Rhône in flood, Goms and Binntal hit",
     "where": "Upper Valais, southern edge of the study area", "kind": "heavy rain with a high zero-degree level",
     "src": "https://www.srf.ch/news/schweiz/unwetter-in-der-schweiz-ticker-zu-den-unwettern-im-wallis-und-tessin-zum-nachlesen", "by": "SRF"},
    {"from": "2024-08-12", "to": "2024-08-12", "name": "Thunderstorm: debris flow of the Milibach in Brienz, road to Grindelwald cut",
     "where": "Bernese Oberland, northern edge of the study area", "kind": "local thunderstorm",
     "src": "https://www.plattformj.ch/artikel/223876/", "by": "Jungfrau Zeitung"},
    {"from": "2025-05-28", "to": "2025-05-28", "name": "Collapse of the Birch glacier above Blatten",
     "where": "Lötschental, inside the study area", "kind": "glacier collapse, which the rule does not cover", "cover": False,
     "src": "https://www.srf.ch/news/schweiz/katastrophe-im-loetschental-ein-grollen-ein-beben-und-in-blatten-ist-nichts-mehr-wie-zuvor", "by": "SRF"},
]

out = {
    "at": datetime.date.today().isoformat(), "from": keys[0], "to": keys[-1], "minMm": MIN_MM,
    # zero-degree level in tens of metres (-1 = no forecast), precipitation in tenths of a millimetre
    "z": [-1 if days[k]["z"] is None else round(days[k]["z"] / 10) for k in keys],
    "rain": [round(days[k]["rain"] * 10) for k in keys],
    # per site id: [day index, tenths of a millimetre of rain] for the days with MIN_MM or more
    "site": {str(s["id"]): [[i, round(days[k]["site"][n] * 10)] for i, k in enumerate(keys) if days[k]["site"][n] >= MIN_MM] for n, s in enumerate(SITES)},
    "events": EVENTS,
}
json.dump(out, open(B + "hindcast.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print("wrote hindcast.json:", len(json.dumps(out, separators=(",", ":"))), "bytes | site days kept:", sum(len(v) for v in out["site"].values()))
