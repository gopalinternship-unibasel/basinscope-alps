# BasinScope Alps: self-hosted dashboard

A digital twin of the Jungfrau–Aletsch glacier region: where glacier meltwater could be stored,
what the region is doing today, and how the answer shifts under climate scenarios.
Team Swisstainability, Swiss Hackathon 2026, Track 06 (Digital Twin Earth, Switzerland).

Live: https://gopalinternship-unibasel.github.io/basinscope-alps/

This folder is a complete static site. It needs no build step and no backend.

## Run it on your own machine

```bash
python -m http.server 8080 --bind 127.0.0.1 --directory .
```

Then open http://localhost:8080. Any static web server works the same way.

## Put it on a public address

Upload the folder as it is to any static host (GitHub Pages, Netlify, Vercel,
Cloudflare Pages, or your own web server). `index.html` must sit next to the
`assets` and `data` folders. The empty `.nojekyll` file is for GitHub Pages.

## How the page is organised

The dashboard is split into sheets, like the sheets of a workbook. The tab strip under the title bar
switches between them, and each sheet has its own address:

| Sheet | Address | What it holds |
|---|---|---|
| Overview | `#overview` | Headline numbers, the top of the shortlist, a guide to the other sheets |
| Sites | `#sites` | Weights, map, ranked shortlist, the evidence card of the selected site |
| Live now | `#live` | River discharge and mountain weather from the federal services |
| Risk outlook | `#risk` | Five-day forecast of thaw and heavy precipitation, set against the hazard process areas mapped at each site |
| Meltwater | `#water` | Seasonal runoff shift, where meltwater leaves, ice by elevation, the ten largest glaciers |
| Satellite | `#satellite` | Sentinel-2 pictures of 2016 and 2026 to compare, for the whole area and around each site; snow and ice left at the end of each summer since 2015; glacier thinning measured from space; the latest satellite passes |
| Business case | `#business` | Illustrative cost, energy and payback for a site, storage against glacier size, hydropower plants and dams near the site, energy held in Swiss reservoirs |
| Method & sources | `#method` | Checks on the ranking, evidence layers, roll-out architecture, the Track 06 brief point by point, scope, limits and sources |

The scenario settings (runoff period, emissions, dam height, protection, melt rate, glacier size)
and the selected site carry over from sheet to sheet.

## What is live

The page asks three federal services and one forecast service directly from the visitor's browser,
on load, every 5 minutes while the tab is visible (the forecast hourly), and when "Refresh now" is pressed:

| What | Source | Updated by the source |
|---|---|---|
| River discharge and water temperature at 7 gauges | Federal Office for the Environment, via the federal SPARQL endpoint `ld.admin.ch/query` (fallback `lindas.admin.ch/query`) | about every 10 minutes |
| Air temperature and precipitation at 6 mountain stations | MeteoSwiss automatic stations, via `data.geo.admin.ch` | every 10 minutes |
| Protected-area inventories within 250 m of each ranked site | `api3.geo.admin.ch` identify service | when inventories change; the page asks at most once a day, or on "Re-check federal inventories" |
| Zero-degree level and precipitation for the next five days at the 15 site locations | MeteoSwiss ICON-CH2 forecast, served by `api.open-meteo.com` (CC BY 4.0, free for non-commercial use) | several times a day |
| The six latest Sentinel-2 passes over the study area: time, cloud share, true-colour picture | swissEO S2-SR, swisstopo: the catalogue and the cloud-optimised files on `data.geo.admin.ch` | a new mosaic 10 to 24 hours after each overpass, every two to three days; the page asks when the Satellite sheet is opened, at most every 30 minutes, or on "Check again" |

The satellite files are read in the browser with [geotiff.js](https://geotiffjs.github.io/), which the page loads from `cdn.jsdelivr.net`
the first time the Satellite sheet is opened. Only a small window of each file is fetched.

From the station temperatures the page fits a straight line against altitude and reports
where it crosses 0 °C, and how much of the glacier area lies below that level.
That figure is an estimate from six stations, not a measurement.

The Risk outlook marks a day "Watch" when the zero-degree level passes a threshold (default 4,000 m) or the day's
precipitation does (default 30 mm), and "Elevated" when both happen. A site is marked when such a trigger meets a
hazard process mapped within 250 m of it. Both thresholds can be moved on the page. They are a first setting and
are not calibrated against past events: this is a prototype of trigger conditions, not a warning service.

## What is not live

`data/dataset.json` holds the terrain analysis of 2 October 2026 (15 ranked sites,
28 other candidates), the Hydro-CH2018 runoff scenarios for nine catchments, and the
context figures. The page re-reads this file at every check, so editing it and
uploading the new version updates every open page within 5 minutes, and at once on reload.
Records that fail validation are ignored and the built-in copy is used instead.

The same file carries federal layers that were read once, when the site was built (`federal` in the dataset):

| What | Source | How it is read |
|---|---|---|
| Hazard process areas within 250 m of each site: debris flow, shallow landslide, rockfall, permafrost | SilvaProtect-CH and the map of potential permafrost distribution, FOEN (index maps of 2005 and 2006, valid to 1:50,000) | share of a 500 m square that the federal map service draws as marked; the same maps are laid over the dashboard map |
| Hydropower plants of 300 kW or more, dams under federal supervision | SFOE | `api3.geo.admin.ch` identify service, whole map extent |
| Energy held in Swiss reservoirs, weekly | SFOE, filling level of the storage lakes | CSV file; it does not allow browser calls from other sites |
| Satellite base map | swissEO S2-SR, swisstopo (Copernicus Sentinel-2) | clearest mosaic of the chosen period, from the federal data catalogue |

The satellite evidence of the Satellite sheet is also made when the site is built (`satellite` in the dataset, pictures in `assets/sat/`):

| What | Source | How it is made |
|---|---|---|
| Snow and ice left at the end of each summer, 2015 to 2026 | swissEO S2-SR, swisstopo (Copernicus Sentinel-2) | All 244 mosaics between 10 August and 5 October are screened for cloud inside the study area; on the 46 clear enough, snow and ice are counted where the snow index (NDSI) is 0.4 or more on a 40 m grid. Each year shows the clear scene with the least snow that a second scene confirms within 5% |
| Then and now pictures, whole area (30 m) and 4 km around each ranked site (10 m) | the scenes of 29 September 2016 and 27 September 2026 | true-colour pictures cut from the cloud-optimised files |
| Glacier thinning 2000 to 2019, for the area and its largest glaciers | Hugonnet et al. 2021 (ASTER satellite stereo pictures), on Randolph Glacier Inventory 6.0 outlines | the 367 glaciers whose centre lies in the study area, area-weighted; 318 of them have a measurement |

Avalanches are left out: the federal index map only models avalanches that start in forest.
The hazard shares are an indication for a hazard assessment. They are not part of the score.

## Data API

The figures behind the dashboard are also served as read-only JSON under `api/v1/`, with a documentation
page at `api/` and an OpenAPI 3.0 description at `api/v1/openapi.json`. No key, no server: the files are static.

| Endpoint | What it returns |
|---|---|
| `api/v1/sites.json`, `api/v1/sites/{id}.json` | The 15 ranked sites: location (LV95 and WGS84), basin volume, dam length, protection, illustrative investment |
| `api/v1/sites.geojson` | The same sites as GeoJSON for GIS and web maps |
| `api/v1/candidates.json` | The 28 further candidate points with their protection check |
| `api/v1/catchments.json`, `api/v1/catchments/{id}.json` | Hydro-CH2018 catchments and their monthly runoff scenarios |
| `api/v1/glaciers.json`, `api/v1/exits.json`, `api/v1/elevation-bands.json` | Glaciers, meltwater exits, area by elevation |
| `api/v1/hydropower-plants.json`, `api/v1/dams.json`, `api/v1/reservoir-storage.json` | Hydropower plants and dams in the map extent, energy held in Swiss reservoirs |
| `api/v1/satellite.json` | Snow and ice left at the end of each summer since 2015, the two scenes behind the then and now pictures, glacier thinning measured from space |

Each site also carries `hazard_index_percent`, the mapped share of its 250 m square for each hazard process.

The files are generated from `data/dataset.json` by `build_api.py` in the build folder. Scores, classes and the
energy side of the business case depend on the scenario settings and are computed in the dashboard, not served by the API.

## How it is built

The page, the dataset and the API are generated by the scripts in `pipeline/`:

```bash
python pipeline/fetch_federal.py pipeline      # hazard maps, plants, dams, reservoir storage
python pipeline/fetch_satellite.py pipeline    # Sentinel-2 base map (needs rasterio)
python pipeline/fetch_satellite_series.py pipeline   # Satellite sheet: yearly snow and ice, then and now pictures, glacier thinning (needs rasterio)
python pipeline/build.py pipeline .            # index.html, data/dataset.json, api/
```

`pipeline/template.html` is the dashboard's source. `pipeline/build/` holds the inputs: the 15 sites and context
figures of the terrain analysis (`base.json`), the map georeference (`geo.json`), the Hydro-CH2018 runoff scenarios
(`hydro.json`), the raw answers of the protected-area check (`checks_raw.json`) and the outputs of the fetch scripts
(`federal.json`, `base_s2.json`, `satellite.json`). The pictures the fetch scripts write are kept in `assets/` only. The terrain analysis itself
(GRASS `r.watershed` and `r.lake` on swissALTI3D) was run separately and is described on the Method & sources sheet.

## Limits

- The gauges lie below reservoirs and diversions. They show what each river carries now,
  not the inflow at a basin site.
- The Lonza gauge at Blatten has reported nothing since 28 May 2025.
- If a federal service is unreachable, the page keeps the last readings it saw in that browser, shows their measurement times, and says so.
- Expert reviews recorded on this page are kept in the visitor's browser only.
  The version published on claude.ai keeps them in a shared database instead.
- Map backgrounds and layers are static images, not live map tiles.
- The risk thresholds are not calibrated, and glacier collapse and avalanches are not covered.
- The energy side stops at the plants, the dams and the national reservoir storage: the grid is not modelled.
- The yearly snow and ice figure is what stays white at the end of summer, not a glacier area: it misses debris-covered ice
  and ice in deep shadow, includes snow fields outside the glaciers, and 2017 has no clear scene. Four of the eleven yearly values rest on a single scene.
- Glacier thinning is net ice loss on the glacier outlines of 2003. It is not the total meltwater, and it ends in 2019.

## Sources and attribution

Terrain: swissALTI3D, © swisstopo. Glaciers: Swiss Glacier Inventory SGI 2016, GLAMOS.
Runoff scenarios: Hydro-CH2018, Federal Office for the Environment.
Live hydrology: Federal Office for the Environment. Live weather: MeteoSwiss.
Forecast: MeteoSwiss ICON-CH2 through Open-Meteo (CC BY 4.0).
Protected areas: federal inventories (FOEN, SFOE) through geo.admin.ch.
Hazard index maps: SilvaProtect-CH and potential permafrost distribution, FOEN.
Hydropower plants, dams and reservoir storage: Swiss Federal Office of Energy.
Satellite pictures and scenes: swissEO S2-SR, © swisstopo, contains modified Copernicus Sentinel data 2015–2026.
Glacier thinning: Hugonnet et al. 2021, Nature 592, doi:10.1038/s41586-021-03436-z, on Randolph Glacier Inventory 6.0 outlines.
