"""Agent Skill tools: thin wrappers so any AI agent can use Naqsha AI."""
import os

import httpx

API = os.getenv("NAQSHA_API", "http://localhost:8000")


def assess_photo(path: str, lat: float, lon: float, note: str = "") -> dict:
    with open(path, "rb") as f:
        r = httpx.post(f"{API}/api/report", files={"image": (os.path.basename(path), f, "image/jpeg")},
                       data={"lat": lat, "lon": lon, "description": note, "source": "agent"}, timeout=240)
    r.raise_for_status()
    return r.json()


def ask_map(question: str) -> dict:
    r = httpx.post(f"{API}/api/ask", json={"question": question}, timeout=240)
    r.raise_for_status()
    j = r.json()
    return {"summary": j["summary"], "count": j["count"], "query": j["query"], "geojson": j["geojson"]}


def route_check(origin: str, destination: str) -> dict:
    r = httpx.post(f"{API}/api/route-check", json={"origin": origin, "destination": destination}, timeout=240)
    r.raise_for_status()
    j = r.json()
    return {"verdict": j["verdict"], "advice": j["advice"], "hazards": j["primary"]["hazards"],
            "alternate": j["alternate"] and {k: j["alternate"][k] for k in ("distance_km", "duration_h", "verdict")}}


def exposure(hazard_id: int, radius_m: int = 1000) -> dict:
    r = httpx.get(f"{API}/api/hazards/{hazard_id}/exposure", params={"r": radius_m}, timeout=120)
    r.raise_for_status()
    return r.json()["counts"]
