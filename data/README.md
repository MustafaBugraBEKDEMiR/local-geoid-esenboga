# Data

`raw/` holds small clips of open datasets. Retrieved 2026-11-01.

| File | Content | Licence |
|---|---|---|
| `aybu_esenboga_campus_osm.geojson` | Campus boundary, OSM relation 17692965 | © OpenStreetMap contributors, ODbL 1.0 |
| `osm_campus_features.json` | Buildings, roads, pitches, parking, grass and POIs inside the campus (OSM) | ODbL 1.0 |
| `tg20_ankara_window.csv` | TG-20 hybrid geoid nodes, 39.6–40.7 N, 32.4–33.5 E (5′) | CC BY 4.0, Yıldız et al. (2020), doi:10.5880/isg.2020.011; validation: Yıldız et al. (2021), Boll. Geofis. Teor. Appl. 62(3), doi:10.4430/bgta0345 |
| `egm2008_2p5min_ankara.tif` | EGM2008 geoid, 2.5′, clipped from PROJ-data `us_nga_egm08_25.tif` | NGA; redistributed by the PROJ project (PROJ-data) |
| `srtm30m_campus_grid.csv` | SRTM 1″ heights, 51 × 78 grid (~30 m) over the campus (OpenTopoData, bilinear) | NASA/USGS, public domain |

`processed/` is produced by `scripts/run_experiments.py`.

The OSM-derived files are a Derivative Database under ODbL. If you
redistribute them, keep the attribution and share them under the same licence.
