# Roadmap

## M0: research and design (in progress)
- Research: [tools](research/tools.md), [pain points](research/pain-points.md), [legal](research/legal.md), [geolocation](research/geolocation.md)
- [Practitioner interview](research/practitioner-interview.md)
- [Design brief](design-brief.md): 4 concepts → pick one → full prototype

## M1: search engine (CLI, no UI) ✅
- `hunt search SEED... --case NAME --purpose TEXT`. A new case can't start without a purpose.
- Sources (`hunt/sources/`):
  - Maigret: top 500 sites, with profile parsing
  - WhatsMyName: about 690 sites
  - user-scanner: email registrations, passive modules only
  - libphonenumber: offline
- Scoring (`hunt/match.py`): hand-set Fellegi-Sunter-style weights with ICD 203 verdicts, and a reason behind every point. It also handles nicknames, Gravatar email hashes, linked accounts, and display names that just repeat the username.
- Evidence: raw page source plus a Playwright screenshot and rendered HTML of likely matches, all SHA-256-named, with the audit log in per-case SQLite.
- Live test: username + name + location seeds take about 40 s, with about 1,200 site checks across both engines.

**M1 hardening (done)**
- ✅ **Username rarity** comes from the measured hit rate across sites. `nasa` is taken on 469 of 788 sites, so it's common.
- ✅ **Two-identifier rule:** a handle alone can't lift a profile above "roughly even chance". This stops a namesake who holds the same rare handle from rating as "likely".
- ✅ **Name matching** has graded tiers (similar / part of). A shared word that is just the handle counts for nothing, so "Nasa Nguyen" isn't evidence for NASA.
- ✅ **Locations** are geocoded (`hunt/geo.py`, Nominatim, cached) and compared by distance tier. Placeholders like "Unknown" and "Earth" are dropped first: there is a real village called Unknown in India.
- ✅ **Proxy routing** (`--proxy` / `HUNT_PROXY`) covers every network call.
- ✅ **Self-check** covers the case store end to end (purpose gate, evidence hashes, engine merging, pivots).
- ✅ **Email checks audited.** All 220 user-scanner modules have been read and classified (`NOTIFIES` / `AUDITED_SILENT` in `hunt/sources/user_scanner.py`, one reason per module):
  - 51 flagged loud upstream
  - 42 more never run: password login attempts, sign-ups that only a captcha stops, reset and recovery flows
  - 127 audited silent

  `uv run python -m hunt.sources.user_scanner` re-checks coverage after an upgrade, and the silent list is only trusted for the audited release. The proxy also now reaches the 172 modules that open their own connections.
- ✅ **WhatsMyName validated** against each site's known account and a nonsense handle (`scripts/validate_wmn.py`). Redirects are now handled the way WMN's own checker does:
  - known accounts found: 424 → 447
  - both checks right: 335 → 348
  - false "found" on nonsense: 0
- ✅ **Geocoding hardened:**
  - US state codes and metro nicknames ("AZ" was Azerbaijan)
  - falls back to the part after the last comma
  - a joke-location stoplist
  - a street or shop hit only counts if the string has a number
  - ambiguous names ("Washington", "Portland") keep only the country; "Georgia" stays unplaced

**Still open**
- Recognise acronyms, so "NASA" matches "National Aeronautics and Space Administration".
- Five email modules (Facebook, Amazon, Patreon, Vedantu, HackTheBox) are off only because a notification couldn't be ruled out. Testing each against an account the investigator owns could bring them back.
- About 100 WhatsMyName sites block automated checks (Cloudflare etc.), and some entries are stale (Mastodon titles, Fiverr status codes). Report those fixes upstream to WMN.

## M2: app UI
- Local FastAPI server, results streamed live; frontend built from the chosen design prototype.

## M3: photo geolocation (ON HOLD: shown as "coming soon" in the app)
Paused 2026-10-29 to focus on people search and media scanning. What exists works and is tested; measured on the Commons benchmark:
- GeoCLIP alone: 27% within 25 km, median 582 km (75 photos).
- Densest-spot rule, no text and no vision model: 41% within 25 km, median 221 km (75 photos).
- Full fusion with the vision model's town refinement: 53% within 25 km, median 5 km (47 photos, offline replay).
- `--verify`: an opt-in OpenStreetMap lookup of the photo's text.
- When it resumes: environment clues (vegetation, soil, sun) and local geolocation models; a survey and a bigger benchmark were in progress on side branches.
- ✅ `hunt photo IMAGE... --case NAME`, entirely on-device. Steps:
  - SHA-256 + dHash
  - EXIF (device, time, camera GPS)
  - Apple Vision OCR with automatic language detection
  - GeoCLIP top-50, clustered and labelled offline (GeoNames)
  - fused, ranked hypotheses, each with a radius and reasons

  Images are stored as hashed evidence, and every analysis is audited.
- ✅ Clue knowledge (`hunt/clues.py`, [research](research/geoguessr-meta.md)): what GeoGuessr pros and OSINT geolocators use that still holds in an ordinary photo.
  - Included: script, rare letters, domains, phone codes, currency signs, postcodes, mph, driving side.
  - Excluded: Street-View-only "meta" (the camera, the car, blur, coverage).
- ✅ Profile-photo linking. The top candidates' avatars are fetched and hashed. A profile sharing its picture with a likely match, or with a photo supplied in the case, gains an independent identifier. Default avatars are recognised by URL and skipped.
- Local vision model (Qwen3-VL via Ollama) for clues and reranking, plus a benchmark on geotagged Commons photos (`scripts/eval_geo.py`).
- Later: investigator-triggered verification (Overpass, Mapillary, sun position), and GeoRanker for NVIDIA. See [geolocation.md](research/geolocation.md).

**Known limits**
- Profile-photo linking catches the same picture re-posted, not the same face or logo cropped differently. NASA's logo on six sites lands 15–40 bits apart. Next step: CLIP embeddings, validated on labelled pairs.
- OCR is macOS-only for now. Elsewhere the vision model reads the signs.

## M4: records and reports
- OpenFEC, SEC EDGAR, CourtListener, Wayback CDX, plus YouTube, Bluesky, Mastodon and GitHub APIs.
- Report builder: BLUF drafted by a local LLM with enforced citations, ICD 203 language, hash manifest, PDF via Playwright, FCRA mode.

## M5: ship
- One-command install (`uvx hunt`).
- Landing page with a fictional-data demo on GitHub Pages.
- Transfer the repo to Laura.
