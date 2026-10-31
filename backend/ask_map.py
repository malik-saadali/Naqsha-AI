"""Module A: Ask the Map. Question -> parse -> geocode -> AI-written Overpass query -> self-healing loop -> map."""
import json

from . import db, geo, llm, prompts


def _fallback_query(parsed: dict, places: list[dict], bbox: list | None) -> str:
    """Deterministic query used if the model fails 3 times, so the demo never dies."""
    feats = parsed.get("features") or ["amenity=hospital"]
    d = int(parsed.get("distance_m") or 3000) or 3000
    rel = parsed.get("relation", "near")
    if places and rel == "between" and len(places) >= 2:
        areas = ["(around:%d,%s)" % (d, ",".join(f'{p["lat"]},{p["lon"]}' for p in places))]
    elif places and rel == "within" and places[0].get("bbox"):
        s, w, n, e = places[0]["bbox"]
        areas = [f"({s},{w},{n},{e})"]
    elif places:
        areas = [f'(around:{d},{p["lat"]},{p["lon"]})' for p in places]
    elif bbox:
        s, w, n, e = bbox
        areas = [f"({s},{w},{n},{e})"]
    else:
        areas = ["(33.4,72.6,36.5,75.5)"]  # northern Pakistan
    lines = []
    for f in feats:
        if "=" not in f:
            continue
        k, v = f.split("=", 1)
        for a in areas:
            lines.append(f'  nwr["{k.strip()}"="{v.strip()}"]{a};')
    return "[out:json][timeout:25];\n(\n" + "\n".join(lines) + "\n);\nout center 300;"


async def _distance(question: str, parsed: dict, places: list[dict]) -> dict:
    """Distance questions: straight line + road distance from OSRM, drawn as a route."""
    a, b = places[0], places[1]
    crow = round(geo.haversine_m(a["lat"], a["lon"], b["lat"], b["lon"]) / 1000, 1)
    feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [p["lon"], p["lat"]]},
              "properties": {"name": p["name"], "category": p["display_name"]}} for p in (a, b)]
    try:
        rt = (await geo.routes(a, b, alternatives=0))[0]
        feats.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": rt["coords"]},
                      "properties": {"name": f'{rt["distance_km"]} km by road',
                                     "category": f'about {round(rt["duration_h"] * 60)} min driving'}})
        road = f'{rt["distance_km"]} km by road (about {round(rt["duration_h"] * 60)} min driving)'
    except Exception:
        road = "road distance unavailable"
    summary = f'{a["name"]} → {b["name"]}: {road}; {crow} km in a straight line.'
    gj = {"type": "FeatureCollection", "features": feats}
    qid = db.insert("queries", {"question": question, "query": "", "attempts": [], "result_count": len(feats),
                                "summary": summary, "created_at": db.now()})
    return {"id": qid, "question": question, "parsed": parsed, "places": places, "query": "",
            "attempts": [], "geojson": gj, "count": len(feats), "summary": summary,
            "label": parsed.get("label") or "Distance"}


async def ask(question: str, bbox: list | None = None) -> dict:
    parsed = await llm.chat_json(prompts.PARSE, question)
    places = []
    for name in parsed.get("places", [])[:4]:
        g = await geo.geocode(name) or (await geo.geocode(name.split(",")[0]) if "," in name else None)
        if g:
            places.append(g)

    if parsed.get("relation") == "distance":
        if len(places) < 2:
            found = [p["name"] for p in places]
            raise ValueError(f"Could not find both places on the map (found: {', '.join(found) or 'none'}). "
                             "Try fuller names, e.g. 'National Incubation Center, Islamabad'.")
        return await _distance(question, parsed, places)

    context = json.dumps({"question": question, "parsed": parsed,
                          "places": [{"name": p["name"], "lat": p["lat"], "lon": p["lon"], "bbox": p["bbox"]}
                                     for p in places],
                          "map_view_bbox_SWNE": bbox}, ensure_ascii=False)
    attempts = []
    gj = None
    try:
        query = (await llm.chat_json(prompts.OVERPASS, context)).get("query", "")
    except Exception as e:
        query, attempts = "", [{"query": "", "error": f"model error: {e}"}]

    for i in range(3):
        if not query:
            break
        try:
            gj = geo.to_geojson(await geo.overpass(query))
            if gj["features"]:
                attempts.append({"query": query, "error": None, "count": len(gj["features"])})
                break
            err = "Query ran but returned 0 results."
        except Exception as e:
            err = str(e)[:500]
        attempts.append({"query": query, "error": err})
        gj = None
        if err.startswith("OpenStreetMap servers are busy"):
            break  # the query is fine, the servers are not; asking the model to fix it would not help
        if i < 2:
            try:
                fix = await llm.chat_json(prompts.FIX, f"{context}\n\nQUERY:\n{query}\n\nERROR:\n{err}")
                query = fix.get("query", "")
            except Exception:
                break

    if gj is None or not gj["features"]:
        query = _fallback_query(parsed, places, bbox)
        try:
            gj = geo.to_geojson(await geo.overpass(query))
            attempts.append({"query": query, "error": None, "count": len(gj["features"]), "fallback": True})
        except Exception as e:
            if str(e).startswith("OpenStreetMap servers are busy"):
                raise
            gj = {"type": "FeatureCollection", "features": []}
            attempts.append({"query": query, "error": str(e)[:300], "fallback": True})

    lang = "Urdu (Urdu script)" if parsed.get("language") == "ur" else "English"
    sample = [f["properties"]["name"] for f in gj["features"][:25]]
    try:
        summary = await llm.chat([{"role": "system", "content": prompts.SUMMARY.format(lang=lang)},
                                  {"role": "user", "content": json.dumps(
                                      {"question": question, "count": len(gj["features"]),
                                       "names": sample, "places": [p["name"] for p in places]},
                                      ensure_ascii=False)}], max_tokens=300)
    except Exception:
        summary = f"Found {len(gj['features'])} results."

    final_query = attempts[-1]["query"] if attempts else query
    qid = db.insert("queries", {"question": question, "query": final_query, "attempts": attempts,
                                "result_count": len(gj["features"]), "summary": summary, "created_at": db.now()})
    return {"id": qid, "question": question, "parsed": parsed, "places": places, "query": final_query,
            "attempts": attempts, "geojson": gj, "count": len(gj["features"]), "summary": summary,
            "label": parsed.get("label") or question[:40]}
