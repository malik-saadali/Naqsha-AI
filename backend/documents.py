"""Module M: printable official documents (situation report, complaint letter, traveler emergency card).

They are HTML pages styled for printing; the browser's "Save as PDF" handles Urdu script perfectly.
"""
import html
import json
import time

from . import db, hazards, llm, prompts

EMERGENCY = [("Rescue", "1122"), ("Edhi", "115"), ("Police", "15"), ("Motorway Police", "130"),
             ("NDMA", "051-111-157-157")]

BASE = """<!doctype html><html><head><meta charset="utf-8"><title>{title}</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Nastaliq+Urdu&family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
<style>
body{{font-family:Inter,Arial,sans-serif;max-width:860px;margin:24px auto;padding:0 24px;color:#111}}
h1{{font-size:22px;margin:0}} h2{{font-size:16px;margin:22px 0 8px;border-bottom:2px solid #111;padding-bottom:4px}}
.meta{{color:#555;font-size:13px}} table{{width:100%;border-collapse:collapse;font-size:13px}}
td,th{{border:1px solid #ccc;padding:6px;text-align:left;vertical-align:top}} th{{background:#f2f2f2}}
.ur{{font-family:'Noto Nastaliq Urdu',serif;direction:rtl;text-align:right;line-height:2.2;font-size:15px}}
.badge{{display:inline-block;padding:2px 8px;border-radius:10px;color:#fff;font-weight:600;font-size:12px}}
.high{{background:#d62828}} .medium{{background:#f08c00}} .low{{background:#2b9348}}
pre{{white-space:pre-wrap;font-family:inherit;font-size:14px;line-height:1.6}}
.print{{position:fixed;top:12px;right:12px;padding:8px 14px;background:#111;color:#fff;border:0;border-radius:6px;cursor:pointer}}
@media print{{.print{{display:none}}}}
</style></head><body><button class="print" onclick="window.print()">Save as PDF</button>{body}</body></html>"""

e = html.escape


def _badge(level):
    return f'<span class="badge {e(level or "low")}">{e((level or "low").upper())}</span>'


def _emergency_table():
    return "<table><tr>" + "".join(f"<th>{e(n)}</th>" for n, _ in EMERGENCY) + "</tr><tr>" + \
        "".join(f"<td><b>{e(p)}</b></td>" for _, p in EMERGENCY) + "</tr></table>"


async def sitrep() -> str:
    hs = hazards.active()
    now = time.strftime("%d %b %Y, %H:%M")
    counts = {lvl: sum(1 for h in hs if h["risk_level"] == lvl) for lvl in ("high", "medium", "low")}
    exposed_schools = sum((h.get("exposure") or {}).get("counts", {}).get("schools", 0) for h in hs)
    exposed_health = sum((h.get("exposure") or {}).get("counts", {}).get("health", 0) for h in hs)
    safe = db.one("SELECT COUNT(*) n FROM checkins WHERE status='safe' AND created_at>?", (time.time() - 86400,))["n"]
    help_ = db.one("SELECT COUNT(*) n FROM checkins WHERE status='help' AND created_at>?", (time.time() - 86400,))["n"]
    facts = {"active_hazards": len(hs), "by_level": counts, "roads_blocked": sum(h["road_blocked"] or 0 for h in hs),
             "schools_exposed": exposed_schools, "health_facilities_exposed": exposed_health,
             "safe_checkins_24h": safe, "help_requests_24h": help_,
             "top": [{"type": h["hazard_type"], "risk": h["risk_score"], "lat": round(h["lat"], 3),
                      "lon": round(h["lon"], 3)} for h in hs[:5]]}
    try:
        brief = await llm.chat_json(prompts.BRIEFING.format(facts=json.dumps(facts)), "Write the briefing.")
    except Exception:
        brief = {"en": json.dumps(facts), "ur": ""}

    rows = "".join(
        f"<tr><td>#{h['id']}</td><td>{e(h['hazard_type'].replace('_', ' '))}</td><td>{h['severity']}/5</td>"
        f"<td>{_badge(h['risk_level'])} {h['risk_score']}</td><td>{'Yes' if h['road_blocked'] else 'No'}</td>"
        f"<td>{h['lat']:.4f}, {h['lon']:.4f}</td>"
        f"<td>{e(str((h.get('exposure') or {}).get('counts', '')))}</td>"
        f"<td>{h.get('rain_72h') if h.get('rain_72h') is not None else '-'} mm</td>"
        f"<td>{e(h.get('recommended_action') or '')}</td><td>{e(h['status'])}</td></tr>" for h in hs)
    teams = db.query("SELECT a.status, t.name, a.hazard_id FROM assignments a JOIN teams t ON t.id=a.team_id "
                     "ORDER BY a.updated_at DESC LIMIT 20")
    team_rows = "".join(f"<tr><td>#{t['hazard_id']}</td><td>{e(t['name'])}</td><td>{e(t['status'])}</td></tr>"
                        for t in teams) or "<tr><td colspan=3>No assignments yet</td></tr>"
    body = f"""<h1>Naqsha AI — Situation Report</h1><div class="meta">Generated {now} · open-weight AI · data: citizens, OpenStreetMap, Open-Meteo</div>
<h2>Briefing</h2><pre>{e(brief.get('en', ''))}</pre><div class="ur">{e(brief.get('ur', '')).replace(chr(10), '<br>')}</div>
<h2>Summary</h2><table><tr><th>Active hazards</th><th>High</th><th>Medium</th><th>Low</th><th>Roads blocked</th><th>Schools exposed</th><th>Health exposed</th><th>Safe check-ins (24h)</th><th>Help requests (24h)</th></tr>
<tr><td>{len(hs)}</td><td>{counts['high']}</td><td>{counts['medium']}</td><td>{counts['low']}</td><td>{facts['roads_blocked']}</td><td>{exposed_schools}</td><td>{exposed_health}</td><td>{safe}</td><td>{help_}</td></tr></table>
<h2>Hazards (highest risk first)</h2><table><tr><th>ID</th><th>Type</th><th>Severity</th><th>Risk</th><th>Road blocked</th><th>Location</th><th>Exposed within 1 km</th><th>Rain 72h</th><th>Recommended action</th><th>Status</th></tr>{rows}</table>
<h2>Responder assignments</h2><table><tr><th>Hazard</th><th>Team</th><th>Status</th></tr>{team_rows}</table>
<h2>Emergency numbers</h2>{_emergency_table()}"""
    return BASE.format(title="Situation Report", body=body)


async def letter(hid: int, authority: str = "National Highway Authority (NHA)", lang: str = "English") -> str:
    h = hazards.get(hid)
    if not h:
        return BASE.format(title="Not found", body="<p>Hazard not found.</p>")
    facts = {k: h.get(k) for k in ("hazard_type", "severity", "road_blocked", "risk_score", "summary_en",
                                   "evidence", "rain_72h", "slope_deg", "exposure", "lat", "lon", "report_count")}
    text = await llm.chat([{"role": "user", "content": prompts.LETTER.format(
        lang=lang, authority=authority, facts=json.dumps(facts, ensure_ascii=False))}], max_tokens=1200)
    cls = "ur" if lang.lower().startswith("urdu") else ""
    photo = f'<p><img src="{e(h["photo"])}" style="max-width:100%;max-height:340px"></p>' if h.get("photo") else ""
    body = f"""<h1>Application to {e(authority)}</h1><div class="meta">Hazard #{h['id']} · {h['lat']:.5f}, {h['lon']:.5f} · {_badge(h['risk_level'])} risk {h['risk_score']}/100</div>
<pre class="{cls}">{e(text)}</pre><h2>Attached evidence</h2>{photo}
<p>Map: https://www.openstreetmap.org/?mlat={h['lat']}&mlon={h['lon']}#map=16/{h['lat']}/{h['lon']}</p>"""
    return BASE.format(title="Complaint letter", body=body)


def card(result: dict) -> str:
    """Traveler emergency card from a route check result."""
    pr = result["primary"]
    alt = result.get("alternate")
    use = alt or pr
    hz = "".join(f"<tr><td>km {x['km_from_start']}</td><td>{e(x['type'].replace('_', ' '))}</td>"
                 f"<td>{_badge(x['risk_level'])} {x['risk_score']}</td><td>{'Blocked' if x['road_blocked'] else ''}</td></tr>"
                 for x in use["hazards"]) or "<tr><td colspan=4>No active hazards reported on this route</td></tr>"
    hp = "".join(f"<tr><td>km {f['properties'].get('km_along')}</td><td>{e(f['properties']['category'].split('=')[-1])}</td>"
                 f"<td>{e(f['properties']['name'])}</td><td>{e(f['properties'].get('phone') or '')}</td></tr>"
                 for f in result["help_points"]["features"][:40])
    body = f"""<h1>Traveler Emergency Card</h1>
<div class="meta">{e(result['origin']['name'])} → {e(result['destination']['name'])} · {use['distance_km']} km · ~{use['duration_h']} h · verdict {_badge({'avoid': 'high', 'caution': 'medium', 'safe': 'low'}[result['verdict']])} {e(result['verdict'].upper())}{' · using ALTERNATE route' if alt else ''}</div>
<h2>Advisory</h2><pre>{e(result['advice'].get('en', ''))}</pre><div class="ur">{e(result['advice'].get('ur', ''))}</div>
<h2>Emergency numbers</h2>{_emergency_table()}
<h2>Hazards on route</h2><table><tr><th>Where</th><th>Type</th><th>Risk</th><th></th></tr>{hz}</table>
<h2>Help along the route</h2><table><tr><th>Where</th><th>Type</th><th>Name</th><th>Phone</th></tr>{hp or '<tr><td colspan=4>None found in OpenStreetMap</td></tr>'}</table>
<p class="meta">Save this page as PDF on your phone before you lose signal.</p>"""
    return BASE.format(title="Emergency card", body=body)
