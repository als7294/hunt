# Hunt local API

`hunt app` serves the app and this API on `http://127.0.0.1:<random port>`. The browser
opens `/login?t=<token>`, which sets an HttpOnly, SameSite=Strict cookie and redirects to `/`.

## Security rules (enforced by middleware on every request)
- **Host:** must be exactly `127.0.0.1:<port>` or `localhost:<port>`. Anything else gets 403 (blocks DNS rebinding).
- **Cookie:** must carry the launch token (`hmac.compare_digest`), or the request gets 403.
- **Non-GET requests:**
  - `Origin` must be `http://127.0.0.1:<port>` (or the `localhost` form).
  - JSON bodies need `Content-Type: application/json`.
  - Uploads (`/api/cases/{slug}/media`, `/api/settings/logo`) are `multipart/form-data` with the same Origin check; nothing else accepts multipart.
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
| GET | `/api/startup` | `{version, proxy: bool, checks: [{id, label, ok, detail, items?}]}`. Check ids, in order: `cases`, `evidence` (re-hash; quick for unchanged files), `ai` (Ollama `/api/tags` lists `HUNT_VLM`; the model isn't loaded), `network`, `proxy`, `sources` (`hunt.sources.health()`: "N of M ready; K of L keys set"; `items: [{source, ready, reachable, key, key_set, key_required, detail}]`), any **Hunt Browser rows**, then `retention` (cases past 90 days without a legal hold; `items: [{slug, label, created}]`, each to be deleted or held) |
| GET | `/api/cases` | `[{slug, label, kind, reference, tool, created, updated, headline, closed, legal_hold, retention_due}]`, newest first. `headline` reads like "9 flagged posts" or "Confirmed · report ready" |
| POST | `/api/cases` | `{label, seeds: [str], kind: "insurance"\|"background"\|"diligence"\|"journalism", reference?, purpose (required: who asked and why it's lawful), injury_date?: "YYYY-MM-DD", limits?: str, look_for: [category key or custom text], tool: "person"}` plus any **report header fields** (below) → `201 {slug}`. A label that's already taken gets a `-2` suffix; nothing is ever merged |
| GET | `/api/cases/{slug}` | `{slug, details: {label, kind, reference, purpose, injury_date, limits, look_for, tool, created, client, adjuster, file_number, assignment_date, subject_dob, recommendations}, seeds: [{kind, value}], steps: {search, identity, posts, report}` (each `"todo"`, `"running"` or `"done"`), `status: {closed, legal_hold, retention_ends, retention_due}, active_job: {id, kind} \| null, counts: {accounts, flagged, evidence}}` |
| POST | `/api/cases/{slug}/close` | `{reason?}` → status. Watching stops, and no search, scan, re-check or watch run starts until it's reopened (409). Audited (`case closed`); the report says when it was closed. 409 while a job runs |
| POST | `/api/cases/{slug}/reopen` | `{}` → status. Audited (`case reopened`). Watching doesn't restart by itself |
| POST | `/api/cases/{slug}/hold` | `{on: bool, reason?}` → status. A legal hold keeps the case past its retention period, keeps watching it, and blocks deleting. Audited (`legal hold`); the report's disclaimers mention it |
| POST | `/api/cases/{slug}/delete` | `{confirm: <slug>, reason?}` → `{deleted, to: "Trash"}`. Moves the whole case folder to the Trash (Finder's Put Back restores it). 409 under a legal hold or while a job runs. Audited in the case (`case deleted`, which goes to the Trash with it) and in `~/Hunt/deleted-cases.log` |
| POST | `/api/cases/{slug}/details` | Any of `{reference, injury_date, limits, look_for, client, adjuster, file_number, assignment_date, subject_dob, recommendations}`; `""` clears a field → `{details}`. Audited. Dates are `YYYY-MM-DD` |
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
- **`stage`:** `{stage: "asking"|"finding"|"checking"|"collecting"|"scanning"|"rechecking"|"capturing"|"done"}`
- **`source`:** `{source, seed, status: "running"|"found"|"nothing found"|"failed", found, checked, note}`
- **`account`:** `{url, site, verdict, probability}`, sent as candidates are scored
- **`scan`:** `{checked, total, photos, videos, found, eta_s, media_id}` (`eta_s` is from the measured rate, null until known; `media_id` is the file just checked, null on other updates)
- **`hit`:** a hit object (below)
- **`change`:** `{change, account, …, audit}`, from a re-check (see "Check again" below)
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

**Case lifecycle.** `status.closed` and `status.legal_hold` are the times they were set, or null. Retention runs 90
days from opening (`RETENTION_DAYS` in `hunt/case.py`); `retention_ends` is null under a hold. `hunt/watch.py` stops
watching on the same two rules.

**Hunt Browser rows on the startup page.** Once a `hunt/browser.py` exists, `/api/startup` calls its `status()` (sync or
async). It should return `[{id, label, ok, detail}]`, e.g. one row per site the investigator is signed in to in Hunt
Browser, and appends them after `sources`. Until then there are no rows.

**Every source run is in the case log.** `Case.add_run` also writes a `source run` audit entry, and the run keeps its
row id, so the report cites a run as `M-a<id>`, which is in the evidence bundle's `audit-log.csv`. Runs recorded before
this keep citing `M-<run rowid>`.

**Report header fields** (case details; all optional, all audited): `client` (carrier, TPA or law firm), `adjuster`,
`file_number` (the investigator's own file number; the report falls back to the case slug), `assignment_date`,
`subject_dob` (dropped in screening mode), `recommendations` (the investigator's own words, printed under
"Conclusion and recommendations" and cited to the log entry that set them). `reference` is the client's claim or
reference number; `injury_date` is the date of injury or loss.

## Report settings (one per investigator, under `HUNT_HOME`)
| Method | Path | Body / response |
|---|---|---|
| GET | `/api/settings` | `{firm, investigator, licence, contact, timezone, confidentiality, logo: bool}`. `timezone` defaults to this computer's (an IANA name); `confidentiality` to a standard line |
| POST | `/api/settings` | Any of the fields above as strings (≤ 500 characters; `""` clears one; `timezone` must be an IANA zone name); `{logo: null}` removes the logo → the settings |
| POST | `/api/settings/logo` | `multipart/form-data` with one `file`: PNG or JPEG under 2 MB (SVG and everything else get 415) → the settings |
| GET | `/api/settings/logo` | The logo image, or 404 |

## Report
Laid out like an insurance / online-activity investigation report (`docs/research/report-format.md`).

| Method | Path | Body / response |
|---|---|---|
| GET | `/api/cases/{slug}/report?screening=0\|1` | The report dict (below) |
| GET | `/api/cases/{slug}/report.html` \| `.pdf` \| `.json` `?screening=1` | Downloads. Every evidence hash is re-verified at export (views use the quick check). HTML prints on US Letter with a running header and "Page X of Y" footer; the PDF has the same from Chromium |
| GET | `/evidence/{slug}/{sha256}.{ext}` | Evidence file (security rules above) |

The report dict:
- `screening: bool`
- `header: {title, firm, investigator, licence, contact, logo, client, adjuster, reference, file_number, subject, subject_dob, injury_date, assignment_date, report_date, timezone, confidentiality}` (`subject_dob` and `injury_date` are null in screening mode)
- `sections: [{id, title, done}]`, in order: `summary` Synopsis, `scope` Assignment and scope, `method` Search methodology, `presence` Online presence, `identity` Identity confirmation, `records` Public records, `found` Findings, `conclusion` Conclusion and recommendations, `couldnt_see` Limitations: what we couldn't see, `disclaimers` Disclaimers
- `sentences: [{section, text, cites: [id], platform?}]`: every one cited. Findings sentences carry `platform`, so they can be grouped under platform headings. `couldnt_see` sentences aren't here; they're the bullets below
- `presence: [{row, id, platform, url, username, visibility: "public"|"private"|"registered; no public profile seen", last_activity, relevant: "yes"|"no"|"not reviewed", status: "confirmed"|<verdict, at most likely>, exhibit}]`: the online presence table (accounts only)
- `records: [{row, id, source: "fec"|"edgar"|"npi"|"courtlistener", site, url, summary, status, exhibit}]`: public records likely or confirmed to concern the subject, each with a one-line summary. They're records about the person, so they never appear in `presence` or as unread posts
- `exhibits: [{no, id, kind, file, name, sha256, captured, platform, url, account?, posted_at, description, relevance?, page_source?}]`: numbered in the order the report refers to them (confirmed accounts' screenshots, then kept items by platform and date). `name` is the file's name in the evidence bundle (`hunt export`), e.g. `2026-04-04_bluesky_kestrel-vane88_image_1765f69b.jpg`
- `evidence: [{id, exhibit, date, what, source, verdict, file}]`: the kept items
- `accounts: [{id, site, url, verdict, decision, screenshot, captured}]`
- `couldnt_see: [str]`, `couldnt_see_cites: [[id]]`: the limitations, as bullets, with their citations in the same order
- `log: [{id, when, what, audit_log_id}]`: Appendix B, every `M-` id cited, in order; exports print `M-` citations as "Log n". `audit_log_id` is the entry's `id` in the evidence bundle's `audit-log.csv` (null for source runs)
- `certification: {text, investigator, licence, firm, date}`: the signature block
- `checks: {every_sentence_cited, files_checked, tampered: [file], missing: [header field]}`. `missing` lists what the header still needs (client, reference, assignment_date, investigator, licence)

**Screening mode** (`?screening=1`, for employment use) leaves out: protected characteristics in any sentence; the date
of birth and date of loss; injury items; profile and record screenshots; FEC contribution records and their source
runs (political affiliation); NPI registry records and runs (health); and court dockets whose case, cause or nature of
suit is about health or politics. It says so in its disclaimers.

Citation ids: `E-<hit id>` (a kept item), `A-<finding id>` (an account), `M-<run rowid>` (a source run), `M-a<audit rowid>`
(a case-log entry: purpose, decisions, captures, the scan). The exports print them as "Ex. n" (an exhibit), "Acct. n" (a
row of the presence table), "Rec. n" (a row of the public records table) or "Log n" (Appendix B).

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

## Quality of life: the Downloads inbox, the evidence bundle, links, Check again, notes, watching
See [qol.md](qol.md) for the screens that use these.

| Method | Path | Body / response |
|---|---|---|
| GET | `/api/cases/{slug}/inbox?folder=&days=7` | `{folder, days, files: [inbox file]}`, newest first. `folder` defaults to `~/Downloads` and must be an absolute path to a folder; `days` is 0–365. Only photos and videos directly in the folder are listed. Nothing changes on disk |
| POST | `/api/cases/{slug}/inbox` | `{folder?, days?, take: [{id, url?, platform?, handle?, posted_at?}], keep?: false}` → `{files: [inbox file + result, trashed]}`. Re-lists the folder and files the chosen ids through `posts.add_files`. The client never sends paths. An id that's gone returns 409. Each original goes to the Trash once its bytes are in the evidence, unless `keep`. Audited as `inbox import` |
| GET | `/api/cases/{slug}/evidence.zip` | Download: `exhibits/`, `manifest.csv`, `SHA256SUMS`, `audit-log.csv`, `notes.csv`, `README.txt`. Header `x-bundle-sha256` carries the zip's hash, which is also audited as `evidence exported` |
| GET | `/api/unfurl?url=` | `{platform, handle, post_id, posted_at, url}`. Works offline. `url` comes back without tracking parameters. `posted_at` is read from TikTok and X post ids |
| POST | `/api/cases/{slug}/recheck` | `{}` → `{job}`. **Check again:** the accounts marked `him` (not email hits) are looked at again. Returns 409 if none are marked, or if the case already has an active job. Takes the heavy lock only while capturing screenshots |
| GET | `/api/cases/{slug}/changes` | `{checks: [{cite, ts, change: "recheck", accounts, new_posts, changes, captured}], changes: [change]}`, newest first. `cite` is the report's `M-a<audit rowid>` |
| GET | `/api/cases/{slug}/watch` | `{on, every_days, started, last, next, status, stopped, why, unseen_alerts, background}`. `status`: `ok`, `waiting: on battery`, `waiting: the Mac is busy`, `waiting: the Mac is in use`, or `failed: …`. `why` is why watching stopped: `turned off`, `the case is closed`, or the retention period ended. `background` is whether the LaunchAgent is installed |
| POST | `/api/cases/{slug}/watch` | `{on: bool, every_days?: 1\|3\|7}` (default 7) → the same state. The first check is one interval away; changing `every_days` while on counts from the last check. Returns 409 if no account is marked `him`, or the case can't be watched any more. Audited as `watch on` / `watch off` |
| GET | `/api/cases/{slug}/alerts` | `{alerts: [{id, ts, kind: "flagged"\|"posts gone"\|"no posts"\|"account gone", text, audit, cite: "M-a<audit>", seen: bool}]}`, newest first |
| POST | `/api/cases/{slug}/alerts/seen` | `{}` → `{marked: n}` |
| GET | `/api/watch/background` | `{on}`: whether "Keep watching when Hunt is closed" is installed (one per-user LaunchAgent, for every watched case) |
| POST | `/api/watch/background` | `{on: bool}` → `{on}`. Installs `~/Library/LaunchAgents/io.github.als7294.hunt.watch.plist` and loads it with `launchctl`, or unloads it and moves the plist to the Trash. Audited as `background watching` in every watched case. Returns 409 if `launchctl` refuses |
| GET | `/api/cases/{slug}/notes?about=&ref=` | `{notes: [note]}`, oldest first, optionally only the notes about one thing. Returns 400 for an unknown `about` or a bad `ref` |
| POST | `/api/cases/{slug}/notes` | `{text, about?: "case"\|"account"\|"post"\|"hit", ref?, replaces?: note id}` → `201 note`. A correction (`replaces`) keeps the old note's subject; a note can only be replaced once. Returns 400 for empty text (or more than 20,000 characters), an unknown subject, or a note that's already replaced. Audited as `note`, with its text |

- **inbox file:** `{id (first 8 hex of sha256), sha256, name, folder, size, saved, in_case: bool, named_by, platform, handle, post_id, posted_at, url, where_from: [url], from: {platform|handle|posted_at: "file name"|"where from"|"case"|"link"|"post id"|"you"}, exhibit}`
  - `named_by` is the downloader site whose naming the file follows (`ssstik`, `snaptik`…, or `Facebook or Instagram` for files saved from their servers).
  - `exhibit` is the proposed clean name.
  - A handle `from: "case"` is a guess from the subject's only confirmed account on that platform. Show it as one.
- **result:** `"added"`, `"already in the case"` or `"changed since listed"`.
- **trashed:** `true`, or a sentence saying why the original was left (`"kept, as asked"`, `"left: …"`).

### Check again: events and changes
**Stages, in order:**
- `rechecking`: profiles are read again.
- `collecting`: from `posts.collect`, with its usual `source` events.
- `capturing`: screenshots are taken again.
- `done`.

`log` events say which profiles can't be read logged out, and which captures failed.

**`change` events** (also each an audit entry, `audit` = its rowid):
| change | fields |
|---|---|
| `account gone` / `account back` | `account, last_seen` / `account, missing_on`: the profile can't be found at its address any more, or can be again. Bluesky and Mastodon only |
| `profile changed` | `account, field: "name"\|"bio"\|"profile photo", before, after, before_seen`, plus `before_sha256, after_sha256` for the photo |
| `posts gone` | `account, none_left: bool, posts: [{id, url, posted_at, last_seen}]`. Only posts at least as new as the oldest one this read returned are judged. `none_left` means the account showed no posts at all |
| `post back` | `account, post, url, gone_since` |

**How changes are judged:**
- A failed read judges nothing.
- A profile is compared only with an earlier read by the same source (an earlier re-check, or the search's own Bluesky or Mastodon finding).
- The end-of-run summary is audited as `recheck`, and new screenshots as `recapture`.

- **note:** `{id, cite: "N-<id>", ts, about, ref, text, replaces: id|null, replaced_by: id|null}`.
  - `ref` is `null` for the case, the account's normalised URL, or the post's or hit's id, as a string.
  - Notes are never edited or deleted. A replaced note stays, with `replaced_by` set.

### Watching: runs and jobs
- **While Hunt is open:** due cases are checked every 10 minutes, one at a time. Each run is a job of kind `"watch"`, so `GET /api/cases/{slug}` shows it in `active_job`, and its events stream like a scan's.
- **Event stages, in order:** `rechecking`, `collecting`, `capturing` (from Check again), then `scanning` (new media only), then `done`. Check again's own `done` is held back.
- **What a run does:** `change` events as in Check again, then `scan` and `hit` events as in a scan.
- **When it waits:** a case with another job running waits for the next round. So does every due case while the Mac is on battery, busy (1-minute load average above 0.5 per core), or in use (input in the last 5 minutes). "In use" stops counting once a check is a day overdue.
- **After a run:** it's audited as `watch run` `{new_posts, changes, new_flagged, alerts}`.
  - Each alert is audited as `alert` `{kind, text, hits | change}`, where `change` is the rowid of the Check again audit entry it came from.
  - One local macOS notification sums up the run's alerts.
  - A failed run is tried again an hour later.
