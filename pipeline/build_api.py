"""Write the read-only data API of the self-hosted site.

Reads   <site>/data/dataset.json
Writes  <site>/api/v1/*.json, <site>/api/v1/sites.geojson, <site>/api/v1/openapi.json, <site>/api/index.html

Run on its own with `python build_api.py <site folder>`; build.py calls it after writing the dataset.
"""
import json, os, sys, shutil, datetime, hashlib

VERSION = "1.3.0"
BASE = "https://gopalinternship-unibasel.github.io/basinscope-alps/api/v1"
TRIFT = {"chf": 387, "vol": 85, "gwh": 215}  # same reference project as the dashboard's business case
TYPE = {"new": "New site", "reservoir": "Existing reservoir", "lake": "Existing lake", "settlement": "Settlement area"}
PROT = {"floodplain": ("Floodplain of national importance", 2), "mire_landscape": ("Mire landscape of national importance", 2),
        "fen": ("Fen of national importance", 2), "bog": ("Raised bog of national importance", 2),
        "hydro_waiver": ("Hydropower use waived for compensation", 2), "unesco": ("UNESCO World Heritage property", 1),
        "bln": ("Federal landscape inventory (BLN)", 1), "game_reserve": ("Federal game reserve", 1)}
LEVEL = {0: "none", 1: "landscape", 2: "strict"}
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
SOURCES = [
    {"what": "Sites, volumes, dam lengths, glacier areas", "source": "Team terrain analysis on swissALTI3D (swisstopo) and the Swiss Glacier Inventory SGI 2016 (GLAMOS)", "as_of": "2026-10-02"},
    {"what": "Monthly runoff scenarios", "source": "Hydro-CH2018, data set L03, Federal Office for the Environment (FOEN)"},
    {"what": "Protected areas", "source": "Federal inventories (FOEN, SFOE) through api3.geo.admin.ch, 250 m square around each point", "as_of": "2026-10-03"},
    {"what": "Hazard process areas", "source": "SilvaProtect-CH (debris flow, rockfall, shallow landslide) and the map of potential permafrost distribution, FOEN, read from wms.geo.admin.ch for a 250 m square around each site. Index maps, valid to 1:50,000", "as_of": "2026-10-03"},
    {"what": "Hydropower plants, dams, reservoir storage", "source": "Hydropower statistics (WASTA), dams under federal supervision and filling level of the storage lakes, Swiss Federal Office of Energy (SFOE)"},
    {"what": "Satellite scenes, snow and ice extent", "source": "swissEO S2-SR, swisstopo, contains modified Copernicus Sentinel data 2015-2026; the extent is the dashboard's own count on those scenes"},
    {"what": "Glacier thinning", "source": "Hugonnet et al. 2021, Nature 592 (ASTER satellite stereo pictures, 2000-2019), on Randolph Glacier Inventory 6.0 outlines"},
    {"what": "Grid records", "source": "Electricity production by source, national consumption, cross-border exchange and filling of the storage lakes: Swiss Federal Office of Energy, energy dashboard files (Swissgrid figures). Precipitation at Grimsel Hospiz and air temperature at Jungfraujoch: MeteoSwiss open data"},
    {"what": "Glacier area by year", "source": "OGGM standard projections v1.6.1 (Open Global Glacier Model, Maussion et al. 2019), CMIP5 runs, Randolph Glacier Inventory region 11 (Central Europe)"},
    {"what": "Past forecasts", "source": "Forecast archive of Open-Meteo (CC BY 4.0): zero-degree level and precipitation at the 15 site locations"},
]
NOTICE = ("Screening-level results from terrain, inventory and index-map evidence only. Natural hazards are read from federal index maps, not assessed on site; geology is not assessed. "
          "Not a basis for engineering or investment decisions without a feasibility study.")


def wgs84(E, N):
    """LV95 to WGS84 with swisstopo's approximate formulas (about 1 m)."""
    y, x = (E - 2600000) / 1e6, (N - 1200000) / 1e6
    lon = 2.6779094 + 4.728982 * y + 0.791484 * y * x + 0.1306 * y * x * x - 0.0436 * y ** 3
    lat = 16.9023892 + 3.238272 * x - 0.270978 * y * y - 0.002528 * x * x - 0.0447 * y * y * x - 0.0140 * x ** 3
    return round(lon * 100 / 36, 6), round(lat * 100 / 36, 6)


def protection(hits):
    out = [{"kind": h["k"], "label": PROT[h["k"]][0], "level": LEVEL[PROT[h["k"]][1]], "name": h["name"]} for h in hits if h["k"] in PROT]
    top = max([PROT[h["k"]][1] for h in hits if h["k"] in PROT], default=0)
    return {"level": LEVEL[top], "strict": top == 2, "areas": out}


HAZ = {"debris": "debris_flow", "landslide": "shallow_landslide", "rockfall": "rockfall", "permafrost": "permafrost"}


def site(s, fed=None):
    lon, lat = wgs84(s["E"], s["N"])
    hz = ((fed or {}).get("haz") or {}).get(str(s["id"]))
    return {
        "id": s["id"], "report_rank": s["id"], "name": s["name"], "type": s["type"], "type_label": TYPE[s["type"]], "valley": s["valley"],
        "location": {"easting_lv95": s["E"], "northing_lv95": s["N"], "longitude": lon, "latitude": lat, "elevation_m": s["z"]},
        "glacier_area_upstream_km2": s["gl"],
        "basin": {"volume_10m_dam_mio_m3": s["v10"], "volume_20m_dam_mio_m3": s["v20"], "lake_area_ha": s["lake"], "dam_length_m": s["dam"]},
        "illustrative_investment_chf_m": {"dam_10m": round(s["v10"] / TRIFT["vol"] * TRIFT["chf"], 1), "dam_20m": round(s["v20"] / TRIFT["vol"] * TRIFT["chf"], 1)},
        "catchment_id": s["hc"],
        "protection": protection(s.get("prot", [])),
        "hazard_index_percent": {v: hz.get(k, 0) for k, v in HAZ.items()} if hz else None,
        "confidence_note": s.get("low"),
        "notes": s.get("notes", []),
    }


def scenarios(q):
    return {rcp: {per: {st: dict(zip(MONTHS, vals)) for st, vals in stats.items()} for per, stats in periods.items()} for rcp, periods in q.items()}


def main(site_dir):
    d = json.load(open(os.path.join(site_dir, "data", "dataset.json"), encoding="utf-8"))
    api = os.path.join(site_dir, "api")
    out = os.path.join(api, "v1")
    shutil.rmtree(api, ignore_errors=True)
    os.makedirs(os.path.join(out, "sites"))
    os.makedirs(os.path.join(out, "catchments"))
    generated = datetime.date.today().isoformat()
    logo_v = hashlib.sha1(open(os.path.join(site_dir, "assets/logo.webp"), "rb").read()).hexdigest()[:8]

    def write(path, data, count=None):
        meta = {"api_version": VERSION, "generated": generated, "notice": NOTICE, "docs": BASE.rsplit("/", 1)[0] + "/"}
        if count is not None:
            meta["count"] = count
        json.dump({"meta": meta, "data": data}, open(os.path.join(out, path), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    fed = d.get("federal") or {}
    sites = [site(s, fed) for s in d["sites"]]
    write("sites.json", sites, len(sites))
    for s in sites:
        write(f"sites/{s['id']}.json", s)
    feats = [{"type": "Feature", "id": s["id"], "geometry": {"type": "Point", "coordinates": [s["location"]["longitude"], s["location"]["latitude"]]},
              "properties": {"id": s["id"], "name": s["name"], "type": s["type"], "valley": s["valley"], "elevation_m": s["location"]["elevation_m"],
                             "glacier_area_upstream_km2": s["glacier_area_upstream_km2"], **s["basin"],
                             "investment_10m_dam_chf_m": s["illustrative_investment_chf_m"]["dam_10m"], "investment_20m_dam_chf_m": s["illustrative_investment_chf_m"]["dam_20m"],
                             "protection_level": s["protection"]["level"], "strict_protection": s["protection"]["strict"], "catchment_id": s["catchment_id"]}} for s in sites]
    json.dump({"type": "FeatureCollection", "features": feats}, open(os.path.join(out, "sites.geojson"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    cands = []
    for i, c in enumerate(d["candidates"]):
        lon, lat = wgs84(c["E"], c["N"])
        cands.append({"id": f"c{i + 1}", "location": {"easting_lv95": c["E"], "northing_lv95": c["N"], "longitude": lon, "latitude": lat}, "protection": protection(c.get("prot", []))})
    write("candidates.json", cands, len(cands))

    catch = []
    for k, c in d["catchments"].items():
        head = {"id": c["id"], "river": c["river"], "gauge_place": c["place"], "area_km2": c["area"], "glacier_cover_percent": c["glac"],
                "site_ids": [s["id"] for s in sites if s["catchment_id"] == c["id"]]}
        catch.append(head)
        write(f"catchments/{k}.json", {**head, "runoff_unit": "mm per month", "runoff": scenarios(c["q"])})
    write("catchments.json", catch, len(catch))

    write("glaciers.json", [{"name": g["n"], "area_km2": g["a"], "length_km": g["l"], "lowest_m": g["lo"], "highest_m": g["hi"]} for g in d["glaciers"]], len(d["glaciers"]))
    write("exits.json", [{"path": e["n"], "glacier_area_km2": e["g"], "description": e["d"], **({"warning": e["warn"]} if e.get("warn") else {})} for e in d["exits"]], len(d["exits"]))
    write("elevation-bands.json", [{"band_from_m": b["z"], "area_km2": b["ar"], "glacier_area_km2": b["gl"]} for b in d["bands"]], len(d["bands"]))

    plants = []
    for p in fed.get("plants", []):
        lon, lat = wgs84(p["E"], p["N"])
        plants.append({"name": p["n"], "place": p["loc"], "type": p["type"], "status": p["st"], "turbine_power_mw": p["mw"], "expected_production_gwh_per_year": p["gwh"], "in_operation_since": p["y"],
                       "location": {"easting_lv95": p["E"], "northing_lv95": p["N"], "longitude": lon, "latitude": lat}})
    write("hydropower-plants.json", plants, len(plants))
    dams = []
    for p in fed.get("dams", []):
        lon, lat = wgs84(p["E"], p["N"])
        dams.append({"name": p["n"], "reservoir": p["res"], "type": p["type"], "height_m": p["h"], "crest_length_m": p["crest"], "reservoir_volume_mio_m3": p["vol"], "built": p["y"], "purpose": p["aim"],
                     "location": {"easting_lv95": p["E"], "northing_lv95": p["N"], "longitude": lon, "latitude": lat}})
    write("dams.json", dams, len(dams))
    sto = fed.get("storage") or {}
    write("reservoir-storage.json", {"date": sto.get("date"), "energy_gwh": sto.get("gwh"), "capacity_gwh": sto.get("max"), "area": "Switzerland",
                                     "past_year": [{"date": a, "energy_gwh": v} for a, v in sto.get("year", [])]})

    sat = d.get("satellite") or {}
    if sat:
        pics = BASE.rsplit("/", 2)[0] + "/assets/sat/"
        scene = lambda s: {"scene": s["id"], "date": s["date"], "snow_and_ice_km2": s["km2"], "under_cloud_km2": s["unknown"]}
        thin = sat["thin"]
        write("satellite.json", {
            "snow_and_ice_at_end_of_summer": {
                "product": sat["product"] + ", swisstopo (Copernicus Sentinel-2)", "study_area_km2": sat["area"],
                "method": f"NDSI >= {sat['ndsi']} on a {sat['grid']} m grid inside the study area, clear pixels only, persistent water taken out. Per year: the clear scene between 10 August and 5 October "
                          f"with the least snow and ice that a second scene confirms within {round(sat['confirm'] * 100)} per cent. Misses debris-covered ice and ice in deep shadow, includes snow fields outside the glaciers.",
                "mosaics_screened": sat["mosaics"], "mosaics_measured": sat["used"],
                "years": [{"year": y["y"], **({**scene(y), "confirmed_by_second_scene": y["confirmed"], "partly_cloudy": y["partly"]} if "km2" in y else {"scene": None}),
                           "clear_scenes": y["clear"], "passes": y["passes"]} for y in sat["years"]]},
            "scene_pair": {"then": scene(sat["pair"]["then"]), "now": scene(sat["pair"]["now"]),
                           "pictures": {"study_area": [pics + "area_then.webp", pics + "area_now.webp"], "site": pics + "s{site id}_then.webp and s{site id}_now.webp, 4 km square at 10 m per pixel",
                                        "study_area_box_lv95": sat["frames"]["box"]}},
            "glacier_thinning": {
                "source": "Hugonnet et al. 2021, Nature 592, doi:10.1038/s41586-021-03436-z: elevation change from ASTER satellite stereo pictures, on Randolph Glacier Inventory 6.0 outlines",
                "glaciers_with_centre_in_study_area": thin["n"], "outline_year": thin["outlines"],
                "study_area": [{"period": k[:5] + str(int(k[5:]) - 1), "glaciers_measured": v["measured"], "area_km2": v["area"], "mass_change_m_water_per_year": v["mwe"],
                                "surface_change_m_per_year": v["dh"], "net_water_loss_mio_m3_per_year": v["water"]} for k, v in thin["periods"].items()],
                "glaciers": [{"name": g["n"], "rgi_id": g["rgi"], "rgi_area_km2": g["area"], "surface_change_m_per_year": g["dh"], "uncertainty_m_per_year": g["err"],
                              "mass_change_m_water_per_year": g["mwe"], "mass_uncertainty_m_water_per_year": g["errm"], "surface_change_2000_2009": g["dh1"], "surface_change_2010_2019": g["dh2"],
                              "shares_rgi_outline": g["shared"]} for g in thin["glaciers"]]}})

    en, hc, gp = d.get("energy") or {}, d.get("hindcast") or {}, d.get("glacierPath") or {}
    if en:
        mix, fill = en["mix"], en["fill"]
        write("grid.json", {
            "data_up_to": {"production": en["to"]["prod"], "consumption": en["to"]["use"], "cross_border_exchange": en["to"]["imp"], "storage_lakes": en["to"]["fill"]},
            "monthly_mean_gwh": {"years": mix["years"], "months": MONTHS, "national_consumption": mix["use"], "net_import": mix["imp"],
                                 "production": {"run_of_river": mix["src"]["ror"], "storage": mix["src"]["sto"], "nuclear": mix["src"]["nuc"], "solar": mix["src"]["pv"], "thermal_and_wind": mix["src"]["oth"]}},
            "hydropower_by_year": {"correlation_with_precipitation": en["r"]["rain"], "correlation_with_summer_temperature": en["r"]["temp"],
                                   "years": [{"year": h[0], "run_of_river_gwh": h[1], "storage_gwh": h[2], "precipitation_grimsel_hospiz_oct_to_sep_mm": h[3], "summer_temperature_jungfraujoch_c": h[4]} for h in en["hydro"]]},
            "winter_net_import_gwh": [{"winter": w, "october_to_march": v} for w, v in en["winter"]],
            "storage_lakes_percent_full_by_week": {"range_years": fill["years"], "lowest": fill["lo"], "median": fill["med"], "highest": fill["hi"], "latest_year": {"year": fill["now"][0], "values": fill["now"][1]}},
            "plants_by_catchment": [{"catchment_id": int(k), "match": "by plant name and location on the map, not checked with the operators",
                                     "plants": [{"name": q["n"], "run_of_river": q["ror"], "turbine_power_mw": q["mw"], "expected_production_gwh_per_year": q["gwh"]} for q in v]} for k, v in en["chain"].items()]})
    if hc:
        write("risk-hindcast.json", {
            "from": hc["from"], "to": hc["to"],
            "method": "Per day, from the forecast for that day at the 15 site locations: the highest hourly median zero-degree level and the summed hourly mean precipitation. "
                      "Per site: rain only, precipitation that falls while the zero-degree level is more than 300 m above the site; days below " + str(hc["minMm"]) + " mm are left out. "
                      "The dashboard applies its two thresholds to these figures.",
            "zero_degree_level_m": [None if z < 0 else z * 10 for z in hc["z"]], "precipitation_mm": [v / 10 for v in hc["rain"]],
            "site_rain_mm": {sid: [[i, v / 10] for i, v in rows] for sid, rows in hc["site"].items()},
            "events": [{"from": e["from"], "to": e["to"], "event": e["name"], "where": e["where"], "kind": e["kind"], "covered_by_the_rule": e.get("cover", True), "source": e["src"]} for e in hc["events"]]})
    if gp:
        write("glacier-path.json", {
            "what": "Glacier area as a share of the area in " + str(gp["base"]) + ", per cent, summed over Randolph Glacier Inventory region 11 (Central Europe). Not specific to Jungfrau-Aletsch.",
            "years": gp["years"], "emission_paths": {k: {"climate_models": v["n"], "median": v["med"], "lowest": v["lo"], "highest": v["hi"]} for k, v in gp["rcp"].items()}})

    ENDPOINTS = [
        ("/sites.json", "Sites", "The 15 ranked basin sites: location, basin volume, dam length, glacier area upstream, protection, illustrative investment."),
        ("/sites/{id}.json", "Sites", "One site by id (1 to 15, its rank in the terrain analysis report)."),
        ("/sites.geojson", "Sites", "The same sites as a GeoJSON FeatureCollection in WGS84, for GIS and web maps."),
        ("/candidates.json", "Sites", "The 28 further candidate points that did not make the shortlist, with their protection check."),
        ("/catchments.json", "Meltwater", "The 9 Hydro-CH2018 catchments the sites are matched to."),
        ("/catchments/{id}.json", "Meltwater", "One catchment with monthly runoff for RCP2.6, 4.5 and 8.5 in the reference period, 2035, 2060 and 2085 (median, minimum, maximum of the model ensemble)."),
        ("/glaciers.json", "Meltwater", "The ten largest glaciers of the study area."),
        ("/exits.json", "Meltwater", "Where meltwater leaves the study area, with the glacier area behind each exit."),
        ("/elevation-bands.json", "Meltwater", "Land and glacier area by 500 m elevation band."),
        ("/hydropower-plants.json", "Energy", f"The {len(plants)} hydropower plants of 300 kW or more in the map extent: type, status, turbine power, expected yearly production (SFOE)."),
        ("/dams.json", "Energy", f"The {len(dams)} dams under federal supervision in the map extent: type, height, crest length, reservoir volume (SFOE)."),
        ("/reservoir-storage.json", "Energy", "Energy held in Swiss reservoirs, latest week and the past year, with the capacity (SFOE)."),
    ] + ([("/grid.json", "Energy", "Swiss grid records: mean production by source, consumption and net import per calendar month, hydropower output per year against precipitation, net import per winter, filling of the storage lakes by week since 2000, and the plants matched to each catchment.")] if en else []) + ([("/glacier-path.json", "Meltwater", "Glacier area by year to 2100 as a share of today's, for RCP2.6, 4.5 and 8.5, from a published glacier model (Alps-wide).")] if gp else []) + ([("/risk-hindcast.json", "Risk", "What the risk outlook works with, for every day since March 2021: zero-degree level, precipitation, rain at each site, and the documented events the rule is tested against.")] if hc else []) + ([("/satellite.json", "Satellite", "Snow and ice left in the study area at the end of each summer since 2015 (Sentinel-2), the two scenes behind the then/now pictures, and glacier thinning measured from space for 2000 to 2019.")] if sat else [])
    write("index.json", {"name": "BasinScope Alps data API", "study_area": "Jungfrau-Aletsch, 781 km2, Bernese and Valais Alps", "base_url": BASE,
                         "endpoints": [{"path": p, "url": BASE + p, "description": t} for p, _, t in ENDPOINTS] + [{"path": "/openapi.json", "url": BASE + "/openapi.json", "description": "OpenAPI 3.0 description of this API."}],
                         "sources": SOURCES})

    # OpenAPI description
    env = lambda schema: {"type": "object", "properties": {"meta": {"$ref": "#/components/schemas/Meta"}, "data": schema}}
    arr = lambda ref: {"type": "array", "items": {"$ref": "#/components/schemas/" + ref}}
    ok = lambda schema, media="application/json": {"200": {"description": "OK", "content": {media: {"schema": schema}}}}
    num, st, integer = {"type": "number"}, {"type": "string"}, {"type": "integer"}
    loc = {"type": "object", "properties": {"easting_lv95": integer, "northing_lv95": integer, "longitude": num, "latitude": num, "elevation_m": integer}}
    prot_schema = {"type": "object", "properties": {"level": {"type": "string", "enum": ["none", "landscape", "strict"]}, "strict": {"type": "boolean"},
                   "areas": {"type": "array", "items": {"type": "object", "properties": {"kind": {"type": "string", "enum": list(PROT)}, "label": st, "level": st, "name": st}}}}}
    id_param = lambda desc: [{"name": "id", "in": "path", "required": True, "schema": integer, "description": desc}]
    schemas = {
        "Meta": {"type": "object", "properties": {"api_version": st, "generated": {"type": "string", "format": "date"}, "notice": st, "docs": st, "count": integer}},
        "Protection": prot_schema,
        "Site": {"type": "object", "properties": {
            "id": integer, "report_rank": integer, "name": st, "type": {"type": "string", "enum": list(TYPE)}, "type_label": st, "valley": st, "location": loc,
            "glacier_area_upstream_km2": num,
            "basin": {"type": "object", "properties": {"volume_10m_dam_mio_m3": num, "volume_20m_dam_mio_m3": num, "lake_area_ha": num, "dam_length_m": num}},
            "illustrative_investment_chf_m": {"type": "object", "description": "Basin volume scaled in a straight line from the KWO Trift project (CHF 387 m for 85 Mio m3). Order of magnitude only.", "properties": {"dam_10m": num, "dam_20m": num}},
            "catchment_id": integer, "protection": {"$ref": "#/components/schemas/Protection"},
            "hazard_index_percent": {"type": "object", "nullable": True, "description": "Share of the 250 m square around the site that the federal index maps mark, in per cent. An indication for the hazard assessment, not a hazard map.",
                                     "properties": {"debris_flow": num, "shallow_landslide": num, "rockfall": num, "permafrost": num}}, "confidence_note": {"type": "string", "nullable": True}, "notes": {"type": "array", "items": st}}},
        "Candidate": {"type": "object", "properties": {"id": st, "location": loc, "protection": {"$ref": "#/components/schemas/Protection"}}},
        "Catchment": {"type": "object", "properties": {"id": integer, "river": st, "gauge_place": st, "area_km2": num, "glacier_cover_percent": num, "site_ids": {"type": "array", "items": integer}}},
        "CatchmentRunoff": {"allOf": [{"$ref": "#/components/schemas/Catchment"}, {"type": "object", "properties": {"runoff_unit": st,
            "runoff": {"type": "object", "description": "Keys: RCP26 | RCP45 | RCP85, then ref | 2035 | 2060 | 2085, then med | min | max, then jan to dec.", "additionalProperties": True}}}]},
        "Glacier": {"type": "object", "properties": {"name": st, "area_km2": num, "length_km": num, "lowest_m": integer, "highest_m": integer}},
        "Exit": {"type": "object", "properties": {"path": st, "glacier_area_km2": num, "description": st, "warning": st}},
        "ElevationBand": {"type": "object", "properties": {"band_from_m": integer, "area_km2": num, "glacier_area_km2": num}},
        "Plant": {"type": "object", "properties": {"name": st, "place": st, "type": st, "status": st, "turbine_power_mw": num, "expected_production_gwh_per_year": num, "in_operation_since": integer, "location": loc}},
        "Dam": {"type": "object", "properties": {"name": st, "reservoir": st, "type": st, "height_m": num, "crest_length_m": num, "reservoir_volume_mio_m3": num, "built": integer, "purpose": st, "location": loc}},
        "ReservoirStorage": {"type": "object", "properties": {"date": {"type": "string", "format": "date"}, "energy_gwh": num, "capacity_gwh": num, "area": st,
                             "past_year": {"type": "array", "items": {"type": "object", "properties": {"date": {"type": "string", "format": "date"}, "energy_gwh": num}}}}},
    }
    R = {"/sites.json": ok(env(arr("Site"))), "/sites/{id}.json": ok(env({"$ref": "#/components/schemas/Site"})),
         "/sites.geojson": ok({"type": "object", "description": "GeoJSON FeatureCollection of Point features"}, "application/geo+json"),
         "/candidates.json": ok(env(arr("Candidate"))), "/catchments.json": ok(env(arr("Catchment"))),
         "/catchments/{id}.json": ok(env({"$ref": "#/components/schemas/CatchmentRunoff"})), "/glaciers.json": ok(env(arr("Glacier"))),
         "/exits.json": ok(env(arr("Exit"))), "/elevation-bands.json": ok(env(arr("ElevationBand"))),
         "/hydropower-plants.json": ok(env(arr("Plant"))), "/dams.json": ok(env(arr("Dam"))), "/reservoir-storage.json": ok(env({"$ref": "#/components/schemas/ReservoirStorage"})),
         "/satellite.json": ok(env({"type": "object", "description": "Keys: snow_and_ice_at_end_of_summer, scene_pair, glacier_thinning. Extents in km2, rates in metres per year.", "additionalProperties": True})),
         "/grid.json": ok(env({"type": "object", "description": "Keys: data_up_to, monthly_mean_gwh, hydropower_by_year, winter_net_import_gwh, storage_lakes_percent_full_by_week, plants_by_catchment.", "additionalProperties": True})),
         "/glacier-path.json": ok(env({"type": "object", "description": "Keys: what, years, emission_paths (RCP26 | RCP45 | RCP85, each with median, lowest, highest in per cent).", "additionalProperties": True})),
         "/risk-hindcast.json": ok(env({"type": "object", "description": "Keys: from, to, method, zero_degree_level_m and precipitation_mm (one value per day from the first day), site_rain_mm (per site id: [day index, mm]), events.", "additionalProperties": True}))}
    paths = {}
    for p, tag, text in ENDPOINTS:
        op = {"tags": [tag], "summary": text, "responses": dict(R[p])}
        if "{id}" in p:
            op["parameters"] = id_param("Site id, 1 to 15" if "sites" in p else "Hydro-CH2018 catchment id: " + ", ".join(sorted(d["catchments"])))
            op["responses"]["404"] = {"description": "No such id"}
        paths[p] = {"get": op}
    spec = {"openapi": "3.0.3", "info": {"title": "BasinScope Alps data API", "version": VERSION,
            "description": "Read-only data on glacier-meltwater retention basin sites in the Jungfrau-Aletsch area. Static JSON, no key, open to browser calls from any origin. " + NOTICE},
            "servers": [{"url": BASE}], "paths": paths, "components": {"schemas": schemas}}
    json.dump(spec, open(os.path.join(out, "openapi.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # documentation page
    row = lambda p, text: f'<tr><td><a href="v1{p.replace("{id}", "1" if "sites" in p else sorted(d["catchments"])[0])}"><code>GET /api/v1{p}</code></a></td><td>{text}</td></tr>'
    groups = "".join(f'<h3>{tag}</h3><div class="scroll"><table><tbody>' + "".join(row(p, t) for p, g, t in ENDPOINTS if g == tag) + "</tbody></table></div>" for tag in ("Sites", "Meltwater", "Energy") + (("Satellite",) if sat else ()) + (("Risk",) if hc else ()))
    example = json.dumps({"meta": {"api_version": VERSION, "generated": generated}, "data": {k: sites[1][k] for k in ("id", "name", "type", "location", "glacier_area_upstream_km2", "basin", "illustrative_investment_chf_m", "catchment_id")}}, ensure_ascii=False, indent=1)
    fields = [("location", "LV95 coordinates as in the terrain analysis, plus WGS84 longitude and latitude converted with swisstopo's approximate formulas (about 1 m)."),
              ("glacier_area_upstream_km2", "Glacier area draining to the site (SGI 2016)."),
              ("basin.volume_10m_dam_mio_m3, volume_20m_dam_mio_m3", "Basin volume behind a 10 m and a 20 m dam, in million cubic metres."),
              ("basin.lake_area_ha, dam_length_m", "Lake surface and dam length from the terrain analysis."),
              ("illustrative_investment_chf_m", "Volume scaled in a straight line from the KWO Trift project (CHF 387 m for 85 Mio m³). Order of magnitude only."),
              ("protection.level", "<code>strict</code>: floodplain, mire landscape, fen, raised bog or hydropower waiver. <code>landscape</code>: UNESCO, BLN or game reserve only. <code>none</code>: no hit. The grouping is the team's own."),
              ("hazard_index_percent", "Share of the 250 m square around the site that the federal index maps mark for debris flow, shallow landslide, rockfall and permafrost. An indication for the hazard assessment, not a hazard map, and not part of any score."),
              ("catchment_id", "Hydro-CH2018 catchment the site is matched to. The matching is the team's assumption."),
              ("runoff", "Monthly runoff in mm per month: emissions path, then period, then <code>med</code>, <code>min</code>, <code>max</code> of the model ensemble, then month.")]
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BasinScope Alps data API</title>
<meta name="description" content="Read-only JSON API with the BasinScope Alps basin sites, runoff scenarios and protection checks.">
<style>
:root{{--bg:#f6f7f5;--panel:#fff;--ink:#15201c;--ink-2:#4c5a55;--line:#dde2de;--accent:#0b6b62;--code:#eef2f0}}
@media (prefers-color-scheme:dark){{:root{{--bg:#111715;--panel:#19211e;--ink:#e8eeeb;--ink-2:#a3b0ab;--line:#2c3733;--accent:#5fc7ba;--code:#212b28}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}}
main{{max-width:920px;margin:0 auto;padding:28px 16px 56px}}
h1{{font-size:1.9rem;line-height:1.2;margin:0 0 6px}} h2{{font-size:1.2rem;margin:36px 0 10px}} h3{{font-size:.8rem;text-transform:uppercase;letter-spacing:.06em;color:var(--ink-2);margin:20px 0 6px}}
p{{margin:0 0 12px}} .lead{{color:var(--ink-2);max-width:65ch}} a{{color:var(--accent)}}
.logo{{display:flex;align-items:center;gap:10px;margin-bottom:22px;font-weight:600}} .logo img{{height:40px;width:auto}}
.base{{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px 14px;overflow-x:auto;white-space:nowrap}}
.scroll{{overflow-x:auto;background:var(--panel);border:1px solid var(--line);border-radius:8px}}
table{{border-collapse:collapse;width:100%;font-size:.93rem}} td{{padding:9px 12px;border-top:1px solid var(--line);vertical-align:top}} tr:first-child td{{border-top:0}} td:first-child{{white-space:nowrap}}
code,pre{{font:.86rem/1.5 ui-monospace,Consolas,monospace}} code{{background:var(--code);padding:1px 5px;border-radius:4px}} td a code{{color:var(--accent)}}
pre{{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px 14px;overflow-x:auto;margin:0 0 12px}} pre code{{background:none;padding:0}}
.note{{border-left:3px solid var(--accent);background:var(--panel);padding:10px 14px;border-radius:0 8px 8px 0;color:var(--ink-2)}}
footer{{margin-top:40px;color:var(--ink-2);font-size:.88rem}}
</style>
</head>
<body>
<main>
<div class="logo"><img src="../assets/logo.webp?v={logo_v}" alt=""><a href="../">BasinScope Alps</a></div>
<h1>Data API</h1>
<p class="lead">The figures behind the dashboard as plain JSON: the ranked basin sites of the Jungfrau–Aletsch area with their protection and hazard-index checks, the runoff scenarios of their catchments, the hydropower plants and dams around them, Swiss grid records, what satellites measured of the area's snow and ice, and the past forecasts the risk outlook is tested against. Read-only, no key, callable from a browser on any origin.</p>
<div class="base"><code>{BASE}</code></div>

<h2>Endpoints</h2>
{groups}
<p style="margin-top:12px">Machine-readable description: <a href="v1/openapi.json"><code>openapi.json</code></a> (OpenAPI 3.0). List of all endpoints: <a href="v1/index.json"><code>index.json</code></a>.</p>

<h2>Quick start</h2>
<h3>curl</h3>
<pre><code>curl {BASE}/sites.json</code></pre>
<h3>JavaScript</h3>
<pre><code>const res = await fetch("{BASE}/sites.json");
const {{ data }} = await res.json();
const free = data.filter(s =&gt; s.type === "new" &amp;&amp; !s.protection.strict);</code></pre>
<h3>Python</h3>
<pre><code>import requests
sites = requests.get("{BASE}/sites.json").json()["data"]
big = [s for s in sites if s["basin"]["volume_20m_dam_mio_m3"] &gt;= 5]</code></pre>

<h2>Response shape</h2>
<p>Every JSON endpoint returns a <code>meta</code> block (version, generation date, notice) and the payload in <code>data</code>. <code>sites.geojson</code> is a plain GeoJSON FeatureCollection.</p>
<pre><code>{example.replace("&", "&amp;").replace("<", "&lt;")}</code></pre>

<h2>Fields</h2>
<div class="scroll"><table><tbody>{"".join(f"<tr><td><code>{k}</code></td><td>{v}</td></tr>" for k, v in fields)}</tbody></table></div>

<h2>What the API does not do</h2>
<p>The files are static, so there is no filtering, paging or writing on the server: fetch a file and filter it in your own code. Scores, the A/B/C classes, usable volume and the energy and payback of the business case depend on the scenario settings chosen in the dashboard and are computed there, not served here. An unknown id returns HTTP 404.</p>
<p class="note">{NOTICE}</p>

<h2>Sources</h2>
<div class="scroll"><table><tbody>{"".join(f"<tr><td>{s['what']}</td><td>{s['source']}{', as of ' + s['as_of'] if s.get('as_of') else ''}</td></tr>" for s in SOURCES)}</tbody></table></div>
<footer>API version {VERSION}, generated {generated}. Team Swisstainability, Swiss Hackathon 2026, Track 06. Please credit the sources above when you reuse the data.</footer>
</main>
</body>
</html>
"""
    open(os.path.join(api, "index.html"), "w", encoding="utf-8").write(html)
    print("api files:", sum(len(f) for _, _, f in os.walk(api)))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
