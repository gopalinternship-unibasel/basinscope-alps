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
| Risk outlook | `#risk` | Five-day forecast of thaw and heavy precipitation, set against the hazard process areas mapped at each site and at 21 hydropower plants and 9 dams; the same rule run over every day since March 2021 and four documented events, with a table of what other thresholds would have said |
| Meltwater | `#water` | Seasonal runoff shift, where meltwater leaves, ice by elevation, the ten largest glaciers |
| Satellite | `#satellite` | Sentinel-2 pictures of 2016 and 2026 to compare, for the whole area and around each site; snow and ice left at the end of each summer since 2015; glacier thinning measured from space; the latest satellite passes |
| Energy | `#energy` | Stress test of the hydropower plants on the rivers of the nine catchments under the runoff scenario; that stress test carried into the Swiss half-year balance (winter import, summer export, with the new basins added); the Swiss grid through the year; hydropower output against precipitation; filling of the storage lakes since 2000; net import per winter |
| Business case | `#business` | Illustrative cost, energy and payback for a site, storage against glacier size, hydropower plants and dams near the site, energy held in Swiss reservoirs |
| Method & sources | `#method` | Checks on the ranking, evidence layers, the sites set against the 2024 Federal Council report on hydropower from glacier melt, roll-out architecture, the Track 06 brief point by point, scope, limits and sources |

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

The satellite files are read in the browser with [geotiff.js](https://geotiffjs.github.io/), which the site serves itself
(`assets/vendor/geotiff.js`) and loads the first time the Satellite sheet is opened. Only a small window of each file is fetched.
The fonts are served by the site as well (`assets/fonts/`), so a visitor's browser calls no third party except the forecast service.

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
| Hazard process areas within 250 m of each site: debris flow, shallow landslide, rockfall, permafrost | SilvaProtect-CH and the map of potential permafrost distribution, FOEN (index maps of 2005 and 2006, valid to 1:50,000) | share of the 500 m square centred on the site: measured on the SilvaProtect-CH polygons of the federal data catalogue (`data.geo.admin.ch`) for debris flow, shallow landslide and rockfall, and on a picture of the federal map service for permafrost; the map service's pictures are laid over the dashboard map |
| Hydropower plants of 300 kW or more, dams under federal supervision | SFOE | `api3.geo.admin.ch` identify service, whole map extent |
| Energy held in Swiss reservoirs, weekly | SFOE, filling level of the storage lakes | CSV file; it does not allow browser calls from other sites |
| Satellite base map | swissEO S2-SR, swisstopo (Copernicus Sentinel-2) | clearest mosaic of the chosen period, from the federal data catalogue |

The satellite evidence of the Satellite sheet is also made when the site is built (`satellite` in the dataset, pictures in `assets/sat/`):

| What | Source | How it is made |
|---|---|---|
| Snow and ice left at the end of each summer, 2015 to 2026 | swissEO S2-SR, swisstopo (Copernicus Sentinel-2) | All 244 mosaics between 10 August and 5 October are screened for cloud inside the study area; on the 46 clear enough, snow and ice are counted where the snow index (NDSI) is 0.4 or more on a 40 m grid. Each year shows the clear scene with the least snow that a second scene confirms within 5% |
| Then and now pictures, whole area (30 m) and 4 km around each ranked site (10 m) | the scenes of 29 September 2016 and 27 September 2026 | true-colour pictures cut from the cloud-optimised files |
| Glacier thinning 2000 to 2019, for the area and its largest glaciers | Hugonnet et al. 2021 (ASTER satellite stereo pictures), on Randolph Glacier Inventory 6.0 outlines | the 367 glaciers whose centre lies in the study area, area-weighted; 318 of them have a measurement |

Three more inputs are read when the site is built:

| What | Source | How it is used |
|---|---|---|
| Swiss grid records (`energy` in the dataset): electricity production by source (daily, since 2015), national consumption (daily), cross-border exchange (hourly, since 2017), filling of the storage lakes (weekly, since 2000) | Swiss Federal Office of Energy, energy dashboard files (Swissgrid figures); the files only allow the origin `map.geo.admin.ch` and are not updated daily, so this is a record, not a live feed | Energy sheet: mean month by month, hydropower output per year against the precipitation at Grimsel Hospiz (MeteoSwiss open data), net import per winter, reservoir filling by week |
| Past forecasts (`hindcast`): zero-degree level and precipitation at the 15 site locations for every day since 23 March 2021 | Forecast archive of Open-Meteo (CC BY 4.0); it serves the best model it has for each date | Risk outlook: the page applies its two thresholds to every past day, counts the days marked per year and sets four documented events against them |
| Glacier area by year to 2100 (`glacierPath`), as a share of today's, for RCP2.6, 4.5 and 8.5 | OGGM standard projections v1.6.1, CMIP5 runs, Randolph Glacier Inventory region 11 (Central Europe), median and range over 10 to 11 climate models | The Glacier size control shows the year a size stands for and offers the size that matches the chosen runoff period |

The stress test on the Energy sheet matches 21 hydropower plants to the nine catchments by name and location on the map
(`CHAIN` in `pipeline/fetch_energy.py`). That match is ours and has not been checked with the operators. A run-of-river plant follows
the monthly runoff up to its turbine capacity; a storage plant is shown by the energy of the water that reaches it. Every plant is
scaled so that the reference runoff of 1981–2010 gives its expected production in the SFOE statistics.

Avalanches are left out: the federal index map only models avalanches that start in forest.
The hazard shares are an indication for a hazard assessment. They are not part of the score.
A process counts at a site from 20% of the square; permafrost, which the federal map marks in patches, from 5%.

Correction of 4 October 2026: until then the page and the API showed about a fifth of the true share for debris flow,
shallow landslide and rockfall. The federal map service draws these areas as hatching, and the build counted the hatch
lines of the picture. The shares are now measured on the polygons. The bar for the three processes moved from 5% to 20%
with them, which marks the same sites, plants and dams as before; permafrost was not affected.

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
| `api/v1/grid.json` | Swiss grid records behind the Energy sheet, and the plants matched to each catchment |
| `api/v1/glacier-path.json` | Glacier area by year to 2100 as a share of today's, per emissions path (Alps-wide glacier model) |
| `api/v1/risk-hindcast.json` | Zero-degree level, precipitation and rain per site for every day since March 2021, and the events the risk rule is tested against |
| `api/v1/infrastructure-hazards.json` | Hazard process areas mapped around the 21 plants of the stress test and the 9 dams near the ranked sites, with their ground height |
| `api/v1/federal-report.json` | The projects of the 2024 Federal Council report that lie in the study area, with the report's figures and the ranked site each one matches |
| `api/v1/satellite.json` | Snow and ice left at the end of each summer since 2015, the two scenes behind the then and now pictures, glacier thinning measured from space |

Each site also carries `hazard_index_percent`, the mapped share of the 500 m square centred on it for each hazard process.

The files are generated from `data/dataset.json` by `build_api.py` in the build folder. Scores, classes and the
energy side of the business case depend on the scenario settings and are computed in the dashboard, not served by the API.

## How it is built

The page, the dataset and the API are generated by the scripts in `pipeline/`:

```bash
python pipeline/fetch_federal.py pipeline      # hazard shares and maps, plants, dams, reservoir storage (needs pyogrio and shapely)
python pipeline/fetch_satellite.py pipeline    # Sentinel-2 base map (needs rasterio)
python pipeline/fetch_satellite_series.py pipeline   # Satellite sheet: yearly snow and ice, then and now pictures, glacier thinning (needs rasterio)
python pipeline/fetch_energy.py pipeline       # Energy sheet: Swiss grid records, station climate, plants per catchment
python pipeline/fetch_hindcast.py pipeline     # Risk outlook: past forecasts since 2021 and the documented events
python pipeline/fetch_infra_hazard.py pipeline # Risk outlook: hazard shares and ground height at the plants and dams (after fetch_federal and fetch_energy)
python pipeline/hazard_share.py pipeline       # only the hazard shares again, in federal.json and infra_hazard.json
python pipeline/fetch_glacier_path.py pipeline # Glacier size control: glacier area by year from a published glacier model
python pipeline/fetch_vendor.py pipeline       # the site's own copies of the fonts and of geotiff.js
python pipeline/build.py pipeline .            # index.html, data/dataset.json, api/
```

`pipeline/template.html` is the dashboard's source. `pipeline/build/` holds the inputs: the 15 sites and context
figures of the terrain analysis (`base.json`), the map georeference (`geo.json`), the Hydro-CH2018 runoff scenarios
(`hydro.json`), the raw answers of the protected-area check (`checks_raw.json`) and the outputs of the fetch scripts
(`federal.json`, `base_s2.json`, `satellite.json`, `energy.json`, `hindcast.json`, `glacier_path.json`, `infra_hazard.json`). `federal_report.json` is entered by hand from the appendix of the 2024 Federal Council report. The pictures the fetch scripts write are kept in `assets/` only. The hazard polygons are downloaded into `pipeline/build/haz_cache/`, which is not kept in the repo. The terrain analysis itself
(GRASS `r.watershed` and `r.lake` on swissALTI3D) was run separately and is described on the Method & sources sheet.

## When it was made

This repository's history starts on 3 October 2026, during the Swiss Hackathon 2026 (2 to 4 October, Lucerne). The terrain analysis it builds on is the team's own report of 2 October 2026. Everything else comes from the public sources listed at the end; the commit history shows what was added when.

## Limits

- The gauges lie below reservoirs and diversions. They show what each river carries now,
  not the inflow at a basin site.
- The Lonza gauge at Blatten has reported nothing since 28 May 2025.
- If a federal service is unreachable, the page keeps the last readings it saw in that browser, shows their measurement times, and says so.
- Expert reviews recorded on this page are kept in the visitor's browser only.
  The version published on claude.ai keeps them in a shared database instead.
- Map backgrounds and layers are static images, not live map tiles.
- The risk thresholds are tested against past forecasts and four documented events, not calibrated: at the default setting the rule marks about 80 days a year as Watch and about two as Elevated. The sheet shows what eleven other settings would have marked; choosing between them needs a hazard specialist and more events. Glacier collapse and avalanches are not covered.
- The check of plants and dams reads the index maps at the powerhouse or the dam only. Intakes, pressure lines, access roads and protective works are not covered.
- The sites are matched to the projects of the federal report by the lake or glacier named. The report gives no coordinates, and its projects are operator designs with higher dams than the 10 or 20 m basins screened here.
- The energy side is a first-order stress test of 21 plants and a set of grid records. Power lines, the market and pumping are not modelled, and the grid figures are not a live feed. The half-year balance gives a range, because storage operators decide when their water is turbined; it changes only the output of these 21 plants, 7% of Swiss hydropower.
- The years of the Glacier size control come from an Alps-wide model run. One shrink rate is applied to all glaciers of the area; Jungfrau–Aletsch holds the largest glaciers of the Alps, which respond more slowly, so the years are early.
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
Federal benchmark: Analyse des Wasserkraftpotenzials der Gletscherschmelze, report of the Federal Council of 6 December 2024 (postulate 21.3974), appendix.
Ground height of plants and dams: swisstopo height service.
Grid records: Swiss Federal Office of Energy, energy dashboard (Swissgrid figures). Station climate: MeteoSwiss open data.
Glacier area by year: OGGM standard projections v1.6.1 (Maussion et al. 2019). Past forecasts: Open-Meteo (CC BY 4.0).
Fonts: Barlow Semi Condensed, IBM Plex Mono, Source Sans 3 (SIL Open Font License). geotiff.js (MIT licence).
