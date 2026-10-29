# Hunt local API

`hunt app` serves the app and this API on `http://127.0.0.1:<random port>`. The browser
opens `/login?t=<token>`, which sets an HttpOnly, SameSite=Strict cookie and redirects to `/`.

## Security rules (enforced by middleware on every request)
- **Host:** must be exactly `127.0.0.1:<port>` or `localhost:<port>`. Anything else gets 403 (blocks DNS rebinding).
- **Cookie:** must carry the launch token (`hmac.compare_digest`), or the request gets 403.
- **Non-GET requests:**
  - `Origin` must be `http://127.0.0.1:<port>` (or the `localhost` form).
  - JSON bodies need `Content-Type: application/json`.
  - Uploads are `multipart/form-data` with the same Origin check.
- **`Sec-Fetch-Site`:** if present, must be `same-origin` or `none`.
- **CORS:** no CORS headers, ever. GET requests never change state.
- **Content-Security-Policy:**
  ```
  default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';
  img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self';
  object-src 'none'; base-uri 'none'; frame-ancestors 'none'
  ```
- **Evidence:** filenames must match `^[0-9a-f]{64}\.\w{2,5}$`. Every response is `nosniff`; `.html` and `.svg` evidence is served as `text/plain` with `CSP: sandbox`.

Errors are `{"error": "message"}` with a 4xx or 5xx status.

## Cases
| Method | Path | Body / response |
|---|---|---|
| GET | `/api/startup` | `{version, proxy: bool, checks: [{id, label, ok, detail}]}`. Check ids: `cases`, `evidence` (re-hash), `ai` (Ollama `/api/tags` lists `HUNT_VLM`; the model isn't loaded), `network`, `proxy`, `retention` (cases older than 90 days with no legal hold) |
| GET | `/api/cases` | `[{slug, label, kind, reference, tool, created, updated, headline}]`, newest first. `headline` reads like "9 flagged posts" or "Confirmed · report ready" |
| POST | `/api/cases` | `{label, seeds: [str], kind: "insurance"\|"background"\|"diligence"\|"journalism", reference?, purpose (required: who asked and why it's lawful), injury_date?: "YYYY-MM-DD", limits?: str, look_for: [category key or custom text], tool: "person"}` → `201 {slug}`. A label that's already taken gets a `-2` suffix; nothing is ever merged |
| GET | `/api/cases/{slug}` | `{slug, details: {label, kind, reference, purpose, injury_date, limits, look_for, tool, created}, seeds: [{kind, value}], steps: {search, identity, posts, report}` (each `"todo"`, `"running"` or `"done"`), `active_job: {id, kind} \| null, counts: {accounts, flagged, evidence}}` |
| POST | `/api/cases/{slug}/seeds` | `{seeds: [str]}` → `{seeds}` |
| GET | `/api/cases/{slug}/case.json` | The full `search.build()` dict (candidates, methodology, audit…) |

## Jobs and live progress
| Method | Path | Notes |
|---|---|---|
| POST | `/api/cases/{slug}/search` | `{capture?: true}` → `{job}`. Returns 409 if the case already has an active job |
| POST | `/api/cases/{slug}/scan` | `{check_everything?: false}` → `{job}`. Collects posts from accounts marked `him`, then scans them. Runs under the heavy lock |
| GET | `/api/jobs/{id}/events` | Server-sent events, each with an `id:`. Replays from `Last-Event-ID`. Heartbeat comment every 15 s |
| POST | `/api/jobs/{id}/pause`, `/resume`, `/cancel` | `{}` → `{state}` |

Event `data` is JSON with a `type`:
- **`stage`:** `{stage: "asking"|"finding"|"checking"|"collecting"|"scanning"|"done"}`
- **`source`:** `{source, seed, status: "running"|"found"|"nothing found"|"failed", found, checked, note}`
- **`account`:** `{url, site, verdict, probability}`, sent as candidates are scored
- **`scan`:** `{checked, total, photos, videos, found, eta_s}` (`eta_s` is from the measured rate; null until known)
- **`hit`:** a hit object (below)
- **`log`:** `{message}`
- **`done`:** `{ok: true}`
- **`error`:** `{message}`

## Is it him?
| Method | Path | Body / response |
|---|---|---|
| GET | `/api/cases/{slug}/person` | `{accounts: [{url, site, handle, verdict, probability, reasons: [str], decision, avatar: url\|null}], summary: [{tag, text, count}], weakest_verdict, namesakes: [{url, site, label, why: [str], decision}], decision: "him"\|"not him"\|"unsure"\|null}`. **The person** = candidates at "likely" or better, minus `not him`, plus `him`. **Namesakes** = name matches below 0.2 |
| POST | `/api/cases/{slug}/decisions` | `{url?, decision: "him"\|"not him"\|"unsure", note?}`. Without `url`, the decision applies to every account in the person. Append-only; the latest wins; audited |

## Posts and media scan
| Method | Path | Body / response |
|---|---|---|
| POST | `/api/cases/{slug}/media` | `multipart/form-data`: `files[]`, `platform?`, `posted_at?` → `{added: n}`. Uploads are streamed and hashed. HEIC is converted with `sips`; SVG is rejected |
| GET | `/api/cases/{slug}/posts` | `{counts: {read_automatically, added_by_you, flagged, by_category: {}}, weekly: [{week: "YYYY-Www", posts, flagged}], hits: [hit], posts: [post]}` |
| POST | `/api/cases/{slug}/hits/{id}` | `{status: "kept"\|"not relevant"\|"in report"}` → hit |

- **post:** `{id, source, account_url, url, posted_at, text, origin: "fetched"|"added", media: [{id, kind: "image"|"video"|"screenshot", file, duration}]}`
- **hit:** `{id, post_id, media_id, category, what, t0, t1, verdict, p, timing: "before"|"after", days_after, status: "new"|"kept"|"not relevant"|"in report", who: "unknown"|"him"|"other", file, source, posted_at, url, caption}`

Machine verdicts never exceed "likely". Only the investigator's Keep raises an item's status, never the verdict wording.

## Report
| Method | Path | Body / response |
|---|---|---|
| GET | `/api/cases/{slug}/report?screening=0\|1` | `{sections: [{id, title, done}], sentences: [{section, text, cites: [id]}], evidence: [{id, date, what, source, verdict, file}], couldnt_see: [str], checks: {every_sentence_cited, files_checked, tampered: [file]}}` |
| GET | `/api/cases/{slug}/report.html` \| `.pdf` \| `.json` `?screening=1` | Downloads. Hashes are re-verified at export |
| GET | `/evidence/{slug}/{sha256}.{ext}` | Evidence file (security rules above) |

Citation ids: `E-<post or hit id>` (evidence), `A-<finding id>` (accounts), `M-<run rowid>` (method).

## Python interface between the server and the scan modules
`hunt/posts.py` and `hunt/scan.py` own their tables (`posts`, `media`, `hits`) and create them on first use. `emit(event: dict)` is a plain, non-blocking callable.

```python
posts.collect(case, accounts: list[dict], since: str | None, emit) -> int  # Bluesky, Mastodon, YouTube RSS; accounts = [{url, site}]
posts.add_files(case, paths: list[Path], platform: str | None, posted_at: str | None) -> list[int]
posts.list_posts(case) -> list[dict]
scan.CATEGORIES: dict[str, dict]  # key -> {label, prompts, keywords}; keys match the wizard
scan.run(case, look_for: list[str], limits: str, injury_date: str | None, emit, pause: asyncio.Event, check_everything=False) -> None
scan.hits(case) -> list[dict]
scan.set_status(case, hit_id: int, status: str) -> dict
```

`scan.CATEGORIES` keys, in wizard order:
- `activity`: physical activity
- `lifting`: lifting or carrying
- `sport`: sport and gym
- `walks`: long walks or hikes
- `travel`: travel
- `other_job`: working another job
- `driving`: driving
- `injury`: mentions of the injury

## Quality of life: the Downloads inbox, the evidence bundle, links
See [qol.md](qol.md) for the screens that use these.

| Method | Path | Body / response |
|---|---|---|
| GET | `/api/cases/{slug}/inbox?folder=&days=7` | `{folder, days, files: [inbox file]}`, newest first. `folder` defaults to `~/Downloads` and must be an absolute path to a folder; `days` is 0–365. Only photos and videos directly in the folder are listed. Nothing changes on disk |
| POST | `/api/cases/{slug}/inbox` | `{folder?, days?, take: [{id, url?, platform?, handle?, posted_at?}], keep?: false}` → `{files: [inbox file + result, trashed]}`. Re-lists the folder and files the chosen ids through `posts.add_files`. The client never sends paths. An id that's gone returns 409. Each original goes to the Trash once its bytes are in the evidence, unless `keep`. Audited as `inbox import` |
| GET | `/api/cases/{slug}/evidence.zip` | Download: `exhibits/`, `manifest.csv`, `SHA256SUMS`, `audit-log.csv`, `README.txt`. Header `x-bundle-sha256` carries the zip's hash, which is also audited as `evidence exported` |
| GET | `/api/unfurl?url=` | `{platform, handle, post_id, posted_at, url}`. Works offline. `url` comes back without tracking parameters. `posted_at` is read from TikTok and X post ids |

- **inbox file:** `{id (first 8 hex of sha256), sha256, name, folder, size, saved, in_case: bool, named_by, platform, handle, post_id, posted_at, url, where_from: [url], from: {platform|handle|posted_at: "file name"|"where from"|"case"|"link"|"post id"|"you"}, exhibit}`
  - `named_by` is the downloader site whose naming the file follows (`ssstik`, `snaptik`…, or `Facebook or Instagram` for files saved from their servers).
  - `exhibit` is the proposed clean name.
  - A handle `from: "case"` is a guess from the subject's only confirmed account on that platform. Show it as one.
- **result:** `"added"`, `"already in the case"` or `"changed since listed"`.
- **trashed:** `true`, or a sentence saying why the original was left (`"kept, as asked"`, `"left: …"`).
