# Changelog

What Hunt does, release by release, in an investigator's words. How to use each part is in the [user guide](docs/user-guide.md).

## Unreleased

Changes since 0.1.0, mostly from the compliance audit and the decisions in [Hunt's rules](docs/research/legal.md#decisions-provisional-2026-10-30). Those decisions are provisional, and Aaron may overrule them.

### Changed
- **Facebook is read one profile at a time,** only when you click **Read public preview**, never as part of a batch search.
- **YouTube needs your free key.** YouTube's rules don't let software read its feed, so Hunt reads a channel's uploads only through the official API. Without the key it reads nothing from YouTube.
- **More platforms Hunt never contacts itself:** Reddit, Threads, Strava and Snapchat join Facebook, Instagram, X and LinkedIn.
  - **Check again** no longer screenshots them in the background; that's for TikTok, YouTube, Bluesky and Mastodon only.
  - **No more Mastodon mix-ups:** Hunt no longer mistakes a Threads, TikTok or YouTube address for a Mastodon account.
- **Hard stops on Hunt's own reads:**
  - **Rate limits:** a "slow down" (429) ends that platform's automatic reads for the rest of the run.
  - **Hard stops:** a CAPTCHA, a blocked address or a login wall on an automatic read stops that platform until you resume it.
- **Site checks name Hunt.** The username checks send Hunt's own User-Agent, one request per site.
- **Children are never named.** A child mentioned in a post ("my son Leo") appears only as "a child":
  - in the people Hunt notices around the subject
  - in the report
  - in the evidence bundle's log, where the names you give people in photos are withheld (they stay in the case)
- **Relationships are quoted, not labelled:** "posted 'my brother Dan'", never "brother: Dan".
- **"Seen before"** compares only the subject's own photos and videos, never a friend's post captured in passing.
- **The face check** (still not in the app) runs only for a subject whose recorded home is a place it recognises and doesn't block. California is always blocked.
- **Retention is a reminder:** at 90 days Hunt asks you to delete, hold or trim the case.
- **The evidence bundle's README** now describes this case exactly:
  - how many ways its files came in (adding "through a vendor" when Apify was used)
  - whether captures were made signed in or signed out
  - any guided-mode steps
  - whether the scan's leads are still to review
  - which requests named Hunt
  - It still carries the original, unblurred files, for chain of custody.

### Decided, being built
- **Guided mode** will be off until you turn it on in Hunt, with an acknowledgement of what it does. Until then, leave it alone.
- **Background-check reports** will always be the screening version. Until then, choose it yourself.
- **"Keep" keeps a flag for the case file only;** only **Add to report** puts it in the report. Today the report still lists kept flags too.
- **Deleting a case** will leave only a minimal record: the time, a hash of the case's name, its opening date, the reason, and the log entry's number. Today `~/Hunt/deleted-cases.log` also keeps the case's name, label and purpose.

## 0.1.0: first release

Hunt finds a person's accounts, helps you decide which are really theirs, looks through what they post for what your client needs, and hands over a report where every sentence cites its evidence. It runs on your Mac (Apple Silicon); your cases, evidence and the AI that reads photos and videos stay on it.

### Getting started
- **Install:** two lines in Terminal, once. Then **Hunt** sits in Applications. Double-click it to start; Quit it in the Dock to stop.
- **`hunt setup`:**
  - puts Hunt in Applications
  - downloads the browser Hunt uses (about 0.2 GB)
  - downloads the vision model (3.3 GB), through Ollama
  - **shows each size and asks first**
- **Ollama:** you install it yourself from ollama.com; Hunt points you to it.
- **First run:**
  - **Startup checks:** your cases, evidence fingerprints, the local AI, the internet and your proxy, every source, the Hunt Browser, and retention dates. The version is shown there too.
  - **Connect your accounts:** sign in once, as yourself, in the Hunt Browser.
  - **Free keys (optional).**
- **A demo case** (`hunt demo`): a finished, fictional investigation to look through, marked DEMO everywhere and read-only.
- **`hunt doctor`** checks everything Hunt needs and gives a plain fix for each problem.
- **`hunt update`** updates Hunt.
- **`hunt uninstall`** removes Hunt. It asks separately before moving your cases to the Trash.

### Find a person
- **Opening a case:**
  - Choose the kind of work (insurance claim, background check, due diligence or journalism) and give its **purpose**, which is required and goes in the report.
  - For a claim, add the injury date, the reported restrictions and what to look for.
- **What you start from:** a name, username, email, phone number, address, profile link, date of birth, age or employer.
- **What Hunt checks:**
  - **Usernames:** about 500 sites with Maigret and about 690 with WhatsMyName.
  - **Email:** whether it's registered on sites, using only checks that can't notify the person. All 220 checks were read and sorted.
  - **Phone numbers,** read offline.
  - **Profiles:** GitHub, Keybase, Bluesky, Mastodon, Stack Exchange and the Wayback Machine, plus what Facebook shows logged out for a profile.
  - **Email-linked records:** Gravatar and OpenPGP keyservers.
  - **Public records:**
    - campaign donations (FEC)
    - SEC filings (EDGAR)
    - the healthcare provider registry (NPI)
    - state professional licences, state business registries and motor carriers (FMCSA)
    - **court records:** federal dockets and state appellate case law (CourtListener), plus the court tables cities and states publish as open data (New York City housing and civil cases, OATH hearings, New York State tax warrants, the Ohio Court of Claims, Chicago administrative hearings, Texas environmental judgments)
- **Court portals that bar automated searches** are listed as links for you to search by hand.
- **Logged:** every source asked, including the ones that found nothing.
- **Screenshotted:** likely matches are captured as evidence.
- **Seen before:** Hunt tells you when another case on this Mac shares an identifier with this one.

### Is it them?
- Every account is scored against everything the case knows. The reasons are shown (name, place, links, the same profile photo re-posted elsewhere), including what doesn't match.
- **Namesakes** are set aside, each with the reason.
- **Public records** are shown apart from the accounts and weighed against the case's facts (date of birth or age, employer, place), so a namesake's court case can be set aside with the reason.
- **Verdicts** use intelligence-analysis wording (ICD 203), from "almost no chance" to "almost certain".
  - One identifier alone can't go above "roughly even chance".
  - Hunt's own readings stop at "likely".
- **You decide:** them, not them, or unsure. Your decisions are logged.

### Posts
- **Read automatically, logged out:**
  - Bluesky and Mastodon.
  - YouTube: the latest 15 uploads, or every upload with a free YouTube key.
  - TikTok's public pages, read only where TikTok allows it and stopping at the first refusal: a profile's bio and counts, and each video's caption, time and file. The file is fetched unless the uploader turned downloads off; then only the cover is kept.
- **Facebook, Instagram, TikTok, X and LinkedIn:** you browse yourself, signed in as you, in the **Hunt Browser**.
  - **Hunt Capture** records what you view: page archives, screenshots, and on request a recording of a video as you watch it.
  - A **capture record** goes with each capture: when it was made, whether you were signed in (and as whom, if you told Hunt your handle), the audience the platform showed, and the tool versions.
  - **When it's on:** it's off until you turn it on. It never clicks, scrolls, likes or follows, and never records LinkedIn.
  - **If a platform challenges or blocks your account,** recording on that platform stops until you resume it.
  - A checklist ticks off each profile's sections as you capture them.
- **Read public preview:** one logged-out read of a confirmed account, on your click.
- **Optionally, through Apify on your own paid account:** public Instagram and Facebook posts. The cost is estimated and capped before each run, and every post is marked as obtained through Apify.
- **Facebook pages you saved** can be imported.
- **From Downloads** files the videos and screenshots you saved under clear names:
  - TikTok and X post times are read from the post's ID.
  - The originals go to the Trash.
- **Your own files** can be added directly too.

### The media scan
- Looks through every photo and video on your Mac, including captions, text in screenshots and video frames, for what you asked for:
  - physical activity
  - lifting or carrying
  - sport and gym
  - long walks or hikes
  - travel
  - another job
  - driving
  - mentions of the injury
  - or your own words
- **Faster:** about twice as fast on photos and twelve times on video as before release, with accuracy held. Measured on a hand-labelled set of 213 photos and 40 videos.
- **Each flag shows:**
  - what was seen
  - the date
  - before or after the injury, and by how many days
  - for video, the exact seconds
- **Children:** flags where a child may be visible are blurred.
- **Review:** each flag is **kept**, **not relevant** or **in the report**. A flag nobody reviewed is a lead, never a finding.

### Report
- Written from the case's records, with no AI writing. **Every sentence cites its evidence:** an account, a post, a source, a log entry or one of your notes.
- **It also says what Hunt couldn't see:** sources that failed or weren't run, sites whose posts Hunt couldn't read, flags ruled out, undated items, and which public records weren't searched.
- **Downloads:** PDF, HTML or JSON, with your report settings (firm, investigator, licence and so on).
- **The screening version,** for employment, drops protected traits and records about them.

### Over the life of a claim
- **Check again:**
  - **Bluesky and Mastodon,** where Hunt reads profiles itself: new posts, posts gone (with when each was last seen), name, bio and profile-photo changes, and accounts that vanished. Screenshots are retaken automatically where sites allow it.
  - **Instagram, Facebook, X, LinkedIn and TikTok:** a **worklist** to open yourself. The moment you capture, Hunt compares it with your last capture of that page.
  - LinkedIn warns you before you view the same profile twice in a week.
- **Watch this subject:**
  - Checks again every day, 3 days or week, scans what's new, and sends a notification with counts only.
  - Waits while your Mac is on battery, busy or in use.
  - Can keep watching while Hunt is closed (off unless you turn it on).
- **Notes:** timestamped, can be cited, never deleted. A correction is kept beside the original.

### Evidence and custody
- **Fingerprints:** every file is stored under its SHA-256 fingerprint and re-checked at startup.
- **The case log** records every search, decision, capture, import and export.
- **The evidence bundle**, for the client, counsel or court:
  - every exhibit under a readable name
  - a manifest of what each is, how it was collected and its capture record, marking scan frames as leads, never evidence
  - fingerprints anyone can check with standard tools
  - the case log and your notes
  - a description of the collection process for a certification under FRE 902(13) and (14)
- **Move a case to another Mac** in one encrypted, passphrase-protected file. Every file is checked on arrival.
- **Case lifecycle:** close, reopen, put on legal hold, or delete (to the Trash).
  - Cases come due 90 days after opening.
  - At that point you can also remove the unused media and keep the case.

### Optional, with a key
Hunt works fully without any of these. Add them in Hunt's **Keys** screen.
- **Free:**
  - **GitHub:** more profile reads and searches.
  - **Gravatar:** more lookups, and every verified account instead of 4.
  - **OpenFEC:** its own quota instead of the shared demo key.
  - **CourtListener:** needed for federal court records. Without a key that source is skipped.
  - **State open-data portals** (licences, businesses, motor carriers, court tables): their own quota.
  - **YouTube Data API:** every upload instead of the latest 15.
  - **SEC EDGAR:** no key. SEC asks you to give your firm and a contact email.
- **Paid, your own account:**
  - **Apify:** public Instagram and Facebook posts, within the caps you set.

A **proxy or VPN** (`HUNT_PROXY`) can route all of Hunt's requests.

### Coming, not in this release
- **Guided mode:** Hunt Capture walking you through each profile, counting how much you've covered and what's left. It's built and tested but not yet tried live, so it's held back.
- **The face check against a reference photo:** an opt-in, one-to-one check of your own photo of the subject against candidate profile photos, allowed only where the subject's home state or country permits it. The engine is built; the reference-photo screen isn't.
- **Learning from your decisions,** so Hunt's weights follow how you rule.
- **Locate a photo** (estimating where a photo was taken) shows "Coming soon". It works and is benchmarked from the command line (`hunt photo`), but is on hold.
- **For Hunt Capture:**
  - a Reddit post reader, and the Facebook photos tab
  - saving a video from what the player already loaded
  - a Safari version
- **A per-account attribution section** in the bundle or the report.
- **Platforms and install:**
  - macOS only, Apple Silicon.
  - Installing needs Terminal once, through uv. Hunt isn't on PyPI yet.
  - An extension loaded by hand into another browser must be paired again after each Hunt restart. The Hunt Browser doesn't need this.
