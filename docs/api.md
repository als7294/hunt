# Hunt local API

`hunt app` serves the app and this API on `http://127.0.0.1:<random port>`. The browser
opens `/login?t=<token>`, which sets an HttpOnly, SameSite=Strict cookie and redirects to `/`.

## Security rules (enforced by middleware on every request)
- **Host:** must be exactly `127.0.0.1:<port>` or `localhost:<port>`. Anything else gets 403 (blocks DNS rebinding).
- **Cookie:** must carry the launch token (`hmac.compare_digest`), or the request gets 403.
- **Non-GET requests:**
  - `Origin` must be `http://127.0.0.1:<port>` (or the `localhost` form).
  - JSON bodies need `Content-Type: application/json`.
  - Uploads (`/api/cases/{slug}/media`, `/api/cases/{slug}/facebook`, `/api/settings/logo`) are `multipart/form-data` with the same Origin check; nothing else accepts multipart. (The extension's `/api/capture/*` uploads pass their own check; see Hunt Capture.)
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
| GET | `/api/startup` | `{version, proxy: bool, checks: [{id, label, ok, detail, items?}]}`. Check ids, in order: `cases`, `evidence` (re-hash; quick for unchanged files), `ai` (Ollama `/api/tags` lists `HUNT_VLM`; the model isn't loaded), `network`, `proxy`, `sources` (`hunt.sources.health()`: "N of M ready; K of L keys set"; `items: [{source, ready, reachable, key, key_set, key_required, detail}]`), `browser` (the Hunt Browser and its sign-ins; below), then `retention` (cases past 90 days without a legal hold; `items: [{slug, label, created}]`, each to be deleted or held) |
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
- **`progress`:** `{item: "model"|"chromium", done, total, message}` (bytes), from a setup download
- **`log`:** `{message}`
- **`done`:** `{ok: true}`
- **`error`:** `{message}`

## Is it him?
| Method | Path | Body / response |
|---|---|---|
| GET | `/api/cases/{slug}/person` | `{accounts: [{url, site, handle, verdict, probability, reasons: [str], decision, avatar: url\|null}], summary: [{tag, text, count}], weakest_verdict, namesakes: [{url, site, label, why: [str], decision}], records: [{url, site, source, summary, attrs, verdict, probability, reasons, name_only, decision, fetched}], coverage: [{source, status, found, note}], decision: "him"\|"not him"\|"unsure"\|null}`. **The person** = candidates at "likely" or better, minus `not him`, plus `him`. Public records in the person (`fec`, `edgar`, `npi`, `courtlistener`, `licences`, `businesses`, `fmcsa`) are in `records`, not `accounts`; `name_only` is true when only the name agrees. `coverage` is every records run, with its note on what was searched. **Namesakes** = name matches below 0.2 |
| POST | `/api/cases/{slug}/decisions` | `{url?, decision: "him"\|"not him"\|"unsure", note?}`. Without `url`, the decision applies to every account in the person. Append-only; the latest wins; audited |

## Posts and media scan
| Method | Path | Body / response |
|---|---|---|
| POST | `/api/cases/{slug}/media` | `multipart/form-data`: `files[]`, `platform?`, `posted_at?` → `{added: n}`. Uploads are streamed and hashed. HEIC is converted with `sips`; SVG is rejected |
| POST | `/api/cases/{slug}/facebook` | `multipart/form-data`: `files[]`, `saved_at?` (ISO) → `{added, posts, pages, screenshots, skipped: [name]}`. Details below |
| POST | `/api/cases/{slug}/preview` | `{url}` (a confirmed account's https address) → whatever `hunt.public.preview(case, url)` returns, at least `{note}` (e.g. "12 posts shown logged out; the rest need the Hunt Browser"). Read public preview, on her click, one account at a time. 501 until `hunt/public.py` exists; 409 on a closed case |
| GET | `/api/cases/{slug}/facebook/links` | `{links: [{label, url}]}`: Facebook search and `site:facebook.com` search-engine links for the case's seeds. For the investigator to open in their own browser; Hunt never requests them |
| GET | `/api/cases/{slug}/posts` | `{counts: {read_automatically, added_by_you, captured, flagged, by_category: {}}, weekly: [{week: "YYYY-Www", posts, flagged}], hits: [hit], posts: [post]}` |
| POST | `/api/cases/{slug}/hits/{id}` | `{status: "kept"\|"not relevant"\|"in report"}` → hit |

- **post:** `{id, source, account_url, url, posted_at, text, origin: "fetched"|"added"|"captured", media: [{id, kind: "image"|"video"|"screenshot", file, duration}], extra}`
  - `extra` is `null`, except on imported Facebook posts: `{posted_at_precision: "second"|"minute"|"hour"|"day"|"week"|"month"|"year", posted_at_text, author, fb_id, post_id, place, activity, life_event, truncated, reactions, comments, shares, evidence}`, with only the keys found. `evidence` is the stored page the post came from.
  - `posted_at` always starts with `YYYY-MM-DD`: an ISO date-time with an offset when exact, a date-time without one when it's what Facebook displayed (the saving browser's time zone), or a date.
- **hit:** `{id, post_id, media_id, category, what, t0, t1, verdict, p, timing: "before"|"after", days_after, status: "new"|"kept"|"not relevant"|"in report", who: "unknown"|"him"|"other", file, source, posted_at, url, caption}`

Machine verdicts never exceed "likely". Only the investigator's Keep raises an item's status, never the verdict wording.

**Case lifecycle.** `status.closed` and `status.legal_hold` are the times they were set, or null. Retention runs 90
days from opening (`RETENTION_DAYS` in `hunt/case.py`); `retention_ends` is null under a hold. `hunt/watch.py` stops
watching on the same two rules.

**The Hunt Browser row on the startup page.** `/api/startup` turns `hunt.browser.status()` into one check after
`sources`: `{id: "browser", label: "Hunt Browser <version>", ok, detail, items: [{platform, label, url, state:
"signed_in"|"signed_out"|"unknown"}], checked_at}`. Being signed out isn't a failure (each platform is optional);
`ok` is false only when the browser isn't installed or its status can't be read.

**Every source run is in the case log.** `Case.add_run` also writes a `source run` audit entry, and the run keeps its
row id, so the report cites a run as `M-a<id>`, which is in the evidence bundle's `audit-log.csv`. Runs recorded before
this keep citing `M-<run rowid>`.

**`POST /api/cases/{slug}/facebook`** imports what the investigator saved while browsing Facebook themselves ([facebook.md](facebook.md)):

- **Accepted:** `.html`/`.htm` saved pages with their `_files` folder, `.mhtml`/`.mht`, `.webarchive`, and screenshots (`.png`, `.jpg`, `.jpeg`, `.webp`, `.heic`).
- **Filenames are relative paths.** Send each file with its `webkitRelativePath`, so `Saved/Page.html` finds `Saved/Page_files/…`. An absolute path, a drive letter or a `..` part returns 400.
- **Skipped, never stored:** SVG, scripts, styles and anything else; they're listed in `skipped`. Pictures inside a `…_files` folder are the page's own, not separate uploads.
- **Pages:** each is hashed into the evidence as uploaded (`.webarchive` as `<sha>.plist`; HTML and MHTML are served as `text/plain`), then parsed into posts.
- **Screenshots:** one showing a post's date line becomes that post; any other picture is added as a plain file, as `/media` does.
- **Repeats:** a post already in the case (same link, or the same date and words) isn't added twice.
- **`saved_at`** anchors relative times ("3d") for pages that carry no save date of their own. Otherwise an MHTML's `Date:` header, else the upload time.
- **Response:** `posts` counts posts read, `added` counts new ones.
- **Audit:** `facebook page imported`, `post imported`, `post already added`.

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

## Free keys (one set per investigator, under `HUNT_HOME`)
| Method | Path | Body / response |
|---|---|---|
| GET | `/api/keys` | `{keys: [{key, label, sources: [source], required, url, free, set, where: "saved"\|"environment"\|null}]}`, one row per env var (the state portals share `HUNT_SOCRATA_TOKEN`). Never a value |
| POST | `/api/keys` | `{<env var>: value}`; `""` removes one → as GET. 400 for a key Hunt doesn't use, a value over 500 characters, or a key set in the shell that started Hunt (the shell wins; change it there) |

`hunt/keys.py` keeps them in `HUNT_HOME/keys.json` (mode 0600) and puts them into the server's environment, where the
sources read them. Which keys exist comes from the source modules' `KEY`, `KEY_REQUIRED`, `KEY_URL` and `KEY_FREE`; a
key read elsewhere in Hunt (not by a source) is added to `keys.EXTRA = {env var: {label, url, free}}`. Every key is
optional except CourtListener's, and Hunt works fully without any.

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
`hunt/posts.py` and `hunt/scan.py` own their tables (`posts`, `media`, `post_extra`, `hits`) and create them on first use. `emit(event: dict)` is a plain, non-blocking callable.

```python
posts.collect(case, accounts: list[dict], since: str | None, emit) -> int  # Bluesky, Mastodon, YouTube RSS; accounts = [{url, site}]
posts.add_files(case, paths: list[Path], platform: str | None, posted_at: str | None) -> list[int]
posts.add_posts(case, items: list[dict], kind="image", evidence: str | None = None, origin="added") -> list[int]  # facebook / capture
posts.store(case, path, ext=None) -> (file, sha256)  # hash a file into evidence/
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

## Hunt Capture
The browser extension that records what the investigator views while logged in as herself ([capture.md](capture.md)).

**For the web app** (the usual cookie Guard):

| Method | Path | Body / response |
|---|---|---|
| GET | `/api/browser/status` | `{facebook, instagram, tiktok, linkedin, x: "signed_in"\|"signed_out"\|"unknown", checked_at, browser: {available, running, version, profile: bool, pinned: bool\|null}, capture: {case, on, since}, problems: [{ts, message}], stopped: {platform: {ts, reason, url, message}}, accounts: {platform: handle}, logins: [{platform, label, url}]}`. `pinned`: is Hunt Capture on the toolbar, where its REC badge shows. `problems`: the extension's latest 20 errors, newest last. Sign-in states come from the Hunt Browser's extension: whether each sign-in cookie exists, never its value. Also re-points an open Hunt Browser at this Hunt's port (internal; no case or user state changes) |
| POST | `/api/browser/open` | `{url, case?, window?: {width, height}}` → `{opened, started}`. `window` (300–5000 px) sizes the browser when it starts. Opens an http(s) page in the Hunt Browser, starting it if needed. `case` is preselected in the extension's popup. 400 for other schemes; 404 for an unknown case; 503 when Playwright's browser isn't installed |
| POST | `/api/browser/capture` | `{case, on}` → `{case, on, since}`. Turns Hunt Capture on (into `case`) or off. The extension mirrors it at its next page load. Capture is off whenever Hunt starts. 400 for on without a case; 404 for an unknown case |
| POST | `/api/browser/resume` | `{platform}` → `{stopped}`. Lifts a hard stop (audited `capture resumed`). Only on her deliberate choice, after she's spoken to Ethos |
| GET, POST | `/api/browser/accounts` | `{facebook?: handle, …}` → the handles she signs in with, used in `viewed_as` ("logged in as {handle}") |
| POST | `/api/browser/sign-out` | `{}` → `{moved_to: "Trash"\|null, …status}`. Moves the Hunt Browser's profile (every login) to the Trash, never deletes. 409 while it's open |
| GET | `/api/pairing` | `{paired: bool, origin?, name?, paired_at?}` |
| POST | `/api/pairing` | `{}` → `{code: "<port>-<8 digits>", expires_in: 300}`. A one-time code for the extension's popup. Five wrong tries close it; a new one replaces it |
| POST | `/api/pairing/forget` | `{}` → `{paired: false}`. The extension's key stops working at once |
| GET | `/api/cases/{slug}/checklist` | `{accounts: [{account, platform, sections: [{key, label, url, seen, seen_at, evidence}], progress: {grid_seen, grid_total, flagged, opened, videos, played}, todo: [{url, kind: "post"\|"video", file, why}]}]}` for each account confirmed as the subject's. `todo` is the "open these" list: flagged posts seen only as grid thumbnails, then unplayed videos |
| GET | `/api/cases/{slug}/captures` | `{captures: [{ts, kind: "view"\|"page"\|"recording", url, where, platform, file, sha256, viewed_at, extension, …}]}`, newest first (200) |

**For the extension.** These routes never take the cookie. Every request needs:
- method POST
- `Origin: chrome-extension://<paired id>`
- `x-hunt-key: <key>` (except `pair`)
- JSON, or multipart for uploads

Anything else gets 403, 405 or 415. The key opens no other route.

| Path | Body → response |
|---|---|
| `/api/capture/pair` | `{code, name?}` → `{key}`. 403 if the code is wrong, used, expired or closed |
| `/api/capture/hello` | `{}` → `{version, paired, origin, name, paired_at, cases: [{slug, label}], active_case: {slug, label}\|null, capture: {case, on, since, label}, off_sites: ["LinkedIn"]}` |
| `/api/capture/state` | `{case, on}` → `{case, on, since}`. The popup turned capture on or off; Hunt's status follows |
| `/api/capture/problem` | `{message}` → `{ok: true}`. An error the extension hit; listed in `/api/browser/status` |
| `/api/capture/revoked` | `{url}` → the stop entry. The extension saw a checkpoint, challenge or suspension address; that platform stops. 400 for an ordinary address |
| `/api/capture/guided` | `{case, action: "scroll"\|"open", url, to?}` → `{audit}`. One press of Next, audited as `guided step`. 403 where capture is off or stopped |
| `/api/capture/signins` | `{facebook?, instagram?, tiktok?, linkedin?, x?: "signed_in"\|"signed_out"\|"unknown", pinned?: bool}` → as `GET /api/browser/status`. Anything that isn't one of those states is refused (400) |
| `/api/capture/checklist` | `{case}` → as `GET /api/cases/{slug}/checklist` |
| `/api/capture/view` | multipart `case, url, viewed_at?, title?, kind? (view\|frame\|manual), screenshot` (JPEG or PNG) → `{post, file}`. `post` is null when that picture was already in the case |
| `/api/capture/page` | multipart `case, url, viewed_at?, capture_version?, session?, archive` (MHTML) → `{posts, added, upgraded, file, stopped, changes}`. `upgraded`: grid-only posts now captured in full. `stopped`: the hard stop, if the page showed a checkpoint or block. `changes`: Check again's comparison with the last capture of this page (once QOL's `recheck.diff_captures` is merged; `[]` until then) |
| `/api/capture/recording` | multipart `case, url, started_at?, video` (WebM or MP4) → `{post, file}` |

Capture uploads also share these rules:
- They carry `capture_version` (the extension's version) and `session` (`signed_in`/`signed_out` for that platform, from the sign-in cookie's presence), which Hunt turns into the capture record: `viewed_as`, `audience`, `audience_flag`, `captured_at`, `time_source`, `received_at`, `capture_version`, `hunt_version`, `capture_sha256`. They go in the audit detail and in each post's `extra` (see [capture.md](capture.md#capture-record)).
- A platform under a hard stop gets 403 with the stop's message.
- `url` must be an https page on Facebook, Instagram, TikTok, X, YouTube or Reddit (else 400). LinkedIn, Strava and Snapchat pages get 403: Hunt Capture never records them, because their terms name extensions.
- An unknown case returns 404.
- A file of the wrong kind returns 415.
- Posts are stored with `origin: "captured"`, and `/posts` counts them as `counts.captured`.

## Quality of life: the Downloads inbox, the evidence bundle, links, Check again, notes, watching, moving cases, seen before, setup
See [qol.md](qol.md) for the screens that use these.

| Method | Path | Body / response |
|---|---|---|
| GET | `/api/cases/{slug}/inbox?folder=&days=7` | `{folder, days, files: [inbox file]}`, newest first. `folder` defaults to `~/Downloads` and must be an absolute path to a folder; `days` is 0–365. Only photos and videos directly in the folder are listed. Nothing changes on disk |
| POST | `/api/cases/{slug}/inbox` | `{folder?, days?, take: [{id, url?, platform?, handle?, posted_at?}], keep?: false}` → `{files: [inbox file + result, trashed]}`. Re-lists the folder and files the chosen ids through `posts.add_files`. The client never sends paths. An id that's gone returns 409. Each original goes to the Trash once its bytes are in the evidence, unless `keep`. Audited as `inbox import` |
| GET | `/api/cases/{slug}/evidence.zip` | Download: `exhibits/`, `manifest.csv` (now also `role`: evidence or lead, `collected`: read by Hunt / captured in the Hunt Browser / added by the investigator, and the capture record `viewed_as`, `audience`, `tool_version`), `SHA256SUMS`, `audit-log.csv`, `notes.csv`, and `README.txt` (with the collection process for an FRE 902(13) certification). Header `x-bundle-sha256` carries the zip's hash, which is also audited as `evidence exported` |
| GET | `/api/unfurl?url=` | `{platform, handle, post_id, posted_at, url}`. Works offline. `url` comes back without tracking parameters. `posted_at` is read from TikTok and X post ids |
| POST | `/api/cases/{slug}/recheck` | `{}` → `{job}`. **Check again:** the accounts marked `him` (not email hits) are looked at again. Instagram, Facebook, X and LinkedIn are never fetched or screenshotted by Hunt (their robots.txt denies unnamed bots): for those, the job compares any captures not yet compared and points to the worklist. The `recheck` summary gains `worklist` (how many accounts are hers to open). Returns 409 if none are marked, or if the case already has an active job. Takes the heavy lock only while capturing screenshots |
| GET | `/api/cases/{slug}/changes` | `{checks: [{cite, ts, change: "recheck", accounts, new_posts, changes, captured}], changes: [change]}`, newest first. `cite` is the report's `M-a<audit rowid>` |
| GET | `/api/cases/{slug}/watch` | `{on, every_days, started, last, next, status, stopped, why, unseen_alerts, background}`. `status`: `ok`, `waiting: on battery`, `waiting: the Mac is busy`, `waiting: the Mac is in use`, or `failed: …`. `why` is why watching stopped: `turned off`, `the case is closed`, or the retention period ended. `background` is whether the LaunchAgent is installed |
| POST | `/api/cases/{slug}/watch` | `{on: bool, every_days?: 1\|3\|7}` (default 7) → the same state. The first check is one interval away; changing `every_days` while on counts from the last check. Returns 409 if no account is marked `him`, or the case can't be watched any more. Audited as `watch on` / `watch off` |
| GET | `/api/cases/{slug}/alerts` | `{alerts: [{id, ts, kind: "flagged"\|"posts gone"\|"no posts"\|"account gone", text, audit, cite: "M-a<audit>", seen: bool}]}`, newest first |
| POST | `/api/cases/{slug}/alerts/seen` | `{}` → `{marked: n}` |
| GET | `/api/watch/background` | `{on}`: whether "Keep watching when Hunt is closed" is installed (one per-user LaunchAgent, for every watched case) |
| POST | `/api/watch/background` | `{on: bool}` → `{on}`. Installs `~/Library/LaunchAgents/io.github.als7294.hunt.watch.plist` and loads it with `launchctl`, or unloads it and moves the plist to the Trash. Audited as `background watching` in every watched case. Returns 409 if `launchctl` refuses |
| POST | `/api/cases/{slug}/pack` | `{passphrase (12+ characters), folder?}` → `{name, path, sha256, manifest_sha256, files, bytes, changed}`. Writes `<case>-<UTC time>.hunt-case.dmg` (AES-256 encrypted disk image) into `folder`, default `~/Downloads`. The archive never passes through the browser. Returns 400 for a short passphrase or a bad folder. Audited as `case packed` (inside the archive) and `case pack sealed` (here) |
| GET | `/api/case-archives?folder=` | `{folder, files: [{name, folder, size, saved}]}`: `.hunt-case.dmg` files in the folder (default `~/Downloads`), newest first. Their contents stay locked until unpacked |
| POST | `/api/case-archives/unpack` | `{name, folder?, passphrase, replace?: false}` → `{slug, files, replaced, sha256, manifest_sha256}`. Every file is checked against the manifest before the case is put in place. A case with the same name here is kept, and the new one gets `-2`; with `replace`, the one here goes to the Trash first. Returns 400 for a wrong passphrase, a file that doesn't match, or a file that isn't in the manifest; nothing is changed. Returns 409 with `replace` while any job runs. Audited as `case unpacked`; watching is turned off on arrival |
| GET | `/api/cases/{slug}/seen-before?screening=0\|1` | `{checked, why, skipped_screenings, matches: [{case, label, kind, created, strong, on: [{kind: "username"\|"email"\|"phone"\|"url"\|"address"\|"name"\|"file", value}]}]}`, strongest first. Local and read-only, and never merges anything. A `background` case, or `screening=1`, gives `checked: false` with `why`. `background` cases never appear in others' matches |
| POST | `/api/seen-before` | `{seeds: [str], kind?}` → the same, for the new-case form before the case exists. `kind: "background"` gives `checked: false` |
| GET | `/api/setup` | `{version, doctor: [{id, label, ok, detail, fix}], items: [{id: "ollama"\|"model"\|"chromium", label, installable, size, detail}]}`. `doctor` rows: `python`, `uv`, `hunt`, `ollama`, `model`, `chromium`, `capture`, `ffmpeg`, `disk`, `home`, `launcher`. `items` is only what's missing; `size` is the download size in bytes (null if it can't be read, which also makes `installable` false). Ollama itself is never installable here: its `detail` says where to get it |
| POST | `/api/setup/{item}` | `{size}` → `{job}`. `size` must equal the `size` the client showed and the investigator accepted; otherwise 400. Returns 404 if the item isn't missing, 409 if it can't be installed here or a download is already running. The job streams `progress` events: the model is pulled through the local Ollama's `/api/pull`, the browser with `playwright install chromium` |
| GET | `/api/cases/{slug}/worklist` | `{worklist: [{account, platform: "Facebook"\|"Instagram"\|"TikTok"\|"X"\|"LinkedIn", last_opened, last_capture, warning}], uncompared_captures}`. Check again on login-walled platforms: the subject's confirmed accounts there, for the investigator to open one by one. `warning` is set when a LinkedIn profile was opened in the last 7 days |
| POST | `/api/cases/{slug}/worklist/open` | `{account, confirmed?: false}` → `{opened, started, warning}`. Her click: audited as `worklist open`, then the account opens in the Hunt Browser (one click, one page load). With a pacing warning and no `confirmed: true`, returns 409 with the warning and opens nothing. Returns 404 for an account that isn't on the worklist |
| POST | `/api/cases/{slug}/captures/compare` | `{}` → `{changes: [change]}`. Compares every page capture not yet compared with the last capture of the same page: `posts gone`, `post back`, `profile changed` (`field: "page title"`), `account gone` / `account back`, each with `"via": "capture"` and audited. The Check again job runs this too; the capture route should call it after each page capture (docs/qol.md) |
| GET | `/api/cases/{slug}/minimise` | `{ready, why, files: [{file, sha256, bytes, post, kind, source, posted_at}], count, bytes}`. After the retention date, and never on legal hold: raw media of posts that no kept or reported hit and no note points to, plus frames of flags nobody kept |
| POST | `/api/cases/{slug}/minimise` | `{count, bytes}` (exactly what was shown) → `{count, bytes, trashed_as}`. Moves those files to the Trash as one folder. Audited as `media minimised`, with every file's hash. Returns 409 before the retention date, on legal hold, for a different count or size, or while a job runs |
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
