"""GIS helpers: geocoding, OpenStreetMap queries, routing, rain, slope, exposure, geometry."""
import asyncio
import math
import re
import time

import httpx

from . import config

HEADERS = {"User-Agent": config.USER_AGENT}
_geocode_cache: dict[str, dict | None] = {}
_geocode_lock = asyncio.Lock()


# ---------- geometry (pure python, no GIS install needed) ----------

def haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _seg_dist_m(plat, plon, a, b):
    """Distance from point to segment a-b (a, b are [lon, lat]); returns (meters, t along segment)."""
    kx = 111320 * math.cos(math.radians(plat))
    ky = 110540
    ax, ay = (a[0] - plon) * kx, (a[1] - plat) * ky
    bx, by = (b[0] - plon) * kx, (b[1] - plat) * ky
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / L))
    return math.hypot(ax + t * dx, ay + t * dy), t


def distance_to_line(lat, lon, coords) -> tuple[float, float]:
    """Min distance (m) from a point to a polyline of [lon, lat] coords, plus km along the line."""
    best, best_km, run = float("inf"), 0.0, 0.0
    for a, b in zip(coords, coords[1:]):
        seg_len = haversine_m(a[1], a[0], b[1], b[0])
        d, t = _seg_dist_m(lat, lon, a, b)
        if d < best:
            best, best_km = d, (run + t * seg_len) / 1000
        run += seg_len
    return best, best_km


def sample_line(coords, n):
    if len(coords) <= n:
        return coords
    step = (len(coords) - 1) / (n - 1)
    return [coords[round(i * step)] for i in range(n)]


# ---------- geocoding ----------

_URDU = re.compile(r"[؀-ۿ]")
_COORDS = re.compile(r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*$")


async def geocode(place: str) -> dict | None:
    m = _COORDS.match(place)
    if m:  # "33.6844, 73.0479" (from "my location" or a map click)
        lat, lon = float(m.group(1)), float(m.group(2))
        return {"name": place.strip(), "lat": lat, "lon": lon, "display_name": place.strip(), "bbox": None}
    key = place.strip().lower()
    if key in _geocode_cache:
        return _geocode_cache[key]
    async with _geocode_lock:  # Nominatim policy: max 1 request/second
        async with httpx.AsyncClient(timeout=30, headers=HEADERS) as cl:
            r = await cl.get(config.NOMINATIM_URL, params={"q": place, "format": "json", "limit": 1,
                                                           "countrycodes": "pk"})
        await asyncio.sleep(1.0)
    res = r.json() if r.status_code == 200 else []
    out = None
    if res:
        h = res[0]
        bb = [float(x) for x in h.get("boundingbox", [])]  # south, north, west, east
        out = {"name": place, "lat": float(h["lat"]), "lon": float(h["lon"]),
               "display_name": h.get("display_name", place),
               "bbox": [bb[0], bb[2], bb[1], bb[3]] if len(bb) == 4 else None}  # S, W, N, E
    _geocode_cache[key] = out
    return out


async def search(q: str, lat: float | None = None, lon: float | None = None, limit: int = 7) -> list[dict]:
    """Search-as-you-type for the map search box (Photon, biased to Pakistan)."""
    params = {"q": q, "limit": limit, "bbox": "60.8,23.6,77.9,37.1", "lang": "en"}
    if lat is not None and lon is not None:
        params.update({"lat": lat, "lon": lon})
    async with httpx.AsyncClient(timeout=15, headers=HEADERS) as cl:
        r = await cl.get("https://photon.komoot.io/api/", params=params)
    out = []
    for f in r.json().get("features", []) if r.status_code == 200 else []:
        p = f["properties"]
        if p.get("countrycode") not in (None, "PK"):  # the box around Pakistan also covers its neighbours
            continue
        lo, la = f["geometry"]["coordinates"]
        sub = ", ".join(dict.fromkeys(x for x in (p.get("street"), p.get("district"), p.get("city"),
                                                  p.get("county"), p.get("state")) if x and x != p.get("name")))
        out.append({"name": p.get("name") or sub or q, "address": sub, "lat": la, "lon": lo,
                    "type": (p.get("osm_value") or "").replace("_", " "), "extent": p.get("extent")})
    if len(out) < 3 or not any(o["name"].lower() == q.lower() for o in out):
        # Photon misses some towns (e.g. Naran): ask Nominatim too, exact name matches go first
        async with _geocode_lock:  # Nominatim policy: max 1 request/second
            async with httpx.AsyncClient(timeout=15, headers=HEADERS) as cl:
                r = await cl.get(config.NOMINATIM_URL, params={"q": q, "format": "json", "limit": 4,
                                                               "countrycodes": "pk", "accept-language": "en"})
            await asyncio.sleep(1.0)
        for h in r.json() if r.status_code == 200 else []:
            la, lo = float(h["lat"]), float(h["lon"])
            if any(abs(la - o["lat"]) < .01 and abs(lo - o["lon"]) < .01 for o in out):
                continue
            bb = [float(x) for x in h.get("boundingbox", [])]
            parts = h.get("display_name", "").split(", ")
            item = {"name": h.get("name") or parts[0], "address": ", ".join(parts[1:4]), "lat": la, "lon": lo,
                    "type": (h.get("type") or "").replace("_", " "),
                    "extent": [bb[2], bb[1], bb[3], bb[0]] if len(bb) == 4 and h.get("class") in ("place", "boundary") else None}
            if item["name"].lower() == q.lower():
                out.insert(0, item)
            else:
                out.append(item)
    return out[:limit]


async def reverse(lat: float, lon: float) -> dict:
    async with httpx.AsyncClient(timeout=15, headers=HEADERS) as cl:
        r = await cl.get(config.NOMINATIM_URL.replace("/search", "/reverse"),
                         params={"lat": lat, "lon": lon, "format": "json", "zoom": 16, "accept-language": "en"})
    j = r.json() if r.status_code == 200 else {}
    return {"name": j.get("name") or "", "address": j.get("display_name") or f"{lat:.5f}, {lon:.5f}"}


async def weather(lat: float, lon: float) -> dict:
    async with httpx.AsyncClient(timeout=20) as cl:
        r = await cl.get("https://api.open-meteo.com/v1/forecast",
                         params={"latitude": lat, "longitude": lon, "timezone": "Asia/Karachi", "forecast_days": 3,
                                 "current": "temperature_2m,precipitation,weather_code,wind_speed_10m",
                                 "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min"})
    j = r.json()
    return {"current": j.get("current", {}), "daily": j.get("daily", {}), "elevation": j.get("elevation")}


# ---------- OpenStreetMap / Overpass ----------

OVERPASS_MIRRORS = [config.OVERPASS_URL, "https://overpass.kumi.systems/api/interpreter",
                    "https://overpass.private.coffee/api/interpreter"]
_overpass_cache: dict[str, dict] = {}
_overpass_good = {"url": config.OVERPASS_URL}


async def overpass(query: str, budget: float = 90) -> dict:
    """Run a query on the public Overpass servers. They are often busy, so fall through the mirrors
    within `budget` seconds, remember the one that answered last, and cache answers (demo questions repeat)."""
    if query in _overpass_cache:
        return _overpass_cache[query]
    urls = [_overpass_good["url"]] + [u for u in dict.fromkeys(OVERPASS_MIRRORS) if u != _overpass_good["url"]]
    busy = None
    deadline = time.monotonic() + budget
    async with httpx.AsyncClient(headers=HEADERS) as cl:
        for url in urls:
            left = deadline - time.monotonic()
            if left < 5:
                break
            try:
                r = await cl.post(url, data={"data": query}, timeout=httpx.Timeout(min(45, left), connect=10))
            except httpx.HTTPError as e:
                busy = f"{url.split('/')[2]} did not answer ({type(e).__name__})"
                continue
            if r.status_code == 400:  # bad query: no point asking a mirror, let the AI fix it
                raise RuntimeError(f"Overpass 400: {r.text[:400]}")
            if r.status_code != 200:
                busy = f"{url.split('/')[2]} busy ({r.status_code})"
                continue
            _overpass_good["url"] = url
            j = r.json()
            if len(_overpass_cache) > 300:
                _overpass_cache.clear()
            _overpass_cache[query] = j
            return j
    raise RuntimeError(f"OpenStreetMap servers are busy right now, try again in a minute ({busy})")


def _category(tags: dict) -> str:
    for k in ("amenity", "shop", "tourism", "highway", "waterway", "natural", "landuse", "building"):
        if k in tags:
            return f"{k}={tags[k]}"
    if tags.get("bridge") == "yes":
        return "bridge"
    return "feature"


def to_geojson(osm: dict) -> dict:
    feats = []
    for el in osm.get("elements", []):
        if el["type"] == "node":
            lat, lon = el.get("lat"), el.get("lon")
        else:
            c = el.get("center") or {}
            lat, lon = c.get("lat"), c.get("lon")
        if lat is None:
            continue
        tags = el.get("tags", {})
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
                      "properties": {"id": f'{el["type"]}/{el["id"]}',
                                     "name": tags.get("name:en") or tags.get("name") or "(unnamed)",
                                     "name_ur": tags.get("name:ur"),
                                     "category": _category(tags),
                                     "phone": tags.get("phone") or tags.get("contact:phone")}})
    return {"type": "FeatureCollection", "features": feats}


async def exposure(lat: float, lon: float, radius_m: int = 1000, budget: float = 30) -> dict:
    q = f"""[out:json][timeout:25];
(
  nwr["amenity"~"^(school|college|university|kindergarten)$"](around:{radius_m},{lat},{lon});
  nwr["amenity"~"^(hospital|clinic|doctors)$"](around:{radius_m},{lat},{lon});
  nwr["amenity"="place_of_worship"](around:{radius_m},{lat},{lon});
  way["bridge"="yes"](around:{radius_m},{lat},{lon});
);
out center 300;"""
    gj = to_geojson(await overpass(q, budget))
    counts = {"schools": 0, "health": 0, "worship": 0, "bridges": 0}
    for f in gj["features"]:
        c = f["properties"]["category"]
        if c.startswith("amenity=") and c.split("=")[1] in ("school", "college", "university", "kindergarten"):
            counts["schools"] += 1
        elif c.startswith("amenity=") and c.split("=")[1] in ("hospital", "clinic", "doctors"):
            counts["health"] += 1
        elif c == "amenity=place_of_worship":
            counts["worship"] += 1
        else:
            counts["bridges"] += 1
    return {"radius_m": radius_m, "counts": counts, "geojson": gj}


async def nearby_help(lat: float, lon: float, radius_m: int = 8000) -> dict:
    q = f"""[out:json][timeout:25];
(
  nwr["amenity"~"^(hospital|clinic|police|fire_station|shelter)$"](around:{radius_m},{lat},{lon});
  nwr["social_facility"="shelter"](around:{radius_m},{lat},{lon});
);
out center 100;"""
    gj = to_geojson(await overpass(q, budget=50))
    for f in gj["features"]:
        lo, la = f["geometry"]["coordinates"]
        f["properties"]["distance_km"] = round(haversine_m(lat, lon, la, lo) / 1000, 1)
    gj["features"].sort(key=lambda f: f["properties"]["distance_km"])
    return gj


async def help_along_route(coords) -> dict:
    pts = sample_line(coords, 25)
    line = ",".join(f"{p[1]:.5f},{p[0]:.5f}" for p in pts)
    q = f"""[out:json][timeout:40];
(
  nwr["amenity"~"^(hospital|police|fuel)$"](around:2500,{line});
);
out center 150;"""
    gj = to_geojson(await overpass(q, budget=30))
    for f in gj["features"]:
        lo, la = f["geometry"]["coordinates"]
        f["properties"]["km_along"] = round(distance_to_line(la, lo, coords)[1], 1)
    gj["features"].sort(key=lambda f: f["properties"]["km_along"])
    return gj


# ---------- routing ----------

async def routes(a: dict, b: dict, alternatives: int = 3) -> list[dict]:
    url = (f'{config.OSRM_URL}/route/v1/driving/{a["lon"]},{a["lat"]};{b["lon"]},{b["lat"]}'
           f"?overview=full&geometries=geojson&alternatives={alternatives}&steps=true")
    async with httpx.AsyncClient(timeout=60, headers=HEADERS) as cl:
        r = await cl.get(url)
    j = r.json()
    if j.get("code") != "Ok":
        raise RuntimeError(f"Routing failed: {j.get('message', j.get('code'))}")
    return [{"distance_km": round(rt["distance"] / 1000, 1), "duration_h": round(rt["duration"] / 3600, 2),
             "coords": rt["geometry"]["coordinates"], "steps": _steps(rt)} for rt in j["routes"]]


def _steps(rt: dict, limit: int = 80) -> list[dict]:
    """Turn-by-turn directions from OSRM, merged so short steps on the same road don't repeat."""
    out = []
    for leg in rt.get("legs", []):
        for s in leg.get("steps", []):
            m = s.get("maneuver", {})
            kind, mod = m.get("type", ""), (m.get("modifier") or "").replace("_", " ")
            name, ref = (s.get("name") or "").strip(), (s.get("ref") or "").split(";")[0].strip()
            # OSM names here are often Urdu script only; lead with the road number (N-35, M-15) when there is one
            road = f"{ref} ({name})" if ref and name and _URDU.search(name) else (name or ref)
            if out and road and out[-1]["road"] == road and kind not in ("arrive", "roundabout", "rotary") \
                    and (kind in ("continue", "new name", "merge", "fork") or mod in ("", "straight")):
                out[-1]["km"] += s["distance"] / 1000
                continue
            if kind == "depart":
                text = "Start" + (f" on {road}" if road else "")
            elif kind == "arrive":
                text = "Arrive at destination"
            elif kind in ("roundabout", "rotary"):
                text = f"At the roundabout take exit {m.get('exit', '')}".strip() + (f" onto {road}" if road else "")
            else:
                verb = {"turn": "Turn", "end of road": "Turn", "fork": "Keep", "merge": "Merge",
                        "on ramp": "Take the ramp", "off ramp": "Take the exit", "continue": "Continue",
                        "new name": "Continue"}.get(kind, kind.capitalize() or "Continue")
                if mod == "straight":
                    verb = "Continue"
                text = f"{verb} {mod}".strip() + (f" onto {road}" if road else "")
            out.append({"text": text, "road": road, "km": s["distance"] / 1000, "modifier": mod, "type": kind,
                        "lat": m.get("location", [0, 0])[1], "lon": m.get("location", [0, 0])[0]})
    for s in out:
        s["km"] = round(s["km"], 1)
    return out[:limit]


# ---------- weather + terrain (Open-Meteo, free, no key) ----------

async def rain(lat: float, lon: float) -> dict:
    async with httpx.AsyncClient(timeout=30) as cl:
        r = await cl.get("https://api.open-meteo.com/v1/forecast",
                         params={"latitude": lat, "longitude": lon, "daily": "precipitation_sum",
                                 "forecast_days": 3, "timezone": "Asia/Karachi"})
    d = r.json().get("daily", {})
    vals = [round(v or 0, 1) for v in d.get("precipitation_sum", [])]
    return {"days": d.get("time", []), "mm": vals, "total_mm": round(sum(vals), 1)}


async def slope(lat: float, lon: float, step_m: float = 100) -> float:
    """Easy slope: elevation at the point and 100 m N/E/S/W; slope = atan(biggest drop / 100 m)."""
    dlat = step_m / 110540
    dlon = step_m / (111320 * math.cos(math.radians(lat)))
    lats = [lat, lat + dlat, lat, lat - dlat, lat]
    lons = [lon, lon, lon + dlon, lon, lon - dlon]
    async with httpx.AsyncClient(timeout=30) as cl:
        r = await cl.get("https://api.open-meteo.com/v1/elevation",
                         params={"latitude": ",".join(f"{x:.6f}" for x in lats),
                                 "longitude": ",".join(f"{x:.6f}" for x in lons)})
    el = r.json().get("elevation", [])
    if len(el) < 5:
        raise RuntimeError("elevation unavailable")
    diff = max(abs(el[0] - e) for e in el[1:])
    return round(math.degrees(math.atan(diff / step_m)), 1)
