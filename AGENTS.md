# AGENTS.md: Hunt (local-first investigation software)

Hunt finds a person's public accounts and records from a name/username/email/phone, shows which belong to them and why, and writes a report where every sentence cites evidence. Local-first: cases, evidence and the vision AI stay on the Mac. macOS (Apple Silicon), Python 3.12, uv. Read README.md ("Guardrails") and SECURITY.md before changing what it collects.

## Commands
- Setup: `uv sync`. **`uv run hunt setup` downloads a browser (~0.2 GB) and a 3.3 GB vision model and needs Ollama: it asks first, never run it unattended.**
- Run: `uv run hunt` (entry point `hunt.cli:main`).
- Check: `scripts/check.sh` runs every offline `test_*.py` like CI does and prints pass/fail per file. One file: `scripts/check.sh test_app.py`. Model-backed checks (`test_scan.py test_photo.py test_geo.py test_vlm.py test_clues.py`) need CLIP/GeoCLIP weights: run them by name, locally only.
- Source health: `uv run python sourcecheck.py`; other tools are in `scripts/` (eval_*, train_*, validate_wmn).

## Layout
`hunt/` package (`api2/` is the HTTP/app layer) · `docs/` (user guide, for-counsel, research) · `extension/` browser extension · `fixtures/` demo case and test data · `packaging/` macOS build · about 90 `test_*.py` at the repo root (each a standalone plain-assert script).

## Traps
- CI (`.github/workflows/checks.yml`) runs on every push and PR on macos-14: pushing to GitHub spends runner minutes. Check with `scripts/check.sh` first.
- The checks use macOS `sips` and the Trash: they don't run on Linux.
- Optional API keys (GitHub, Gravatar, OpenFEC, CourtListener) are entered in the app, not read from env. No `.env` files; never add keys to the repo.
- `.venv` is 1.4 GB: search with `rg`, not `grep -r`. Don't read case data or fixtures that look like real people.
- Real cases, evidence and subjects' data never go in git, issues, logs or messages.

## Off-limits
Don't weaken the guardrails (consent, citation, local-only evidence). Don't add collection of private (non-public) data.
