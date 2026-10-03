# BasinScope Alps: self-hosted dashboard

Screening of glacier-meltwater retention basin sites in the Jungfrau–Aletsch area.
Team SwissStainability, Swiss Hackathon 2026, Track 06.

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

## What is live

The page asks three federal services directly from the visitor's browser,
on load, every 5 minutes while the tab is visible, and when "Refresh now" is pressed:

| What | Source | Updated by the source |
|---|---|---|
| River discharge and water temperature at 7 gauges | Federal Office for the Environment, via the federal SPARQL endpoint `ld.admin.ch/query` (fallback `lindas.admin.ch/query`) | about every 10 minutes |
| Air temperature and precipitation at 6 mountain stations | MeteoSwiss automatic stations, via `data.geo.admin.ch` | every 10 minutes |
| Protected-area inventories within 250 m of each ranked site | `api3.geo.admin.ch` identify service | when inventories change; the page asks at most once a day, or on "Re-check federal inventories" |

From the station temperatures the page fits a straight line against altitude and reports
where it crosses 0 °C, and how much of the glacier area lies below that level.
That figure is an estimate from six stations, not a measurement.

## What is not live

`data/dataset.json` holds the terrain analysis of 2 October 2026 (15 ranked sites,
28 other candidates), the Hydro-CH2018 runoff scenarios for nine catchments, and the
context figures. The page re-reads this file at every check, so editing it and
uploading the new version updates every open page within 5 minutes, and at once on reload.
Records that fail validation are ignored and the built-in copy is used instead.

## Limits

- The gauges lie below reservoirs and diversions. They show what each river carries now,
  not the inflow at a basin site.
- The Lonza gauge at Blatten has reported nothing since 28 May 2025.
- If a federal service is unreachable, the page keeps the last readings it saw in that browser, shows their measurement times, and says so.
- Expert reviews recorded on this page are kept in the visitor's browser only.
  The version published on claude.ai keeps them in a shared database instead.
- Map backgrounds are static images, not live map tiles.

## Sources and attribution

Terrain: swissALTI3D, © swisstopo. Glaciers: Swiss Glacier Inventory SGI 2016, GLAMOS.
Runoff scenarios: Hydro-CH2018, Federal Office for the Environment.
Live hydrology: Federal Office for the Environment. Live weather: MeteoSwiss.
Protected areas: federal inventories (FOEN, SFOE) through geo.admin.ch.
