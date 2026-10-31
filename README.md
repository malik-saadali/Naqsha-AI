# 🗺 Naqsha AI — نقشہ

**An open-weight AI command center for landslides, floods and road safety in northern Pakistan.**

Ask any map question in Urdu or English, report a hazard with a photo and voice note, check if your road is safe, and coordinate rescue. Every AI component runs on **open-weight models** (gpt-oss, Qwen, Whisper), hosted on Groq or fully offline with Ollama.

Built at **Hacktoberfest Islamabad 2026** (NIC H-9/1).

---

## ⚡ Quick start (Windows, 2 minutes)

1. Install **Python 3.10+** from python.org (tick **Add to PATH**).
2. Double-click **`START_NAQSHA.bat`**. It installs packages, starts the server and opens **http://localhost:8000**.
   If `.env` is missing it opens Notepad so you can paste your keys (see [Keys](#keys)).
3. *(Optional, recommended)* Load the demo data in a second window while the server is running:
   ```bash
   python demo/seed_demo.py --reset
   ```
   This takes 5–8 minutes because every demo hazard goes through the real AI pipeline.
4. Open the dashboard and follow the [Demo script](#-demo-script-5-minutes).

To stop: close the black server window (or press `Ctrl+C` in it).

### Keys

`.env` (never commit it; it is in `.gitignore`):

| Setting | What it is |
|---|---|
| `GROQ_API_KEY` | Free key from https://console.groq.com |
| `TELEGRAM_BOT_TOKEN` | From @BotFather in Telegram |
| `GROQ_TEXT_MODEL` | `openai/gpt-oss-120b` (text, JSON, Urdu) |
| `GROQ_VISION_MODEL` | `qwen/qwen3.8-27b` (photo analysis) |
| `GROQ_WHISPER_MODEL` | `whisper-large-v3` (voice notes) |
| `PUBLIC_URL` | Link used inside Telegram messages. Keep `http://localhost:8000` locally; set it to your tunnel URL for phones |

Groq retires models from time to time. If you see `model ... does not exist`, open https://console.groq.com/docs/models, pick a current text model and a current vision model, and put their names in `.env`. Then restart the server.

### ⚠️ Network note: VPN, Groq and Telegram

On some Pakistani networks **Telegram is blocked**, and **Groq refuses some VPN servers** ("Access denied. Please check your network settings").

| Connection | Dashboard + AI (Groq) | Telegram bot |
|---|---|---|
| Normal internet, no VPN | ✅ works | ❌ blocked on this network |
| Free Proton VPN, most servers (e.g. RO-FREE#28, NL-FREE#147) | ❌ Groq says "Access denied" | ✅ works |
| Free Proton VPN, **NL-FREE#160** (tested 31 Oct 2026) | ✅ works | ✅ works |

**Simple rule:**
1. Connect Proton VPN. If the dashboard shows *"Groq refused this connection … turn the VPN off"*, click **Change server** in Proton until AI answers work (the bot keeps running).
2. If no server works for both: **dashboard → VPN off**, **Telegram → VPN on**. The bot waits and reconnects by itself when the VPN comes back; the dashboard works again as soon as the VPN is off.
3. Best: a network where Telegram is not blocked (e.g. a mobile-data hotspot) with no VPN. Then everything works at once.

With the bot on and the AI blocked, commands that do not need AI (`/start`, `/id`, `/subscribe`, `/safe`, `/family`, `/status`) still work.

## 🏆 Hackathon judging criteria — how Naqsha meets them

| Criterion | What to show |
|---|---|
| **Technology** | Multimodal AI pipeline: Whisper (voice) → vision model with a 9-point engineering-geology checklist → rain + slope + exposure enrichment → transparent 0–100 risk score. Self-healing natural-language → Overpass query loop. Live WebSocket dashboard + Telegram bot sharing one FastAPI backend. One switch moves every AI call between Groq and fully offline Ollama. |
| **Design** | Google-Maps-style UI: search with autocomplete, satellite/hybrid, terrain, right-click "what's here", my location, rain radar, turn-by-turn directions, phone layout. Urdu, Roman Urdu and English everywhere, Urdu text-to-speech, bilingual alerts and letters. |
| **Completion** | Every module works end to end (see *Tested* below): Ask Map, report → risk → alert, route safety, response teams, family circle, assistant, situation report, KML/GeoJSON export, Telegram bot. Demo data loads with one command. |
| **Learning** | New for us: Overpass QL, OSRM routing, Open-Meteo slope from elevation, multimodal LLM prompting with a domain checklist, Whisper for Urdu, WebSockets, Telegram Bot API, Leaflet, and running open-weight models locally with Ollama. |

**Challenges entered:** Best Open Source AI Project (MIT licence, open-weight models only, all open data).

---

## The problem

Every monsoon, landslides and floods block the Karakoram Highway, Swat, Naran and Murree roads. Travelers drive into danger without knowing the road is closed, locals see cracks in slopes but don't know who to tell, and rescue teams lack one shared picture. Existing tools are English-only and need constant internet, which is exactly what disappears in a disaster.

## What Naqsha does

| For | Feature |
|---|---|
| 🚗 Travelers | **Route safety check**: verdict (safe / caution / avoid), hazards within 500 m of the road with km markers, rain along the route, **automatic safer alternate route**, hospitals / police / fuel along the way, printable **offline emergency card** |
| 🏘 Residents | **Report a hazard** by photo + voice note (dashboard, phone page or Telegram). **Alerts** for hazards near you. **Family safety circle** ("Are you safe?" → ✅ / 🆘). Formal **complaint letter** to NHA / Deputy Commissioner in English or Urdu |
| 🚑 Responders | **Priority queue** by risk score, **assign teams** (task arrives on Telegram with map link), teams reply `/status onway / reached / cleared`, the pin disappears live |
| 🏛 Authorities | Live **command dashboard**, **situation report PDF** with AI briefing in Urdu + English, **KML / GeoJSON export** for GIS teams |
| 🗺 Everyone | **Ask the Map** in plain Urdu or English → AI writes an OpenStreetMap (Overpass) query, runs it, **fixes its own query if it fails**, and draws the result. Also answers **distance** questions ("Islamabad se Murree kitna door hai?") with road and straight-line distance |

### 🗺 The map (Google-Maps style)

| Feature | How to use it |
|---|---|
| **Map types** | Bottom-left switcher: **Map** (Esri streets), **Satellite** (Esri World Imagery + road and place labels, like Google's hybrid view), **Terrain**, **Dark**, **OSM** |
| **Search** | Search box on the map (or press `/`): type any place, shop, mosque, hospital or town in Pakistan; suggestions appear as you type; ↑ ↓ Enter work |
| **Place card** | Picking a result flies there and opens a card: address, coordinates, temperature, rain for 3 days, elevation, and buttons for **Directions**, **From here**, **Nearby help**, **Report here**, **Google Maps** |
| **What's here?** | **Right-click** anywhere: dropped pin with address, weather, copyable coordinates and the same actions |
| **My location** | ◎ button: blue dot with accuracy circle (like Google Maps) |
| **Nearby help** | Hospitals, clinics, police, fire stations and shelters within 8 km, with distance, phone and a Navigate link |
| **Measure** | Ruler button: click points to measure a distance, **Done** or `Esc` to finish |
| **Rain radar** | Top-right toggle: live precipitation radar (RainViewer) over the map |
| **Share** | Share button copies a link; the view (centre, zoom, map type) is in the URL, so the link opens the same view |
| **Full screen**, smooth zoom (mouse wheel, quarter-steps), scale bar, live coordinates under the mouse | |
| **Turn-by-turn directions** | Route tab: autocomplete for both fields, swap ⇅, start from my location, step list (click a step to zoom there), **Navigate** opens Google Maps navigation |

---

## How it works (what happens behind each button)

### 1. Ask the Map
1. The text model turns your question into JSON: places, OSM tags (e.g. `amenity=hospital`), relation (`near`, `between`, `within`, `distance`) and language.
2. Each place is found with **Nominatim** (OpenStreetMap geocoder, limited to Pakistan, 1 request/second).
3. **Distance questions**: OSRM gives the road route; the app draws it and reports road km, driving minutes and straight-line km.
4. **Search questions**: the model writes an **Overpass QL** query. The app runs it. If it fails or returns 0 results, the error is sent back to the model to fix the query (up to 3 tries). If that still fails, a built-in safe query runs, so the map always shows something.
5. The model writes a 2–3 sentence answer in your language (Urdu script if you asked in Urdu). The query log is shown under "AI query + self-healing log", and the result becomes a map layer you can hide or download as GeoJSON.

### 2. Report a hazard (dashboard Report tab, phone page `/report`, or Telegram)
1. **Location**: from the map click, GPS, or the photo's EXIF GPS.
2. **Voice note → text** with Whisper (Urdu, Pashto, English).
3. **Photo → vision model** with a 9-point **engineering-geology checklist** (tension cracks, fresh scarp, debris on road, toe erosion, seepage, tilted trees/poles, failed retaining walls, rockfall source, debris-flow marks). It returns hazard type, severity 1–5, confidence, visible indicators, "road blocked", recommended action, and summaries in English and Urdu. With no photo, the text is classified instead (confidence capped at 0.5).
4. **Enrichment, in parallel**: rain forecast for 72 h and elevation for slope (Open-Meteo), schools / health / mosques / bridges within 1 km (Overpass).
5. **Risk score** (below). A report within 200 m of an open hazard from the last 24 h is **merged** into it (report count +1).
6. Saved in SQLite, pushed **live** to every open dashboard (WebSocket: red toast + beep). If the risk is **high**, Telegram subscribers within 10 km and nearby family members get an alert automatically.

### 3. Route safety check
1. Both towns are geocoded; **OSRM** returns the fastest route plus alternatives.
2. Every active hazard within **500 m** of a route is listed with its km from the start.
3. Rain is checked at 5 points along the road.
4. Verdict: **avoid** if any hazard is high risk or blocks the road; **caution** for medium hazards or ≥ 40 mm rain; otherwise **safe**.
5. If the main route is "avoid", the fastest alternative that is not "avoid" is drawn as a dashed line.
6. Hospitals, police and fuel within 2.5 km of the road are added; the model writes the advisory in English and Urdu. **🧳 Emergency card** opens a printable page.

### 4. Hazard card (click any pin)
Risk breakdown bar, slope, rain chart, exposure counts, geology evidence, voice note player, status dropdown, **Assign team**, **◎ Exposure map** (facilities within 1 km), **📢 Alert** (SMS/WhatsApp text in English + Urdu), **✉ Letter to NHA** / **✉ Urdu letter to the DC**, **📲 Notify nearby**, **💬 Safety advice**.

### 5. Ops, assistant and documents
- **Ops tab**: add response teams (with their Telegram chat id from `/id`), live activity feed, **📄 Situation report** (AI briefing + tables; use "Save as PDF").
- **Assignment**: the team gets the task on Telegram with a Google Maps link; `/status cleared` resolves the hazard and frees the team.
- **Assistant tab**: safety Q&A in Urdu, Roman Urdu or English. It uses the selected hazard as context and always includes the emergency numbers.
- **Header switch**: flips every AI call between Groq and Ollama (offline).

### Transparent risk score (0–100)

| Factor | Points |
|---|---|
| Severity from the vision model | severity × 8 (max 40) |
| Rain next 72 h (Open-Meteo) | >50 mm = 25 · 20–50 = 15 · <20 = 5 |
| Slope from elevation (Open-Meteo) | >35° = 20 · 25–35° = 12 · 15–25° = 6 · <15° = 2 |
| Schools / health facilities / bridges within 1 km (OpenStreetMap) | 3 per school or health facility + 1 per bridge (max 15) |

**70+ = 🔴 high** (auto-alerts subscribers and families nearby) · 40–69 = 🟠 medium · <40 = 🟢 low.
In dry weather most reports score medium; use **📲 Notify nearby** on the card to alert people manually.

Slope is computed the easy way: elevation at the point and 100 m north, east, south and west; slope = atan(biggest height difference ÷ 100 m).

---

## 🕸 Codebase knowledge graph (Graphify)

We used [Graphify](https://graphify.com) to turn the whole project (backend, frontend, bot, prompts, docs) into a knowledge graph, so judges and new contributors can see how the modules connect without reading every file.

**See it:** open **http://localhost:8000/graph** (or *Ops → Code knowledge graph* in the dashboard), or open `graphify-out/graph.html` in a browser. Click a node to see what it calls and what calls it; search any function.

**What it found** (`graphify-out/GRAPH_REPORT.md`): 305 nodes, 719 edges, 10 communities that match our modules (`main.py`, `geo.py`, `llm.py`, `bot.py`, `db.py`, `documents.py`, `app.js`), no import cycles. The most connected functions are `create_report()` (the hazard pipeline), `check()` (route safety), `ask()` (Ask the Map) and the database helpers.

**Rebuild it** after changing code (no LLM or API key needed; it parses the code with tree-sitter):
```bash
pip install graphifyy
graphify update .
```
`.graphifyignore` keeps the bundled Leaflet library and demo media out of the graph. Useful queries:
```bash
graphify god-nodes
graphify explain "create_report"
graphify path "api_report" "create_report"
```

## Architecture

```
 Phone page (/report) ─┐                         ┌── Groq / Ollama  (gpt-oss, Qwen, Whisper)
 Telegram bot ─────────┼──► FastAPI backend ─────┼── OpenStreetMap: Nominatim (places), Overpass (features)
 Dashboard (/) ◄─ WS ──┘   SQLite · WebSocket    ├── OSRM (routing + alternates)
                                                 └── Open-Meteo (rain forecast + elevation)
```

```
backend/
  main.py        API routes, WebSocket, printable pages
  llm.py         Groq ⇄ Ollama switch: chat, JSON, vision, Whisper
  prompts.py     all prompts, incl. the geology checklist
  ask_map.py     natural language → Overpass → self-healing loop; distance questions
  hazards.py     reports, enrichment, duplicate merge, alerts
  routes.py      route safety check + alternate route
  geo.py         geocoding, Overpass, OSRM, rain, slope, exposure, geometry
  risk.py        risk score
  documents.py   situation report, complaint letter, emergency card
  live.py        WebSocket hub + Telegram push
  db.py          SQLite (data/naqsha.db)
frontend/        dashboard (Leaflet), phone report page with offline queue
bot.py           Telegram bot (talks to the API on localhost:8000)
demo/            demo photos, voice notes and seed_demo.py
```

## Run it by hand (any OS)

```bash
pip install -r requirements.txt
cp .env.example .env      # then put your keys in .env
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```
Open http://localhost:8000. Telegram bot, in a second terminal: `python bot.py`.

**Fully offline AI**: `ollama pull qwen3:8b`, `ollama pull qwen3-vl:8b`, `pip install faster-whisper`, then set `LLM_PROVIDER=ollama` (or use the header switch). Map data services still need internet. Needs a decent GPU to be fast.

**Phones**: camera, mic and GPS need HTTPS. Run `cloudflared tunnel --url http://localhost:8000`, put the printed URL in `PUBLIC_URL`, and open `<that URL>/report` on a phone.

## Telegram commands

| Command | What it does |
|---|---|
| photo → voice note → 📍 location | Full AI hazard report |
| `/subscribe` | Alerts for high-risk hazards within 10 km |
| `/route Islamabad to Gilgit` | Route safety verdict, hazards, alternate route, emergency card link |
| `/safe` · `/needhelp` | Safety check-in; family is notified |
| `/family new <name>` · `/family join <CODE> <name>` · `/family` | Family safety circle |
| `/help` | Nearest hospital, police, shelter |
| `/id` | Chat id (to register a response team) |
| `/status onway \| reached \| cleared` | Responder updates |
| any text | Safety assistant |

---

## 🧪 Demo data

`python demo/seed_demo.py --reset` wipes the database and loads:

| # | Where | Input |
|---|---|---|
| 1 | KKH near **Besham** | `01_landslide_truck_blocked.jpg` + English voice note |
| 2 | KKH near **Dasu** | `02_landslide_wet_road.jpg` + Roman Urdu text |
| 3 | KKH at **Pattan** | `03_landslide_fallen_pole.jpg` |
| 4 | **Murree** road, Jhika Gali | `04_rocks_mud_curved_road.jpg` |
| 5 | **Kaghan** valley road | `05_mudslide_rural_road.jpg` |
| 6 | **Mingora**, Swat | `06_flooded_street.jpg` + English voice note |
| 7 | **Nowshera** | `07_flooded_houses.jpg` |
| 8 | **Balakot** | Roman Urdu text only (no photo) |

Plus 4 response teams, 1 subscriber near Besham, a family circle (Ali, Sara) and two check-ins.
`demo/photos/08_clear_mountain_road.jpg` is not loaded. Upload it yourself to see a "no hazard" result.
Photos are from Unsplash (free licence); voice notes were made with Windows text-to-speech.

## 🎬 Demo script (5 minutes)

1. **Ask Map** → click the chips: *Hospitals between Besham and Chilas*, *ایبٹ آباد میں پیٹرول پمپ* (answer comes in Urdu), *Islamabad se Murree kitna door hai?* (distance + route). Open "AI query + self-healing log" to show the model fixing its own query.
2. **Hazards** tab → the priority queue; click the top hazard → card with photo, risk breakdown, geology evidence, voice note.
3. On the card: **📢 Alert** (English + Urdu SMS), **✉ اردو درخواست DC** (Urdu letter), **◎ Exposure map**.
4. **Route** → *Islamabad → Gilgit* → 🔴 AVOID: the road goes via Balakot and Kaghan (N-15), where the demo has a road subsidence at km 159 and a debris flow blocking the road at km 218. Also try *Abbottabad → Besham* (🔴 AVOID, rockfall at km 136) and *Islamabad → Murree* (🟢 SAFE). Show the directions list, **🧳 Emergency card** and **Navigate**.
5. **Report** tab → drop `demo/photos/08_clear_mountain_road.jpg` (or any photo) on the box, click **Click on map**, click a road, **Submit**. The pin appears live with a toast and the card opens.
6. **Map tricks**: search *Faisal Mosque* → **Satellite** → right-click nearby → **Nearby help**; turn on **Rain radar**; **Share** the view.
7. **Ops** → assign **Rescue 1122 Shangla** to the Besham hazard → status "Action taken". **📄 Situation report** → Save as PDF.
8. **Assistant** → *Seelab aaye to kya karein?*
9. **Telegram**: open **@naqsha_hacktoberfest_bot**, send `/start`, then `/route Islamabad to Gilgit`, then a photo + 📍 location.
10. Phone: open `/report` (same Wi-Fi: `http://<laptop-ip>:8000/report`; camera/GPS need the HTTPS tunnel).

## ✅ Tested on 31 Oct 2026

Run against the live server with Groq; all passed:

- **API**: Ask Map (English, Urdu, Roman Urdu; between / near / within / distance; self-healing retry) · report with photo + voice (Whisper + vision + rain + slope + exposure + risk) · text-only report · report without location (clear error) · route check (Islamabad→Gilgit, Abbottabad→Besham, Islamabad→Murree) with turn-by-turn directions · emergency card · nearby help · exposure · bilingual alert · subscribe · family new / join / view · safe / help check-ins · add team · assign · team status onway / cleared · hazard status change · assistant (English + Urdu) · transcribe · situation report · NHA letter (English) and DC letter (Urdu) · GeoJSON + KML export · provider switch · place search · reverse geocode · weather.
- **Dashboard (browser)**: all 6 tabs · Ask Map chips · Report tab end to end · Route with directions · hazard card and all its buttons · search with autocomplete · Map / Satellite / Terrain / Dark / OSM · right-click "what's here" · nearby help · live WebSocket updates · phone layout (375 px) · phone report page.
- **Telegram**: token valid, bot connects as @naqsha_hacktoberfest_bot through the VPN, command menu registered. Commands sent from a real phone were not tested (that needs your Telegram account).
- **Not exercised**: duplicate-report merge (needs two reports within 200 m) and the green alternate route (OSRM offered no alternatives for the demo routes). "Help along the route" depends on Overpass load and may show "servers busy".

## Troubleshooting

| Problem | Fix |
|---|---|
| `LLM error 404 ... model does not exist` | Groq retired the model. Put a current model name in `.env` (see [Keys](#keys)) and restart. |
| *Groq refused this connection (Access denied) … turn the VPN off* | Your VPN server is blocked by Groq. Click **Change server** in Proton, or turn the VPN off (see [Network note](#️-network-note-vpn-groq-and-telegram)). |
| Bot window says "keeps retrying" and nothing else | Telegram is blocked on this network. Turn the VPN on; the bot connects by itself and prints *Connected to Telegram as @…* |
| Map tiles grey for a moment | Tiles are still downloading; zoom changes load new ones. Try another map type if one is slow. |
| Ask Map / Route is slow (30–90 s) | The free OpenStreetMap servers (Overpass, Nominatim, OSRM) are busy. Wait; the app retries and falls back automatically. |
| Port 8000 already in use | Another copy is running. Close it, or open http://localhost:8000. |
| Microphone / GPS does not work on a phone | Phones only allow them on HTTPS. Use the cloudflared tunnel. |

## Data & credits

OpenStreetMap contributors (ODbL) via Nominatim, Overpass and Photon · OSRM · Open-Meteo · Esri basemaps and World Imagery · RainViewer · Leaflet · Material Symbols · demo photos from Unsplash.
Emergency numbers: Rescue 1122 · Edhi 115 · Police 15 · Motorway Police 130 · NDMA 051-111-157-157.

## Roadmap

SMS reporting for feature phones · WhatsApp channel · Sentinel-2 before/after imagery · InSAR slow-slope detection · NASA Global Landslide Catalog history layer · fine-tuned small vision model on Pakistani slope-failure photos · Pashto voice output.

## License

MIT — see [LICENSE](LICENSE).
