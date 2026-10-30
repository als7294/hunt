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

Sections 1–3, 5, 7 and 8 run offline. Check again (4) and watching (6) make the same logged-out requests a search and a scan already make, through `HUNT_PROXY`; watching's notifications are local. Nothing is ever downloaded from Instagram, TikTok or Facebook for the investigator.

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
| `manifest.csv` | Exhibit, SHA-256, bytes, hash OK, **role** (evidence or lead), **collected** (read by Hunt / captured in the Hunt Browser / added by the investigator), what it is, source, URL, account, posted at, saved at, the **capture record** (`viewed_as`, `audience`, `tool_version`), original name. Cells a spreadsheet would run as formulas (`=`, `+`, `-`, `@`) are quoted. |
| `SHA256SUMS` | The hashes each file was *saved* under, so `shasum -a 256 -c SHA256SUMS` checks the whole bundle on any machine. A file that changed fails, as it should, and is also flagged in the manifest and README. |
| `audit-log.csv` | The case log with its row ids. They match the report's `M-a<id>` citations. |
| `README.txt` | The case, its purpose on record, the Hunt version, how to check the bundle on macOS, Linux and Windows, and **how the evidence was collected**: automation-legal.md's Appendix A paragraph, for a certification under FRE 902(13) and (14). |

The zip's own SHA-256 is printed, sent as the `x-bundle-sha256` header, and logged as `evidence exported`.

**Every sentence in the README stays true** (automation-legal.md's Appendix A asks for exactly this):
- **The capture record.** Its sentence ("the account it was viewed from, the audience…, the versions of Hunt and Hunt Capture") appears only when every captured exhibit carries all three fields. Otherwise the README says how many captured files lack them. Today none carry them: Hunt Capture doesn't send them yet (integration point 18), and K5 is still partly built.
- **User-Agents.** The Appendix's "a User-Agent naming Hunt" isn't true for every request, so the README says which: public APIs and post feeds name Hunt; the site-existence checks, profile-photo fetches and screenshots present a common browser's (integration point 19).
- **Leads.** Frames the automatic scan saved from a video are `role: lead`, described as "a lead, not evidence; the video is the evidence". Every other file is `evidence`.
- **Not built:** the separate attribution section per account (numeric ID, matching details; *Vayner*). The report owner may prefer it in the report; see integration point 20.

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
3. **Screenshots:** a fresh, dated, logged-out capture of every account (`recapture`), **except Instagram, Facebook, X and LinkedIn**, whose robots.txt denies unnamed bots. Hunt never sends those platforms a request of its own.

**On Instagram, Facebook, X, LinkedIn and logged-in TikTok, Check again is a worklist** (automation-legal.md §4.3):
- **The worklist** (`GET /api/cases/{slug}/worklist`) lists the subject's confirmed accounts there, with when each was last opened or captured.
- **Opening is hers:** `POST …/worklist/open` opens one account in the Hunt Browser, on her click. It's one page load, audited as `worklist open`, and there is no "open all".
- **LinkedIn pacing:** re-opening a LinkedIn profile within 7 days needs `confirmed: true` after a warning, since LinkedIn can show members who viewed them (Colorado 4.4(a); NYSBA 4.C).
- **Capture comparison** (`recheck.diff_captures`): with Hunt Capture on, each new page archive is compared with the last archive of the same page (the extension's `where` key), giving the same change kinds:
  - **`posts gone`:** a post from the last capture counts as gone only if an **older** post from that capture is still on the page now. Grids often carry no dates, and a post that simply wasn't scrolled to is never called gone.
  - **`post back`.**
  - **`profile changed`,** with `field: "page title"`. The title carries the name, and on LinkedIn the headline too.
  - **`account gone` / `account back`,** from the platform's own "isn't available" / "doesn't exist" wording.
  - **Private accounts:** a page saying the account is private gives `posts gone` with `none_left` and that reason.
  - **Empty captures:** a capture that showed no posts judges nothing, and isn't used as the baseline.
  - Every entry carries `"via": "capture"`.
- **When it runs:** at the start of every Check again job, from `POST …/captures/compare`, and, once the capture owner adds the hook, right after each page capture (integration point 17).

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

### 7. Move a case between computers (`hunt/pack.py`, `hunt pack` / `hunt unpack`)

Laura works on a work laptop and at home. A whole case travels as one encrypted archive: `<case>-<UTC time>.hunt-case.dmg`.

**What's in the archive:**
- `case.db`: a consistent copy, with the audit log, notes, decisions, posts, hits and watch settings.
- Every evidence file.
- `case.json`.
- `manifest.json`: every file's SHA-256 and size, the case, which computer it was packed on, when, and the Hunt version.

**The format:** an **AES-256 encrypted disk image**, made with macOS's own `hdiutil`.
- It needs no extra software.
- Finder can open it with the passphrase.
- The passphrase is chosen per archive (12+ characters) and goes to `hdiutil` on stdin, never on a command line or in a log.
- I chose it over adding a crypto library: the `cryptography` package isn't installed, and a home-made cipher is out of the question.

**Unpacking:**
- The image is mounted read-only and hidden from Finder.
- The manifest may only name `case/case.db`, `case/case.json` and `case/evidence/<sha256>.<ext>`, so a crafted archive can't write anywhere else.
- Every file is copied aside while being hashed. One mismatch, one missing file, or one file the manifest doesn't list, and nothing is accepted.
- The database's integrity is checked, and only then is the case put in place.
- **Never merged:** a case with the same name here is kept, and the new one arrives as `-2`. "Replace" moves the one here to the Trash first.

**Chain of custody across the move:**
- The archived case's own log ends with `case packed`: which computer, which file.
- The computer it left logs `case pack sealed`, with the archive's and the manifest's SHA-256.
- The computer it arrives on logs `case unpacked`, with the same two hashes, so the two logs can be tied together.
- Watching is turned off on arrival (`watch off`, "moved from another computer"), so two computers never both watch one subject.

```
hunt pack --case vance-claim             # asks for the passphrase twice; saves to ~/Downloads
hunt unpack ~/Downloads/vance-claim-20261029-120000Z.hunt-case.dmg [--replace]
```

### 8. Have we seen this person before? (`hunt/seen.py`, `hunt seen`)

Investigators re-encounter subjects and do the work twice. When a case is created, and after a search, its identifiers are looked up in the other cases on this computer:
- **What's compared:**
  - seeds (username, email, phone, profile URL, address, name), normalised: case, `@` and spacing don't matter, and URLs are normalised as decisions are
  - the URLs and handles of accounts marked as the subject's
  - the SHA-256 of the photos and videos in the case
- **Not compared:** page sources and screenshots. A site serves the same "not found" page to everyone.
- **Strength:** a name alone is a **weak** match (namesakes); everything else is strong.
- **What a match shows:** the other case's label, kind and opening date, and what matched. Nothing more.
- **Safety:** local and read-only, and nothing is merged.

**Screening:** an employment screening is purpose-bound, so it works both ways:
- A `background` case's lookup, or any lookup with `screening=1`, doesn't open other cases, and says why.
- `background` cases never appear in another case's matches.
- **Why:** an employment screening may only use what was collected for it (FCRA permissible purpose). Many states bar hiring decisions based on past workers' compensation claims, which is what an insurance case often is.

```
hunt seen kestrel_vane88 kestrel@example.com     # before opening a case
hunt seen --case vance-claim [--screening]
```

### 9. Install, first run, doctor, update, uninstall (`hunt/setup.py`)

Laura installs and runs Hunt without knowing Python. The investigator-facing story is in [user-guide.md](user-guide.md).

**Install, once, in Terminal:** `uv tool install --python 3.12 git+https://github.com/als7294/hunt && hunt setup`.
- `--python 3.12` keeps the installed Hunt on the Python every self-check runs on. Without it, uv picks the newest Python it has (3.13 on the release test Mac).
- This works before Hunt is on PyPI. Once it's published, `uv tool install hunt-osint`.
- uv brings its own Python 3.12.
- Getting uv itself is `brew install uv`, or uv's own installer. That one *is* a `curl | sh`; Hunt doesn't ship one of its own.
- About 1.2 GB on disk.

**The launcher, `hunt setup` → `~/Applications/Hunt.app`.** I chose an **AppleScript applet made on her Mac with `osacompile`**, a stay-open app:
- Double-click starts `hunt app`, which opens the browser.
- Clicking the Dock icon again reopens the page.
- **Quit** stops the server.
- **Why it isn't blocked:** Gatekeeper checks only quarantined files, which means downloaded ones, and an app made locally is never quarantined. `osacompile` signs it ad hoc by itself. So it runs without code signing, notarisation or "Open Anyway". Checked on this Mac: signature `adhoc`, no `com.apple.quarantine`.
- **Why not ship a prebuilt Hunt.app:** a downloaded, unsigned `.app` or `.command` *would* be quarantined. On macOS 15+ that means a trip to System Settings → Privacy & Security → Open Anyway.
- **What it carries:** it remembers `HUNT_HOME`, `HUNT_PROXY` and `HUNT_VLM` as they were when it was made, because an app started from the Dock doesn't see the shell's settings. Run `hunt setup --launcher` after changing the proxy; the old app goes to the Trash.
- **Its log:** `~/Hunt/app.log`, made under umask 077 because it holds the run's sign-in link.

**`hunt doctor`:** Python, uv, Hunt's version and install kind, Ollama (running, installed, or not), the vision model, the browser build, the Hunt Capture extension folder, ffmpeg, free disk space, the `~/Hunt` folder, and the launcher. Each row has a plain fix, and it exits 1 if anything needs fixing. Offline, apart from a 2-second look at the local Ollama.

**First-run downloads** (`hunt setup`, `GET /api/setup`, `POST /api/setup/{item}`):
- **What's offered:** the vision model and the browser build. Nothing else.
- **The size comes first:**
  - The model's size is read from its manifest in Ollama's library, a ~1 KB request. `qwen3-vl:4b-instruct` is 3.34 GB.
  - The browser's size comes from Playwright's own `--dry-run` plus a `HEAD` per file: Chrome for Testing 156 is 195 MB.
  - A download starts only when the investigator accepts that exact size: the route takes `{size}` and refuses any other number.
  - If the size can't be read, the item isn't offered.
- **How each is fetched:**
  - The model through the local Ollama's own `/api/pull`, so Ollama does the downloading and keeps the model where it always does.
  - The browser with `playwright install chromium`.
  - Both stream `progress` events over the existing SSE job pattern.
- **Ollama itself** is an app from ollama.com. Hunt points to it and doesn't install it.

**`hunt update`:**
- `uv tool upgrade hunt-osint`, after a yes.
- Its size can't be known in advance: usually a few MB, more when a dependency like PyTorch changes, and the prompt says so.
- A source checkout is told to `git pull && uv sync`.
- `hunt --version` and the startup screen show the version.

**`hunt uninstall`:**
- Refused while Hunt is open.
- Removes the background watcher (audited in every watched case).
- Moves Hunt.app to the Trash.
- `uv tool uninstall hunt-osint`.
- Asks **separately**, showing the case count and size, before moving `~/Hunt` to the Trash.
- Leaves the browser build and the model, which other tools may share, and says how to remove them.

### 10. Minimisation at the end of retention (`hunt/minimise.py`, `hunt minimise`, `/api/cases/{slug}/minimise`)

Hunt scans everything, but a report uses only what's material (10 CCR §2695.7(d); automation-legal.md §4.5). Once a case's retention date has passed, the raw media nobody used can go while the case stays.

**What goes:** the photos, videos and screenshots of posts that no kept or reported hit and no note points to, plus the frames the scan saved for flags nobody kept.

**What stays:**
- everything kept, reported or noted
- page archives, search results and profile screenshots (they're records)
- the case itself

**How the house rules shape it:**
- **Never a deletion.** The files go to the Trash as one folder (`<case> unused media <date>`). The purge isn't complete until the investigator empties the Trash herself, and the UI and CLI say so.
- **Asked first.** It happens only for the exact count and size the investigator was shown. If moving fails, every file is put back.
- **Never on legal hold:** removing files under a hold would be spoliation. Never before the retention date, and never while a job runs.
- **Audited** as `media minimised`, with every file's path, SHA-256, size and post.

**Afterwards:** the case's posts still list those media, but their files are gone. `Case.verify()` and the bundle skip missing files, and the evidence route answers 404. The UI should show "removed at retention" for media whose SHA-256 is in a `media minimised` entry (integration point 21).

**Release test (0.1.0), on the development Mac, as a first-time user:** each step worked.
- `uv tool install` from the checkout, pinned to `uv.lock`. Hunt Capture is packaged.
- `hunt doctor` reports the real state.
- `hunt setup` makes `~/Applications/Hunt.app`.
- Double-clicking it starts `hunt app` from the installed tool and opens the sign-in page. Its log is mode 600.
- Signing in shows the startup screen with "v0.1.0", then Connect your accounts, with no console errors.
- A second double-click reopens the page without a second server.
- Quit stops the server and removes the PID file.
- `hunt uninstall` (keep data) moves Hunt.app to the Trash, removes the tool and keeps `~/Hunt`.

Fixed along the way:
- The disk row said "10 GB free" while failing a 10 GB minimum (it rounded 9.8); it now shows one decimal.
- Its fix wording read "Free disk space: Free up space…" in setup's summary.
- uv had picked Python 3.13, so the install is now pinned to 3.12.

### Self-checks

All offline, using temp folders only. `test_inbox.py`, `test_bundle.py`, `test_recheck.py`, `test_worklist.py`, `test_notes.py`, `test_watch.py`, `test_pack.py`, `test_seen.py`, `test_setup.py`, `test_minimise.py` and `test_qol.py` each print `ok`.

`test_worklist.py` runs hand-made page archives of a fictional Instagram profile through Hunt Capture's own `extension.add_page`. In turn, the profile:
- loses a post
- changes its title
- gets the post back
- shows no posts
- turns private
- disappears
- comes back

The coverage rule (an older post must still be visible) is mutation-checked. The test also covers the worklist's LinkedIn pacing confirmation.

`test_minimise.py` checks:
- no purge before retention, or on legal hold
- exactly what goes and what stays
- a wrong count or size is refused
- a failing Trash puts every file back
- the audit holds every hash

`test_setup.py` never installs or downloads anything:
- Ollama's API and library are stubbed `httpx` transports.
- Playwright is a fake shell script, for the dry run and the progress lines.
- `uv`, `launchctl` and the Trash are stubbed.
- `osacompile` runs for real, into a temp folder. It compiles the launcher, and the test reads the result back with `osadecompile`.

`test_pack.py` makes one real encrypted image in a temp folder (about 10 s) and checks:
- a wrong passphrase is refused
- a taken name gets `-2`, and `replace` moves the old case to a stubbed Trash
- the hashes in the logs on both sides agree
- watching is off on arrival

On plain folders, it checks that a changed, extra or missing file, a path outside `case/`, and a folder with no manifest are each refused, and that the case itself is never touched. It leaves no image attached.

`test_seen.py` checks:
- strong and weak matches, and their order
- matches through a confirmed account and through the same video
- lookups from typed seeds
- both screening rules

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
| **Private, profile-photo and bio changes on Instagram, Facebook, X and LinkedIn by Hunt itself** | Hunt never requests those platforms. Changes come from comparing her own captures (the page title, the posts shown, "private" and "isn't available" pages). The profile photo and the bio aren't compared there: the extension's parsers return posts, not profile fields. |
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
- **The worklist,** for Instagram, Facebook, X, LinkedIn and TikTok, sits beside the list (`GET …/worklist`):
  - One row per account: platform icon, account, "last opened 3 Oct" (or "never"), and an **Open in Hunt Browser** button → `POST …/worklist/open` `{account}`.
  - On 409, show the warning ("You opened this LinkedIn profile on 2 Oct…") with **Open anyway** (`confirmed: true`) and **Cancel**.
  - There is no "Open all".
  - Helper: "Hunt doesn't visit these sites itself. Open each one with Hunt Capture on; Hunt compares what you see with your last visit."
  - If `uncompared_captures` > 0, call `POST …/captures/compare` and add the returned changes to the list.
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
  - Toggling sends `POST /api/cases/{slug}/watch` `{on, every_days}`. A 409 is shown as is (e.g. "mark at least one account as the subject’s on Is it them? first", "its 90-day retention period has ended").
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

### H. "Move to another computer" in the case menu, and "Bring a case in" on the case list

**Packing:**
- Case menu: **Move to another computer…** opens a dialog.
- **Passphrase** and **Again** fields (password inputs). Helper: "12 or more characters; a few words works well. Hunt can't recover it."
- **Save to** folder, default `~/Downloads`.
- Button **Pack case** → `POST /api/cases/{slug}/pack` `{passphrase, folder}`.
- Show progress, since it's slow for big cases: "Packing… (large videos take a while)".
- On success: "Saved `vance-claim-20261029-120000Z.hunt-case.dmg` (3 files, 1.2 GB). Fingerprint: `71a9…f6`. Copy it to the other computer, and send the passphrase separately."
- Clear the passphrase fields when the dialog closes.

**Unpacking:**
- Case list: **Bring a case in…** lists `GET /api/case-archives` (default `~/Downloads`), plus a folder field.
- Pick an archive, enter the **Passphrase**, then **Unpack** → `POST /api/case-archives/unpack` `{name, folder, passphrase}`.
- If the answer's `slug` isn't the archive's case name, say: "A case with this name is already here, so this one was added as vance-claim-2. Nothing was merged."
- Offer **Replace the one here instead** (`replace: true`), with a confirm step: "The case on this computer goes to the Trash. You can put it back from there."
- Errors are shown as is, e.g. "wrong passphrase, or not a Hunt case archive", or "case/evidence/… doesn't match its hash in the manifest; nothing was imported".
- After unpacking: "Watching is off on this computer. Turn it on here if this is where the case will be watched."

### I. "Seen before" in the new-case form and on the search results

- **New-case form:**
  - As seeds are typed (debounced), call `POST /api/seen-before` `{seeds, kind}`.
  - If there are matches, show a banner above **Create**: "You may have looked into this person before: *Vance 2025 claim* (insurance, opened 3 Mar 2025) shares the username kestrel_vane88."
  - Each match links to the case and lists its `on` items: `file` as "the same photo/video", `name` as "same name only: could be someone else", in a weaker style.
  - **Nothing is merged and nothing is blocked:** the investigator decides.
- **After a search** (Is it them?, or the case overview): `GET /api/cases/{slug}/seen-before` gives the same list.
- **`checked: false`:** show `why` in place of the list (employment screenings).
- **`skipped_screenings` > 0:** add a quiet line, "1 employment screening on this computer wasn't looked at."
- **Notes:** a **Note** button on each match pre-fills "Seen before in *Vance 2025 claim*: …" (`about: "case"`). Linking the two cases goes on the record that way, by the investigator's own hand.

### J. Setup and version on the start screen

- **The version:** done for 0.1.0. The startup screen shows "v0.1.0" beside the Hunt brand, from `GET /api/startup` → `version` (a two-line change in `hunt/static/app.js`, `#boot-version`). Still to do: "Update: run `hunt update`" beside it.
- **A setup card** when `GET /api/setup` → `items` isn't empty. One row per item:
  - **Ollama** (`installable: false`): "Hunt runs its vision model with Ollama, a free app." A link to `https://ollama.com/download` (opened in her browser), plus "Open Ollama once, then **Check again**", which re-fetches `/api/setup`.
  - **The vision model / the browser:** label, `detail`, and the size in GB (`size / 2**30`, one decimal).
    - Button **Download 3.3 GB** → `POST /api/setup/{id}` `{size}`, sending exactly the `size` shown.
    - Then a progress bar from the job's `progress` events (`done / total`), with the `message` underneath, small.
    - Pause and cancel use the existing job controls.
    - When it's done, re-fetch `/api/setup`.
  - **`installable: false` with a size of null:** "Couldn't read the download size; check the connection", and a **Try again** button. Never offer a download without a size.
- **"Everything Hunt needs"** (collapsed): the `doctor` rows, ✓ or ✗ with `detail`, and `fix` under each ✗.
- **The Hunt Browser's sign-in rows** stay as the capture session designed them (`/api/browser/status`).

### K. Retention: "Remove unused media" beside delete and legal hold

- **Where:** the startup screen's retention row, and the case's own page once `Case.status().retention_due`.
- **The offer:** `GET /api/cases/{slug}/minimise` gives `count` and `bytes`. Show **Remove unused media (34 files, 1.2 GB) and keep the case**, beside **Delete the case** and **Put on legal hold**.
- **The confirm dialog** lists the files (kind, source, posted date) and says: "Nobody kept, reported or noted these. They go to the Trash; the case and everything kept stay."
- **Then:** `POST …/minimise` `{count, bytes}`. On success: "Moved to the Trash as 'vance-claim unused media 2027-01-28 …'. Empty the Trash to finish removing them."
- **409:** shown as is (legal hold, not yet due, changed since shown).
- **Under legal hold:** the row says "On legal hold: nothing may be removed", and there's no button.

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
| `worklist open` | `account, platform, warned` | Methodology: "{platform} account {account} was opened by the investigator in the Hunt Browser on {date}." | How we searched |
| changes with `"via": "capture"` | as Check again's, plus `page` | Same sentences as Check again's; say "on the investigator's capture of {date}" instead of "when Hunt checked again". | What we found |
| `media minimised` | `count, bytes, trashed_as, files: [{file, sha256, bytes, post, kind}]` | "On {date}, at the end of the retention period, {count} unused media files were removed (data minimisation); their hashes are in the case log." | How we searched (or an appendix) |
| `watch on` / `watch off` | `every_days, next` / `why` | "From {date}, the subject's accounts were watched every {every_days} days." / "Watching stopped on {date}: {why}." | How we searched |
| `watch run` | `new_posts, changes, new_flagged, alerts` | Usually folded into one sentence: "The accounts were checked {n} times between {first} and {last} while watched; {sum new_flagged} posts were newly flagged." | How we searched |
| `alert` | `kind, text, hits` or `change` | Not a report sentence in itself: the hits and changes it points to are already cited. Useful as "first noticed on {date}". | (none) |
| `background watching` | `on, agent` | Methodology detail: "Checks also ran in the background while Hunt was closed, from {date}." | How we searched |
| `case packed` | `from, file` | "The case was packed on {from} on {date} to move it to another computer." | How we searched (chain of custody) |
| `case pack sealed` | `file, sha256, manifest_sha256, files, bytes, changed` | Only on the computer it left: "Archive {file} (SHA-256 {sha256:8}) was sealed on {date}." | Appendix |
| `case unpacked` | `file, sha256, manifest_sha256, from, packed_at, files, as, replaced` | "On {date}, the case was brought onto this computer from {from} (packed {packed_at}); all {files} files matched their hashes (archive SHA-256 {sha256:8})." | How we searched (chain of custody) |
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
12. **Screening as a case setting.** "Screening" is a report flag today (`?screening=1`), plus the `background` kind. `seen.py` treats every `background` case as an employment screening. If a case-level "this is an employment screening" setting arrives, `seen.for_case` should read it instead of the kind.
13. **A case created from "seen before".** The new-case form could offer "Open *Vance 2025 claim* instead". That's navigation only, never a merge.
14. **Hunt Capture must ship inside the installed package.** `browser.SOURCE` is `<repo>/extension`, outside the `hunt` package, so a wheel (and `uv tool install`) had no extension.
    - **Stopgap here:** `[tool.hatch.build.targets.wheel.force-include] "extension" = "extension"` in `pyproject.toml`, so it lands at `<site-packages>/extension`, which `browser.SOURCE` already resolves to. That's safe because uv tools get an environment of their own.
    - **Proper fix, for the capture owner:** move `extension/` to `hunt/extension/` and set `SOURCE = Path(__file__).parent / "extension"`, then drop the force-include.
    - `hunt doctor`'s `capture` row catches a missing extension either way.
15. **`_new_job` opens the case** (to refuse jobs on closed cases), so jobs that aren't tied to a case (setup downloads, slug `""`) build their `Job` directly. A small `_new_job(..., case=False)` would share the pattern.
16. **`watch.py` now reads `Case.status()`** (`closed`, `retention_due`) instead of meta keys, so it follows `case.py`'s lifecycle exactly.
17. **A hook after each page capture, for the capture owner (asked).** In `app.capture_page`, after `extension.add_page(...)`, call `recheck.diff_captures(c)` and return its changes. Changes then appear the moment she captures. Until then, they appear at the next Check again or `POST …/captures/compare`.
18. **Capture-record fields (K5), for the capture owner (asked).** The bundle reads these from `capture view` / `capture page` / `capture recording` audit details, and per post from `post_extra`:
    - `viewed_as`: "logged in as <handle>" or "logged out"
    - `audience`: e.g. "Public" or "Friends"
    - `hunt_version`
    - `capture_version`: the extension's manifest version

    Names can change if the capture owner prefers others; `bundle._record` is the one place to adjust.
19. **User-Agents vs "honest UA".** `sources/wmn.py` sends a Chrome User-Agent, and `search.avatars` reuses it. Maigret sends its own headers, and Playwright screenshots send Chromium's. automation-legal.md §4.4 asks for an honest User-Agent on the automatic checks. The bundle README describes what's true today; when the sources change, its sentence in `bundle.COLLECTED` should change with them.
20. **The per-account attribution section** (*Vayner*: numeric ID, matching details), listed in automation-legal.md's bundle additions, isn't built. It reads like report content: the "Is it them?" reasons per account, plus each platform's numeric ID where a capture recorded it. The report owner can decide where it lives; the bundle can carry it as `attribution.csv` once those IDs are recorded.
21. **Media removed at retention.** The posts and scan views should show "removed at retention (data minimisation)" for media whose SHA-256 appears in a `media minimised` audit entry, rather than a broken image.


## Known gaps (from the walkthrough of docs/user-guide.md, 2026-10-29)

The walkthrough followed the guide in the real app, from a clean `HUNT_HOME`, on NASA's public accounts, at 1024 and
1400 px. What it found and fixed is in the hunt-server commits from that day. What's left:

**Not fixed**
- **Mirror accounts score high, and higher since the analysis merge.** Eight Mastodon instances showing a copy of
  `@NASA` scored 62% each on the first run. On the re-run after the analysis merge (126de25) the same accounts scored
  94–99% ("almost certain"), with the same three reasons: shared profile photo, a link back to the real profiles, and
  the username. It isn't `hunt/learning.py`, which needs 30 decisions of each kind first. The UI words them "likely"
  at most, and she ruled them out by hand (Is it them? keeps them listed, with Undo). A federated copy should
  probably not count the photo it copies as a second identifier (`hunt/match.py`, analysis session).
- **Case-level notes aren't in the report**; only notes on an item that's in the report are (cited "Note n"). A
  choice of which case notes to print would be a new screen.
- **`posts.collect` calls every unreadable site "Reddit".** For an account on a site it has no reader for (GitHub,
  SoundCloud…) it emits `failed` with "this site's posts can't be read logged out (Reddit answers 403)", now visible
  in the scan's source list. The note should name the site, and "not readable logged out" isn't a failure
  (`hunt/posts.py`, posts owner).
- **The subject's name in the search cluster** can sit under a match badge ("✓ 12 of 16 accounts share a profile
  photo"); the account labels now step aside, the subject's doesn't. Cosmetic; the name is in the case pill.
- **Face comparison isn't downloadable from Hunt yet.** The start-up row says when OpenCV or the two models are
  missing, but the "button on the startup screen" (docs/analysis.md "Plug in") would be a `setup.plan` item: the
  setup owner's.

**Fixed** (2026-10-30, hunt-server)
- **The search cluster crowded at 15 accounts.** Each account label is measured every frame against the subject's
  name, the headline, the match badges and the labels already placed; one that would overlap stays hidden until its
  node is hovered.
- **Text-only flags showed an empty striped thumbnail.** They show a quote mark, and the card is shorter.
- **"Web page" downloaded the HTML.** It opens in a tab (`report.html?view=1`), inline and sandboxed (no script, no
  requests, not the app's origin), and prints as the download does.
- **Media removed at retention showed as a broken image.** An evidence picture that no longer loads becomes a box
  reading "Removed from the case".

**Not verified live, on purpose**
- **Sign in / Open in Hunt Browser** (launches Chrome for Testing on the Mac) and **worklist opens**. Both routes
  were exercised only up to the click.
- **Read public preview**: `hunt/public.py` is on main now, but no case in the walkthrough had an Instagram,
  Facebook or TikTok account it could read (nasa's TikTok is an archived link), so the button wasn't pressed.
- **Downloads on the start screen**: nothing was missing on this Mac, so the Download button and its progress
  weren't seen. The doctor rows were (low disk space; Hunt not in Applications).
- **"Keep watching when Hunt is closed"** installs a LaunchAgent. Only Watch on and off were tried.
- **Replace on unpack** sends the case here to the Trash. Pack and "add as a second case" were tried.
- **Remove unused media**: no case in the walkthrough was past its 90 days. The plan and the 409s are covered by
  test_qol.
- **Dropping files onto Posts**: the browser pane can't drag from Finder. The two test files went in through
  From Downloads pointed at their folder, with the originals kept.
- **The worklist's grid counter, "open these" list and grid labels** read the extension's `progress`, `todo` and
  `extra.from` (on main since the facebook merge), but no capture with them was made in the walkthrough. Without
  them the worklist falls back to the checklist and the case's flags, which is what was seen.
- **Hard stops** were tested with a stop written by `browser.stop()` (the extension's watcher wasn't triggered):
  the start screen, Connect your accounts and the worklist show it, and Resume lifts it after the confirmation.
- **The capture switch** was tested without a Hunt Browser running: Start / Stop capturing changes Hunt's state;
  the extension's mirroring of it wasn't seen.
- **Face comparison** ran for real on `nasa` (16 profile photos, OpenCV and the cached models) with a generated
  reference image that has no face, so every result was "couldn't compare", and the screen says the reference can't
  be used. "Same face" / "Different face" were seen only with a simulated `/person` answer in the page: no real
  person's face was processed.
- **The Apify estimate** was seen only with a simulated `/vendor` answer in the page. The real one, with Aaron's key,
  answered "nothing to run" (no Instagram or Facebook account in the case). No Apify run was started: it spends his
  credit.

**Noticed while testing, not a Hunt bug**
- Restarting `hunt app` makes a new sign-in link, so an open tab stops working. It now says "Open Hunt again"
  (page loads) or shows a banner (calls from an open page), instead of a JSON error or silent failures.
