# Roadmap

## M0: research and design (in progress)
- Research: [tools](research/tools.md), [pain points](research/pain-points.md), [legal](research/legal.md), [geolocation](research/geolocation.md)
- [Practitioner interview](research/practitioner-interview.md)
- [Design brief](design-brief.md): 4 concepts → pick one → full prototype

## M1: search engine (CLI, no UI)
- `uv`-managed Python 3.12 package. `tessera search <seed>` returns JSON findings.
- One module per source, `tessera/sources/<name>.py`, exposing `async def search(seed) -> list[Finding]`. The registry is a plain list.
- Sources: Maigret, WhatsMyName data, user-scanner, python-phonenumbers.
- Same-person scoring: hand-set Fellegi-Sunter-style weights over rapidfuzz/jellyfish/nicknames comparisons. Every score explains itself. Splink once labelled data exists.
- Evidence capture: Playwright snapshot → SHA-256 → per-case SQLite under `~/Tessera/cases/<id>/`. The audit log lives in the same DB.
- Case purpose attestation required before the first search.

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
