---
name: naqsha-geohazard
description: Assess slope/road hazard photos from northern Pakistan, query OpenStreetMap in plain Urdu or English, and check whether a road route is safe, using a running Naqsha AI server.
---

# Naqsha geohazard skill

Requires a Naqsha AI server (default `http://localhost:8000`). Use `tools.py`:

- `assess_photo(path, lat, lon, note="")` — engineering-geology hazard assessment + risk score 0-100.
- `ask_map(question)` — natural-language OpenStreetMap query; returns GeoJSON and a summary.
- `route_check(origin, destination)` — safe / caution / avoid verdict, hazards by km, alternate route.
- `exposure(hazard_id, radius_m=1000)` — schools, health facilities, mosques, bridges near a hazard.

Report the verdict and the reasons; always include Rescue 1122 for life-threatening situations.
