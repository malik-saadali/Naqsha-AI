"""Naqsha AI — FastAPI app. Run: uvicorn backend.main:app --reload --port 8000"""
import json
import random
import string

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import ask_map, config, db, documents, geo, hazards, live, llm, prompts, routes

db.init()
app = FastAPI(title="Naqsha AI", description="Open-weight AI command center for landslides, floods and road safety in Pakistan")
app.mount("/media", StaticFiles(directory=config.UPLOAD_DIR), name="media")
app.mount("/static", StaticFiles(directory=config.FRONTEND_DIR), name="static")

_route_cache: dict[str, dict] = {}


def _err(e: Exception):
    raise HTTPException(status_code=400, detail=str(e)[:500])


# ---------------- pages ----------------
@app.get("/", response_class=HTMLResponse)
def dashboard():
    return FileResponse(config.FRONTEND_DIR / "index.html")


@app.get("/report", response_class=HTMLResponse)
def report_page():
    return FileResponse(config.FRONTEND_DIR / "report.html")


@app.get("/graph", response_class=HTMLResponse)
def code_graph():
    """Interactive knowledge graph of this codebase, built with Graphify (graphify update .)."""
    f = config.ROOT / "graphify-out" / "graph.html"
    if not f.exists():
        raise HTTPException(404, "Run `graphify update .` in the project folder to build the code graph.")
    return FileResponse(f)


@app.get("/print/sitrep", response_class=HTMLResponse)
async def print_sitrep():
    return HTMLResponse(await documents.sitrep())


@app.get("/print/letter/{hid}", response_class=HTMLResponse)
async def print_letter(hid: int, authority: str = "National Highway Authority (NHA)", lang: str = "English"):
    return HTMLResponse(await documents.letter(hid, authority, lang))


@app.get("/print/card", response_class=HTMLResponse)
async def print_card(origin: str, destination: str):
    key = f"{origin.lower()}|{destination.lower()}"
    res = _route_cache.get(key) or await routes.check(origin, destination)
    return HTMLResponse(documents.card(res))


# ---------------- settings ----------------
class ProviderIn(BaseModel):
    provider: str


@app.get("/api/settings")
def get_settings():
    return {**llm.models(), "telegram": bool(config.TELEGRAM_BOT_TOKEN), "public_url": config.PUBLIC_URL,
            "websocket": not config.SERVERLESS, "ai_key": bool(config.GROQ_API_KEY)}


@app.post("/api/settings")
def set_settings(body: ProviderIn):
    try:
        llm.set_provider(body.provider)
    except ValueError as e:
        _err(e)
    return llm.models()


# ---------------- A. ask the map ----------------
class AskIn(BaseModel):
    question: str
    bbox: list[float] | None = None  # south, west, north, east


@app.post("/api/ask")
async def api_ask(body: AskIn):
    try:
        return await ask_map.ask(body.question, body.bbox)
    except Exception as e:
        _err(e)


@app.get("/api/queries")
def api_queries():
    return db.query("SELECT id, question, result_count, summary, created_at FROM queries ORDER BY id DESC LIMIT 30")


# ---------------- B/C/D. hazards ----------------
@app.post("/api/report")
async def api_report(image: UploadFile | None = File(None), audio: UploadFile | None = File(None),
                     lat: float | None = Form(None), lon: float | None = Form(None),
                     description: str = Form(""), source: str = Form("web"), reporter: str = Form("")):
    img = await image.read() if image else None
    aud = await audio.read() if audio else None
    try:
        return await hazards.create_report(img or None, (image.content_type if image else None) or "image/jpeg",
                                           aud or None, (audio.filename if audio else None) or "voice.webm",
                                           lat, lon, description, source, reporter)
    except Exception as e:
        _err(e)


@app.get("/api/hazards")
def api_hazards(include_closed: bool = False):
    if include_closed:
        return db.query("SELECT * FROM hazards ORDER BY risk_score DESC")
    return hazards.active()


@app.get("/api/hazards/{hid}")
def api_hazard(hid: int):
    h = hazards.get(hid)
    if not h:
        raise HTTPException(404, "not found")
    h["assignments"] = db.query("SELECT a.*, t.name team FROM assignments a JOIN teams t ON t.id=a.team_id "
                                "WHERE hazard_id=? ORDER BY a.id DESC", (hid,))
    return h


class StatusIn(BaseModel):
    status: str  # New | Verified | Action taken | Resolved | False report


@app.patch("/api/hazards/{hid}")
async def api_hazard_status(hid: int, body: StatusIn):
    db.update("hazards", hid, {"status": body.status, "updated_at": db.now()})
    h = hazards.get(hid)
    await live.hub.send("hazard", h)
    return h


@app.get("/api/hazards/{hid}/exposure")
async def api_exposure(hid: int, r: int = 1000):
    h = hazards.get(hid)
    try:
        return await geo.exposure(h["lat"], h["lon"], r)
    except Exception as e:
        _err(e)


@app.post("/api/alert/{hid}")
async def api_alert(hid: int):
    try:
        return await hazards.make_alert(hid)
    except Exception as e:
        _err(e)


@app.post("/api/hazards/{hid}/notify")
async def api_notify(hid: int):
    await hazards.notify_people(hazards.get(hid))
    return {"ok": True}


# ---------------- E. route safety ----------------
class RouteIn(BaseModel):
    origin: str
    destination: str


@app.post("/api/route-check")
async def api_route(body: RouteIn):
    try:
        res = await routes.check(body.origin, body.destination)
    except Exception as e:
        _err(e)
    _route_cache[f"{body.origin.lower()}|{body.destination.lower()}"] = res
    return res


@app.get("/api/search")
async def api_search(q: str, lat: float | None = None, lon: float | None = None):
    if len(q.strip()) < 2:
        return []
    try:
        return await geo.search(q.strip(), lat, lon)
    except Exception as e:
        _err(e)


@app.get("/api/reverse")
async def api_reverse(lat: float, lon: float):
    try:
        return await geo.reverse(lat, lon)
    except Exception as e:
        _err(e)


@app.get("/api/weather")
async def api_weather(lat: float, lon: float):
    try:
        return await geo.weather(lat, lon)
    except Exception as e:
        _err(e)


@app.get("/api/nearby")
async def api_nearby(lat: float, lon: float):
    try:
        return await geo.nearby_help(lat, lon)
    except Exception as e:
        _err(e)


# ---------------- F/J. subscribers, check-ins, families ----------------
class SubIn(BaseModel):
    chat_id: str
    lat: float
    lon: float
    radius_km: float = config.ALERT_RADIUS_KM
    name: str = ""


@app.post("/api/subscribe")
def api_subscribe(b: SubIn):
    db.execute("INSERT OR REPLACE INTO subscribers(chat_id,name,lat,lon,radius_km,created_at) VALUES(?,?,?,?,?,?)",
               (b.chat_id, b.name, b.lat, b.lon, b.radius_km, db.now()))
    near = [h for h in hazards.active() if geo.haversine_m(b.lat, b.lon, h["lat"], h["lon"]) <= b.radius_km * 1000]
    return {"ok": True, "active_nearby": len(near)}


class CheckIn(BaseModel):
    chat_id: str
    name: str = ""
    status: str = "safe"  # safe | help
    lat: float | None = None
    lon: float | None = None


@app.post("/api/checkin")
async def api_checkin(b: CheckIn):
    m = db.one("SELECT * FROM family_members WHERE chat_id=?", (b.chat_id,))
    lat = b.lat if b.lat is not None else (m or {}).get("lat")
    lon = b.lon if b.lon is not None else (m or {}).get("lon")
    db.insert("checkins", {"chat_id": b.chat_id, "name": b.name, "lat": lat, "lon": lon,
                           "status": b.status, "created_at": db.now()})
    notified = 0
    if m:
        db.update("family_members", b.chat_id, {"status": b.status, "updated_at": db.now(),
                                                "lat": lat, "lon": lon}, key="chat_id")
        for other in db.query("SELECT * FROM family_members WHERE code=? AND chat_id!=?", (m["code"], b.chat_id)):
            msg = (f"✅ {m['name']} is SAFE / محفوظ ہیں" if b.status == "safe"
                   else f"🆘 {m['name']} NEEDS HELP / مدد چاہیے" +
                   (f"\nhttps://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=16/{lat}/{lon}" if lat else ""))
            notified += await live.telegram(other["chat_id"], msg)
    await live.hub.send("checkin", {"status": b.status, "name": b.name, "lat": lat, "lon": lon})
    return {"ok": True, "family_notified": notified}


class FamilyIn(BaseModel):
    chat_id: str
    name: str
    code: str | None = None
    lat: float | None = None
    lon: float | None = None


@app.post("/api/family/new")
def api_family_new(b: FamilyIn):
    code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    db.insert("families", {"code": code, "created_at": db.now()})
    db.execute("INSERT OR REPLACE INTO family_members(chat_id,code,name,status,lat,lon,updated_at) VALUES(?,?,?,?,?,?,?)",
               (b.chat_id, code, b.name, "unknown", b.lat, b.lon, db.now()))
    return {"code": code}


@app.post("/api/family/join")
def api_family_join(b: FamilyIn):
    code = (b.code or "").upper()
    if not db.one("SELECT * FROM families WHERE code=?", (code,)):
        raise HTTPException(404, "Family code not found")
    db.execute("INSERT OR REPLACE INTO family_members(chat_id,code,name,status,lat,lon,updated_at) VALUES(?,?,?,?,?,?,?)",
               (b.chat_id, code, b.name, "unknown", b.lat, b.lon, db.now()))
    return {"code": code, "members": db.query("SELECT name,status FROM family_members WHERE code=?", (code,))}


@app.post("/api/family/location")
def api_family_location(b: FamilyIn):
    db.execute("UPDATE family_members SET lat=?, lon=?, updated_at=? WHERE chat_id=?", (b.lat, b.lon, db.now(), b.chat_id))
    return {"ok": True}


@app.get("/api/family/{chat_id}")
def api_family(chat_id: str):
    m = db.one("SELECT * FROM family_members WHERE chat_id=?", (chat_id,))
    if not m:
        raise HTTPException(404, "Not in a family yet")
    return {"code": m["code"], "members": db.query("SELECT name,status,updated_at FROM family_members WHERE code=?",
                                                   (m["code"],))}


# ---------------- H. responders ----------------
class TeamIn(BaseModel):
    name: str
    type: str = "Rescue 1122"
    chat_id: str = ""


@app.get("/api/teams")
def api_teams():
    return db.query("SELECT * FROM teams ORDER BY id")


@app.post("/api/teams")
def api_team_add(b: TeamIn):
    return {"id": db.insert("teams", {"name": b.name, "type": b.type, "chat_id": b.chat_id, "status": "available"})}


class AssignIn(BaseModel):
    hazard_id: int
    team_id: int


@app.post("/api/assign")
async def api_assign(b: AssignIn):
    h, t = hazards.get(b.hazard_id), db.one("SELECT * FROM teams WHERE id=?", (b.team_id,))
    if not h or not t:
        raise HTTPException(404, "hazard or team not found")
    aid = db.insert("assignments", {"hazard_id": h["id"], "team_id": t["id"], "status": "assigned",
                                    "created_at": db.now(), "updated_at": db.now()})
    db.update("teams", t["id"], {"status": "busy"})
    db.update("hazards", h["id"], {"status": "Action taken", "updated_at": db.now()})
    sent = await live.telegram(t["chat_id"], (
        f"🚑 TASK #{aid} for {t['name']}\n{h['hazard_type'].replace('_', ' ').title()} · risk {h['risk_score']}/100"
        f"{' · ROAD BLOCKED' if h['road_blocked'] else ''}\n{h.get('summary_en') or ''}\n"
        f"Location: https://www.google.com/maps/dir/?api=1&destination={h['lat']},{h['lon']}\n"
        f"Photo: {config.PUBLIC_URL}{h['photo'] or ''}\n"
        f"Reply: /status onway | /status reached | /status cleared"))
    await live.hub.send("hazard", hazards.get(h["id"]))
    return {"assignment_id": aid, "telegram_sent": sent}


class TeamStatusIn(BaseModel):
    chat_id: str
    status: str  # onway | reached | cleared


@app.post("/api/assignments/status")
async def api_team_status(b: TeamStatusIn):
    t = db.one("SELECT * FROM teams WHERE chat_id=?", (b.chat_id,))
    if not t:
        raise HTTPException(404, "This Telegram account is not registered as a team")
    a = db.one("SELECT * FROM assignments WHERE team_id=? ORDER BY id DESC", (t["id"],))
    if not a:
        raise HTTPException(404, "No assignment")
    db.update("assignments", a["id"], {"status": b.status, "updated_at": db.now()})
    if b.status == "cleared":
        db.update("hazards", a["hazard_id"], {"status": "Resolved", "road_blocked": 0, "updated_at": db.now()})
        db.update("teams", t["id"], {"status": "available"})
    await live.hub.send("hazard", hazards.get(a["hazard_id"]))
    return {"ok": True, "hazard_id": a["hazard_id"]}


# ---------------- N. assistant, speech, stats ----------------
class AssistantIn(BaseModel):
    question: str
    hazard_id: int | None = None


@app.post("/api/assistant")
async def api_assistant(b: AssistantIn):
    ctx = "none"
    if b.hazard_id:
        h = hazards.get(b.hazard_id)
        if h:
            ctx = json.dumps({k: h[k] for k in ("hazard_type", "severity", "risk_level", "summary_en",
                                                 "recommended_action")}, ensure_ascii=False)
    try:
        ans = await llm.chat([{"role": "system", "content": prompts.ASSISTANT.format(context=ctx)},
                              {"role": "user", "content": b.question}], max_tokens=600)
    except Exception as e:
        _err(e)
    return {"answer": ans}


@app.post("/api/transcribe")
async def api_transcribe(audio: UploadFile = File(...)):
    try:
        return await llm.transcribe(await audio.read(), audio.filename or "voice.webm")
    except Exception as e:
        _err(e)


@app.get("/api/stats")
def api_stats():
    hs = hazards.active()
    return {"active": len(hs), "high": sum(h["risk_level"] == "high" for h in hs),
            "medium": sum(h["risk_level"] == "medium" for h in hs),
            "blocked": sum(bool(h["road_blocked"]) for h in hs),
            "subscribers": db.one("SELECT COUNT(*) n FROM subscribers")["n"],
            "safe": db.one("SELECT COUNT(*) n FROM checkins WHERE status='safe'")["n"],
            "help": db.one("SELECT COUNT(*) n FROM checkins WHERE status='help'")["n"],
            "teams": db.one("SELECT COUNT(*) n FROM teams")["n"]}


@app.get("/api/export")
def api_export(fmt: str = "geojson"):
    hs = hazards.active()
    if fmt == "kml":
        pm = "".join(f"<Placemark><name>#{h['id']} {h['hazard_type']} risk {h['risk_score']}</name>"
                     f"<description>{(h.get('summary_en') or '').replace('&', 'and').replace('<', '')}</description>"
                     f"<Point><coordinates>{h['lon']},{h['lat']},0</coordinates></Point></Placemark>" for h in hs)
        kml = f'<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>Naqsha AI hazards</name>{pm}</Document></kml>'
        return HTMLResponse(kml, media_type="application/vnd.google-earth.kml+xml",
                            headers={"Content-Disposition": "attachment; filename=naqsha_hazards.kml"})
    feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [h["lon"], h["lat"]]},
              "properties": {k: h[k] for k in ("id", "hazard_type", "severity", "risk_score", "risk_level",
                                               "road_blocked", "status", "summary_en")}} for h in hs]
    return {"type": "FeatureCollection", "features": feats}


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await live.hub.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        live.hub.drop(websocket)
