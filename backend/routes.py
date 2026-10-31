"""Module E: Route safety check with automatic alternate route."""
import asyncio
import json

from . import config, geo, hazards, llm, prompts


def _hazards_on(coords: list) -> list[dict]:
    found = []
    for h in hazards.active():
        d, km = geo.distance_to_line(h["lat"], h["lon"], coords)
        if d <= config.ROUTE_BUFFER_M:
            found.append({"id": h["id"], "type": h["hazard_type"], "risk_score": h["risk_score"],
                          "risk_level": h["risk_level"], "road_blocked": bool(h["road_blocked"]),
                          "km_from_start": round(km, 1), "distance_m": round(d),
                          "lat": h["lat"], "lon": h["lon"]})
    return sorted(found, key=lambda x: x["km_from_start"])


def _verdict(found: list, max_rain: float) -> str:
    if any(f["risk_level"] == "high" or f["road_blocked"] for f in found):
        return "avoid"
    if any(f["risk_level"] == "medium" for f in found) or max_rain >= 40:
        return "caution"
    return "safe"


async def check(origin: str, destination: str) -> dict:
    a, b = await geo.geocode(origin), await geo.geocode(destination)
    if not a or not b:
        raise ValueError(f"Could not find {'origin' if not a else 'destination'} on the map.")
    options = await geo.routes(a, b)

    for r in options:
        r["hazards"] = _hazards_on(r["coords"])

    primary = options[0]
    pts = geo.sample_line(primary["coords"], 5)
    rains = await asyncio.gather(*[geo.rain(p[1], p[0]) for p in pts], return_exceptions=True)
    rain_points = [{"lat": p[1], "lon": p[0], "total_mm": rr["total_mm"]}
                   for p, rr in zip(pts, rains) if not isinstance(rr, Exception)]
    max_rain = max([x["total_mm"] for x in rain_points] or [0])

    for r in options:
        r["verdict"] = _verdict(r["hazards"], max_rain)

    alternate = None
    if primary["verdict"] == "avoid":
        safer = [r for r in options[1:] if r["verdict"] != "avoid"]
        if safer:
            alternate = min(safer, key=lambda r: r["duration_h"])

    try:
        help_pts = await geo.help_along_route((alternate or primary)["coords"])
    except Exception:
        help_pts = {"type": "FeatureCollection", "features": [], "unavailable": True}

    facts = {"origin": origin, "destination": destination,
             "distance_km": primary["distance_km"], "duration_h": primary["duration_h"],
             "verdict": primary["verdict"], "hazards_on_route": primary["hazards"],
             "max_rain_next_72h_mm": max_rain,
             "alternate": None if not alternate else {
                 "distance_km": alternate["distance_km"], "duration_h": alternate["duration_h"],
                 "extra_hours": round(alternate["duration_h"] - primary["duration_h"], 1),
                 "hazards": len(alternate["hazards"])}}
    try:
        advice = await llm.chat_json(prompts.ROUTE.format(facts=json.dumps(facts, ensure_ascii=False)), "Advise.")
    except Exception:
        advice = {"en": f"Verdict: {primary['verdict'].upper()}. {len(primary['hazards'])} hazard(s) on route.",
                  "ur": ""}

    def geo_line(r):
        return {"type": "Feature", "geometry": {"type": "LineString", "coordinates": r["coords"]},
                "properties": {k: r[k] for k in ("distance_km", "duration_h", "verdict")}}

    return {"origin": a, "destination": b, "verdict": primary["verdict"], "advice": advice,
            "primary": {**{k: primary[k] for k in ("distance_km", "duration_h", "hazards", "verdict", "steps")},
                        "geojson": geo_line(primary)},
            "alternate": None if not alternate else {
                **{k: alternate[k] for k in ("distance_km", "duration_h", "hazards", "verdict", "steps")},
                "geojson": geo_line(alternate)},
            "rain_points": rain_points, "max_rain_mm": max_rain, "help_points": help_pts}
