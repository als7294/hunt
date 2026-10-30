# Compliance audit: main against Hunt's rules

_2026-10-29. Commit `9e1e39c`._

**Method.** Four code readers each took a group of rules from [legal.md's "Hunt's rules"](legal.md#hunts-rules) and read the code, not the docs. Every finding cites file:line at this commit.
- **Offline self-checks run, all printing `ok`:** `test_analysis` (its face-model checks skipped), `test_app`, `test_bundle`, `test_capture`, `test_e2e`, `test_facebook`, `test_hunt`, `test_minimise`, `test_posts`, `test_public`, `test_qol`, `test_recheck`, `test_report`, `test_scan`, `test_seen`, `test_sources`, `test_vendor`, `test_watch` and `test_worklist`. Also user-scanner's own coverage audit, `python -m hunt.sources.user_scanner`: "220 modules: 51 upstream-loud, 42 noisy, 127 silent; unaudited none; gone none".
- **Probes ran with mocked networks only:** `httpx.MockTransport` for every Python request, a mocked `chrome` API under node, and mutated scratch copies of `extension/`.
- **No live platform requests.** The only live reads were three robots.txt files: youtube.com, threads.net and api.github.com. `HUNT_LIVE` was never set.

**Not run:**
- **The face models.** OpenCV and the models aren't installed, so `face.compare` itself never ran.
- **WhatsMyName's live list.** There was no cached copy, so its sites and its POST entries weren't checked.
- **Live tests.** None: no real browser, no `scripts/browser_e2e.py`, no `scripts/validate_wmn.py`.

**Status legend** (the audit's own scale):

| Status | Meaning |
|---|---|
| **Enforced** | The code enforces it on every path the readers found |
| **Partly** | Some paths enforce it; others don't |
| **Not enforced** | At most the data is recorded; nothing acts on it |
| **Policy only** | The rule is about her conduct; code can at most remind her |

**Tags:**
- **[confirmed]**: the coordinator re-checked this finding against the code.
- **[judgement]**: the audit's own view, not a fact about the code.

**Docs only.** This file is the only change. No code, test or other doc was edited, legal.md included. The fixes in "Fixes by owner" are for the main session to hand out.

## 1. Summary

### Counts

| Status | Count | Rules |
|---|---|---|
| Enforced | 4 | C2, C9, K4, F1 (dormant: nothing in the app runs the face check) |
| Partly | 23 | C1, C4, C6, C7, C8, C10, C11, C12, C13, K1, K2, K5, K6, K7, K8, F2, A1, A2, A4, A5, A6, A7, A10 |
| Not enforced | 6 | K3, F3, F4, A3, A8, A9 |
| Policy only | 2 | C3, C5 |

That makes 35 rules. Guided mode isn't a rule of its own; judged against legal.md's description of it, it is **Partly** enforced (G1–G7 below).

### The most serious gaps, ranked by harm [judgement]

1. **Minors' names leak.** The map keeps a minor's name in other entries and other people's quotes, before the relationship word, and in lower case. Photo labels aren't checked. Reports, the UI and the bundle don't redact at all. C13, A5. Owner: analysis (AN1), then app screens (AP1) and QOL (Q1).
2. **The face gate fails open.** `face.gate` (`hunt/face.py:116`) allows any code it doesn't recognise: `UK`, `EL`, `XX`, `US-ZZ` [confirmed], and also `EU`, `GP`, `RE`. It is dormant today, because no app route runs the face check. F2. Owner: analysis (AN2); app screens (AP2).
3. **Unaudited email checks can run.** `user_scanner._skip` (`hunt/sources/user_scanner.py:212`) falls back to a regex for a new module or a changed version, and `pyproject.toml` pins only `>=1.5.2.3` [confirmed]. After a version bump, 25 of the 127 silent modules would run unread, and the regex misses a module that sends a passcode email. WhatsMyName POSTs entries from an unpinned list fetched live. C4. Owner: data sources (DS1, DS4).
4. **Employment reports name family and include unconfirmed accounts.** A background case prints every "likely" account and record. The screening version is opt-in, and its filter keeps "wife", "son", "mom" and co-party captions. K1, A8. Owner: app screens (AP3).
5. **Non-Public content reaches reports.** `audience_flag` is stored and never read, and there's no counsel-approval record. K3. Owner: app screens (AP4); analysis (AN3); capture (CA5).
6. **Automatic requests to default-deny hosts, with spoofed User-Agents and TLS fingerprints.** On every Search:
   - Maigret probes Facebook, Instagram's internal API, X's GraphQL (with a bearer token bundled in its database), LinkedIn, Reddit, Threads and Snapchat. It uses Chrome TLS impersonation on 67 sites; its `CurlCffiChecker` says it is there to "emulate browser TLS fingerprint and bypass WAF" [confirmed].
   - user-scanner checks emails on Instagram and X, and 22 of its running modules impersonate Chrome.
   - WhatsMyName sends a Chrome User-Agent (`sources/wmn.py:23`) [confirmed].

   C6, C7, C11. Owner: data sources (DS2, DS3, DS1, DS4).
7. **Threads is read as Mastodon.** `posts._site` falls through to the Mastodon regex for `/@handle` URLs (`posts.py:329` [confirmed]; the note gives the regex at `:331`). `recheck._read` sends WebFinger requests to threads.net, tiktok.com, youtube.com and medium.com. Both also run on watch's schedule. C6. Owner: collectors (CO1); QOL (Q2).
8. **Apify, and every other automatic read, ignore hard stops.** After a stop on Instagram, `vendor.plan` still schedules the account with `ok: True`. `posts.collect`, headless screenshots and the engines don't check `stops()`. No automatic 429 or CAPTCHA ever records a stop. C8, C12. Owner: capture (CA1, CA4); collectors (CO2, CO3); app screens (AP5).
9. **Guided mode: the lock can be raced, and the wrong profile matches.** Two quick presses give two scrolls. `profile.php?id=N` matches any numeric Facebook profile. The audit is sent after the step and doesn't gate it, and there's no off switch. C1, guided mode G1–G7. Owner: capture (CA2); app screens (AP6).
10. **Collection on associates.** An associate can be added as a seed and searched. `POST /preview` reads any account's feed. Capturing an associate's page keeps, scans and hashes all its posts, and those hashes link cases in `seen.py`. C13, A1, A3, A10. Owner: app screens (AP7); capture (CA3); analysis (AN5); QOL (Q3).
11. **Hunt's own headless shots and batch reads of default-deny hosts.** `search.screenshot` shoots every likely account. Check again and watch screenshot Reddit and Threads, because `recheck.NO_BOTS` lacks Reddit, Threads, Strava and Snapchat [confirmed]. The `facebook` source runs in every batch search. YouTube's disallowed RSS feed is read on watch's schedule. C1, C6. Owner: capture (CA4); QOL (Q4); data sources (DS5); collectors (CO4); app screens (AP8).
12. **Pictures of children are shown and exported unblurred.** Caption, tag, OCR and "model unavailable" hits are always stored with `blur = False`, and report exports embed the originals. K7, A5. Owner: analysis (AN4); app screens (AP9).

## 2. Rule by rule

Fix ids in the Owner column are in section 3. Detail is in section 3 and in the four audit notes (see section 6).

| Rule | Status | Enforced where (file:line) and test | Gap (short) | Owner |
|---|---|---|---|---|
| C1 | Partly | CSP `connect-src 'self' http://127.0.0.1:*` (`extension/manifest.json:79-81`); no fetch in `content.js`; capture copies only (`background.js:190, 203`; `offscreen.js:16`); one click, one page (`app.py:1235, 1501`). Tests: `test_capture.py:454-482, 489, 493` | The static check lets 13 regressions through. Maigret and WMN probe login-walled hosts. `NO_BOTS` lacks Reddit, Strava, Snapchat and Threads [confirmed]. Guided mode has no off switch | CA8, CA2, AP6, DS3, DS4, Q4, CA4 |
| C2 | Enforced | Plain `Popen` launch (`browser.py:150-153`); presence-only cookies (`background.js:100-110, 437`); no `web_accessible_resources`. Tests: `test_capture.py:261-263, 306, 317, 495-496` | The cookie tripwire lets `const { value } = …` through. The banned-flag assert checks `launched[0]` only | CA8 |
| C3 | Policy only | `STOP_MESSAGE` (`browser.py:33-34`), shown in the popup only; stops persist in `stops.json`. Tests: `test_capture.py:415-417` | Hunt's screens give no account guidance and show no stop. A sign-in after a ban goes unnoticed, and the handle can change while stopped | AP18, CA9 |
| C4 | Partly | No contact actions in `hunt/` or `extension/`. user-scanner: `NOTIFIES` always skipped (`user_scanner.py:217`), `AUDITED_SILENT` only at `AUDITED` (`:219`). No test imports `user_scanner` | `_skip` fails open (`:212`) and the pin is only `>=1.5.2.3` [confirmed]. WMN POSTs from an unpinned list. Maigret is a floor too (`>=0.6.6`). Nothing asks before her own follow, like or message | DS1, DS4, DS3, CA7 |
| C5 | Policy only | The extension never submits (`test_capture.py:472-476`); no persona features | No screen states the rule. `requestSubmit()` and `HTMLElement.prototype.click.call` pass the ban | AP18, CA8 |
| C6 | Partly | `public._walled` (`public.py:167-172`; `test_public.py:216-229`); `posts._site` is None for X, LinkedIn, Reddit (`posts.py:322-333`); TikTok paths only (`public.py:100-129`; `test_public.py:170-199`); honest UA on API sources (`_api.py:10`) | `facebook` source in batch; `search.screenshot`; YouTube RSS (pinned by `test_public.py:212-214`); Maigret, user-scanner and WMN on deny hosts; Threads read as Mastodon; Reddit and Threads recaptures; no TikTok gap | DS2–DS5, CA4, CO1, CO4, CO5, Q2, Q4, AP8 |
| C7 | Partly | No CAPTCHA solving; one fixed `HUNT_PROXY` (`test_sources.py:543-581`); yt-dlp flags (`public.py:234-238`; `test_public.py:238-244`); `Limited` on 429 (`_api.py:22-32`) | The engines spoof UAs and TLS (67 Maigret sites, 22 user-scanner modules). TikTok carries on after a 429, and `test_public.py:237` asserts it. `capture.screenshots` detects no wall. yt-dlp impersonation is latent | DS1, DS3, DS4, CO3, CO6, CA4, AP8 |
| C8 | Partly (capture only) | `browser.stop` and `stops()` (`browser.py:188-201`); upload and guided routes refuse (`app.py:1543-1544, 1616-1617`); revocation watcher (`extension.py:45-56, 329-334, 381-384`). Test: `test_capture.py:411-421` | `vendor.plan` ignores stops: the known gap, still open. No other automatic read checks a stop or records one | CA1, CO2, CO3, CA4, AP5, CA10 |
| C9 | Enforced | `SITE` allowlist (`background.js:21`); `matches` (`manifest.json:48-64`); `CAPTURE_OFF` (`extension.py:43`); 403s (`app.py:1541-1542, 1616-1617`). Tests: `test_capture.py:187, 245, 297, 429-431, 437, 486-488` | Minor: `guidedOpen` doesn't check its destination. No test keeps `web_accessible_resources` absent | CA2, CA8 |
| C10 | Partly | Story `confirm()` (`content.js:56-65`); LinkedIn repeat-view warning (`recheck.py:70, 353-357`; `test_worklist.py:52-60`); popup banner (`popup.js:53`) | The Story warning shows only on `signed_in`, and middle-click and auto-advance skip it. No behaviour test (`test_capture.py:483` checks the string). LinkedIn pacing sees worklist opens only | CA6, AP12 |
| C11 | Partly | No barred connector in Hunt's code; YouTube on the Data API with her key (`public.py:132-164, 181-189`; `test_public.py:201-211`) | Maigret calls X's internal GraphQL with a bundled bearer token and mints guest tokens. Maigret and user-scanner call Instagram, Reddit and X internal endpoints. Without a key, YouTube uses RSS | DS3, DS1, CO4 |
| C12 | Partly | Off by default, her key only (`vendor.py:73, 279-280`; `app.py:579`); provenance and audit (`vendor.py:40, 175-180, 232-233`); spend caps. Tests: `test_vendor.py:17, 43, 89-99, 132, 142-148, 159-160` | The bundle labels vendor media "added by the investigator" (`bundle.py:126`). The report never says Apify. No `stops()` check | Q5, AP16, CO2, CO7 |
| C13 | Partly | `graph.associates` reads stored data only (`graph.py:208-307`); a minor's name is set to None (`:231-237`). Tests: `test_analysis.py:333, 336, 337` | Minors' names survive in other entries and quotes, before the word and in lower case. No redaction in the report, UI or bundle. Seeds, preview and capture collect on associates | AN1, AP1, Q1, AP7, CA3 |
| Guided mode (legal.md text, not a rule id) | Partly | One input (`manifest.json:72-77`; `background.js:448-451`; `popup.js:137-145`); one move (`content.js:35-37`; `background.js:329-332`); audited (`extension.py:401-403`) | G1 lock race. G2 `profile.php` match. G3 audit after the step. G4 manual mode never captured. G5 wrong archive unlocks. G6 no off switch. G7 destination unchecked | CA2, AP6 |
| K1 | Partly | Purpose required (`case.py:62-64`; `cli.py:146-149`; `app.py:445-446`; `test_hunt.py:130-134`; `test_app.py:87`); kind in `KINDS` (`app.py:447-448`); FCRA text (`report.py:558`); screening (`report.py:49-51, 59`; `test_report.py:166-176, 211-218`) | Unconfirmed likely accounts reach background reports. Screening is opt-in. The CLI records no kind. `PROTECTED` is narrow. No test that a background case carries FCRA | AP3, AP14 |
| K2 | Partly | `Case.audit` (`case.py:148-149`) for queries, captures, imports, worklist opens, stops and exports. Tests: `test_hunt.py:152`; `test_capture.py:364-366, 421`; `test_bundle.py:73-74` | A hard stop with no capture target isn't audited (`browser.py:198`; `app.py:1603-1604`). "Seen before" lookups are never audited. No test of `report exported` | CA10, AP17 |
| K3 | Not enforced | `audience_flag` stored (`extension.py:373`; `test_capture.py:369-375`) | Nothing reads it. No counsel-approval record. Views and recordings carry no audience | AP4, AN3, CA5 |
| K4 | Enforced | Hits start `new`, capped at 0.79 (`scan.py:51, 131, 305-309, 402`); only `KEPT` reaches findings (`report.py:63, 262-263`); `report.cap()`. Tests: `test_report.py:88-89, 115`; `test_scan.py:132, 139, 267-268` | Minor: `kept` also means reported. The undated bullet cites `new` hits. Export isn't blocked while hits are `new` | AP15 |
| K5 | Partly | `extension.record()` (`extension.py:317-326`); hash on landing (`case.py:231-246`); manifest columns (`bundle.py:35-38, 210-214`); README (`bundle.py:55-90, 188-193`). Tests: `test_capture.py:362-366`; `test_bundle.py:113-133` | Views and recordings lack audience. `viewed_at` isn't checked. Six README sentences aren't true of the code | Q5, CA5, CA11, CA4 |
| K6 | Partly | 90 days and hold (`case.py:28, 123-129, 140-146`); delete to the Trash (`app.py:802-812`; `inbox.py:201-210`). Tests: `test_e2e.py:277-298`; `test_watch.py:154-167`; `test_minimise.py:40-47` | Advisory: searches, scans, previews, captures and the CLI run past retention (the CLI on closed cases too). `deleted-cases.log` keeps the label and the purpose (`app.py:819`) [confirmed] | AP10, AP13 |
| K7 | Partly | `child_visible` → `blur` (`vlm.py:106, 130-142`; `scan.py:236-238`); CSS blur (`app.css:127-129, 153-155`). Test: `test_scan.py:142-143` | Caption, tag, OCR and "model unavailable" hits always `blur = False`. Report exports embed originals | AN4, AP9 |
| K8 | Partly | `Limited` per source (`_api.py:22-32`; `stackexchange.py:35-36`); module-wide pacing in `facebook`, `stackexchange`, `geo`. Tests: `test_sources.py:104-109, 129-130, 194-195, 212-219, 248-250, 278-279, 364-376` | `fan_out` runs every seed at once, so pacing and the stop don't hold across seeds. Socrata sends every dataset at once. Six sources have no 429 test. No TikTok gap | AP5, DS6, DS7, CO5, CO3 |
| F1 | Enforced (dormant) | 1:1 against the case's own references (`face.py:90-111, 183-202`); vectors in memory only (`face.py:290-304, 336-338`). Tests: `test_analysis.py:198-206, 243-268` (model checks skipped) | `face.compare()` is public and ungated. The face check isn't wired into the app. No test that nothing is written to disk | AN11 |
| F2 | Partly | `BLOCKED` and `EEA` (`face.py:68-77`); `gate()` audited (`face.py:116-126`); runs in `enable()` and `verify_all()` (`face.py:140, 185-187`). Test: `test_analysis.py:222-236` | Fails open on unlisted codes: `UK`, `EL`, `XX`, `US-ZZ` [confirmed], `EU`, `GP`, `RE`. No CA counsel path. Residence isn't in the UI | AN2, AP2 |
| F3 | Not enforced | `Case.mhmda` for US-WA (`case.py:111-115`); `mhmda_basis` optional. Test: `test_analysis.py:237-238` | `case.mhmda` is never read. The basis isn't required or printed. Health wording is unchanged | AP11, AN10 |
| F4 | Not enforced | Only effect: GB, CA and the EEA are blocked from the face check (`face.py:74-75, 121-123`; `test_analysis.py:224`) | No basis field and no no-notice field. Collection runs on the general purpose alone | AP10 |
| A1 | Partly | The map reads stored data only; Check again and watch act only on "him" (`recheck.py:76-80`; `app.py:1083`) | Associates are accepted as seeds (`app.py:526-531`). `/preview` reads any account (`app.py:843-858`). `pivot.suggestions` would offer associates' handles | AP7, AN8 |
| A2 | Partly | Entry fields (`graph.py:231-243`); quotes ≤200 characters. Test: `test_analysis.py:326-337` | "same address" stores an address, and `test_analysis.py:330` asserts it. Quotes are unfiltered | AN6 |
| A3 | Not enforced | The map ignores others' posts (`graph.py:245-248`); comments aren't stored (`hunt/facebook.py:462-464`) | Capture stores every post on an associate's page, and the scan reads them. `/preview` reads their whole feed | CA3, AN5, AP7 |
| A4 | Partly | No contact code; the Story warning covers anyone's Story (`content.js:55-65`, no test) | No prompt before her own follow, like or message. No LinkedIn view warning outside the worklist | CA7, CA6, AP12 |
| A5 | Partly | As C13 (`graph.py:172-177, 185, 205, 226, 229-237`); CSS blur from `hits.blur` (`app.js:587-594`) | All the C13 gaps. Photo labels name minors. Labels say "son" or "daughter", not "a child" | AN1, AP1, Q1, AN4, AP9 |
| A6 | Partly (report: by absence) | `report.py` doesn't call `graph`; notes print as `N-` (`report.py:470-478`) | `graph.associates` generates "mother", "parent" and "possible relative", and `test_analysis.py:331` asserts it. analysis.md §8 specifies "Brother: Dan" | AN7 |
| A7 | Partly | No identity or findings logic on associates (`match.py`, `report.py`, `clues.py`); `who='unknown'` (`scan.py:11`) | Associates' captured posts can become findings, unmarked | CA3, AN5, AP19 |
| A8 | Not enforced | The screening filter is `PROTECTED` alone (`report.py:49-51, 225, 259-261`; `test_report.py:169, 218`) | "wife", "son", "mom" and co-party captions survive. `/people` serves background cases (`app.py:644-648`) | AP3 |
| A9 | Not enforced | None | Associates' health is kept in quotes, captions and captured posts. `PROTECTED` lacks chemo, surgery, hospital and cancer | AN6, AP3 |
| A10 | Partly | `seen.identifiers` uses seeds, "him" accounts and media hashes (`seen.py:29-38`; `test_seen.py:42-48`); learning store salted and unwired (`learning.py:58-72, 229`) | Media hashes from associates' pages become cross-case identifiers, and so do associate seeds. The entry `id` is the same in every case. No test that associates are absent | Q3, AN9 |

## 3. Fixes by owner

This is the hand-out list. Inside each owner, fixes run from most to least serious, following the ranking in section 1 [judgement].

**Land these first.** Other owners call them:
- **DS2**, the one deny list: `_api.denied(url)`.
- **CA1**, the one stop check: `browser.stopped(url)`.
- **AN1**, the one minor pass: the minor names `graph.associates` marks.

**Owners and modules:**

| Owner | Modules | Fixes |
|---|---|---|
| collectors | `hunt/public.py`, `hunt/vendor.py`, `hunt/posts.py` | CO1–CO7 |
| capture | `extension/`, `hunt/capture.py`, `hunt/extension.py`, `hunt/browser.py` | CA1–CA11 |
| QOL | `watch.py`, `recheck.py`, `bundle.py`; also `seen.py` (not on the list; qol.md documents it) | Q1–Q5 |
| analysis | `match.py`, `graph.py`, `face.py`, `minimise.py`, `pivot.py`, `similar.py`, `learning.py`; also `scan.py` (not on the list; analysis is nearest) | AN1–AN11 |
| app screens | `hunt/static`, `app.py`, `report.py`, `search.py`; also `case.py` and `cli.py` (not on the list; app screens is nearest) | AP1–AP19 |
| data sources and courts | `hunt/sources/`, and their pins in `pyproject.toml` | DS1–DS7 |

**Existing tests that enshrine a gap.** Change these with the fix:
- `test_public.py:237` asserts the TikTok run carries on after a 429: `[VID, BLOCKED, SECOND, SECOND]` (CO3).
- `test_public.py:212-214` asserts the RSS read without a key (CO4).
- `test_public.py:222-228` previews an unconfirmed account, `@nasa` (AP7).
- `test_analysis.py:330` asserts `Marta Ruiz` → `["same address"]` (AN6).
- `test_analysis.py:331` asserts the "possible relative" type (AN7).

**Tests that would pass with the guard broken:**
- `test_capture.py:483` checks only that the Story warning string exists (CA6).
- `test_capture.py:263` checks the banned flags on `launched[0]` only (CA8).
- `test_capture.py:495-496`: the `.value` check can be slipped past (CA8).
- `test_recheck.py:123` tests only the Instagram exclusion (Q4).
- `test_report.py:102` checks only an insurance case, so nothing checks that a background case carries FCRA (AP3).

### 3.1 Collectors (`hunt/public.py`, `hunt/vendor.py`, `hunt/posts.py`)

**CO1. Threads and other `/@handle` hosts aren't Mastodon** (C6)
- **Where:** `posts._site` (`posts.py:322-333`). Its fallback regex `https?://[^/]+/@[^/?#]+/?$` is at `:331`; the coordinator confirmed the fall-through at `:329` [confirmed].
- **Change:** `if _api.denied(url): return None` before the Mastodon rule (DS2). Today Scan, Check again and watch GET `www.threads.net/api/v1/accounts/lookup`.
- **Test:** in `test_public.py`, the route sees no request to `*.threads.net` for a confirmed `https://www.threads.net/@jane`.
- **Also:** QOL's Q2 needs the same guard in `recheck._read`.

**CO2. Apify skips a stopped platform** (C8, C12)
- **Where:** `vendor.plan` (`vendor.py:101-141`).
- **Change:** if `browser.stopped(a["url"])` (CA1), put the account in `skipped` with `why = stop["message"]`. This one guard covers `vendor.collect` (`vendor.py:144-184`), the `/vendor` plan route (`app.py:558-563`) and `/scan` (`app.py:578-580`). A probe confirmed the gap: after `browser.stop("Instagram", …)`, `plan()` still schedules the account with `ok: True`.
- **Test:** in `test_vendor.py`, after `browser.stop("Instagram", "test")`, `plan()` skips Instagram with the stop message and still runs Facebook. `calls` holds no `POST …/acts/apify~instagram-post-scraper/runs`.

**CO3. Automatic post reads honour stops, and stop a platform at its first wall** (C7, C8, K8)
- **Where:** `posts.collect` (`posts.py:59-89`; the wall is caught at `:76-87`); `public._tt_wall` (`public.py:217-229`); `public.download`.
- **Change:**
  - Add `public.Wall(ValueError)`. `_tt_wall` raises it for a 429, a CAPTCHA, a login redirect and status 10204. `download()` raises it when yt-dlp reports one.
  - Before reading an account, skip it if `browser.stopped(url)`, with a "failed" note carrying the stop message. That covers Scan, Check again, watch and Read public preview.
  - On the first `Wall`, skip that platform's remaining accounts for this run, noting "stopped after a 429 on …". Call `browser.stop(platform, reason, url, case)` with a message worded for automatic reads. Whether a 429 should set a hard stop is decision D8.
- **Test (`test_public.py`):**
  - Change `test_public.py:237` so that after `BLOCKED`'s 429, no further TikTok yt-dlp run happens.
  - After `@limited`'s 429, `@gone/video/1` is never requested. `"TikTok" in browser.stops()`, and there's an audited `capture hard stop`.
  - After `browser.stop("TikTok", …)`, no request reaches `www.tiktok.com`.

**CO4. No YouTube RSS** (C6, C11)
- **Where:** `public._youtube` (`public.py:134-135`) falls back to `posts._youtube` (`posts.py:293-316`), which reads `YT_RSS` (`posts.py:39, 302`).
- **Change:** without `HUNT_YOUTUBE_KEY`, raise `ValueError("YouTube's robots.txt disallows its feed; add a free YouTube Data API key (Connect free keys)")`. Delete `posts._youtube` and `YT_RSS`. Update `posts.py`'s docstring and tools.md's "RSS without a key".
- **Test:** replace `test_public.py:212-214` with: no key → status failed, the note names `HUNT_YOUTUBE_KEY`, and the route saw no `/feeds/videos.xml`.

**CO5. A polite gap on TikTok page reads** (C6, K8)
- **Where:** `public._tiktok` and `_tiktok_post` (`public.py:104, 120`); the account loop in `posts.collect` (`posts.py:66-87`). Today `SLEEP` reaches only yt-dlp's `--sleep-requests` (`public.py:43, 236`). tools.md says "a second apart".
- **Change:** keep a module-level last-request time in `public.py`, as `sources/facebook.py:26-55` does, and sleep `SLEEP` before each page GET.
- **Test:** in `test_public.py`, set `SLEEP = 0.05`, record request times in `route`, and assert successive `www.tiktok.com` GETs are at least 0.05 s apart.

**CO6. Refuse to run yt-dlp if it could impersonate** (C7)
- **Where:** `public.py`, before any yt-dlp run. yt-dlp's TikTok extractor asks for `impersonate=True` (`yt_dlp/extractor/tiktok.py:281`). With curl_cffi 0.17.0, no target is available, so today it can't. A supported curl_cffi version would turn it on silently.
- **Change:** if `YoutubeDL()._get_available_impersonate_targets()` isn't empty, refuse to run.
- **Test:** in `test_public.py`, `YoutubeDL()._get_available_impersonate_targets() == []`, or else the run is refused.

**CO7. Docs: the key file** (C12)
- `vendor.py:13`'s docstring and vendors.md say the key is kept in `HUNT_HOME/keys.json`, but `keys.py` writes `keys.env`. Fix the text. No test.

### 3.2 Capture (`extension/`, `hunt/capture.py`, `hunt/extension.py`, `hunt/browser.py`)

**CA1. One stop check: `browser.stopped(url)`** (C8). Shared.
- **Where:** new `stopped(url) -> dict | None` in `hunt/browser.py`.
- **Change:** return `stops().get(extension.platform(url))`. Map by `extension.platform`, because `vendor.site` returns lowercase keys (`"instagram"`) and `stops()` uses `"Instagram"`.
- **Callers:** CO2 (`vendor.plan`), CO3 (`posts.collect`), CA4 (`capture.screenshots`), AP5 (`search.fan_out`, and through it the engine exclusions in DS3 and DS4).
- **Caution [judgement]:** `extension.platform` has no Threads (`extension.py:36-38`) and returns None for any `http://` URL (`extension.py:149-150`), so this check alone misses those. The deny list (DS2) covers them.
- **Test:** through the callers' tests (CO2, CO3, CA4).

**CA2. Guided mode: one gate** (C1, C9; G1–G7). App screens does the `app.py` side as AP6.
- **Where:** `extension/background.js`: `guidedNext` (it checks `guiding[tab.id]` at `:295`, awaits `account()` at `:284` and a tab message at `:308`, and only then locks at `:310`), `lock()` (`:274`), `archive()` (`:200, 217-220`), `guidedBlock` (`:290-298`), `guidedOpen` (`:329-332`), `view()` (`:233`).
- **Change:**
  - **G1, the race.** Add a module-level `stepping` flag, set synchronously on entry to `guidedNext` and cleared in `finally`. `lock()` calls `clearTimeout` first, so a stale 20 s timer can't release a later lock.
  - **G3, the audit gates the step.** `await api("guided", …)` before `chrome.tabs.sendMessage(…guided-scroll)` and before `guidedOpen`, and abort on error. Today it is fire-and-forget after the step (`:313-314, 324-325`).
  - **G2, the match.** Stop trusting `norm()` (`:281`), which strips the query string. The server decides (AP6).
  - **G4, manual mode.** `guidedBlock` refuses when `s.mode === "manual"`. When the 20 s timer (`GUIDE_MAX`, `:33`) fires with no capture, report a problem and audit `guided step not recorded`. The legal.md wording is decision D3.
  - **G5, the wrong archive.** Store `t.guidedAt = now`, and unlock only from an archive that started after it.
  - **G6, the off switch.** `guidedBlock` refuses while `hello` says `guided: false` (AP6).
  - **G7 and C9, the destination.** `guidedOpen` refuses unless `SITE.test(url)`, `siteOf(url) === siteOf(currentTab.url)`, and the path has no `/stories/`.
- **Tests:**
  - **Static (`test_capture.py`):**
    - `guidedNext`'s body has no loop or timer;
    - the only sender of `"guided-scroll"` is inside `guidedNext`, once;
    - `guidedNext` and `guidedOpen` appear only in `onCommand` and `handle("next")`;
    - in `guidedNext`, `await api("guided"` comes before `guided-scroll` and `guidedOpen(`;
    - no identifier `guidedScroll` or `guidedOpen` is passed as a value (`/guided(Scroll|Open)\b(?!\()/`);
    - `guidedOpen`'s body contains `SITE.test(`.
  - **Behaviour:** a `vm` harness like `race.js`:
    - two synchronous `guided-next` commands give exactly one move;
    - a `profile.php?id=555` tab against a subject with `id=…012` is refused;
    - mode `manual` is refused;
    - an audit returning 403 gives no move.

    Node isn't a declared dependency, so a Python test should run it when `node` is present and skip otherwise.

**CA3. Associates' pages: keep the archive, store only posts about the subject** (A3, A7, C13, A10)
- **Where:** `extension.add_page` (`extension.py:362-385`), `add_view` (`:348-360`), `add_recording`. Today they store every post on whatever page she opens, an associate's included.
- **Change:** when `account_of(url)` isn't a confirmed account, keep the archive as evidence (K5). Store as posts only the items whose text mentions a subject name or handle, or that carry `extra.with` or `tagged` with the subject. Mark the rest `extra.not_subject = true`. AN5 then skips them in the scan, and AP19 keeps them out of findings.
- **Ambiguity:** the note says both "store only" the matching items and "mark the rest", and its test expects one stored post. Pick one reading when building it. Whether the archive itself may be kept is decision D12.
- **Test:** in `test_capture.py`, a captured page from an unconfirmed account, with one post that mentions the subject and one that doesn't, stores one post.

**CA4. One guard in `capture.screenshots`** (C1, C6, C7, C8, K5)
- **Where:** `hunt/capture.py:9-29`. It makes a fresh, non-persistent headless context at `:12-13`.
- **Change:**
  - Skip any URL that `_api.denied` matches (DS2), returning `PermissionError("robots.txt denies unnamed agents; open it from the worklist")` for it.
  - Skip any URL where `browser.stopped(url)` is set (CA1).
  - After `goto`, check the response status (429, 403), the URL (`/login`, `/checkpoint`, `/challenge`) and the page text (`extension.REVOKED_TEXT`). On a hit, return an exception for that URL and skip the remaining URLs on that host. Put the check in a pure function, `capture.wall(status, url, text)`.
  - **User-Agent:** either give the context an honest one (C6 prefers that), or have Q5 change the README to say "screenshots identify themselves as headless Chrome". Today it is `… HeadlessChrome/156.0.8078.4 Safari/537.36`.
- **Covers:** `search.screenshot` (`search.py:222-241`, app screens) and `recheck._recapture` (`recheck.py:223-243`, QOL). After this, `recheck.NO_BOTS` can go (Q4).
- **Tests:**
  - unit asserts on `capture.wall(…)`, since Playwright isn't run offline;
  - in `test_recheck.py`, add Reddit, Threads and `http://www.facebook.com/…` accounts and assert they're absent from `shot[-1]`; with TikTok stopped, a TikTok account is absent too;
  - a stubbed `search.screenshot` test (`test_e2e.py` already stubs `search.screenshots`): Facebook, Instagram, X, LinkedIn, Threads and Reddit candidates marked "him" never reach the stub.

**CA5. Audience on views and recordings** (K3, K5)
- **Where:** `extension.add_view` and `add_recording` (`extension.py:347-358, 384-397`) take `rec` from `extension.record()` (`:317-326`), which has no audience. The app ignores any audience the extension sends (`app.py:1570-1573`).
- **Change:** record `audience` from the page with the same `_audience` readers, and set `audience_flag`.
- **Test:** in `test_capture.py`, a view capture's post has `audience` set.

**CA6. The Story warning fails closed** (C10, A4)
- **Where:** `extension/content.js:56-65` (the state check is at `:60`; the start-up `on?` reply at `:12-13` leaves `signedIn = {}` if it fails); `background.js:437` (`cookies.onChanged`) and `:439-444` (`tabs.onUpdated`).
- **Change:**
  - Warn unless the state is `signed_out`: change `!== "signed_in"` to `=== "signed_out"`.
  - Register the same handler for `auxclick`.
  - Add one sentence to the confirm text: "Instagram and Facebook then move on to other people's Stories by themselves; they can see you too."
  - Call `badge()` from the `cookies.onChanged` listener, so open tabs learn she just signed in.
  - In `tabs.onUpdated`, when a signed-in Instagram or Facebook tab reaches `/stories/<user>/` for a user other than the one she confirmed, report a problem: "now viewing @user's Story; they can see you".
- **Test:** a node or `vm` harness of `content.js` with a fake DOM, about 40 lines, like `race.js`. A click on `a[href="/stories/x/"]` with the state `unknown` calls `confirm`. Cancel sets `defaultPrevented`. `auxclick` is covered too.
- **Still not covered:** "Open link in new tab", a typed or pasted `/stories/` address, and Story rings with no link or label (capture.md admits this one).

**CA7. Ask before her own contact clicks; a LinkedIn view notice** (C4, A4)
- **Where:** `extension/content.js`.
- **Change:**
  - When she's signed in, ask before a click on a follow, add-friend, connect, like, react, comment or message control (matched by aria-label or text), as the `STORY` handler does. Report an override to Hunt, which audits it.
  - On LinkedIn `/in/` pages while she's signed in, show a view notice once per profile per 7 days, mirroring `recheck.LINKEDIN_GAP`, with the list kept in `chrome.storage`. Content scripts don't run on LinkedIn today, though `host_permissions` includes linkedin.com; see decision D13.
- **Test:** a static check in `test_capture.py` that `content.js` defines that selector and calls `confirm`. There's no JS harness for it.

**CA8. Harden the static test and the CSP** (C1, C2, C5, C9)
- **Where:** `test_capture.py:454-496`; `extension/manifest.json:79-81`.
- **Change:**
  - **Add to the banned list:** `\bscroll\(`, `scrollTop\s*[+\-]?=`, `scrollIntoViewIfNeeded`, `\.focus\(`, `\.play\(`, `\.load\(`, `currentTime\s*=`, `window\.open\(|\bopen\(`, `windows\.create`, `tabs\.duplicate`, `requestSubmit`, `\.click\b` (not just `.click(`), `location\.\w+\s*=[^=]`, `new Image\b`, `createElement\(`, `EventSource`, `import\(`.
  - **For `content.js`, also ban:** `\b(append|prepend|before|after|replaceWith|insertBefore|replaceChildren)\(`, `outerHTML\s*=` and `document\.write`.
  - **Forbidden permissions:** add `"alarms"`, `"nativeMessaging"`, `"proxy"`, `"userScripts"` and `"declarativeNetRequest"` to the assert at `:493`.
  - **CSP:** `default-src 'self'; script-src 'self'; object-src 'self'; connect-src 'self' http://127.0.0.1:*`, asserted at `:489`. Today there's no `default-src` or `img-src`, so `new Image().src` loads from any host.
  - **Cookies:** replace the `.value` test with a positive one. `chrome.cookies.get(` occurs once, and its result is used only as a truthy test (`/\(await chrome\.cookies\.get\([^)]*\)\)\s*\?/`). `cookie\.(?!name\b)\w+` and `\bvalue\b` never occur in `background.js`.
  - **Launch flags:** run the banned-flag assert over every entry in `launched`, not just `launched[0]` (`:263`). The `--window-size` launch at `:444` is checked for that flag only today.
  - **Detection:** assert `"web_accessible_resources" not in manifest`.
- **Check:** each regression in the browser-capture note's mutation table is now caught. The scratch harness `run_static.py` can re-run them (section 6). A regex scan stays a tripwire, not a proof; CA2's and CA6's behaviour tests are the real check.

**CA9. Notice a sign-in after a hard stop** (C3)
- **Where:** `browser.record()` (`browser.py:231-242`); `set_accounts()` (`browser.py:181-185`).
- **Change:**
  - If a platform in `stops()` was `signed_out` and is now `signed_in`, add a problem ("You signed in to {platform} again after a hard stop: use no other account") and audit `sign-in after hard stop` in the active case.
  - In `set_accounts()`, refuse a changed handle for a stopped platform (ValueError → 409).
- **Tests (`test_capture.py`):**
  - Stop Instagram, post `signins` with instagram `signed_out` then `signed_in`, and assert the newest problem names the hard stop.
  - `POST /api/browser/accounts {"instagram": "other"}` while stopped → 409.

**CA10. Audit every hard stop** (K2, C8)
- **Where:** `browser.stop()` (`browser.py:193-201`) writes to a case only `if case is not None` (`:198`). `capture_revoked` passes None whenever no case is the capture target (`app.py:1603-1604`).
- **Change:** always add one line (time, platform, reason, url) to a machine-level log under `HOME`, such as `hard-stops.log`. Also audit it in every open case with a confirmed account on that platform, not only the capture target.
- **Test:** in `test_capture.py`, `POST /api/capture/revoked` with capture off leaves a durable record.

**CA11. Capture times in UTC** (K5)
- **Where:** `_record`, used by the capture routes in `app.py`. `viewed_at` is taken as sent (`app.py:1570-1573`).
- **Change:** parse `viewed_at` and `started_at`, and store them normalised to UTC (`…Z`), or `None`.
- **Test:** none proposed in the notes.

### 3.3 QOL (`watch.py`, `recheck.py`, `bundle.py`; also `seen.py`)

**Q1. The bundle names no minor in photo labels** (C13, A5)
- **Where:** `bundle.py:196-197` writes the label from every "person marked in photo" (`graph.py:317`) into `audit-log.csv`.
- **Change:** log the label as `"label": "(withheld)"` when AN1 marks it as a minor's. Or keep labels out of `audit-log.csv`, in the case db only.
- **Not covered:** `notes.csv` carries notes as written, and the notes propose no fix for it.
- **Test:** none proposed in the notes. AN1's tests cover the map.

**Q2. `recheck._read` uses the deny list** (C6)
- **Where:** `recheck._read` and its `MASTODON` regex (`recheck.py:67, 151-152`).
- **Change:** use the shared guard (`_api.denied`), or `posts._site(…) == "mastodon"` (CO1), instead of its own regex. Today it sends WebFinger requests to `www.threads.net/.well-known/webfinger`, and to tiktok.com, youtube.com and medium.com, on every Check again and watch run. It then records those accounts as "gone" in `profile_checks`.
- **Test:** in `test_recheck.py`, `_read("https://www.threads.net/@x")` and `_read("https://www.tiktok.com/@x")` make no request.

**Q3. `seen.py` compares only the subject's media** (A10)
- **Where:** `seen.identifiers` (`seen.py:29-38`), which hashes every media file in the case.
- **Change:** hash only media whose post's `account_url` is an account marked "him", or that has `origin='added'`.
- **Tests (`test_seen.py`):**
  - a case holding a captured post from an unconfirmed account doesn't match another case holding the same file;
  - after `graph.label_photo(c, …, "Dan")` and a post naming "my brother Dan Vell", `("name", "dan vell") not in seen.identifiers(c)`.

**Q4. Headless recaptures: none of default-deny hosts** (C1, C6)
- **Where:** `recheck._recapture` (`recheck.py:223-243`); `NO_BOTS` (`recheck.py:68`, which lacks Reddit, Threads, Strava and Snapchat [confirmed]). `watch.py` runs it on a schedule.
- **Change:** the notes give two forms:
  - **(a)** once CA4 guards `capture.screenshots`, drop `NO_BOTS` (collectors note);
  - **(b)** make the recapture an allowlist of TikTok, YouTube, Bluesky and Mastodon (browser-capture note).

  [judgement] (b) also catches any login-walled host missing from the deny list, such as Strava and Snapchat (decision D2). The two can coexist.
- **Test:** in `test_recheck.py`, a confirmed Reddit, Strava, Snapchat or Threads URL isn't passed to `screenshots`. This extends `test_recheck.py:123`.

**Q5. The bundle README tells the truth, and vendor media gets its own label** (C12, K5)
- **Where:** `bundle.describe()`, whose mapping at `bundle.py:126` sends any origin other than `fetched` or `captured` to `ADDED`; `COLLECTED` (`bundle.py:55-90`); `_record_sentence` (`bundle.py:217-222`).
- **Change:**
  - **Vendor media.** Add one `VENDOR` label, map `origin 'vendor'` to it at `:126`, and add a fourth numbered way to `COLLECTED`, only when such rows exist. The notes word it two ways; pick one:
    - "obtained through a vendor (Apify) under the investigator's own account" (C12);
    - "read through a licensed data vendor (Apify) with the investigator's key" (K5).

    Treat scan frames the same way: say "four ways", or move frames into the leads paragraph.
  - **Signed-out captures.** Make sentence 2 depend on the manifest: "signed in to her own account, or signed out, as manifest.csv's viewed_as column shows".
  - **Guided mode.** When the audit has `guided step` rows, replace "did not … scroll … or open anything" with "…except that, in guided mode, each press of Next scrolled one screen or opened the next listed item; each such step is in audit-log.csv as 'guided step'".
  - **Leads.** Change "leads the investigator reviewed" to "leads for the investigator to review", or keep the original only when no hit is `new`.
  - **User-Agent.** Make the sentence match what `capture.py` sets (CA4). docs/qol.md item 19 already says this sentence should follow the sources.
- **Tests (`test_bundle.py`):**
  - a vendor-origin post's media row has `collected != bundle.ADDED`, and the README names the vendor;
  - with a `guided step` audit row, the README doesn't contain "did not load, scroll";
  - with `viewed_as = "logged out"`, the README doesn't say only "signed in to her own account";
  - the README's User-Agent sentence matches what `capture.py` sets.
- **No fix in the notes for:**
  - the bundle's own `evidence exported` row, written after the zip (`bundle.py:206`), so it never appears in that bundle's `audit-log.csv`;
  - a screening form of the bundle. For a background case, `bundle.make` still ships the FEC and NPI page sources and their `source run` rows.

### 3.4 Analysis (`match.py`, `graph.py`, `face.py`, `minimise.py`, `pivot.py`, `similar.py`, `learning.py`; also `scan.py`)

**AN1. One minor pass in `graph.associates`** (C13, A5). Shared: AP1 (report and UI) and Q1 (bundle) redact the names it marks.
- **Where:** `graph.associates` (`graph.py:208-307`): `RELATIONS` (`:172-177, 185`), `AGE_MINOR` (`:205`), redaction (`:231-237`), photo labels (`:286-289`).
- **What leaks today** (probes 1, 2 and 7, and `probe_minor2.py`):
  - "my son Leo Vell" in one post and "Dinner with Leo Vell" in another give a named `Leo Vell` entry ("tagged with") beside the unnamed son. Their keys differ (`:229-230` against `:230`). The same happens with `extra.with`.
  - In "My son Leo and my brother Dan", Dan's quote keeps "Leo", because `:237` redacts only the minor's own cite.
  - "Gym with Leo Vell, my stepson" gives a minor entry whose own quote still reads "Leo Vell".
  - "my daughter emma" stays as written: the redaction is a case-sensitive `re.sub` on one exact string.
  - Ages it misses: "age 9", "(16yo)", "is 15", "16th birthday", "5-year-old" with no relationship word. Words it misses: "my boy", "my little girl", "mijo", "mija", "Dad to Leo and Emma".
- **Change:**
  - In a first pass, collect every name tied to a minor, from every post, bio, tag and photo label. In a second pass, drop every non-minor entry whose normalised name or first name matches. Then redact those names, case-insensitively, in every cite's quote.
  - When a quote matches a minor relationship and no name follows the word, redact capitalised names next to it.
  - Widen `AGE_MINOR` to `age \d+`, `\d+ ?y/?o`, `is \d+`, `\d+(st|nd|rd|th) birthday` and `\d+-year-old`. Add boy, girl, little one, mijo, mija, toddler, teen, "dad to" and "mom to".
  - Run photo labels through the same checks.
  - Map every minor's label to "a child" (A5). The note's text says their `labels` become `["child"]`, but its test expects `["a child"]`; pick one.
- **Tests (`test_analysis.py`):**
  - for the probe-1, probe-2, "Leo Vell, my stepson" and "age 9" cases, `"Leo" not in json.dumps(r)`;
  - `son["labels"] == ["a child"]` (or `["child"]`, as decided).

**AN2. The face gate: an allow-list only** (F2)
- **Where:** `face.gate` (`face.py:116-126`) [confirmed]; `BLOCKED` and `EEA` (`face.py:68-77`).
- **Change:** allow only an explicit allow-list:
  - `US-` plus one of the 50 states, DC and the territories, minus the blocked states; an unknown state is blocked;
  - ISO 3166-1 alpha-2 codes from a hard-coded set;
  - map `UK` to GB and `EL` to GR;
  - add GP, MQ, GF, RE, YT, MF and AX to `EEA`;
  - anything else gets "the subject's residence isn't a known ISO 3166 code".

  AP2 rejects unknown codes at the API too.
- **Test:** extend the table in `test_analysis.py:222-236` with `("UK", False), ("EL", False), ("EU", False), ("XX", False), ("US-ZZ", False), ("GP", False), ("RE", False)`.
- **Dormant today:** no app route runs the face check (AN11).

**AN3. The scan returns the audience** (K3)
- **Where:** `scan._query` (`scan.py:254-257`), which doesn't join `post_extra`.
- **Change:** return the post's `extra.audience` and `extra.audience_flag`. AP4 acts on them.
- **Test:** AP4's report test covers it.

**AN4. Blur by default when no child check ran** (K7, A5)
- **Where:** hits that are always stored with `blur = False` while showing a real picture:
  - caption-keyword hits (`scan.py:158-166`);
  - Facebook tag hits (`scan.py:389-397`);
  - OCR hits on screenshots (`scan.py:182-183`);
  - hits made while the vision model is unavailable (`scan.py:214-222, 238`).
- **Change:** make `blur` default to `True` for any hit whose picture the vision model didn't see. Or run a CLIP zero-shot "child or baby" check on the hit's file, reusing `face.PROMPTS` with `similar.labels` at the `face.CHILD_MAX` threshold.
- **Test:** in `test_scan.py`, a caption hit with media, made with `vlm.judge` stubbed to raise `VLMUnavailable`, has `blur is True`.

**AN5. The scan skips posts that aren't about the subject** (A3, A7)
- **Where:** `scan.run`, which scans every collected post (`scan.py:147`).
- **Change:** skip posts marked `extra.not_subject` (CA3).
- **Test:** in `test_scan.py`, a `not_subject` post isn't scanned.

**AN6. Associate entries: no address, contact details or health** (A2, A9). The `HEALTH` regex is shared with AP3.
- **Where:** the "same address" block (`graph.py:281-285`); `cite()`; `_around` (`graph.py:343-348`), which quotes the whole sentence unfiltered.
- **Change:**
  - Remove the "same address" block. At most, cite the record id with "a record lists another person at the subject's address", without naming them.
  - In `cite()`, replace any email (`pivot.EMAIL`), phone (`phonenumbers.PhoneNumberMatcher`), street address and URL in `quote` with `[detail withheld]`.
  - In `cite()`, also redact health terms, using a `HEALTH` regex shared with `report.py`: hospital, surgery, chemo, cancer, diagnos…, therapy, rehab, medication, pregnan…, and the Spanish terms.
- **Tests (`test_analysis.py`):**
  - drop the `same address` assertion at `test_analysis.py:330`, which enshrines the gap;
  - no entry's quote contains "12 Alder Lane";
  - a quote with an email or phone comes back redacted;
  - probe 5's quote ("Visiting my mom in hospital after her chemo.") contains neither "chemo" nor "hospital".

**AN7. Observed wording, not relationship labels** (A6, A7)
- **Where:** labels and types in `graph.associates` (`graph.py:166-190`); the shared-surname type (`graph.py:300-305`), added to any named entry.
- **Change:**
  - Replace `labels` with the observed wording: `{"how": "named", "words": "my brother"}` (the matched phrase, quoted), or `"tagged"`, or `"co-party"`.
  - Change the surname type to `"shares the surname"`, added only when the cite is used for identity.
- **Tests:**
  - `test_analysis.py`: no entry has a `types` value in {mother, father, brother, sister, parent, sibling, partner, possible relative}, and Kim Vell's label is "shares the surname". This replaces `test_analysis.py:331`.
  - `test_report.py` (app screens, once a report section on associates exists): no word from `RELATIONS` appears outside quotation marks.
- **Docs:** correct docs/analysis.md §8's report sentences to the A6 form; see decision D7.

**AN8. Pivot suggestions skip associates** (A1)
- **Where:** `pivot.suggestions` (`pivot.py:58-78`): bio `@mentions` (`:115-117`) and emails (`:101-103`). Only `test_analysis.py:60-71` calls it today, but analysis.md §2 plans to wire it in.
- **Change:** drop `mentions @… in the bio` and emails that `graph.associates` ties to a relationship.
- **Test:** in `test_analysis.py`, the bio "Married to @ines_vell" gives no `ines_vell` suggestion.

**AN9. Case-scoped associate ids** (A10)
- **Where:** the entry id, `sha256(normalised name)[:10]` (`graph.py:229-231`), is the same in every case.
- **Change:** salt it with the case, for example `sha256(case.name + key)`. That needs the case passed in; or use per-case `secrets`.
- **Test:** in `test_analysis.py`, the same name in two calls with different cases gives different ids.

**AN10. No "injury" category for a Washington subject** (F3)
- **Where:** the scan's categories in `scan.py`.
- **Change:** skip the "injury" category when `case.mhmda` is set. AP11 does the report side.
- **Test:** AP11's "knee injury" test covers it.

**AN11. Faces are compared only through `verify_all`** (F1)
- **Where:** `face.compare(references, images)` (`face.py:90`) is public, needs no case, and has no gate. Today only tests and `scripts/eval_face.py` call it.
- **Change:** rename it `_compare`, keep `verify_all` as the only public entry point, and point `scripts/eval_face.py` and the test at `_compare`.
- **Test:** in `test_analysis.py`, with `face._faces`, `_gate` and `_embed` monkeypatched to return a fake vector:
  - after `verify_all`, no file in `c.dir` or `HUNT_HOME` was added or changed, except `case.db`;
  - `face_checks` has no blob column;
  - the stored row has no 512-float value.

### 3.5 App screens (`hunt/static`, `app.py`, `report.py`, `search.py`; also `case.py` and `cli.py`)

**AP1. Redact minors outside the map** (C13, A5)
- **Where:**
  - the report: a kept hit prints `shows Caption: "…with my son Leo…"` (`scan.py:161`; `report.py:472`);
  - the UI: the caption is shown in full (`hunt/static/app.js:996`), and `h.what` too (`app.js:593, 979, 993`).
- **Change:**
  - In `report.py`, redact the names AN1 marks as minors in `h["what"]`, captions and notes before `doc.say`.
  - In `app.js`, show a `caption_redacted` field that `scan.list_hits` returns (`scan.py` is analysis's).
- **Test:** in `test_report.py`, a kept hit captioned "with my son Leo" gives no "Leo" in `to_html`.
- **Not checked by the audit:** investigator notes.

**AP2. Validate the residence, and ask for it** (F2, F4)
- **Where:** `_details`, where `RESIDENCE = [A-Z]{2}(-[A-Z0-9]{1,3})?` checks only the shape (`app.py:462, 478-481`); `DETAIL_FIELDS` (`static/app.js:1030-1031`), which has no residence field.
- **Change:** reject codes that AN2 doesn't know with 400, and add the residence field to the wizard. AP10 also makes `subject_residence` required at case creation.
- **Test:** none of its own in the notes; AN2's table covers the gate.

**AP3. Employment (background) reports** (K1, A8, A9)
- **Where:** `report.compose()`; `_Doc.say` (`report.py:223-227`); the hit filter (`report.py:259-261`); `PROTECTED` (`report.py:49-51`); `_summary` (`report.py:668-671`); `export_report` (`app.py:911-927`); `get_people` (`app.py:644-648`).
- **Change:**
  - **Confirmed only.** When `d["kind"] == "background"`, force `screening = True`. Drop candidates and records whose `decision != "him"`, and drop kept hits whose post's `account_url` isn't a confirmed account. Today `people` takes every candidate at P ≥ 0.55 (`report.py:250`).
  - **Export.** `export_report` returns 409 for a background case while no account has the decision "him".
  - **Relationships.** Add `RELATION = re.compile(r"\b(" + graph._WORDS + r")\b", re.I)`, built from `graph.RELATIONS` (125 words, English and Spanish). In screening, `_Doc.say` drops any non-boilerplate sentence on `PROTECTED.search(text) or RELATION.search(text)`. Apply the same to the hit filter at `report.py:259-261`.
  - **Wider `PROTECTED`.** Add colour, ancestry, creed, "gay", "transgender", "church", "mosque", "wheelchair", "cancer", "diagnos…" and criminal-history words, plus AN6's `HEALTH` terms. Or add a second regex for screening only.
  - **Court captions.** In screening, `_summary` prints the CourtListener docket number only, not `a.get("case")`, which names co-parties.
  - **The map.** `get_people` returns `{"notice": NOT_IN_SCREENING, "people": []}` when `c.details()["kind"] == "background"`.
- **Tests:**
  - `test_report.py`: a background case with one unconfirmed likely account gives an empty `rep["presence"]`, has `report.FCRA` in the disclaimers, and has `rep["screening"] is True` without being asked. That also fills the missing FCRA test.
  - `test_report.py`: a screening compose with a kept caption "with my wife Ines" and a note "his mom" has no sentence matching `RELATION`. Neither "Ines" nor a co-party name appears in `to_html`. A screening caption "my mom's surgery" is dropped.
  - `test_app.py`: exporting a background case before confirmation returns 409. `/people` on a background case returns an empty `people`.

**AP4. Non-Public items stay out of the report until counsel approves** (K3)
- **Where:** `report.compose()`, where non-Public kept items go straight into findings and exhibits (`report.py:262-263, 288-293`); a new route; the hit card in `hunt/static`.
- **Change:**
  - Leave out of `kept`, the exhibits and the findings any hit whose audience is shown and isn't "Public", unless the case has an audited `counsel approved` row naming that hit. This needs AN3.
  - Add a `couldnt_see` bullet: "N items shown to a restricted audience were left out pending counsel's approval".
  - Add `POST /api/cases/{slug}/hits/{id}/counsel {by, note}`, audited.
  - Show the flag on the hit card.
- **Test:** in `test_report.py`, a kept hit on a post with `extra.audience = "Friends"` is absent from `rep["evidence"]` and `rep["exhibits"]`, and present after the `counsel approved` audit row.
- **Open question:** what to do with media that has no audience at all; see decision D10.

**AP5. `search.fan_out`: one source at a time, and stops** (K8, C8)
- **Where:** `search.fan_out` (`search.py:62-83`). It builds one job per (source, seed) and gathers them all at once (`:81-83`). With 3 username seeds and 2 URL seeds, Wayback runs 5 loops in parallel, about 5 requests a second against a documented 1/s.
- **Change:**
  - One task per source, looping over its seeds in order. On `Limited`, `break`, and record the remaining seeds as `skipped: rate-limited earlier in this search`. That is a smaller diff than a limiter in every module, and makes each module's pause real.
  - Skip the `facebook` source while Facebook is stopped (moot once DS5 lands).
  - Pass the stopped platforms' hosts (CA1) to `maigret.sites()` and `wmn` as extra exclusions (DS3, DS4).
- **Test:** in `test_hunt.py` or `test_e2e.py`, a stub source that raises `_api.Limited` on its first seed is never called for its second, and its run note says so.

**AP6. Guided mode: the server gate and the off switch** (C1; G2, G3, G6). The `app.py` side of CA2.
- **Where:** `/api/capture/guided` (`app.py:1608-1618`); `/api/capture/hello`.
- **Change:**
  - **The match.** Refuse unless `extension.account_of(url)` is one of `extension.confirmed(case)`, or the URL is on that account's `todo`. The server already canonicalises `profile.php?id=` (`extension.where` and `account_of`). Allow scrolling only on the profile root and its Posts, Reels, Media and Videos tabs, never on `/followers/`, `/following/` or `/friends`.
  - **The gate.** With CA2's awaited audit, this route becomes the one gate.
  - **The switch.** Add a `guided` setting, `false` by default, settable only from Hunt, and audited as `guided mode on` or `off` with a counsel note. Return it in `/api/capture/hello`. See decision D3.
- **Test:** in `test_capture.py`, `hello` carries `guided: false` until it's set, and setting it is audited. CA2's harness covers the `profile.php` refusal.

**AP7. No collection on associates: seeds and preview** (A1, A3, C13)
- **Where:** `add_seeds` and `create_case` (`POST /api/cases/{slug}/seeds`, `app.py:526-531`); `public_preview` (`app.py:843-858`), which calls `public.preview` (`public.py:62-71`) on any https URL.
- **Change:**
  - **Seeds.** Compare new name, username and email seeds with the `graph.associates(…)` names and the handles in its cites. On a match, return 409 with "open them as their own case".
  - **Preview.** Require `url` to be the URL of an account marked "him", or a post URL on one (`norm_url` prefix). Otherwise return 400. Collectors could hold this check in `public.preview` instead.
- **Tests (`test_app.py`):**
  - after a post naming "my brother Dan Vell", `POST /seeds ["Dan Vell"]` returns 409;
  - a preview of an unconfirmed account's URL returns 400.

  Then update `test_public.py:222-228`, which previews the unconfirmed `@nasa`.

**AP8. Facebook on her click; honest avatar fetches** (C6, C7)
- **Where:** `public_preview` (`app.py:843-858`); `search.avatars` (`search.py:24, 208`), which reuses `wmn.UA` (Chrome 141); `search.screenshot` (`search.py:222-241`).
- **Change:**
  - For a Facebook profile URL, `public_preview` calls `sources.facebook.search(Seed("url", url))` and stores the finding. Today a Facebook URL there reaches `public._walled` and reads nothing, while batch search reads it on every Search. The design is the wrong way round [judgement, from the collectors note]. DS5 takes it out of batch.
  - `search.avatars` uses `_api.UA`.
  - `search.screenshot` needs nothing more once CA4's guard lands.
- **Tests:** in `test_app.py`, one POST to `/preview` with a Facebook URL makes exactly one mocked request to `www.facebook.com`. CA4's stub test covers `search.screenshot`.

**AP9. Report exports blur children** (K7, A5)
- **Where:** `report.to_html` and `_img`, which inline the original image (`test_report.py:249`).
- **Change:** for a hit with `blur`, embed a Gaussian-blurred copy (PIL), and say so in the exhibit caption. An exhibit showing a child is the likeliest leak [judgement, from the case note].
- **Test:** in `test_report.py`, a kept hit with `blur = True` doesn't embed the original image bytes.
- **Not covered by the notes' fix:** the evidence route (`app.py:930-941`, served raw, so it's CSS-only in the app) and the bundle. See decision D11.

**AP10. One work gate: closed, past retention, or abroad without a basis** (K6, F4). Capture's routes call it.
- **Where:** `_new_job` (`app.py:194-202`, which checks only `closed`); `public_preview` (`app.py:853`); `_capture_upload` (`app.py:1529-1567`, which checks neither); `cli.main` before `search`, `photo` and `inbox` (`cli.py:146-163`, which checks neither, so a closed case can be searched from the CLI); `DETAILS` (`case.py:21-26`); `report.compose`.
- **Change:**
  - **Retention.** Refuse (409, or `SystemExit` in the CLI) when `case.status()["retention_due"]` or `closed` is set: "past its 90-day retention: delete it to the Trash, or put it on legal hold". See decision D6.
  - **Abroad.** Add `DETAILS` entries `abroad_basis` (the GDPR Art. 6(1)(f), DPA 2018 Sch. 2 para 2 or PIPEDA s.7(1)(b) text) and `no_notice` (why the Art. 14(5)(b) notice wasn't given). Refuse with 409 when the residence country is GB, CA or in the EEA and either is empty. Print both in the report's scope.
  - **Residence.** Require `subject_residence` in `create_case`, or record "unknown" explicitly.
- **Tests:**
  - `test_e2e.py`: with `created` set to 2025-01-01, `POST …/search` gets 409, and so does `POST …/capture/view`.
  - `test_app.py`: a case with `subject_residence = "DE"` gets 409 on `POST …/search` until both details are set, then 202 or 200.

**AP11. Washington subjects** (F3)
- **Where:** `report.compose()`, with `missing` at `report.py:582` and the model's text printed verbatim as "shows {what} ({category})" at `report.py:471-473`; `export_report` (optionally `start_scan`); `static/app.js:1030-1031`, which lacks `mhmda_basis`.
- **Change:** if `case.mhmda` is set:
  - add `mhmda_basis` to `missing`;
  - print a scope sentence, "Washington subject (My Health My Data Act): fraud basis on record: …", cited to the `case details` audit row;
  - leave out hits with `category == "injury"` and any sentence matching a health subset of `PROTECTED`, the way screening does;
  - word findings as "shows {activity label}", without the model's free text;
  - return 409 from `export_report` (and optionally `start_scan`) while `mhmda_basis` is empty.

  AN10 drops the scan category.
- **Tests:**
  - `test_report.py`: a US-WA case without a basis has `"mhmda_basis"` in `rep["checks"]["missing"]`; with one, the scope cites it; the "knee injury" hit isn't in the findings.
  - `test_app.py`: the export returns 409 without a basis.

**AP12. One LinkedIn gate** (C10, A4). QOL's `recheck._pacing` is reused.
- **Where:** `/api/browser/open` (`app.py:1489-1506`); the worklist's `wl-open` (`app.py:1223-1238`); onboarding's one-click LinkedIn sign-in (`browser.py:40`; `app.js:875`).
- **Why:** today the pacing warning sees only worklist opens. The card's Sections "Open" buttons (`app.js:759-762`), "Open these" tiles (`app.js:808`), the popup's checklist links (`popup.js:76`) and a direct `/api/browser/open` all skip it, and only the profile root is counted.
- **Change:** for any URL where `extension.platform(url) == "LinkedIn"`:
  - when `linkedin` is `signed_in`, return 409 "browse logged out or with profile viewing set to private", unless the request has `confirmed: true`;
  - apply `recheck._pacing` to `account_of(url)`, counting every audited LinkedIn open;
  - audit `linkedin view`.

  `wl-open` reuses the same check. Add the private-mode line to the LinkedIn row of "Connect your accounts".
- **Test:** in `test_capture.py`, `POST /api/browser/open {url: linkedin /in/x/details/experience/}` with `linkedin: signed_in` returns 409. With `confirmed`, it returns 200 and is audited. A second open within 7 days returns 409 naming the earlier date.

**AP13. `deleted-cases.log` without the name or the purpose** (K6)
- **Where:** `delete_case` (`app.py:819-821`) [confirmed at `:819`]. It appends `label`, `purpose`, `slug` and `created` to `~/Hunt/deleted-cases.log`, and the wizard makes the subject's name the label (`static/app.js:1170`). So the name and the purpose outlive the 90 days and the Trash.
- **Change:** write only `{ts, slug_hash or slug, created, reason, audit_rowid}`.
- **Test:** in `test_e2e.py`, the `deleted-cases.log` line has no `label` and no `purpose`.

**AP14. A kind on every case** (K1)
- **Where:** `Case.__init__`; `cli.py:147`, which makes `Case(args.case, args.purpose)` with `kind = None`; `KINDS` (`app.py:53`).
- **Change:** move `KINDS` into `case.py`, and require `kind` to be in it for new cases. Add a required `--kind {…}` to the CLI's common parser for a new case. Which kinds is decision D9.
- **Tests:**
  - `test_hunt.py`: `Case("x", "purpose")` without a kind raises.
  - `test_app.py`: `POST /api/cases` without `kind` returns 400.

**AP15. "Kept" and "in report"** (K4)
- **Where:** `KEPT = ("kept", "in report")` (`report.py:63`); the undated bullet (`report.py:534-536`), which includes `new` hits.
- **Change:**
  - Either `KEPT = ("in report",)`, so `kept` means kept for the file only, or a new `"kept (not reported)"` status. A new status would live in `scan.py` (analysis). See decision D4.
  - Filter `undated` to `status != "new"`.
- **Test:** in `test_report.py`, a `kept` hit isn't in `rep["evidence"]` unless its status is `in report`.

**AP16. The report says when posts came through Apify** (C12)
- **Where:** `report.py:52, 528-530`. It says "Posts on Instagram weren't read: Hunt reads Bluesky, Mastodon and YouTube" even when Apify read them, or TikTok was read.
- **Change:** count `origin = 'vendor'` posts per source, and say "N posts obtained through Apify under the investigator's own account". Make `READ_AUTOMATICALLY` include TikTok, or base the line on which posts sources actually ran.
- **Test:** in `test_report.py`, a case with vendor posts carries that sentence, and no "weren't read" line for that account.

**AP17. Audit the lookups** (K2)
- **Where:** `post_seen` and `get_seen` (`POST /api/seen-before`, `app.py:1186-1189`). They query every other case on the machine, and the wizard calls them before any case or purpose exists (`static/app.js:948-953`).
- **Change:** audit `seen lookup {identifiers: count, matches: [slugs]}` in the case, or in a machine log for the wizard's lookups made before a case exists.
- **Test:** in `test_e2e.py`, after an export, the audit actions include `report exported`. Today no test asserts it.
- **No fix in the notes for:** the unaudited `case.json` dumps (`cli.py:165-167`; `GET /api/cases/{slug}/case.json`, `app.py:534-535`). The case note assigns that route to app screens.

**AP18. Connect-screen text, stops and Resume** (C3, C5, C8, C10)
- **Where:** "Connect your accounts" (`hunt/static/app.js:894`); case creation; `/api/browser/status`; Resume, which is reachable today only by a raw POST (`app.py:1621-1626`).
- **Change:**
  - Under "Connect your accounts": "Sign in only with your own real account (your work account, if Ethos's policy says so), never a made-up, shared or borrowed one. If a platform blocks it, stop and tell Ethos; don't sign in with another."
  - There and on case creation: "Never use a false name or a false reason with anyone, online or off (no pretexting)."
  - Render `stopped` and `problems` from `/api/browser/status`, with a Resume button and capture.md's confirmation ("never with another account").
  - The LinkedIn private-mode line (AP12).
- **Test:** in `test_app.py`, the rendered connect screen (or `app.js`) contains the pretexting sentence. It's a weak test, but it's the only kind a policy rule allows.

**AP19. Associates' posts never become findings** (A7)
- **Where:** the findings in `report.py`.
- **Change:** refuse to compose a kept hit whose post is `not_subject` (CA3) without an investigator note.
- **Test:** in `test_report.py`; the note gives no exact assertion.

### 3.6 Data sources and courts (`hunt/sources/`)

**DS1. user-scanner fails closed** (C4, C6, C7, C11)
- **Where:** `user_scanner._skip` (`user_scanner.py:212`) [confirmed]. It returns `None`, which means run (`:221`), for any module that isn't in `NOTIFIES` and whose own source doesn't match `MAY_NOTIFY`. `pyproject.toml:19` reads `user-scanner>=1.5.2.3` [confirmed].
- **Measured on 1.5.2.3:**
  - after a version bump, 25 of the 127 silent modules would run with their new code unread;
  - `MAY_NOTIFY` misses 3 of the 51 upstream-loud modules: `slowly`, `cvkeskus` and `cvmarket_lv`. `slowly` POSTs to `https://api.getslowly.com/auth/email/passcode`, a passcode email;
  - the heuristic reads only the module's own file, not the helpers it imports.
- **Change:**
  - Return `"unaudited"` whenever `version("user-scanner") != AUDITED`, or when the module is in neither set. Keep `MAY_NOTIFY` only as an extra reason in the count.
  - Return `"robots"` when the module's source names a host DS2 denies. Today that's `instagram` and `x`, whitelisted at `:135, 195`.
  - Return `"evades bot checks"` when the source matches `impersonat|curl_cffi`. That's 22 running modules, which "clear TLS-fingerprint bot walls" (`user_scanner/core/impersonate.py:27-29`).
  - Pin `user-scanner==1.5.2.3` in `pyproject.toml`.
  - The `__main__` audit (`:253-262`) counts the new reasons.
- **Tests (`test_sources.py`, offline: it loads modules but runs none).** Today no test imports `user_scanner`.
  - With `user_scanner.version` patched to return `"9.9.9"`, `all(_skip(m) for m in _modules())`.
  - At 1.5.2.3, `{m.__name__ for m in mods if not _skip(m)} == AUDITED_SILENT - loud`, less the modules the two new reasons skip.
  - `_skip(<instagram module>) == _skip(<x module>) == "robots"`.
  - No module that `_skip` lets through has `impersonat` or `curl_cffi` in its source.
  - The `__main__` invariants hold: none unaudited, none gone.

**DS2. One deny list** (C1, C6, C7, C8, C11). Shared.
- **Where:** `hunt/sources/_api.py`.
- **Change:** add `ROBOTS_DENY = ("facebook.com", "fb.com", "instagram.com", "threads.net", "threads.com", "linkedin.com", "x.com", "twitter.com", "reddit.com")` and `denied(url) -> bool`, matching on hostname whatever the scheme. The browser-capture note's list also has Strava and Snapchat, C1's other login-walled platforms; see decision D2.
- **Callers:** DS1, DS3 and DS4 here; CA4 (`capture.screenshots`); CO1 (`posts._site`); Q2 (`recheck._read`). `recheck.NO_BOTS` then goes (Q4).
- **Test:** through the callers' tests.

**DS3. Maigret: one filtered, honest site list** (C4, C6, C7, C8, C11)
- **Where:** `hunt/sources/maigret.py`: `TOP_SITES = 500` (`:20`), no filter (`:27-29`). `pyproject.toml:10` reads `>=0.6.6`.
- **Today:** every username search sends Maigret's default Chrome 132 UA and per-site Chrome or curl UAs. It uses Chrome TLS impersonation through curl_cffi on 67 of 509 sites, Instagram and Threads among them (`maigret/checking.py:408` "emulate browser TLS fingerprint and bypass WAF" [confirmed], `:970-982`). Maigret's Cloudflare bypass stays off, because `maigret.py:28` doesn't pass `cloudflare_bypass`.
- **Change:** build the site dict in a `sites()` function that drops any site:
  - whose `url` or `url_probe` host is `denied` (C6);
  - whose `protection` contains `tls_fingerprint`, `cf_js_challenge`, `cf_firewall`, `ip_reputation` or `custom_bot_protection` (C7; those block honest clients anyway);
  - with a non-empty `activation` (C11: X's guest-token minting through `api.twitter.com/1.1/guest/activate.json`);
  - with `requestMethod != GET`, unless it's on an audited set (C4). Today those are Discord's and LeetCode's checks, both read-only lookups by their nature but not audited in Hunt;
  - on a stopped platform's host, passed in by AP5 (C8).

  Also set `maigret.utils.DEFAULT_USER_AGENTS[:] = [_api.UA]`, and strip per-site `User-Agent` and `sec-ch-*` headers. Pin `maigret==0.6.6` and record it, as user-scanner's `AUDITED` does.
- **Tests (`test_sources.py`, offline against the bundled database):**
  - no site's `url.format(…)` or `url_probe` is `denied`;
  - every site's effective UA is `_api.UA`;
  - no site has any of those protections;
  - no site is named Twitter, Instagram, Reddit, Facebook, LinkedIn or Threads, and none has `activation`.

**DS4. WhatsMyName: a pinned list, an honest UA, no deny hosts, audited POSTs** (C4, C6, C7, C8)
- **Where:** `hunt/sources/wmn.py`: `DATA_URL` (`:20`, the `main` branch, refreshed every 7 days, `:33-37`); `UA` (`:23`, Chrome 141) [confirmed]; each entry's own `headers` (`:51`); POSTs of any `post_body` (`:48-51`); 50 at once (`:69`).
- **Change:**
  - `UA = _api.UA`, and drop entry headers that set a UA.
  - Skip entries whose `uri_check` host is `denied`, or a stopped platform's (AP5).
  - Pin `DATA_URL` to a commit SHA, or vendor the list.
  - Send POSTs only for entries on an audited `POST_OK` allowlist.
- **Tests (`test_sources.py`):**
  - `wmn._client().headers["user-agent"] == _api.UA`;
  - a fixture entry on `www.instagram.com` is filtered out;
  - a list with an unlisted `post_body` entry makes no POST on a mock transport, and that site counts as skipped.
- **Also:** `search.avatars` reuses `wmn.UA` (AP8).

**DS5. The `facebook` source leaves batch search** (C6, C7, C8)
- **Where:** `sources/__init__.py:25` puts it in `SOURCES`. On a 400, 403 or 429 it returns a "refused" note (`hunt/sources/facebook.py:62-64`), and the next seed is requested 3 s later.
- **Change:** drop `facebook` from `SOURCES`; AP8 makes it the click action. If it stays in batch instead, a module-level `_refused` flag ends the remaining seeds of the run, and AP5 skips it while Facebook is stopped.
- **Test:** in `test_sources.py`, `facebook not in SOURCES`. AP8 tests the click path.

**DS6. A 429 test for every source** (K8)
- Add one `raises(_api.Limited, …)` per uncovered source in `test_sources.py`: keybase, bluesky, openpgp, npi, edgar and courtlistener, plus `facebook` if it stays.

**DS7. Socrata by domain (optional)** (K8)
- **Where:** `_socrata.py:122-124` sends every dataset of a source at once, and four Socrata sources run concurrently.
- **Change:** group datasets by `domain`, and run each domain's datasets in sequence.
- **Test:** none proposed.

## 4. Rule text that needs a decision

Each item is a place where the code and a rule conflict, or a rule is ambiguous. The main session or Aaron decides.

**D1. C6 against the Maigret, WhatsMyName and user-scanner existence checks**
- **The conflict.** automation-legal.md Q5 keeps Maigret and WhatsMyName existence checks as "one request each, and a standard practice": "keep them, but document the policy". Its §4 "`sources/`" says "one request each, honest UA". legal.md's C6 exempts nothing. The engines also spoof User-Agents and TLS fingerprints, which C7 bars outright. The policy is written down nowhere beyond docs/qol.md item 19.
- **(a)** Exclude the default-deny hosts from all three engines (DS1, DS3, DS4 as written).
- **(b)** Amend C6 with an explicit, narrow exception: one existence request per site, an honest User-Agent, no TLS or header impersonation.
- [judgement] Under either option, DS3's `activation` and protection filters still apply, because X's GraphQL with a bundled token fails C11 regardless.

**D2. Which hosts the deny list covers: C1 or C6**
- **The ambiguity.** C6 names six default-deny hosts. C1's "login-walled platform" adds Strava, Snapchat, and TikTok when she's signed in. The browser-capture note reads C1 as covering Hunt's logged-out Python requests too. The collectors note's `ROBOTS_DENY` follows C6, so it omits Strava and Snapchat; Maigret probes `snapchat.com/add/<u>` today.
- **(a)** C1 covers only her session, and logged-out reads follow C6 alone. The list stays C6's six hosts plus their aliases.
- **(b)** C1 covers every software-caused request. Add `strava.com` and `snapchat.com` to `ROBOTS_DENY`.

**D3. Guided mode with no off switch or counsel gate**
- **The conflict.** legal.md says firms whose counsel prefers the lower-risk path "should not use guided mode", and that counsel should confirm the trade-off before casework. In the code, Alt+Shift+N is bound by default (`manifest.json:72-77`) and works whenever capture is on.
- **(a)** Off by default, turned on from Hunt with an audited counsel note (AP6, CA2).
- **(b)** Keep it on, and amend legal.md: counsel's confirmation is a firm-level step outside Hunt.
- **Also (G4).** legal.md says the next press is locked "until that step's capture is recorded". The code releases the lock after 20 s (`GUIDE_MAX`), which only capture.md mentions.
  - **(a)** Amend legal.md to state the 20 s release, with an audited `guided step not recorded` (the note's fix).
  - **(b)** Keep the text, and drop the timer release.

**D4. K4: "kept" also means "reported"**
- **The ambiguity.** Both `kept` and `in report` go into the findings, so she can't keep a hit for reference without reporting it.
- **(a)** `KEPT = ("in report",)`, and `kept` means kept for the file only.
- **(b)** Add a `"kept (not reported)"` status.

**D5. F2's California path**
- **The conflict.** F2 blocks CA "unless Ethos's counsel accepts the legal-claims exemption". The code always blocks US-CA and has no way to record acceptance. That's stricter than the rule.
- **(a)** Keep CA always blocked, and amend F2 to say so.
- **(b)** Add `ca_counsel_ok` (text and date, audited) as a case detail that lifts US-CA only.

**D6. K6: retention is advisory, and what the deletion log keeps**
- **The conflict.** K6 says 90 days unless she sets a hold. Nothing deletes or locks a case at 90 days, and new work still runs (AP10).
- **(a)** Enforce it: refuse new work past retention unless the case is on hold.
- **(b)** Amend K6 to say retention is a reminder.
- **The deletion log.** (a) Keep only the time, slug or slug hash, created date, reason and audit row id (AP13). (b) Keep a fuller deletion register, and say so in K6.

**D7. A6 against docs/analysis.md §8**
- **The conflict.** analysis.md §8 specifies report lines such as "Brother: Dan…" and "Partner: Ines Vell", and UI cards such as "son (name withheld)". `graph.associates` generates such labels. A6 says Hunt never generates a relationship label.
- **(a)** Rewrite analysis.md §8 to the A6 form ("@mara_q commented 'proud of you, son' … [E-12]"), and change the graph's labels to observed wording (AN7).
- **(b)** Amend A6 to allow generated labels in the in-app map only, never in the report.

**D8. Is a 429 on an automatic read a hard stop? (C7 against C8)**
- **The conflict.** legal.md's C8 lists CAPTCHA and IP block, but not 429. automation-legal.md's "Hard stops" includes "a CAPTCHA, or an IP block or 429 on any automatic source". CO3 calls `browser.stop` on any wall, a 429 included.
- **(a)** A 429 ends that platform's reads for the run (C7). A CAPTCHA, an IP block or a login wall sets a hard stop (C8 as written).
- **(b)** Any 429 on an automatic source is a hard stop until she resumes, and C8 adds "429".

**D9. K1: the case kinds, and screening by default**
- **The conflict.** K1 names two kinds: claim, and employment and eligibility. The code has four: `insurance`, `background`, `diligence`, `journalism`. Eligibility work has no kind, and "diligence" gets NOT_CONSUMER.
  - **(a)** Map `KINDS` to the rule's two kinds.
  - **(b)** Amend K1 to list the four, and say which ones are consumer reports.
- **The default.** The screening version is opt-in, even for background cases.
  - **(a)** Force it for background cases (AP3).
  - **(b)** Keep it opt-in, and say so in K1.

**D10. K3: media with no audience**
- **The ambiguity.** Screenshots, recordings (until CA5), and vendor, inbox and uploaded media carry no audience at all, so they can't be told apart from Public.
- **(a)** Treat a missing audience as "not shown as Public": flag it and hold it for counsel.
- **(b)** Flag only an audience that is shown and isn't Public (AP4 as written).

**D11. K7's reach: the scan, the app, or every export**
- **The ambiguity.** K7 says "in the scan", A5 says "blurred in the app", and the report, the evidence route (`app.py:930-941`) and the bundle carry the originals. AP9 blurs the report's HTML only.
- **(a)** Cover the report too, but not the bundle or the evidence route (AP9 as written).
- **(b)** Blur in every export, the bundle and the evidence route included.

**D12. A3 against the capture record (K5)**
- **The conflict.** A3 keeps only items that show or mention the subject. K5's page archive (MHTML and screenshots) keeps whole pages, including associates' posts, comment threads and commenters' names and avatars. Nothing marks them.
- **(a)** Amend A3: the archive is kept whole as the capture record, and only its posts are filtered (CA3).
- **(b)** Keep no archives of pages that aren't the subject's.

**D13. A4's LinkedIn notice against C9**
- **The conflict.** A4 wants profile-view warnings on associates' accounts too. Capture is off on LinkedIn (C9), and no content script runs there (`manifest.json:48-64`), though `host_permissions` includes linkedin.com.
- **(a)** Run a notice-only content script on LinkedIn `/in/` pages (CA7).
- **(b)** Keep Hunt's code off LinkedIn pages, and rely on AP12's gate and the popup banner. Her own browsing then gets no warning.

**D14. F1 and whole-image CLIP embeddings**
- **The ambiguity.** `scan.py` keeps CLIP ViT-L/14 embeddings of every photo, close-up portraits included, in `case.db`'s `clip_cache` (`scan.py:136, 440`). They aren't a face template, and they're deleted with the case. The case note flags them as relevant to the spirit of F1.
- **(a)** Leave them; F1 is about face templates.
- **(b)** Treat portrait embeddings under F1, and stop persisting them.

**D15. C4: the report's "no one was contacted" sentence**
- **The ambiguity.** `report.py:551` states that "no one was contacted, friended, followed or messaged", without any check. Hunt's code makes no contact, but her own clicks aren't recorded.
- **(a)** Keep it as Hunt's statement about its own code, and say so.
- **(b)** Word it as her statement, backed by CA7's audited overrides once they exist.

## 5. Corrections to legal.md's "Not yet enforced" list

**Re-checked at `9e1e39c`:**

| legal.md item | Verdict |
|---|---|
| Header "main at `9b3ee7a`" | **Stale:** now `9e1e39c` |
| Built: `recheck.NO_BOTS` worklist | **Overstated:** lacks Reddit, Strava and Snapchat; Threads and `http://` URLs slip past |
| Built: revocation watcher, Story warning | **Overstated:** the watcher stops capture only; the warning fails open unless the state is `signed_in` |
| Built: capture off on LinkedIn, Strava, Snapchat | Holds |
| Built: the capture record | **Overstated:** views and recordings carry no audience |
| Built: the face gate and MHMDA mode | **Overstated:** the gate fails open and is dormant; `case.mhmda` is never read |
| C6: `sources/facebook.py` in batch | **Open.** "Read public preview" exists now, but reads nothing for a Facebook URL |
| C6: `search.screenshot` | **Open**, and Threads and Reddit are shot too |
| C6, C11: `posts.YT_RSS` | **Open**, on watch's schedule too, and pinned by `test_public.py:212-214` |
| F4 | **Open** |
| A1–A10 "the map is being built" | **Stale:** the map is built (`graph.associates`, `GET /people`); its gaps are listed below |
| C8 with C12 | **Open.** The better fix point is `vendor.plan`, which covers the scan and the plan route. "Otherwise meets C12" is stale: the bundle and the report mislabel vendor posts |
| "Not checked here: K3, C10" | **Stale:** K3 is not enforced; C10's LinkedIn warning is partly enforced |

**Ready-to-paste replacement** for legal.md's "Not yet enforced" subsection:

```markdown
### Not yet enforced (main at `9e1e39c`, 2026-10-29)

Built since `099144c`, with the gaps [compliance-audit.md](compliance-audit.md) found:
- Check again's worklist for login-walled accounts (`recheck.NO_BOTS`). It leaves out Reddit, Strava and Snapchat, and Threads and `http://` URLs slip past it, so those still get headless recaptures.
- The revocation watcher, for capture only. The Story warning, which shows only when the sign-in state is `signed_in`; a middle-click, and Stories that advance by themselves, skip it.
- Capture never on LinkedIn, Strava or Snapchat.
- The capture record. Screenshots and recordings carry no audience.
- The face gate. It allows any residence code it doesn't recognise (`UK`, `EL`, `EU`, `XX`, `US-ZZ`), and nothing in the app runs the face check yet.

Still open:
- **C1, guided mode:** no off switch or counsel gate. Two quick presses can both step. A numeric Facebook profile (`profile.php?id=`) matches any other. The audit is sent after the step and doesn't gate it, and in manual mode steps are never captured.
- **C1, C6, C7, C11:** Maigret, user-scanner and WhatsMyName run on every Search against the default-deny hosts. That includes Instagram's, X's and Reddit's internal endpoints, and X's GraphQL with a bundled bearer token. They send browser User-Agents, and 67 Maigret sites and 22 user-scanner modules use Chrome TLS impersonation.
- **C4:** user-scanner runs a module unless a regex finds a trigger word whenever the version isn't the audited one or the module is new, and `pyproject.toml` pins only `>=1.5.2.3`. WhatsMyName POSTs from an unpinned list fetched live. Nothing asks before her own follow, like or message click.
- **C6:** `sources/facebook.py` still runs in every batch search, while "Read public preview" on a Facebook URL reads nothing. `search.screenshot` takes headless screenshots of every likely account, Facebook, Instagram, X, LinkedIn, Threads and Reddit included. Threads accounts are read as Mastodon (`posts._site`, `recheck._read`). TikTok page reads have no gap.
- **C6, C11:** `posts.YT_RSS` reads `/feeds/videos.xml`, which YouTube's robots.txt disallows, whenever no key is set, on watch's schedule too. `test_public.py:212-214` pins it.
- **C7, K8:** a TikTok 429 is followed by reads of the next account, and `test_public.py:237` asserts it. `search.fan_out` runs every seed of a source at once, so no source's pacing or stop holds across seeds. `capture.screenshots` saves a CAPTCHA or login page as evidence and carries on.
- **C8 with C12:** `vendor.plan` and `vendor.collect` don't read `browser.stops()`, so after a hard stop on Instagram or Facebook the next scan still reads that platform through Apify. The fix is a `browser.stopped(url)` check in `vendor.plan`, which covers the scan and the plan route. No other automatic read honours a stop, and no automatic 429, CAPTCHA or IP block records one.
- **C10:** the LinkedIn repeat-view warning covers worklist opens only, and there's no logged-out or private-mode advice before the first view.
- **C12, K5:** the evidence bundle labels Apify media "added by the investigator", and the report never says posts came through Apify. Other README sentences aren't true of the code either: guided mode, signed-out captures, the screenshot User-Agent, and "leads the investigator reviewed".
- **C13, A5:** a minor's name survives in other entries and other people's quotes, before the relationship word, and in lower case. Photo labels aren't checked. The report, the UI and the bundle don't redact at all.
- **K1, A8:** background reports include unconfirmed "likely" accounts and records, and the screening version is opt-in. The screening filter is `PROTECTED` alone, so "wife", "son", "mom" and co-party captions stay, and `/people` serves background cases. The CLI creates cases with no kind.
- **K2:** a hard stop with no capture target, and "Have we seen this person before?" lookups, aren't audited.
- **K3:** `audience_flag` is stored, but nothing reads it, and there's no counsel-approval record.
- **K6:** retention is advisory: searches, scans, previews and captures run past 90 days, and the CLI runs on closed cases too. `deleted-cases.log` keeps the subject's name and the purpose.
- **K7:** caption, tag, OCR and "model unavailable" hits are never blurred, and report exports embed pictures unblurred.
- **F1:** `face.compare()` is public and ungated.
- **F3:** `case.mhmda` is never read. The fraud basis isn't required or printed, and the wording doesn't change.
- **F4:** no per-case basis or no-notice record. EU, UK and Canadian subjects are blocked from the face check for that reason, and collection on them has no record either.
- **A1, A3, A10:** an associate can be added as a seed and searched. `POST /preview` reads any account's feed. Capturing an associate's page keeps and scans all its posts, and their media hashes become `seen.py` identifiers.
- **A2, A6, A9:** `graph.associates` stores an address in "same address" entries, keeps unfiltered quotes (an associate's health included), and generates relationship labels ("mother", "possible relative").
```

## 6. Method and limits

**The four audit notes** are outside the repo, in `/Users/aaronsmith/Library/Application Support/Claude/side-session-notes/local_dc868f5e-4ddc-4d67-a390-017b5e50bf3c/legal-automation/audit/`:
- `browser_capture.md`: C1, C2, C3, C5, C9, C10 and guided mode;
- `collectors_limits.md`: C6, C7, C8, C11, C12, K8, a per-source table, and the "Not yet enforced" re-check;
- `case_report_face.md`: K1–K7 and F1–F4;
- `contact_associates.md`: C4, C13 and A1–A10.

**Scratch probes** are in `/private/tmp/claude-501/-Users-aaronsmith-Documents-OSINT--claude-worktrees-legal-automation-73caa8/b4060bf8-f6b1-4d73-958d-d20914e84856/scratchpad/`:
- `run_static.py`, `static_body.py` and `mut/`: the mutation check of `test_capture.py`'s static block (lines 454–496);
- `race.js` and `race_spaced.js`: guided mode against a mocked `chrome` API, with a 30 ms reply delay, for G1 and G2;
- `probe_assoc.py` and `probe_minor2.py`: `graph.associates` on made-up text;
- `probe.py` and `probe2.py`: the collectors' host probes, all on `httpx.MockTransport`. The note doesn't name its files; these are identified by their headers;
- `gate_probe.py`: `face.gate` on unlisted codes, also identified by its header.

**Package versions read:** maigret 0.6.6, user-scanner 1.5.2.3, yt-dlp 2026.8.19 and curl_cffi 0.17.0. Line numbers in those packages are at these versions.

**What wasn't verified:**
- **Faces.** `face.compare` and the face-model checks (`test_analysis.py:270-299`) didn't run, so F1's in-memory claim rests on reading the code.
- **WhatsMyName.** Its live list wasn't fetched. Whether it has login-walled entries is likely but not verified, and its POST entries weren't counted.
- **Live behaviour.** No live tests, and no real browser was run:
  - Chrome for Testing probably reports UA-CH brands without "Google Chrome" (not verified);
  - the missing lazy-loaded TikTok covers in live QA are consistent with MHTML sending no request, but nothing tests that;
  - Playwright wasn't run, so CA4's wall check is testable offline only as a pure function. The headless User-Agent was read offline.
- **Not read for minors' names:** investigator notes.
- **Maigret's two POST checks** (Discord, LeetCode) are judged read-only by their nature; Hunt hasn't audited them.
- **yt-dlp impersonation** is latent: it depends on the curl_cffi version installed.

**Where the notes differ.** Each is kept as given, and flagged where it matters:
- The deny list's hosts: C6's six, or C1's eight (D2).
- The recapture fix: a guard in `capture.screenshots`, or an allowlist in `recheck` (Q4).
- The vendor label's wording (Q5), and a minor's label, `["child"]` or `["a child"]` (AN1).
- CA3's "store only" against "mark the rest".
- Line references: `posts._site`'s regex at `:331` (note) and its fall-through at `:329` (coordinator); `user_scanner._skip` defined at `:212` and returning `None` at `:221`; the Story handler at `content.js:56-65` (browser-capture note) and `:55-65` (associates note); `browser.stop` at `browser.py:188-201` (collectors note) and `:193-201` (case note).
- The browser-capture note's status line says guided mode goes beyond the text in "four ways", but its detailed list has seven items, G1–G7.

**Confidence.** The coordinator re-checked six findings against the code, marked [confirmed]. The rest rest on one reader each, at `9e1e39c`.
