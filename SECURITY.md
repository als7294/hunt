# Security

Hunt runs entirely on the investigator's own computer. This page says what it defends against, what it doesn't, and how to report a problem.

## What Hunt is

`hunt app` starts a local web server on `127.0.0.1` on a random port and opens the browser with a one-time sign-in link. Case data lives under `~/Hunt` (or `$HUNT_HOME`). Nothing is hosted anywhere else.

## Threat model

**Defended against**

- **Other websites in the same browser.** A page on any other site cannot read or change a case:
  - the sign-in link sets an `HttpOnly`, `SameSite=Strict` cookie bound to a per-launch token;
  - every non-GET request must carry a matching `Origin` and, for JSON, an `application/json` content type;
  - `Sec-Fetch-Site` must be `same-origin` or `none`;
  - there are no CORS headers;
  - the `Host` header must match exactly (against DNS rebinding).
- **Hostile evidence.** Saved pages, screenshots and downloads are untrusted data:
  - evidence filenames are their SHA-256 and are regex-checked before serving;
  - HTML, MHTML and SVG evidence is served as `text/plain` under a sandboxed CSP, so saved pages never execute;
  - the app's own CSP allows no inline or remote scripts, so nothing from a captured page can run in Hunt;
  - every string the app renders goes through an escaping template.
- **Path tricks.** Case slugs must round-trip through `slugify`; `..`, absolute paths and drive letters in uploads return 400; the server never serves files outside a case's `evidence/` folder.
- **The capture extension.** Its routes take a per-pairing key and only accept `Origin: chrome-extension://<paired id>`; the key opens no other route; pairing codes expire and lock after five wrong tries.
- **Tampering after the fact.** Every evidence file is named by its hash and re-hashed at startup and at export; the audit log records every action; the evidence bundle ships `SHA256SUMS` anyone can verify offline.

**Not defended against**

- A malicious program already running as the same user. It can read `~/Hunt` like any other file. Use FileVault and a locked account.
- Someone with the sign-in link while it is valid. Treat it like a password; it is single-use.
- The platforms themselves. Hunt only ever receives what a site serves to a logged-out visitor or to the investigator's own browser.

## What leaves the computer

- Searches send the seed (a username, email hash, name or phone) to each source, through `HUNT_PROXY` when set, with an honest `User-Agent` that names Hunt.
- Photos and videos are scanned locally (CLIP and a local vision model via Ollama). They leave the machine only when the investigator runs an outside search herself, and each such request is audited.
- Hunt never logs in to any platform, never uses or replays the investigator's cookies, and never contacts a subject.

## Reporting a problem

Open a private security advisory on the GitHub repository, or email the maintainer listed in `pyproject.toml`. Please include the version (`hunt --version`), what you did, and what you saw. There is no bounty programme; credit is given in the changelog if you want it.

## Keeping it this way

- `test_app.py` checks the wrong-Host, missing-cookie, cross-origin and cross-site cases return 403, that `..` in evidence paths is rejected, and that HTML evidence is served inert.
- `test_capture.py` checks the extension routes refuse the cookie, a wrong origin and a wrong key.
- `test_e2e.py` runs a whole case through the real routes offline.
- CI runs every self-check on each push (`.github/workflows/checks.yml`).
