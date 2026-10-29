# Quality of life

_2026-10-29._ Day-to-day friction for an investigator doing background checks and insurance social-media reports, and what Hunt now does about it. The broader themes (namesakes, provenance, data overload) are in [research/pain-points.md](research/pain-points.md).

## What practitioners complain about

**[S]** = stated in the cited source; **[I]** = our inference.

**Caveats on the sources:**
- Reddit was read through a mirror.
- IntelTechniques had nothing fetchable beyond its table of contents.
- Many detailed sources are vendors (Forensic OSINT, ProofSnap, PageFreezer, Hunchly). They show what buyers pay for, not what users complain about.
- Nobody complained about downloader-site file names as such. Rank 1 rests on lost provenance, which is widely reported, and on the fact that Hunt deliberately leaves Instagram, TikTok and Facebook downloads to the investigator.

Ranked by how often each comes up × how much it helps this investigator:

| # | Pain point | How often | Evidence | Hunt now |
|---|---|---|---|---|
| 1 | **Saved media loses its source.** Files from downloader sites, screenshot dumps and right-click saves pile up in Downloads. Nobody can say later which post, account or date a file came from. | Common | "Screenshot dumps that get lost" [S] ([r/OSINT via mirror](https://reddit.sentinel-team.org/posts/1smn3i4/snapshots/2026-04-17T17%3A22%3A49.050001Z)). Record the source URL, account, post ID and capture time when you save a video [S] ([Forensic OSINT](https://www.forensicosint.com/support/how-to-download-videos-manually)). Hunchly files Chrome downloads into the case with a hash and their source [S] ([Hunchly](https://support.hunch.ly/article/25-7-working-with-attachments)), but it only screenshots videos, which is why people use downloaders [S] ([Bellingcat](https://bellingcat.gitbook.io/toolkit/more/all-tools/hunchly)). | **Built:** the Downloads inbox |
| 2 | **When was it posted?** Instagram shows relative times, TikTok hid the upload date, and a screenshot's time is only when it was captured. Claimants argue that a photo is older than it looks. | Common | [S] ([Knowlesys](https://knowlesys.com/en/articles/social_websites/youtube/how_to_verify_the_exact_upload_time_of_social_media_videos_and_images.html), [ProofSnap](https://getproofsnap.com/workers-comp-social-media-evidence.html)). Unfurl and Bellingcat's tool read the upload time straight from TikTok and X post IDs, even for deleted posts [S] ([write-up](https://hf-site.pages.dev/blog/tinkering-with-tiktok-timestamps)). For an injury claim, "posted after the injury date" is the whole case [I]. | **Built:** post time from the ID, in file names and links |
| 3 | **Naming exhibits.** Default names collide and lose time order. Vendors sell templated naming. | Common | Name files by case, item, platform, date and UTC time [S] ([PageFreezer](https://blog.pagefreezer.com/how-to-build-an-osint-case-file), [Forensic OSINT](https://www.forensicosint.com/support/custom-file-naming), [ASTM draft](https://www.astm.org/membership-participation/technical-committees/workitems/workitem-wk98799)) | **Built:** exhibit names `date_platform_handle_hash8.ext` |
| 4 | **Hash manifest and chain of custody for the hand-over.** Plain screenshots get discounted at hearings, and the other side wants hashes it can check offline. | Very common, in vendor and legal sources | [S] ([ProofSnap](https://getproofsnap.com/workers-comp-social-media-evidence.html)). Re-encoding or a media player writing metadata back breaks the hash [S] ([Forensic OSINT](https://www.forensicosint.com/support/how-to-download-videos-manually)) | **Built:** the evidence bundle |
| 5 | **Paste a link, get the platform, handle and post time.** `igsh`, `si`, `fbclid` and similar parameters in shared links identify who shared them. | Occasional as a complaint; the tools for it are widely used | Unfurl decodes these links [S]. Add-ons exist just to strip `igsh` [S] ([Mozilla add-ons](https://addons.mozilla.org/sv-SE/firefox/addon/remove-instagram-tracker-param)) | **Built:** link reading, offline |
| 6 | **A timeline of what was done, and when.** It's needed for the methodology section and for testimony. | Common | In R v Hamdan, the officer couldn't say which laptop she captured on [S] ([Forensic OSINT](https://www.forensicosint.com/silly-questions-in-court)). A timeline of steps with reasons makes work retraceable [S] ([r/OSINT via mirror](https://reddit.sentinel-team.org/posts/1sc53ej/snapshots/2026-04-10T22%3A17%3A37.090119Z)) | **Mostly there already:** the audit log. Now it's in the bundle too; the UI view is described below |
| 7 | **Deleted or changed content; re-checking a profile over the life of a claim.** | Common in insurance sources | Posts get deleted and privacy settings change during a claim [S] ([Claims Journal, sponsored](https://www.claimsjournal.com/sponsored/hodsonpi/2026/08/10/339321.htm)) | **Built:** Check again |
| 8 | **Bulk import.** | Occasional | Bellingcat's Auto Archiver is popular for batch processing [S] ([Bellingcat](https://www.bellingcat.com/resources/2025/08/13/the-open-source-tool-that-has-preserved-150000-pieces-of-online-evidence/)) | **Covered by the inbox:** any folder, all at once |
| 9 | **EXIF panel.** | Common in tutorials, rarely decisive | Platforms strip EXIF on upload [S] ([Forensic OSINT](https://www.forensicosint.com/guides/what-is-exif-data-and-why-it-matters)) | Skipped (see below) |
| 10 | **Notes live outside the case.** Investigators keep them in Notepad, Obsidian or OneNote. What was seen gets mixed with what was concluded. | Common | Text-file notes don't scale as a case grows [S] ([DEF CON 26 Recon Village](https://media.defcon.org/DEF%20CON%2026/DEF%20CON%2026%20villages/DEF%20CON%2026%20villages%20captions/DEF%20CON%2026%20-%20RECON%20VILLAGE%20-%20WebBreacher%20-%20Core%20OSINT%20Keeping%20Track%20of%20and%20Reporting%20All%20the%20Things.eng.txt)). Hunchly's cost pushes people to OneNote [S] ([r/OSINT via mirror](https://reddit.sentinel-team.org/posts/1t620fn/snapshots/2026-05-16T13%3A28%3A16.416319Z)). Keep what was observed separate from what was inferred [S] ([r/OSINT via mirror](https://reddit.sentinel-team.org/posts/1sc53ej/snapshots/2026-04-10T22%3A17%3A37.090119Z)) | **Built:** notes |

## What was built

Sections 1–3 and 5 run offline. Check again (4) and watching (6) make the same logged-out requests a search and a scan already make, through `HUNT_PROXY`; watching's notifications are local. Nothing is ever downloaded from Instagram, TikTok or Facebook for the investigator.

### 1. The Downloads inbox (`hunt/inbox.py`, `hunt inbox`)

**What it lists:** photos and videos saved in a folder (default `~/Downloads`) in the last N days. Each file shows:
- **Which downloader named it:**
  - ssstik, snaptik, tikmate, musicaldown and savetik → TikTok
  - snapinsta, sssinstagram, igram and fastdl → Instagram
  - ssstwitter and twittervid → X
  - fdown and getfvid → Facebook
  - savefrom and y2mate → no platform; they handle several
  - `123_456_789_n.jpg` → saved straight from Facebook's or Instagram's servers
- **An `@handle`** anywhere in the name.
- **The post's own time, from a TikTok or X post ID:**
  - TikTok: the top 32 bits of the ID are Unix seconds.
  - X: the bits above bit 22 are milliseconds since X's epoch.
  - An ID that doesn't decode to a time between late 2010 and now is ignored.
  - ssstik's 13-digit numbers are when the file was *downloaded*, so they're never used.
- **macOS's "Where from"** (`kMDItemWhereFroms`). Browsers record the file's URL and often the page it came from. A platform link there beats the file name. Both URLs go in the audit log.
- **The case's knowledge:** if nothing else gives the handle, and the subject has exactly one confirmed account on that platform, that handle is used. It's marked `from: "case"`, and the UI must show it as a guess.
- **A proposed exhibit name,** such as `2024-03-28_tiktok_kestrel_vane88_3fa9c2d1.mp4`.
- **Whether the case already holds it,** by SHA-256.

Every field records where it came from (`file name`, `where from`, `case`, `link`, `post id` or `you`). Precedence: what the investigator types, then a link they paste, then "Where from", then the file name, then the case.

**On import:**
- Each file is hashed again. A file that changed since it was listed is left alone.
- New files go in through `posts.add_files`, so they become posts the media scan reads. TikTok and X posts arrive with their real `posted_at`, so before/after-injury timing works.
- Duplicates are skipped by hash.
- Every file gets an `inbox import` audit entry: original name, folder, SHA-256, exhibit name, platform, handle, link, "Where from", result, and what happened to the original.
- The original moves to the Trash through `NSFileManager.trashItemAtURL`, so Finder's Put Back works. This happens only after its exact bytes are confirmed in `evidence/`. Nothing is deleted, and `--keep` leaves originals where they are.

```
hunt inbox --case vance-claim                       # list; nothing changes
hunt inbox --case vance-claim --import all          # file them all, originals to the Trash
hunt inbox --case vance-claim --import 3fa9c2d1=https://www.tiktok.com/@kestrel_vane88/video/7351… 9b01ee42
hunt inbox --case vance-claim --import all --platform instagram --posted 2026-04-12 --keep
```

Files are picked by the first 8 hex digits of their hash, not by list position, so a new download can't shift the numbers between listing and importing.

### 2. Links (`inbox.from_url`, `GET /api/unfurl`)

A profile or post link becomes `{platform, handle, post_id, posted_at, url}`:
- Tracking parameters are dropped. Only `v`, `id`, `fbid` and `story_fbid` are kept, because they name the content.
- **Platforms:** TikTok, X/Twitter, Instagram, Facebook, YouTube, Bluesky.
- **Short links** (`vm.tiktok.com/…`) can't be expanded offline, so they give the platform only.

### 3. The evidence bundle (`hunt/bundle.py`, `hunt export`, `GET /api/cases/{slug}/evidence.zip`)

A zip for handing to a client, counsel or court:

| In the zip | What it is |
|---|---|
| `exhibits/` | Every evidence file under a readable name, dated when it was saved into the case. Profile photos stored as `.img` get their real type. |
| `manifest.csv` | Exhibit, SHA-256, bytes, hash OK, what it is, source, URL, account, posted at, saved at, original name. Cells a spreadsheet would run as formulas (`=`, `+`, `-`, `@`) are quoted. |
| `SHA256SUMS` | The hashes each file was *saved* under, so `shasum -a 256 -c SHA256SUMS` checks the whole bundle on any machine. A file that changed fails, as it should, and is also flagged in the manifest and README. |
| `audit-log.csv` | The case log with its row ids. They match the report's `M-a<id>` citations. |
| `README.txt` | The case, its purpose on record, the Hunt version, and how to check the bundle on macOS, Linux and Windows. |

The zip's own SHA-256 is printed, sent as the `x-bundle-sha256` header, and logged as `evidence exported`.

`hunt export` writes to `~/Hunt/exports/` by default. The app builds the zip in a temporary folder inside the case, streams it, then removes that temporary copy.

### 4. Check again (`hunt/recheck.py`, `POST /api/cases/{slug}/recheck`)

Insurance cases run for months, and posts vanish or accounts change. A job looks again at every account marked as the subject's (not email hits):

1. **Profiles** (Bluesky and Mastodon). They're read through the same logged-out sources the search uses, so each look is compared with an earlier read by the same parser. Two parsers' different wording is never reported as a change.
   - **Name and bio** are compared as text.
   - **The profile photo** is compared by SHA-256. The new picture is kept as evidence.
   - **A profile that can't be found** at its address any more is `account gone`. One that returns is `account back`.
2. **Posts:** `posts.collect` again. `posts.py` now stamps every post it reads in `post_seen(post_id, last)`, to the microsecond.
   - A post that wasn't seen this time is `posts gone`, with when it was last seen. It's judged only if it's at least as new as the oldest post this read returned (YouTube's feed lists only the latest 15).
   - An account that now shows no posts at all is flagged `none_left`.
   - A post that reappears is `post back`.
   - A failed read judges nothing.
3. **Screenshots:** a fresh, dated capture of every account (`recapture`). For Instagram, TikTok, Facebook and X, which Hunt can't read logged out, this is the only way to see a change: compare the dated screenshots by eye.

Each change is an audit entry and a `change` event on the job, and the summary is audited as `recheck`. `GET /api/cases/{slug}/changes` lists them all with their `M-a` citations. The posts that went missing stay in the case, with their media, as evidence.

### 5. Investigator notes (`hunt/notes.py`, `/api/cases/{slug}/notes`)

**What a note can be about:** the case, one account (normalised URL, as decisions are), one post or one hit. A note is timestamped and audited with its text, and cited as `N-<id>`.

**Never edited or deleted:**
- A correction is a new note that `replaces` the old one. It keeps the old note's subject.
- The old note stays, marked `replaced_by`, because what the investigator thought at the time is part of the record.
- A note can be corrected only once; correct the correction after that.

**In the evidence bundle:** `notes.csv`.

### 6. Watch this subject (`hunt/watch.py`, `hunt watch`, `/api/cases/{slug}/watch`)

Hunt finds the accounts, then keeps looking for fraud clues without the investigator doing the legwork. Watching is opt-in per case: every 1, 3 or 7 days.

**A run:**
1. **Check again:** profiles, posts and screenshots.
2. **The media scan, on new media only.**
3. **Alerts** when the scan flags something new, a post disappears, an account shows no posts any more (made private, or emptied), or an account can't be found.
   - Each alert is an audit entry and a row in the case's alerts list.
   - One **local macOS notification** sums the run up, e.g. "Vance claim: 2 new flagged posts; 3 posts gone from Bluesky". It goes through `osascript` and never touches the network. It carries counts only, never post text or handles, because macOS can show it on the lock screen.
   - The text is passed as an argument, never spliced into the script.

**When it runs:**
- **While Hunt is open:** the app looks for due cases every 10 minutes (`_watch_loop`, started from `serve()`'s lifespan). It runs them one at a time, as jobs of kind `"watch"`, so the UI shows them like a scan, and a case with another job running waits.
- **While Hunt is closed (optional):** "Keep watching when Hunt is closed" installs one per-user LaunchAgent, `~/Library/LaunchAgents/io.github.als7294.hunt.watch.plist`. It runs `hunt watch` hourly.
  - It's off by default.
  - It's removed with one click: unloaded with `launchctl bootout`, and the plist moved to the Trash.
  - Installing and removing are both audited in every watched case.
  - The agent carries `HUNT_HOME`, `HUNT_PROXY` and `HUNT_VLM` from when it was installed, so background checks leave the machine the same way the app does. Turn it off and on again after changing the proxy or reinstalling Hunt.
  - It logs to `~/Hunt/watch.log`.
- **One run at a time across processes:** the open app holds `~/Hunt/.watch.lock`, and `hunt watch` leaves the work to it.

**Not making the Mac lag** (the calibration constants are at the top of `watch.py`):
- A due check **waits** while the Mac is:
  - on battery (`pmset`),
  - busy (1-minute load average above 0.5 per core),
  - or in use (keyboard or mouse input in the last 5 minutes, from `ioreg`'s `HIDIdleTime`).
- "In use" stops counting once a check is a day overdue, so a Mac that's used all day still gets checked. Battery and load always count.
- **The background agent runs at low priority:** launchd `ProcessType: Background` (Apple's background QoS: throttled CPU and I/O), `LowPriorityIO`, and `nice 10`. ffmpeg inherits that.
- **In the app,** the scan takes the heavy lock like every heavy job.
- **The vision model's own load can't be lowered:** Ollama is a separate process. Waiting for an idle Mac is what protects the investigator from it.

**When watching stops by itself:** when the case is closed (meta `closed`), or when its retention period ends (`app.RETENTION_DAYS` after it was opened, unless meta `legal_hold`). Either way it's audited as `watch off` with the reason. `POST /api/cases/{slug}/close` and `/hold` set them (and close stops watching at once); see `docs/api.md`.

**CLI:**

```
hunt watch --case vance-claim --every 3   # watch it
hunt watch --case vance-claim             # status: next check, last result
hunt watch --case vance-claim --off
hunt watch --background on                # keep watching when Hunt is closed (off: remove)
hunt watch                                # check what's due now (what the agent runs)
```

### Self-checks

All offline, using temp folders only. `test_inbox.py`, `test_bundle.py`, `test_recheck.py`, `test_notes.py`, `test_watch.py` and `test_qol.py` each print `ok`.

`test_watch.py` stubs battery, load, idle time, `launchctl`, notifications, the re-check and the scan. It never installs a real LaunchAgent, notifies, or touches `~/Library` or the Trash. It covers:
- waiting on battery, when busy, and when in use
- the overdue override
- a full run's alerts and its single notification
- the retry after a failure
- the agent's plist (low priority, the proxy carried over), its audit, and its removal to the Trash
- the cross-process lock
- stopping on retention and on closing, and continuing under a legal hold

`test_qol.py` runs one watch round as a real app job, inside the server's event loop.

`test_recheck.py` simulates four looks against a stubbed network that changes between them:
1. A new name, a new photo, a deleted post, a vanished account, and a site that can't be read.
2. The deleted post and the vanished account come back.
3. The account shows no posts.
4. Nothing changes.

Its two coverage guards (posts older than the read reached, and failed reads) are mutation-checked.

They never touch the real `~/Downloads` or the real Trash: `inbox._trash` is swapped for a move into a temp folder. `test_bundle.py` runs the real `shasum -c` on the unzipped bundle.

The real Trash call was checked once by hand, on a scratch file.

## Skipped, and why

| What | Why |
|---|---|
| **"Went private" on Instagram, TikTok, Facebook and X** | Telling private from public needs the logged-in or scraped page. Hunt takes a new dated screenshot instead. Bluesky has no private accounts, and Mastodon's "locked" only gates followers. An account whose posts all vanish is flagged `none_left` ("made private, or emptied"). |
| **YouTube profile changes** | The channel's RSS feed carries only its title. Posts gone from the latest 15 are still detected. |
| **EXIF panel** (rank 9) | Platforms strip EXIF, so downloaded social media rarely has any. `posts.add_files` already reads `DateTimeOriginal`, and `photo.py` reads device, time and GPS. "Where from" was the more useful metadata. |
| **Instagram shortcode → time** | The shortcode decodes to a media ID whose top bits look like milliseconds since a 2011 epoch. That's unverified for current IDs, so it isn't used. |
| **The subject's local time** | Times are stored in UTC. Showing the subject's local time needs the case's location and is a UI decision. |
| **Thumbnails in the inbox list** | They would need a route that serves files from outside the case. Every route today serves only case evidence; keep it that way unless the UI really needs previews. |
| **yt-dlp names** (`Title [id].ext`) | An 11-character ID could be YouTube or an Instagram shortcode, so it can't be told apart. Investigators using yt-dlp can paste the link. |

## UI integration points (for the frontend owner)

### A. "From Downloads" on the Posts step, beside the existing "Add files"

**Opening the panel:**
- Button: **From Downloads**. It opens a panel that calls `GET /api/cases/{slug}/inbox`.
- Controls at the top:
  - Folder, shown as a path, with a "Change…" text field (absolute path).
  - Saved in: **Last day · Last 7 days · Last 30 days** (`days=1|7|30`).

**One row per file** (`files[]`, newest first):
- **Checkbox.** Ticked by default. Rows with `in_case: true` are also ticked, so their original can be cleared from Downloads.
- **Original name** (`name`), size, and saved time (`saved`, local time).
- **Arrow and proposed name:** `exhibit`, in monospace.
- **Chips** for platform, `@handle` and "Posted 28 Mar 2024, 09:14 UTC". Each has small grey source text:
  - `file name` → "from the file name"
  - `where from` → "from your browser's download record"
  - `post id` → "read from the post's ID"
  - `link` → "from the link"
  - `you` → nothing
  - `case` → **"guess: the subject's TikTok account. Check it's theirs"**, in the warning style
- **Optional editors:**
  - **Post link** field. On paste, call `GET /api/unfurl?url=` to preview the chips. Send the link as `take[].url`.
  - Platform, handle and posted date fields, sent as `take[].platform|handle|posted_at`.
  - The exhibit name updates from the server's answer after import. Don't compute it in the browser.
- **`in_case` rows:** greyed out, with "Already in this case".

**Footer and import:**
- Footer: **☑ Move the originals to the Trash afterwards** (default on). Helper text: "You can put them back from the Trash." Unticked sends `keep: true`.
- Primary button: **File 3 into this case** → `POST /api/cases/{slug}/inbox` `{folder, days, take: [{id, url?, …}], keep}`.
- Results replace each row's right side:
  - "Added as `2024-03-28_tiktok_…mp4`" or "Already in this case"
  - then "· original in the Trash", or the `trashed` sentence (e.g. "left: it changed after it was listed").

**Errors and refresh:**
- 409: "Some files moved or changed since this list was made. List again."
- Other 4xx: show `error` as is.
- Afterwards, refresh `GET /api/cases/{slug}/posts`.

**Empty state:** "Nothing saved here in the last 7 days. Save the post's video or screenshot first; Hunt never downloads from Instagram, TikTok or Facebook for you."

### B. "Evidence bundle" on the Report step, beside the report downloads

- Link: **Download evidence bundle (.zip)** → `GET /api/cases/{slug}/evidence.zip`. A plain `<a href download>` works.
- Helper: "Every evidence file under a readable name, with a SHA-256 manifest anyone can check with `shasum -c`."
- Optional: fetch it instead, to show "Bundle fingerprint (SHA-256): `71a9…f6`. Also in the case log" from `x-bundle-sha256`.
- If the latest `startup` check reported changed evidence, warn before download: "N files changed since they were saved. The bundle will flag them."

### C. Paste a link in the existing "Add files" dialog

- Add an optional **Post link** field. On paste, call `GET /api/unfurl`, then prefill **platform** and **posted at** (`posted_at`, if any), with the note "Posted 28 Mar 2024, 09:14 UTC, read from the post's ID".
- The upload route doesn't take a link yet (integration point 1 below). Until it does, tell the investigator the link is used for the platform and date only.

### D. Case log (methodology timeline)

- No new route: `GET /api/cases/{slug}/case.json` already carries `audit` (`rowid, ts, action, detail`).
- A "Case log" drawer can list them in local time with plain wording:
  - `inbox import` → "Filed `<name>` from Downloads as `<exhibit>`"
  - `evidence exported` → "Evidence bundle made (SHA-256 …)"
  - `decision` → "Marked … as him"
  - `note` → "Note N-3: …"
  - `recheck` → "Checked the subject's accounts again: 2 changes"
  - …
- Each entry's `M-a<rowid>` matches the report's citations.

### E. "Check again" on the case overview and the Posts step

- **Button:** **Check again**. Helper: "Look at the subject's confirmed accounts again: new posts, deleted posts, profile changes." Below it, "Last checked 3 Oct" (`GET /api/cases/{slug}/changes` → `checks[0].ts`), or "Not checked again yet".
- **Disabled state:** 409 means no accounts are marked as theirs yet: "Mark the subject's accounts on *Is it them?* first."
- **Starting:** `POST /api/cases/{slug}/recheck` `{}` → `{job}`, then stream it like a scan.
- **Stage labels:** `rechecking` "Looking at profiles again", `collecting` "Reading posts again", `capturing` "Taking new screenshots", `done`.
- **A "Since last time" list** fills from `change` events, then from `GET …/changes`. One line each:
  - `posts gone`: "3 posts on Bluesky are gone, last seen 1 Oct". It expands to each post's date and link, and opens the stored post (it's still in the case).
  - `posts gone` with `none_left`: "Bluesky shows no posts any more: made private, or emptied", in the warning style.
  - `profile changed`:
    - "Name on Bluesky changed: 'Alice Example' → 'Alice E.'", with `before_seen` as "was 'Alice Example' on 1 Oct".
    - For the photo, show both side by side from `/evidence/{slug}/{before_sha256}.img` and `/evidence/{slug}/{after_sha256}.img` (avatars are stored as `.img`).
  - `account gone`: "The Mastodon account can't be found at its address any more (last seen 1 Oct)", in the warning style.
  - `account back` and `post back`: neutral.
  - Each line has **Add note** (section F), with `about: "account", ref: account`.
- **Footnote:** "Instagram, TikTok, Facebook and X can't be read logged out. Hunt took a new dated screenshot of each to compare." Link it to the account's captures.
- **Empty state:** "Nothing changed since 1 Oct."
- **Afterwards:** refresh `GET …/posts`, since new posts may need a scan, and offer **Scan new posts**.

### F. Notes, everywhere the investigator decides something

- **Case notes:** a **Notes** drawer on every case screen. Textarea placeholder: "What you saw, did or decided, and why. Keep what you saw apart from what you think it means." **Save** (⌘↩) → `POST /api/cases/{slug}/notes` `{text}`.
- **Notes on one thing:** a small **Note** button on each account card (*Is it them?*), each post, each hit, and each Check again change. It opens the same composer with `about` and `ref` (account URL, post id, hit id), and shows a count badge ("2 notes") from `GET …/notes?about=&ref=`.
- **Each note shows:** `N-3`, local time, and the text.
- **Correcting:**
  - **Correct** pre-fills the composer and sends `{text, replaces: id}`.
  - The replaced note collapses under its correction as "Earlier version", struck through.
  - A 400 "already replaced by N-x" means correct N-x instead.
- **No delete:** a line under the drawer says "Notes can't be deleted; correct one instead. They're part of the case record."
- **Errors:** show `error` as is (empty text, more than 20,000 characters, a subject that doesn't exist).

### G. "Watch this subject" on the case overview

- **A card under Check again:**
  - **☐ Watch this subject**, with a **Every day · Every 3 days · Every week** selector (`every_days` 1/3/7).
  - Helper: "Hunt checks the subject's accounts again, scans what's new and tells you when something changes."
  - Toggling sends `POST /api/cases/{slug}/watch` `{on, every_days}`. A 409 is shown as is (e.g. "mark at least one account as him first", "its 90-day retention period has ended").
- **Status line** (`GET …/watch`):
  - "Last checked 2 Nov, 03:10 · Next 5 Nov" (`last`, `next`, local time).
  - The `status` in words:
    - `waiting: on battery` → "Waiting until the Mac is plugged in"
    - `waiting: the Mac is busy` → "Waiting until the Mac is less busy"
    - `waiting: the Mac is in use` → "Waiting until you step away"
    - `failed: …` → "The last check failed; trying again within the hour", with the detail on hover
  - When stopped by itself: "Stopped: the case is closed" / "Stopped: the retention period ended" (`why`).
  - While a run is going, the case's `active_job` has kind `"watch"`. Stream it like a scan, labelled "Checking again (watching)".
- **The background switch,** below it: **☐ Keep watching when Hunt is closed** (`GET/POST /api/watch/background`).
  - Helper: "Runs hourly in the background at low priority, only when the Mac is plugged in and idle. Applies to every watched case. Turn off to remove it completely."
  - On error, show `error`.
- **Alerts list** (`GET …/alerts`), with a badge for `unseen_alerts` on the case card in the case list too. Each row shows:
  - local time and `text`,
  - an icon by `kind`: `flagged`, `posts gone`, `no posts` and `account gone` (warning style),
  - a link to what it's about: for `flagged`, the Posts step filtered to new hits; for the others, the Check again change list (section E).
  - Opening the list sends `POST …/alerts/seen`.
- **Lock-screen note** near the switch: "Notifications show counts only, never what was posted. To hide them on the lock screen: System Settings → Notifications → Show previews: When unlocked."

## Audit actions for the report (to pass to the report owner)

Every row below is an audit entry, so its citation is `M-a<rowid>`, except notes, which are `N-<id>`. The sentences are suggestions in the report's neutral wording. Dates are the audit `ts`.

| Action | Detail | Suggested sentence | Section |
|---|---|---|---|
| `recheck` | `accounts, new_posts, changes, captured` | "The subject's {accounts} confirmed accounts were looked at again on {date}: {new_posts} new posts and {changes} changes." | How we searched |
| `recapture` | `attempted, saved` | "Pages of {saved} of {attempted} accounts were captured again on {date}." | How we searched |
| `posts gone` | `account, none_left, posts: [{id, url, posted_at, last_seen}]` | "On {date}, {n} posts on {site}, posted between {first} and {last}, were no longer visible. Each was last seen on {last_seen}; copies are kept as evidence." With `none_left`: "On {date}, the {site} account showed no posts; {n} had been seen before, last on {latest last_seen}." | What we found (cite the posts' `E-` ids too, if they were kept) |
| `post back` | `account, post, url, gone_since` | "A {site} post not visible on {gone_since} was visible again on {date}." | What we found |
| `profile changed` | `account, field, before, after, before_seen` (+ `before_sha256, after_sha256` for the photo) | "Between {before_seen} and {date}, the {site} account's {field} changed from '{before}' to '{after}'." Photo: "…changed its profile photo (SHA-256 {before:8} → {after:8})." | What we found |
| `account gone` | `account, last_seen` | "On {date}, the {site} account at {account} could no longer be found; it was last seen on {last_seen}." | What we found; also What we couldn't see (later posts can't be read) |
| `account back` | `account, missing_on` | "On {date}, the {site} account at {account} could be found again; it couldn't be on {missing_on}." | What we found |
| `note` | `note: "N-<id>", about, ref, text, replaces` | An "Investigator's notes" list: "N-4 ({date}): {text}". Omit replaced notes, or mark them "corrected by N-x". Notes about an account, post or hit can sit beside that item. | Its own section, after What we found |
| `watch on` / `watch off` | `every_days, next` / `why` | "From {date}, the subject's accounts were watched every {every_days} days." / "Watching stopped on {date}: {why}." | How we searched |
| `watch run` | `new_posts, changes, new_flagged, alerts` | Usually folded into one sentence: "The accounts were checked {n} times between {first} and {last} while watched; {sum new_flagged} posts were newly flagged." | How we searched |
| `alert` | `kind, text, hits` or `change` | Not a report sentence in itself: the hits and changes it points to are already cited. Useful as "first noticed on {date}". | (none) |
| `background watching` | `on, agent` | Methodology detail: "Checks also ran in the background while Hunt was closed, from {date}." | How we searched |
| `inbox import` | `name, folder, sha256, exhibit, platform, handle, url, posted_at, from, where_from, result, trashed` | "{exhibit} was saved by the investigator as {name} and filed on {date} (SHA-256 {sha256:8})." | Evidence |
| `evidence exported` | `file, sha256, exhibits, changed` | "An evidence bundle of {exhibits} files was made on {date} (SHA-256 {sha256})." | Appendix |

In screening mode, run notes and changed bios through the same protected-traits filter as every other sentence.

## Integration points in modules this session doesn't own

1. **`posts.add_files(case, paths, platform, posted_at, url=None, account_url=None)`.**
   - **Why:** a link the investigator gives (inbox `ID=URL`, or the upload dialog) should land on the post row, so the report and scan hits show it.
   - **Today:** it lives only in the `inbox import` audit entry and the bundle manifest.
   - **Watch for:** the `unique (source, url)` constraint. Two files from one post, such as a video and a screenshot, would need to share the post.
2. **`app.add_media` saves uploads as `0.jpg`, `1.mp4`…**
   - **Problem:** that's the name posts' `file added` audit records, so the investigator's own file name is lost.
   - **Fix:** keep the original name, e.g. `tmp/<n>/<sanitised original name>`.
   - **Until then:** `bundle.describe` ignores names of that shape.
3. **`report.py` could:**
   - show each evidence item's exhibit name (`bundle.describe(case)[sha]`),
   - cite `inbox import` rows (`M-a…`) for where a file came from,
   - mention the last bundle's SHA-256 in an appendix.
4. **`case._sha256`** is used by `inbox.py` and `bundle.py`. Make it public (`sha256_file`) if you'd rather not import a private name.
5. **The startup checks** could add "N photos or videos waiting in Downloads", using `inbox.scan` with no case. Optional.
6. **`report.py`: `N-<id>` citations.** Notes are a fourth citation kind beside `A-`, `E-` and `M-`. `notes.list_notes(case)` gives them with `cite`, `replaced_by` and `ref`.
7. **The startup checks** could also remind about Check again: "2 cases not checked again in 30 days", from the latest `recheck` audit `ts` per case. Optional.
8. **`search.screenshot`** only captures accounts that have no screenshot yet. `recheck._recapture` repeats its loop (about 10 lines) to capture again. An `again=True` flag there would let both share it.
9. **Closing a case, and legal hold.** Done (hunt-server): `Case.close()`, `reopen()`, `set_hold()` and `status()`, and the routes `POST /api/cases/{slug}/close`, `/reopen`, `/hold` and `/delete` (to the Trash). Closing also calls `watch.stop(case, "the case is closed")` at once. `RETENTION_DAYS` now lives in `hunt/case.py`, and `app.RETENTION_DAYS` re-exports it. `watch._ended` could call `case.status()["retention_due"]` instead of repeating the rule.
10. **`serve()`** got one hook (`app.app.router.lifespan_context = _watching(app.app)`) to start the watch loop in the server's own event loop. That loop is where `search.HEAVY` lives. Tests that build the app with `make_app` never start it.
11. **New post collectors** (TikTok, Instagram, Facebook, from data-sources) reach Check again and watching with no change here, as long as they're registered in `posts.FETCHERS`/`posts._site`. "Posts gone" and `none_left` then cover those platforms too.

