"""Naqsha AI Telegram bot — citizens report, subscribe, check routes, check in safe, join family circles.
Responders receive tasks and reply with /status.

Run (in a second terminal, after the API is running):  python bot.py
"""
import logging
import os

import httpx
from telegram import BotCommand, KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from backend import config

API = os.getenv("API_URL", "http://localhost:8000")
logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

HELP = """🗺 Naqsha AI — نقشہ

📷 REPORT a hazard: send a PHOTO, then (optional) a VOICE note, then share your LOCATION 📍.
/subscribe — get alerts for hazards near you
/route Islamabad to Gilgit — is the road safe?
/safe — mark yourself safe · /needhelp — ask for help
/family new <your name> — start a family safety circle
/family join <CODE> <your name> — join one · /family — see everyone's status
/help — nearest hospital, police, shelter
/id — your chat id (for response teams)
Any other message — ask the safety assistant (Urdu or English)
Emergency: Rescue 1122 · Edhi 115 · Police 15"""

LOC_KB = ReplyKeyboardMarkup([[KeyboardButton("📍 Share location", request_location=True)]],
                             resize_keyboard=True, one_time_keyboard=True)


async def call(method: str, path: str, **kw):
    async with httpx.AsyncClient(timeout=240) as cl:
        r = await cl.request(method, API + path, **kw)
    j = r.json()
    if r.status_code >= 400:
        raise RuntimeError(j.get("detail", "error"))
    return j


def name_of(u: Update) -> str:
    return u.effective_user.first_name or "Someone"


async def start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.message.reply_text(HELP)


async def my_id(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.message.reply_text(f"Your chat id: {u.effective_chat.id}")


async def photo(u: Update, c: ContextTypes.DEFAULT_TYPE):
    f = await u.message.photo[-1].get_file()
    c.user_data["photo"] = bytes(await f.download_as_bytearray())
    c.user_data["caption"] = u.message.caption or ""
    await u.message.reply_text("📷 Photo received. Optional: send a voice note. Then share your location to submit.",
                               reply_markup=LOC_KB)


async def voice(u: Update, c: ContextTypes.DEFAULT_TYPE):
    v = u.message.voice or u.message.audio
    f = await v.get_file()
    c.user_data["voice"] = bytes(await f.download_as_bytearray())
    await u.message.reply_text("🎤 Voice note received. Now share your location 📍 to submit the report.",
                               reply_markup=LOC_KB)


async def location(u: Update, c: ContextTypes.DEFAULT_TYPE):
    lat, lon = u.message.location.latitude, u.message.location.longitude
    chat = str(u.effective_chat.id)
    c.user_data["lat"], c.user_data["lon"] = lat, lon
    try:
        await call("POST", "/api/family/location", json={"chat_id": chat, "name": name_of(u), "lat": lat, "lon": lon})
    except Exception:
        pass
    mode = c.user_data.pop("awaiting", None)

    if mode == "subscribe":
        r = await call("POST", "/api/subscribe", json={"chat_id": chat, "lat": lat, "lon": lon, "name": name_of(u)})
        await u.message.reply_text(f"✅ Subscribed. You'll get alerts within {config.ALERT_RADIUS_KM:.0f} km.\n"
                                   f"Active hazards near you right now: {r['active_nearby']}")
        return
    if mode == "help":
        r = await call("GET", "/api/nearby", params={"lat": lat, "lon": lon})
        lines = [f"• {f['properties']['category'].split('=')[-1]}: {f['properties']['name']} — "
                 f"{f['properties']['distance_km']} km {('☎ ' + f['properties']['phone']) if f['properties'].get('phone') else ''}"
                 for f in r["features"][:8]]
        await u.message.reply_text("Nearest help:\n" + ("\n".join(lines) or "None found nearby.") +
                                   "\n\nRescue 1122 · Edhi 115 · Police 15")
        return
    if mode == "needhelp":
        await call("POST", "/api/checkin", json={"chat_id": chat, "name": name_of(u), "status": "help", "lat": lat, "lon": lon})
        await u.message.reply_text("🆘 Help request sent to your family circle and the command center. Call 1122 now if in danger.")
        return

    if c.user_data.get("photo") or c.user_data.get("voice"):
        await u.message.reply_text("⏳ Analysing your report with AI (geology checklist, rain, slope, nearby schools)…")
        files = {}
        if c.user_data.get("photo"):
            files["image"] = ("photo.jpg", c.user_data.pop("photo"), "image/jpeg")
        if c.user_data.get("voice"):
            files["audio"] = ("voice.ogg", c.user_data.pop("voice"), "audio/ogg")
        data = {"lat": lat, "lon": lon, "source": "telegram", "reporter": chat,
                "description": c.user_data.pop("caption", "")}
        try:
            h = await call("POST", "/api/report", data=data, files=files)
            emoji = {"high": "🔴", "medium": "🟠", "low": "🟢"}.get(h["risk_level"], "")
            await u.message.reply_text(
                f"✅ Report #{h['id']} received. شکریہ\n{emoji} Risk {h['risk_score']}/100 ({h['risk_level']})\n"
                f"Type: {h['hazard_type'].replace('_', ' ')} · severity {h['severity']}/5\n\n"
                f"{h.get('summary_en', '')}\n\n{h.get('summary_ur', '')}\n\nAction: {h.get('recommended_action', '')}")
        except Exception as e:
            await u.message.reply_text(f"⚠️ Could not process report: {e}")
    else:
        await u.message.reply_text("📍 Location saved. To report a hazard, send a photo first. /start for all options.")


async def subscribe(u: Update, c: ContextTypes.DEFAULT_TYPE):
    c.user_data["awaiting"] = "subscribe"
    await u.message.reply_text("Share the location you want alerts for 📍", reply_markup=LOC_KB)


async def help_cmd(u: Update, c: ContextTypes.DEFAULT_TYPE):
    c.user_data["awaiting"] = "help"
    await u.message.reply_text("Share your location 📍 to find the nearest hospital, police and shelter.",
                               reply_markup=LOC_KB)


async def route(u: Update, c: ContextTypes.DEFAULT_TYPE):
    text = " ".join(c.args)
    parts = [p.strip() for p in text.replace(" se ", " to ").split(" to ") if p.strip()]
    if len(parts) != 2:
        await u.message.reply_text("Usage: /route Islamabad to Gilgit")
        return
    await u.message.reply_text("⏳ Checking the road, hazards and rain…")
    try:
        r = await call("POST", "/api/route-check", json={"origin": parts[0], "destination": parts[1]})
    except Exception as e:
        await u.message.reply_text(f"⚠️ {e}")
        return
    head = {"safe": "🟢 SAFE TO TRAVEL", "caution": "🟠 TRAVEL WITH CAUTION", "avoid": "🔴 AVOID / DELAY"}[r["verdict"]]
    hz = "\n".join(f"• km {x['km_from_start']}: {x['type'].replace('_', ' ')} (risk {x['risk_score']})"
                   f"{' ROAD BLOCKED' if x['road_blocked'] else ''}" for x in r["primary"]["hazards"]) or "• none reported"
    alt = ""
    if r.get("alternate"):
        alt = f"\n\n↪️ Alternate route: {r['alternate']['distance_km']} km, ~{r['alternate']['duration_h']} h, " \
              f"{len(r['alternate']['hazards'])} hazards."
    card = f"{config.PUBLIC_URL}/print/card?origin={parts[0]}&destination={parts[1]}".replace(" ", "%20")
    await u.message.reply_text(
        f"{head}\n{r['primary']['distance_km']} km · ~{r['primary']['duration_h']} h · rain up to {r['max_rain_mm']} mm\n\n"
        f"Hazards on route:\n{hz}{alt}\n\n{r['advice'].get('en', '')}\n\n{r['advice'].get('ur', '')}\n\n🧳 Emergency card: {card}")


async def safe(u: Update, c: ContextTypes.DEFAULT_TYPE):
    r = await call("POST", "/api/checkin", json={"chat_id": str(u.effective_chat.id), "name": name_of(u), "status": "safe",
                                                 "lat": c.user_data.get("lat"), "lon": c.user_data.get("lon")})
    await u.message.reply_text(f"✅ Marked SAFE. Family members notified: {r['family_notified']}")


async def needhelp(u: Update, c: ContextTypes.DEFAULT_TYPE):
    c.user_data["awaiting"] = "needhelp"
    await u.message.reply_text("🆘 Share your location so your family and responders can find you.", reply_markup=LOC_KB)


async def family(u: Update, c: ContextTypes.DEFAULT_TYPE):
    chat = str(u.effective_chat.id)
    a = c.args
    try:
        if a and a[0].lower() == "new":
            nm = " ".join(a[1:]) or name_of(u)
            r = await call("POST", "/api/family/new", json={"chat_id": chat, "name": nm,
                                                           "lat": c.user_data.get("lat"), "lon": c.user_data.get("lon")})
            await u.message.reply_text(f"👨‍👩‍👧 Family circle created. Code: {r['code']}\n"
                                       f"Family members send: /family join {r['code']} <name>\n"
                                       f"Share your location once so alerts near you reach the family.", reply_markup=LOC_KB)
        elif a and a[0].lower() == "join" and len(a) >= 2:
            nm = " ".join(a[2:]) or name_of(u)
            r = await call("POST", "/api/family/join", json={"chat_id": chat, "name": nm, "code": a[1]})
            await u.message.reply_text(f"✅ Joined family {r['code']}. Members: " + ", ".join(m["name"] for m in r["members"]),
                                       reply_markup=LOC_KB)
        else:
            r = await call("GET", f"/api/family/{chat}")
            icon = {"safe": "✅", "help": "🆘", "asked": "⏳", "unknown": "•"}
            await u.message.reply_text(f"Family {r['code']}:\n" + "\n".join(
                f"{icon.get(m['status'], '•')} {m['name']}: {m['status']}" for m in r["members"]))
    except Exception as e:
        await u.message.reply_text(f"⚠️ {e}\nUsage: /family new <name> · /family join <CODE> <name>")


async def status(u: Update, c: ContextTypes.DEFAULT_TYPE):
    s = (c.args[0].lower() if c.args else "")
    if s not in ("onway", "reached", "cleared"):
        await u.message.reply_text("Usage: /status onway | reached | cleared")
        return
    try:
        r = await call("POST", "/api/assignments/status", json={"chat_id": str(u.effective_chat.id), "status": s})
        await u.message.reply_text(f"✅ Hazard #{r['hazard_id']} status: {s}")
    except Exception as e:
        await u.message.reply_text(f"⚠️ {e}")


async def text(u: Update, c: ContextTypes.DEFAULT_TYPE):
    try:
        r = await call("POST", "/api/assistant", json={"question": u.message.text})
        await u.message.reply_text(r["answer"])
    except Exception as e:
        await u.message.reply_text(f"⚠️ {e}")


def main():
    if not config.TELEGRAM_BOT_TOKEN:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN in .env (get one from @BotFather).")
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).post_init(ready).build()
    app.add_handler(CommandHandler(["start", "menu"], start))
    app.add_handler(CommandHandler("id", my_id))
    app.add_handler(CommandHandler("subscribe", subscribe))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("route", route))
    app.add_handler(CommandHandler("safe", safe))
    app.add_handler(CommandHandler("needhelp", needhelp))
    app.add_handler(CommandHandler("family", family))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(MessageHandler(filters.PHOTO, photo))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, voice))
    app.add_handler(MessageHandler(filters.LOCATION, location))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text))
    try:
        httpx.get(API + "/api/stats", timeout=5)
    except httpx.HTTPError:
        print(f"WARNING: the Naqsha API is not reachable at {API}. Start the server first (START_NAQSHA.bat).")
    print("Naqsha bot starting. If Telegram is blocked on this network it keeps retrying until it can connect\n"
          "(turn on a VPN, or use another network). Then open Telegram and send /start to your bot.")
    logging.getLogger("telegram.ext").setLevel(logging.CRITICAL)  # no tracebacks while retrying
    app.add_error_handler(on_error)
    app.run_polling(bootstrap_retries=-1)


async def ready(app: Application):
    """Runs once Telegram is reachable: show the command menu in Telegram's / list."""
    await app.bot.set_my_commands([
        BotCommand("start", "What this bot does"), BotCommand("route", "Is the road safe? /route Islamabad to Gilgit"),
        BotCommand("subscribe", "Alerts for hazards near you"), BotCommand("help", "Nearest hospital, police, shelter"),
        BotCommand("safe", "Tell your family you are safe"), BotCommand("needhelp", "Ask for help"),
        BotCommand("family", "Family safety circle"), BotCommand("id", "Your chat id (for response teams)"),
        BotCommand("status", "Responders: onway | reached | cleared")])
    print(f"Connected to Telegram as @{app.bot.username}. Open Telegram and send /start", flush=True)


async def on_error(u: object, c: ContextTypes.DEFAULT_TYPE):
    logging.warning("Telegram error: %s", c.error)


if __name__ == "__main__":
    main()
