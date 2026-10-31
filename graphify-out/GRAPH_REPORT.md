# Graph Report - naqsha-ai  (2026-10-31)

## Corpus Check
- 19 files · ~19,571 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 6 file(s) not represented in the graph (top: (none) 3, .example 1, .bat 1)

## Summary
- 305 nodes · 719 edges · 10 communities (8 shown, 2 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 21 edges (avg confidence: 0.86)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- main.py
- geo.py
- app.js
- hazards.py
- llm.py
- bot.py
- 🗺 Naqsha AI — نقشہ
- documents.py
- Hub
- SKILL.md

## God Nodes (most connected - your core abstractions)
1. `get()` - 29 edges
2. `main()` - 18 edges
3. `create_report()` - 17 edges
4. `🗺 Naqsha AI — نقشہ` - 17 edges
5. `now()` - 15 edges
6. `check()` - 15 edges
7. `query()` - 14 edges
8. `_err()` - 14 edges
9. `ask()` - 13 edges
10. `insert()` - 11 edges

## Surprising Connections (you probably didn't know these)
- `🕸 Codebase knowledge graph (Graphify)` --references--> `create_report()`  [INFERRED]
  README.md → backend/hazards.py
- `🕸 Codebase knowledge graph (Graphify)` --references--> `check()`  [INFERRED]
  README.md → backend/routes.py
- `🕸 Codebase knowledge graph (Graphify)` --references--> `ask()`  [INFERRED]
  README.md → backend/ask_map.py
- `set_settings()` --calls--> `set_provider()`  [EXTRACTED]
  backend/main.py → backend/llm.py
- `_distance()` --calls--> `insert()`  [EXTRACTED]
  backend/ask_map.py → backend/db.py

## Import Cycles
- None detected.

## Communities (10 total, 2 thin omitted)

### Community 0 - "main.py"
Cohesion: 0.07
Nodes (57): execute(), insert(), now(), one(), query(), update(), active(), get() (+49 more)

### Community 1 - "geo.py"
Cohesion: 0.07
Nodes (29): _category(), distance_to_line(), exposure(), geocode(), help_along_route(), nearby_help(), overpass(), rain() (+21 more)

### Community 2 - "app.js"
Cohesion: 0.07
Nodes (45): acAttach(), api(), BASES, beep(), COLORS, connectWS(), debounce(), dz (+37 more)

### Community 3 - "hazards.py"
Cohesion: 0.16
Nodes (8): haversine_m(), analyze(), create_report(), exif_gps(), notify_people(), _save(), telegram(), score()

### Community 4 - "llm.py"
Cohesion: 0.16
Nodes (10): _cfg(), chat(), chat_json(), _explain(), _local_whisper(), models(), parse_json(), provider() (+2 more)

### Community 5 - "bot.py"
Cohesion: 0.22
Nodes (18): call(), family(), help_cmd(), location(), main(), my_id(), name_of(), needhelp() (+10 more)

### Community 6 - "🗺 Naqsha AI — نقشہ"
Cohesion: 0.08
Nodes (25): 1. Ask the Map, 2. Report a hazard (dashboard Report tab, phone page `/report`, or Telegram), 3. Route safety check, 4. Hazard card (click any pin), 5. Ops, assistant and documents, Architecture, Data & credits, 🧪 Demo data (+17 more)

### Community 8 - "documents.py"
Cohesion: 0.12
Nodes (10): ask(), _distance(), _fallback_query(), _row(), _badge(), card(), _emergency_table(), letter() (+2 more)

## Knowledge Gaps
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `🗺 Naqsha AI — نقشہ` connect `🗺 Naqsha AI — نقشہ` to `documents.py`?**
  _High betweenness centrality (0.128) - this node is a cross-community bridge._
- **Are the 15 inferred relationships involving `main()` (e.g. with `family()` and `help_cmd()`) actually correct?**
  _`main()` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Should `main.py` be split into smaller, more focused modules?**
  _Cohesion score 0.07323943661971831 - nodes in this community are weakly interconnected._
- **Why does `🕸 Codebase knowledge graph (Graphify)` connect `documents.py` to `geo.py`, `hazards.py`, `🗺 Naqsha AI — نقشہ`?**
  _High betweenness centrality (0.127) - this node is a cross-community bridge._
- **Should `geo.py` be split into smaller, more focused modules?**
  _Cohesion score 0.06883116883116883 - nodes in this community are weakly interconnected._
- **Why does `create_report()` connect `hazards.py` to `main.py`, `geo.py`, `llm.py`, `documents.py`?**
  _High betweenness centrality (0.068) - this node is a cross-community bridge._
- **Should `app.js` be split into smaller, more focused modules?**
  _Cohesion score 0.0693815987933635 - nodes in this community are weakly interconnected._