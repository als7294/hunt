# Roadmap

## M0: research and design (in progress)
- Research: [tools](research/tools.md), [pain points](research/pain-points.md), [legal](research/legal.md), [geolocation](research/geolocation.md)
- [Practitioner interview](research/practitioner-interview.md)
- [Design brief](design-brief.md): 4 concepts → pick one → full prototype

## M1: search engine (CLI, no UI) ✅
- `tessera search SEED... --case NAME --purpose TEXT`. A new case can't start without a purpose.
- Sources (`tessera/sources/`):
  - Maigret: top 500 sites, with profile parsing
  - WhatsMyName: about 690 sites
  - user-scanner: email registrations, passive modules only
  - libphonenumber: offline
- Scoring (`tessera/match.py`): hand-set Fellegi-Sunter-style weights with ICD 203 verdicts, and a reason behind every point. It also handles nicknames, Gravatar email hashes, linked accounts, and display names that just repeat the username.
- Evidence: raw page source plus a Playwright screenshot and rendered HTML of likely matches, all SHA-256-named, with the audit log in per-case SQLite.
- Live test: username + name + location seeds take about 40 s, with about 1,200 site checks across both engines.

**Follow-ups found while building M1**
- user-scanner email checks:
  - Upstream already skips 52 of the 220 modules because they notify the target (e.g. a password-reset email).
  - Tessera also skips 12 more whose code looks like a reset flow (Facebook, Dropbox, Walmart…), and others matched by the same broad source check.
  - Audit each one, and allowlist the ones that turn out to be silent.
- Username rarity uses a length heuristic. Replace it with the hit rate across sites: `nasa` is claimed on 243 of 509 sites, so it's common.
- Profile locations are compared word by word. Geocode them with Nominatim and compare distance instead.
- A single-word known name ("NASA") can't match a long display name. Adding the full name fixes it, but subset matching would be better.
- Route traffic through a proxy or VPN for OPSEC.

## M2: app UI
- Local FastAPI server, results streamed live; frontend built from the chosen design prototype.

## M3: photo geolocation
- EXIF → GeoCLIP + OCR + script ID → local VLM rerank (Ollama) → ranked hypotheses with radius → investigator-triggered verification (Overpass, Mapillary, sun position). See [geolocation.md](research/geolocation.md).

## M4: records and reports
- OpenFEC, SEC EDGAR, CourtListener, Wayback CDX, plus YouTube, Bluesky, Mastodon and GitHub APIs.
- Report builder: BLUF drafted by a local LLM with enforced citations, ICD 203 language, hash manifest, PDF via Playwright, FCRA mode.

## M5: ship
- One-command install (`uvx tessera`).
- Landing page with a fictional-data demo on GitHub Pages.
- Transfer the repo to Laura.
