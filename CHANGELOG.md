# Changelog

What Hunt does, release by release, in an investigator's words. How to use each part is in the [user guide](docs/user-guide.md).

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
  - **Startup checks:** your cases, evidence fingerprints, the local AI, the internet and your proxy, every source, the Hunt Browser, and retention dates.
  - **Connect your accounts:** sign in once, as yourself, in the Hunt Browser.
  - **Free keys (optional).**
  - The version is shown on the startup screen.
- **`hunt doctor`** checks everything Hunt needs and gives a plain fix for each problem.
- **`hunt update`** updates Hunt.
- **`hunt uninstall`** removes Hunt. It asks separately before moving your cases to the Trash.

### Find a person
- **Opening a case:**
  - Choose the kind of work (insurance claim, background check, due diligence or journalism) and give its **purpose**, which is required and goes in the report.
  - For a claim, add the injury date, the reported restrictions and what to look for.
- **What you start from:** a name, username, email, phone number, address or profile link.
- **What Hunt checks:**
  - **Usernames:** about 500 sites with Maigret and about 690 with WhatsMyName.
  - **Email:** whether it's registered on sites, using only checks that can't notify the person. All 220 checks were read and sorted.
  - **Phone numbers,** read offline.
  - **Profiles:** GitHub, Keybase, Bluesky, Mastodon, Stack Exchange and the Wayback Machine, plus what Facebook shows logged out for a profile.
  - **Email-linked records:** Gravatar and OpenPGP keyservers.
  - **Public records:** campaign donations (FEC), SEC filings (EDGAR), the healthcare provider registry (NPI), federal court records (CourtListener), state professional licences, state business registries and motor carriers (FMCSA).
- **Logged:** every source asked, including the ones that found nothing.
- **Screenshotted:** likely matches are captured as evidence.
- **Seen before:** Hunt tells you when another case on this Mac shares an identifier with this one.

### Is it them?
- Every account is scored against everything the case knows. The reasons are shown (name, place, links, the same profile photo), including what doesn't match.
- **Namesakes** are set aside, each with the reason.
- **Public records** are shown apart from the accounts.
- **Verdicts** use intelligence-analysis wording (ICD 203), from "almost no chance" to "almost certain".
  - One identifier alone can't go above "roughly even chance".
  - Hunt's own readings stop at "likely".
- **You decide:** them, not them, or unsure. Your decisions are logged.

### Posts
- **Read automatically, logged out:** Bluesky, Mastodon and YouTube (the latest 15 uploads).
- **Facebook, Instagram, TikTok, X and LinkedIn:** you browse yourself, signed in as you, in the **Hunt Browser**.
  - **Hunt Capture** records what you view: screenshots, page archives, and on request a recording of a video as you watch it.
  - It's off until you turn it on, and it never clicks, scrolls, likes or follows.
  - A checklist ticks off each profile's sections as you capture them.
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
  - **Instagram, Facebook, X, LinkedIn and TikTok:** a **worklist** to open yourself. Hunt compares each new capture with your last one.
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
  - a manifest of what each is and how it was collected, marking scan frames as leads, never evidence
  - fingerprints anyone can check with standard tools
  - the case log and your notes
  - a description of the collection process for a certification under FRE 902(13) and (14)
- **Move a case to another Mac** in one encrypted, passphrase-protected file. Every file is checked on arrival.
- **Case lifecycle:** close, reopen, put on legal hold, or delete (to the Trash).
  - Cases come due 90 days after opening.
  - At that point you can also remove the unused media and keep the case.

### Optional, with a free key
Hunt works fully without any of these. Add them in Hunt's **Keys** screen.
- **GitHub:** more profile reads and searches.
- **Gravatar:** more lookups, and every verified account instead of 4.
- **OpenFEC:** its own quota instead of the shared demo key.
- **CourtListener:** needed for federal court records. Without a key that source is skipped.
- **State open-data portals** (licences, businesses, motor carriers): their own quota.
- **SEC EDGAR:** no key. SEC asks you to give your firm and a contact email.

A **proxy or VPN** (`HUNT_PROXY`) can route all of Hunt's requests.

### Not built yet
- **Locate a photo** (estimating where a photo was taken) shows "Coming soon". It works and is benchmarked from the command line (`hunt photo`), but is on hold.
- **Guided mode:** Hunt Capture counting how much of each profile you've covered, and listing what's left to open. Coming.
- **"Read public preview"** for Instagram, Facebook and TikTok accounts on the worklist (one logged-out read, on your click). Coming.
- **Comparing a capture the moment you make it.** Today it happens at the next Check again.
- **The full capture record:** the account a page was viewed from, the audience the platform showed, and the tool versions. Not recorded yet; the bundle's README says so.
- **A per-account attribution section** in the bundle or the report.
- **Platforms and install:**
  - macOS only, Apple Silicon.
  - Installing needs Terminal once, through uv. Hunt isn't on PyPI yet.
