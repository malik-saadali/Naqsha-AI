"""Module B (PaharWatch) + C (spatial enrichment) + D (risk) + alerts to subscribers and families."""
import asyncio
import io
import json
import uuid

from . import config, db, geo, live, llm, prompts, risk

LEVEL_EMOJI = {"high": "🔴", "medium": "🟠", "low": "🟢"}


def exif_gps(image: bytes):
    try:
        import exifread
        tags = exifread.process_file(io.BytesIO(image), details=False)

        def conv(v):
            d, m, s = [float(x.num) / float(x.den) for x in v.values]
            return d + m / 60 + s / 3600

        lat = conv(tags["GPS GPSLatitude"])
        lon = conv(tags["GPS GPSLongitude"])
        if str(tags.get("GPS GPSLatitudeRef", "N")) == "S":
            lat = -lat
        if str(tags.get("GPS GPSLongitudeRef", "E")) == "W":
            lon = -lon
        return lat, lon
    except Exception:
        return None


def _save(data: bytes, ext: str) -> str:
    name = f"{uuid.uuid4().hex[:12]}.{ext}"
    (config.UPLOAD_DIR / name).write_bytes(data)
    return f"/media/{name}"


async def enrich(lat: float, lon: float) -> dict:
    """Rain, slope and exposure in parallel; each one may fail without breaking the report."""
    rain_r, slope_r, exp_r = await asyncio.gather(geo.rain(lat, lon), geo.slope(lat, lon),
                                                  geo.exposure(lat, lon, 1000), return_exceptions=True)
    out = {"rain_72h": None, "rain_daily": None, "slope_deg": None, "exposure": None}
    if not isinstance(rain_r, Exception):
        out["rain_72h"], out["rain_daily"] = rain_r["total_mm"], rain_r
    if not isinstance(slope_r, Exception):
        out["slope_deg"] = slope_r
    if not isinstance(exp_r, Exception):
        out["exposure"] = exp_r
    return out


async def analyze(image: bytes | None, mime: str, transcript: str) -> dict:
    if image:
        try:
            return await llm.chat_json(prompts.VISION.format(transcript=transcript or "(no voice note)"),
                                       "Assess this photo.", image=image, mime=mime)
        except Exception as e:
            if not transcript:
                raise RuntimeError(f"Vision model failed: {e}")
    return await llm.chat_json(prompts.TEXT_ONLY.format(transcript=transcript), "Classify this report.")


async def create_report(image: bytes | None, image_mime: str, audio: bytes | None, audio_name: str,
                        lat: float | None, lon: float | None, description: str = "",
                        source: str = "web", reporter: str = "") -> dict:
    if (lat is None or lon is None) and image:
        gps = exif_gps(image)
        if gps:
            lat, lon = gps
    if lat is None or lon is None:
        raise ValueError("Location is required (share location, use photo GPS, or click the map).")

    transcript, language = description or "", None
    if audio:
        t = await llm.transcribe(audio, audio_name)
        transcript = (t.get("text", "") + " " + (description or "")).strip()
        language = t.get("language")
    if not image and not transcript:
        raise ValueError("Send a photo or a voice note / description.")

    ai, extra = await asyncio.gather(analyze(image, image_mime, transcript), enrich(lat, lon))
    sev = int(ai.get("severity") or 1)
    r = risk.score(sev, extra["rain_72h"], extra["slope_deg"], extra["exposure"])

    exposure_small = None
    if extra["exposure"]:
        exposure_small = {"radius_m": 1000, "counts": extra["exposure"]["counts"],
                          "names": [f["properties"]["name"] for f in extra["exposure"]["geojson"]["features"][:15]]}

    # Duplicate merge: same area (200 m) within 24 h -> increase report count
    for h in db.query("SELECT * FROM hazards WHERE created_at>? AND status NOT IN ('Resolved','False report')",
                      (db.now() - 86400,)):
        if geo.haversine_m(lat, lon, h["lat"], h["lon"]) <= 200:
            new_sev = max(sev, h["severity"] or 1)
            r = risk.score(new_sev, extra["rain_72h"], extra["slope_deg"], extra["exposure"])
            db.update("hazards", h["id"], {"report_count": (h["report_count"] or 1) + 1, "severity": new_sev,
                                           "risk_score": r["score"], "risk_level": r["level"],
                                           "risk_breakdown": r["breakdown"], "updated_at": db.now()})
            merged = get(h["id"])
            merged["merged"] = True
            await live.hub.send("hazard", merged)
            return merged

    hid = db.insert("hazards", {
        "lat": lat, "lon": lon,
        "hazard_type": ai.get("hazard_type", "landslide"), "severity": sev,
        "confidence": ai.get("confidence"), "indicators": ai.get("indicators", []),
        "evidence": ai.get("evidence", ""), "recommended_action": ai.get("recommended_action", ""),
        "road_blocked": 1 if ai.get("road_blocked") else 0,
        "summary_en": ai.get("summary_en", ""), "summary_ur": ai.get("summary_ur", ""),
        "transcript": transcript, "language": language, "description": description,
        "photo": _save(image, image_mime.split("/")[-1].replace("jpeg", "jpg")) if image else None,
        "audio": _save(audio, audio_name.rsplit(".", 1)[-1] if "." in audio_name else "ogg") if audio else None,
        "rain_72h": extra["rain_72h"], "rain_daily": extra["rain_daily"], "slope_deg": extra["slope_deg"],
        "exposure": exposure_small,
        "risk_score": r["score"], "risk_level": r["level"], "risk_breakdown": r["breakdown"],
        "source": source, "reporter": reporter, "status": "New",
        "created_at": db.now(), "updated_at": db.now()})
    h = get(hid)
    await live.hub.send("hazard", h)
    if r["level"] == "high":
        asyncio.create_task(notify_people(h))
    return h


def get(hid: int) -> dict | None:
    return db.one("SELECT * FROM hazards WHERE id=?", (hid,))


def active() -> list[dict]:
    return db.query("SELECT * FROM hazards WHERE status NOT IN ('Resolved','False report') ORDER BY risk_score DESC")


async def notify_people(h: dict):
    """High risk: alert subscribers nearby and ask family members nearby if they are safe."""
    text = (f"{LEVEL_EMOJI.get(h['risk_level'], '')} NAQSHA ALERT / انتباہ\n"
            f"{h['hazard_type'].replace('_', ' ').title()} reported, risk {h['risk_score']}/100.\n"
            f"{h.get('summary_en') or ''}\n{h.get('summary_ur') or ''}\n"
            f"Map: https://www.openstreetmap.org/?mlat={h['lat']}&mlon={h['lon']}#map=15/{h['lat']}/{h['lon']}\n"
            f"Emergency: Rescue 1122")
    sent = 0
    for s in db.query("SELECT * FROM subscribers"):
        if geo.haversine_m(h["lat"], h["lon"], s["lat"], s["lon"]) <= (s["radius_km"] or config.ALERT_RADIUS_KM) * 1000:
            sent += await live.telegram(s["chat_id"], text)
    for m in db.query("SELECT * FROM family_members WHERE lat IS NOT NULL"):
        if geo.haversine_m(h["lat"], h["lon"], m["lat"], m["lon"]) <= config.ALERT_RADIUS_KM * 1000:
            db.update("family_members", m["chat_id"], {"status": "asked", "updated_at": db.now()}, key="chat_id")
            await live.telegram(m["chat_id"], "⚠️ A high-risk hazard was reported near you. Are you safe?\n"
                                              "کیا آپ محفوظ ہیں؟ Reply /safe or /needhelp")
    await live.hub.send("notified", {"hazard_id": h["id"], "subscribers": sent})


async def make_alert(hid: int) -> dict:
    h = get(hid)
    facts = {k: h.get(k) for k in ("hazard_type", "severity", "road_blocked", "risk_score", "risk_level",
                                   "summary_en", "recommended_action", "rain_72h", "slope_deg", "exposure",
                                   "lat", "lon")}
    a = await llm.chat_json(prompts.ALERT.format(facts=json.dumps(facts, ensure_ascii=False)), "Write the alerts.")
    db.insert("alerts", {"hazard_id": hid, "sms_en": a.get("sms_en"), "sms_ur": a.get("sms_ur"),
                         "notice_en": a.get("notice_en"), "notice_ur": a.get("notice_ur"), "created_at": db.now()})
    return a
