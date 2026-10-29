# Hunt local API

`hunt app` serves the app and this API on `http://127.0.0.1:<random port>`. The browser
opens `/login?t=<token>`, which sets an HttpOnly, SameSite=Strict cookie and redirects to `/`.

## Security rules (enforced by middleware on every request)
- **Host:** must be exactly `127.0.0.1:<port>` or `localhost:<port>`. Anything else gets 403 (blocks DNS rebinding).
- **Cookie:** must carry the launch token (`hmac.compare_digest`), or the request gets 403.
- **Non-GET requests:**
  - `Origin` must be `http://127.0.0.1:<port>` (or the `localhost` form).
  - JSON bodies need `Content-Type: application/json`.
  - Uploads (`/media`, `/facebook`) are `multipart/form-data` with the same Origin check.
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
| POST | `/api/cases/{slug}/facebook` | `multipart/form-data`: `files[]`, `saved_at?` (ISO) → `{added, posts, pages, screenshots, skipped: [name]}`. Details below |
| GET | `/api/cases/{slug}/facebook/links` | `{links: [{label, url}]}`: Facebook search and `site:facebook.com` search-engine links for the case's seeds. For the investigator to open in their own browser; Hunt never requests them |
| GET | `/api/cases/{slug}/posts` | `{counts: {read_automatically, added_by_you, flagged, by_category: {}}, weekly: [{week: "YYYY-Www", posts, flagged}], hits: [hit], posts: [post]}` |
| POST | `/api/cases/{slug}/hits/{id}` | `{status: "kept"\|"not relevant"\|"in report"}` → hit |

- **post:** `{id, source, account_url, url, posted_at, text, origin: "fetched"|"added", media: [{id, kind: "image"|"video"|"screenshot", file, duration}], extra}`
  - `extra` is `null`, except on imported Facebook posts: `{posted_at_precision: "second"|"minute"|"hour"|"day"|"week"|"month"|"year", posted_at_text, author, fb_id, post_id, place, activity, life_event, truncated, reactions, comments, shares, evidence}`, with only the keys found. `evidence` is the stored page the post came from.
  - `posted_at` always starts with `YYYY-MM-DD`: an ISO date-time with an offset when exact, a date-time without one when it's what Facebook displayed (the saving browser's time zone), or a date.
- **hit:** `{id, post_id, media_id, category, what, t0, t1, verdict, p, timing: "before"|"after", days_after, status: "new"|"kept"|"not relevant"|"in report", who: "unknown"|"him"|"other", file, source, posted_at, url, caption}`

Machine verdicts never exceed "likely". Only the investigator's Keep raises an item's status, never the verdict wording.

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

## Report
| Method | Path | Body / response |
|---|---|---|
| GET | `/api/cases/{slug}/report?screening=0\|1` | `{sections: [{id, title, done}], sentences: [{section, text, cites: [id]}], evidence: [{id, date, what, source, verdict, file}], couldnt_see: [str], checks: {every_sentence_cited, files_checked, tampered: [file]}}` |
| GET | `/api/cases/{slug}/report.html` \| `.pdf` \| `.json` `?screening=1` | Downloads. Hashes are re-verified at export |
| GET | `/evidence/{slug}/{sha256}.{ext}` | Evidence file (security rules above) |

Citation ids: `E-<post or hit id>` (evidence), `A-<finding id>` (accounts), `M-<run rowid>` (method).

## Python interface between the server and the scan modules
`hunt/posts.py` and `hunt/scan.py` own their tables (`posts`, `media`, `post_extra`, `hits`) and create them on first use. `emit(event: dict)` is a plain, non-blocking callable.

```python
posts.collect(case, accounts: list[dict], since: str | None, emit) -> int  # Bluesky, Mastodon, YouTube RSS; accounts = [{url, site}]
posts.add_files(case, paths: list[Path], platform: str | None, posted_at: str | None) -> list[int]
posts.add_posts(case, items: list[dict], kind="image", evidence: str | None = None) -> list[int]  # hunt.facebook posts
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

## Quality of life: the Downloads inbox, the evidence bundle, links, Check again, notes
See [qol.md](qol.md) for the screens that use these.

| Method | Path | Body / response |
|---|---|---|
| GET | `/api/cases/{slug}/inbox?folder=&days=7` | `{folder, days, files: [inbox file]}`, newest first. `folder` defaults to `~/Downloads` and must be an absolute path to a folder; `days` is 0–365. Only photos and videos directly in the folder are listed. Nothing changes on disk |
| POST | `/api/cases/{slug}/inbox` | `{folder?, days?, take: [{id, url?, platform?, handle?, posted_at?}], keep?: false}` → `{files: [inbox file + result, trashed]}`. Re-lists the folder and files the chosen ids through `posts.add_files`. The client never sends paths. An id that's gone returns 409. Each original goes to the Trash once its bytes are in the evidence, unless `keep`. Audited as `inbox import` |
| GET | `/api/cases/{slug}/evidence.zip` | Download: `exhibits/`, `manifest.csv`, `SHA256SUMS`, `audit-log.csv`, `notes.csv`, `README.txt`. Header `x-bundle-sha256` carries the zip's hash, which is also audited as `evidence exported` |
| GET | `/api/unfurl?url=` | `{platform, handle, post_id, posted_at, url}`. Works offline. `url` comes back without tracking parameters. `posted_at` is read from TikTok and X post ids |
| POST | `/api/cases/{slug}/recheck` | `{}` → `{job}`. **Check again:** the accounts marked `him` (not email hits) are looked at again. Returns 409 if none are marked, or if the case already has an active job. Takes the heavy lock only while capturing screenshots |
| GET | `/api/cases/{slug}/changes` | `{checks: [{cite, ts, change: "recheck", accounts, new_posts, changes, captured}], changes: [change]}`, newest first. `cite` is the report's `M-a<audit rowid>` |
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
