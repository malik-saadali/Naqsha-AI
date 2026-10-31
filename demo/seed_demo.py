"""Load demo data into a running Naqsha AI server.

Every hazard goes through the real pipeline (/api/report): Whisper, the vision model with the
geology checklist, rain, slope, exposure and the risk score. Takes about 5-8 minutes.

Usage (server must be running on http://localhost:8000):
    python demo/seed_demo.py           # add demo data
    python demo/seed_demo.py --reset   # wipe the database and uploads first, then add demo data
"""
import sys
import time
from pathlib import Path

import httpx

API = "http://localhost:8000"
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# photo, voice note, lat, lon, description (what the reporter typed)
REPORTS = [
    ("01_landslide_truck_blocked.jpg", "besham_landslide_voice_note.wav", 34.9105, 72.8655,
     "KKH near Besham, landslide on the road"),
    ("02_landslide_wet_road.jpg", None, 35.2905, 73.2895,
     "Dasu ke qareeb KKH par mitti aur pathar gir gaye hain"),
    ("03_landslide_fallen_pole.jpg", None, 35.0317, 72.9458,
     "Pattan, KKH: landslide brought down an electric pole onto the road"),
    ("04_rocks_mud_curved_road.jpg", None, 33.9079, 73.3955,
     "Murree road near Jhika Gali, rocks and mud on the bend"),
    ("05_mudslide_rural_road.jpg", None, 34.7800, 73.5250,
     "Kaghan valley road, mudslide with fallen trees"),
    ("06_flooded_street.jpg", "mingora_flood_voice_note.wav", 34.7717, 72.3600,
     "Mingora, street flooded after heavy rain"),
    ("07_flooded_houses.jpg", None, 34.0153, 71.9747,
     "Nowshera, flood water entering houses near Kabul river"),
    (None, None, 34.5510, 73.3530,
     "Balakot: lambi daraarein (cracks) sarak par aur upar pahar par, pani bhi nikal raha hai"),
]

TEAMS = [("Rescue 1122 Shangla", "Rescue 1122"), ("NHA Maintenance Besham", "NHA road crew"),
         ("Rescue 1122 Swat", "Rescue 1122"), ("Al-Khidmat Volunteers Mansehra", "Volunteers")]


def reset():
    import sqlite3
    db = sqlite3.connect(ROOT / "data" / "naqsha.db")
    for t in ("hazards", "queries", "alerts", "subscribers", "families", "family_members", "checkins",
              "teams", "assignments"):
        db.execute(f"DELETE FROM {t}")
    db.execute("DELETE FROM sqlite_sequence")
    db.commit()
    for f in (ROOT / "data" / "uploads").iterdir():
        if f.name != ".gitkeep":
            f.unlink()
    print("Database and uploads cleared.")


def snap_to_road(lat: float, lon: float) -> tuple[float, float]:
    """Move the point onto the nearest road (OSRM) so route checks find it within 500 m."""
    try:
        r = httpx.get(f"https://router.project-osrm.org/nearest/v1/driving/{lon},{lat}?number=1", timeout=20)
        w = r.json()["waypoints"][0]
        if w["distance"] < 2000:
            return round(w["location"][1], 6), round(w["location"][0], 6)
    except Exception:
        pass
    return lat, lon


def main():
    c = httpx.Client(base_url=API, timeout=300)
    try:
        c.get("/api/stats").raise_for_status()
    except Exception:
        sys.exit("Server is not running. Start it first (START_NAQSHA.bat), then run this again.")
    if "--reset" in sys.argv:
        reset()

    for name, kind in TEAMS:
        c.post("/api/teams", json={"name": name, "type": kind, "chat_id": ""}).raise_for_status()
    print(f"Added {len(TEAMS)} response teams.")

    for i, (photo, voice, lat, lon, desc) in enumerate(REPORTS, 1):
        files = {}
        if photo:
            files["image"] = (photo, (HERE / "photos" / photo).read_bytes(), "image/jpeg")
        if voice:
            files["audio"] = (voice, (HERE / "voice" / voice).read_bytes(), "audio/wav")
        lat, lon = snap_to_road(lat, lon)
        t = time.time()
        r = c.post("/api/report", files=files or None,
                   data={"lat": lat, "lon": lon, "description": desc, "source": "demo", "reporter": "demo"})
        if r.status_code != 200:
            print(f"  [{i}/{len(REPORTS)}] FAILED: {r.text[:200]}")
            continue
        h = r.json()
        print(f"  [{i}/{len(REPORTS)}] #{h['id']} {h['hazard_type']} · severity {h['severity']} · "
              f"risk {h['risk_score']} ({h['risk_level']}){' · ROAD BLOCKED' if h['road_blocked'] else ''} "
              f"· {round(time.time() - t)} s")

    # A subscriber and a family circle near Besham, plus check-ins, so the counters and feed are not empty
    c.post("/api/subscribe", json={"chat_id": "demo-subscriber", "name": "Demo traveller",
                                   "lat": 34.92, "lon": 72.87, "radius_km": 10})
    code = c.post("/api/family/new", json={"chat_id": "demo-ali", "name": "Ali",
                                           "lat": 34.93, "lon": 72.87}).json()["code"]
    c.post("/api/family/join", json={"chat_id": "demo-sara", "name": "Sara", "code": code})
    c.post("/api/checkin", json={"chat_id": "demo-sara", "name": "Sara", "status": "safe"})
    c.post("/api/checkin", json={"chat_id": "demo-ali", "name": "Ali", "status": "help", "lat": 34.93, "lon": 72.87})
    print(f"Added 1 subscriber, family circle {code} (Ali, Sara), 1 safe and 1 help check-in.")
    print("Done. Open http://localhost:8000")


if __name__ == "__main__":
    main()
