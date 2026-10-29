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
| 7 | **Deleted or changed content; re-checking a profile over the life of a claim.** | Common in insurance sources | Posts get deleted and privacy settings change during a claim [S] ([Claims Journal, sponsored](https://www.claimsjournal.com/sponsored/hodsonpi/2026/08/10/339321.htm)) | Skipped (see below) |
| 8 | **Bulk import.** | Occasional | Bellingcat's Auto Archiver is popular for batch processing [S] ([Bellingcat](https://www.bellingcat.com/resources/2025/08/13/the-open-source-tool-that-has-preserved-150000-pieces-of-online-evidence/)) | **Covered by the inbox:** any folder, all at once |
| 9 | **EXIF panel.** | Common in tutorials, rarely decisive | Platforms strip EXIF on upload [S] ([Forensic OSINT](https://www.forensicosint.com/guides/what-is-exif-data-and-why-it-matters)) | Skipped (see below) |

## What was built

Everything below runs offline. Nothing leaves the machine, and nothing is ever downloaded for the investigator.

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

### Self-checks

All offline, using temp folders only. `test_inbox.py`, `test_bundle.py` and `test_qol.py` each print `ok`.

They never touch the real `~/Downloads` or the real Trash: `inbox._trash` is swapped for a move into a temp folder. `test_bundle.py` runs the real `shasum -c` on the unzipped bundle.

The real Trash call was checked once by hand, on a scratch file.

## Skipped, and why

| What | Why |
|---|---|
| **Re-checking a profile over time** (rank 7) | High value for insurance work. But it needs repeated collection and a diff in `posts.py`/`sources/`, which are owned elsewhere, and it's a feature, not a quality-of-life fix. **Suggested shape:** `posts.collect` already skips posts it has seen. A "Check again" job could also record which earlier posts are now missing and when, as `posts gone` audit entries. The report's "What we couldn't see" section would cite them. |
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
  - …
- Each entry's `M-a<rowid>` matches the report's citations.

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
