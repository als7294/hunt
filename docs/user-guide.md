# Hunt: a guide for investigators

Hunt helps you find a person's accounts online, decide which ones are really theirs, look through what they post for what your client needs to know, and hand over a report where every sentence points to its evidence.

It runs on your Mac. Your cases, evidence and the AI that reads photos and videos all stay on it.

> The app's screens are being redesigned. Buttons in this guide may be worded slightly differently from what you see; the steps are the same.

---

## 1. Installing Hunt (once)

You need a Mac with Apple Silicon (M1 or later) and about **6 GB of free space**:
- Hunt itself takes about 1.2 GB.
- The vision model takes 3.3 GB.
- The browser Hunt uses takes about 0.2 GB.
- Leave room for your cases on top of that.

Installing needs **Terminal**, once. Open it (Applications → Utilities → Terminal), paste each line, and press Return:

1. **Install uv**, the tool that installs and updates Hunt. If you use Homebrew:
   ```
   brew install uv
   ```
   If you don't, follow the one-line installer at [docs.astral.sh/uv](https://docs.astral.sh/uv/getting-started/installation/).

2. **Install Hunt and set it up:**
   ```
   uv tool install git+https://github.com/als7294/hunt && hunt setup
   ```
   `hunt setup` does three things:
   - It puts **Hunt** in your Applications folder.
   - It shows the size of each remaining download (the browser, and the vision model) and asks before fetching it.
   - It ends with a list of anything still to do.

3. **Install Ollama** from [ollama.com/download](https://ollama.com/download) and open it once. Ollama runs the vision model on your Mac. Hunt points you to it but doesn't install it for you.

From then on, you won't need Terminal for your daily work. The downloads above can also be started from inside Hunt.

## 2. Starting and stopping Hunt

- **To start Hunt,** double-click **Hunt** in Applications. Your browser opens on Hunt's home screen. Hunt is only reachable from this Mac; nothing else on your network can open it.
- **If you closed the browser tab,** click Hunt in the Dock to get the page back.
- **To stop Hunt,** use Hunt in the Dock → **Quit**.

**If nothing opens:**
- Run `hunt doctor` in Terminal. It checks everything Hunt needs and says, in plain words, how to fix what's missing.
- Hunt's own log is at `~/Hunt/app.log`.

## 3. The first run

Hunt's start screen checks its pieces:
- your case folder
- your evidence (every file is re-checked against its fingerprint)
- the local AI model
- the internet, and your proxy if you use one
- the search sources
- the Hunt Browser
- cases past their retention date

Anything missing comes with a fix. If a download is needed, Hunt shows its size and waits for your **yes**.

### Signing in to the Hunt Browser

Hunt reads public pages **logged out**. Facebook, Instagram, TikTok, X and LinkedIn show logged-out visitors very little. For those, you look yourself, **logged in as you**, in the **Hunt Browser**: a separate browser window Hunt opens, with its own profile.

- **Sign in once,** with your own accounts, from Hunt's start screen. You stay signed in from then on.
- **When macOS asks** to let "Google Chrome for Testing Safe Storage" use your Keychain, choose **Always Allow**. That key protects your saved logins.
- **Hunt Capture,** an extension already built into the Hunt Browser, records what you view into the case you have open, with time and fingerprint.
  - **Turning it on:** it's off whenever the browser starts. Turn it on from its toolbar button; a red **REC** badge shows while it's recording.
  - **How much it records:** either every page you settle on (the default), or only when you press **Capture this** (Alt+Shift+H).
  - **Video:** it can also record a video of the tab as you watch it.
- **What it never does:** clicks, scrolls, likes or follows. It only records what you chose to look at.
- **Use your own, real accounts.** Never fake ones.
- **Never interact with the person you're looking into:** no follows, likes, messages or friend requests. Hunt can't stop a click for you.

## 4. A case, from start to report

### Open a case

Give the case a name, choose what kind of work it is (an insurance claim, a background check, due diligence or journalism), and write its **purpose**: who asked, why, and why it's lawful. Hunt won't open a case without a purpose. It's the first line of the case's log, and it goes in the report.

For an insurance claim, add:
- the **injury date**
- the restrictions the claimant reported
- what to look for: lifting or carrying, sport and gym, long walks, travel, another job, driving, mentions of the injury, or your own words

Before you create the case, Hunt tells you if **you've looked into this person before** in another case on this Mac (section 6).

### Find a person

Enter whatever you have: a name, username, email, phone number, address or profile link. You can add more any time.

Hunt then:
- checks hundreds of sites and public records at once
- notes every source it asked, including the ones that found nothing (your methodology section needs those)
- screenshots the likely matches as evidence

### Is it them?

This is where namesakes get caught. Hunt groups the accounts it believes belong to one person. For each account, it shows **why**: the name matches, the place matches, the same profile photo appears elsewhere, it links to another of their accounts. It also shows what **doesn't** match.

People with the same name who are probably someone else are listed separately, with the reason.

**You decide.** For each account, or for the whole person, mark it **them**, **not them** or **unsure**. Your decision is logged and goes in the report. Hunt never decides for you.

### Posts

Hunt reads the confirmed accounts' public posts by itself where it can do so logged out: Bluesky, Mastodon and YouTube. For Facebook, Instagram, TikTok and X, the posts come from you:
- what you viewed in the Hunt Browser with Hunt Capture on
- Facebook pages you saved
- screenshots and videos you saved: use **From Downloads** (section 6)

Then Hunt's **media scan** looks through every photo and video, on your Mac, for what you asked it to look for. Each flag shows:
- what was seen ("a person carrying a box")
- the date
- before or after the injury, and by how many days
- for videos, the exact seconds

**Review each flag:**
- **Keep** it.
- Mark it **Not relevant**.
- Put it **In the report**.

A flag nobody reviewed is not a finding.

### Report

The report is written from the case's own records, with no AI writing:
- **Every sentence cites its evidence:** an account, a post, a source checked, a log entry or one of your notes.
- **A sentence without evidence can't appear.**
- **It says what Hunt couldn't see:** private accounts, failed sources, undated posts.

Download it as **PDF**, **HTML** or **JSON**.

**For employment screening, download the screening version.** It drops protected traits (age, health, religion, politics and the like) and records about them. An employment screening may make you a consumer reporting agency under the FCRA; the report says so.

## 5. What the verdicts mean

Hunt grades how likely each account is to be the subject's. It uses the wording US intelligence analysts use (ICD 203):

| Verdict | Roughly |
|---|---|
| almost certain | 95% or more |
| very likely | 80–95% |
| likely | 55–80% |
| roughly even chance | 45–55% |
| unlikely | 20–45% |
| very unlikely | 5–20% |
| almost no chance | under 5% |

- **One clue is never enough.** An account that matches on the username alone can't rise above "roughly even chance", however rare the username. Investigators require two independent identifiers, and so does Hunt.
- **Machine readings stop at "likely".** In the report, Hunt never words its own reading of an account or a photo more strongly than "likely". Only your decisions go further.
- **Every point has a reason you can read.** Weights stay hidden, because the reasons are what matter.

## 6. Everyday helpers

- **From Downloads.**
  - Videos saved from sites like ssstik or snaptik land in Downloads with names like `ssstik.io_1745821072612.mp4`. Hunt lists recent photos and videos there and proposes a clear name, e.g. `2024-03-28_tiktok_kestrel_vane88_3fa9c2d1.mp4`.
  - For TikTok and X, it reads **when the post was made** from the post's own ID.
  - Paste the post's link to attach it.
  - Filed files go into the case as evidence. The originals go to the Trash, never deleted, so you can put them back.
- **Check again.** Looks at the confirmed accounts again: new posts, posts that disappeared (with when each was last seen), name, bio or profile photo changes, and accounts that vanished. Each change is logged and can be cited.
  - **On Instagram, Facebook, X, LinkedIn and TikTok, Hunt doesn't visit the sites itself.** Check again gives you a **worklist**: open each account from it in the Hunt Browser, with Hunt Capture on.
  - **Hunt compares what you capture with your last visit:** posts gone or back, a changed name, an account that went private or disappeared.
  - **A post you simply didn't scroll to is never called gone.**
  - **LinkedIn can show members who viewed them.** Hunt warns you before you open the same LinkedIn profile twice in a week.
- **Watch this subject.** Turn it on for a case, every day, every 3 days or every week:
  - Hunt checks again, scans what's new, and sends you a notification ("Vance claim: 2 new flagged posts") that contains counts only, never what was posted.
  - It waits while your Mac is on battery, busy or in use, so it doesn't slow you down.
  - To keep watching while Hunt is closed, turn on **Keep watching when Hunt is closed**. It's off unless you turn it on, and one click removes it.
  - Watching stops when you close the case or its retention period ends.
- **Notes.** Write what you saw, did or decided, and why, on the case or on any account, post or flag. Notes are timed and kept, and you can cite them in the report.
  - Notes can't be deleted. To fix one, write a correction; the original stays, marked as corrected.
  - Keep what you saw separate from what you think it means.
- **Seen before?** When you create a case, and after a search, Hunt tells you which other cases on this Mac share a username, email, phone number, profile, address or the same photo or video. It shows only the other case's name and what matched, and never merges cases.
  - A name alone is shown as a weak match.
  - Employment screenings are kept apart: they look into no other case, and no other case sees them.
- **Move a case to another computer.**
  - **Pack** a case into one encrypted file, protected by a passphrase you choose. It's macOS's own encrypted disk image, so Finder can open it too.
  - **Unpack** it on the other Mac. Every file is checked against its fingerprint before anything is accepted.
  - Both Macs log the move with the same fingerprints.
  - Send the passphrase separately from the file.

## 7. Handing over the evidence

**The evidence bundle,** on the Report screen, is a `.zip` for your client, counsel or the court. It contains:

| In the zip | What it is |
|---|---|
| `exhibits/` | Every evidence file, under a readable name |
| `manifest.csv` | What each exhibit is, how it was collected (read by Hunt, captured in the Hunt Browser, or added by you), where it came from, when it was posted and saved, its original name, its **SHA-256 fingerprint**, and whether it's evidence or a **lead** (a frame Hunt's scan picked out of a video: the video is the evidence) |
| `SHA256SUMS` | The same fingerprints, in a standard format |
| `audit-log.csv` | The case's log: every search, decision, import and export, with times |
| `notes.csv` | Your notes, corrections included |
| `README.txt` | The case, its purpose, how to check the bundle, and how the evidence was collected, written so a qualified person can certify it (FRE 902(13) and (14)) |

**How the recipient checks it,** on any computer, in the unzipped folder:

| Computer | Command |
|---|---|
| Mac | `shasum -a 256 -c SHA256SUMS` |
| Linux | `sha256sum -c SHA256SUMS` |
| Windows (PowerShell) | `Get-FileHash -Algorithm SHA256 exhibits\<file>`, then compare it with `manifest.csv` |

Every line should say **OK**. A file changed after it was saved fails the check, and the bundle's own README flags it.

**The bundle's own fingerprint** is shown when you make it and recorded in the case's log. Quote it in your chain-of-custody record.

## 8. What Hunt won't do, and why

Hunt is built for lawful, purpose-bound investigations:
- **Its own collection is passive and logged out.** It never logs in anywhere by itself.
- **It never uses fake accounts,** and never automates a logged-in session.
- **It never contacts or notifies the person:** no follows, messages or email checks that could alert them.
- **It never downloads videos from Instagram, TikTok or Facebook for you.**
- **It never sends your cases anywhere.**

Logged-in viewing is something **you** do, as yourself, in the Hunt Browser. Scraping with sock-puppet accounts is the pattern that has lost in court, and employment and insurance reports carry FCRA and state-law duties that Hunt helps you meet but can't lift.

The reasoning, with sources, is in [legal.md](research/legal.md). It's engineering research, not legal advice.

## 9. Your data

- **Where everything lives:** your Mac, in `~/Hunt`:
  - each case in its own folder, with its log and its evidence named by fingerprint
  - the Hunt Browser's profile, holding your logins
- **What leaves your Mac:**
  - the requests to the sites being checked (through your proxy, if you set one)
  - place names, never people's names, sent to OpenStreetMap to compare locations
  - the downloads you approve in setup
- **Retention:** cases are due for deletion **90 days** after you open them, unless you put them on **legal hold**. Hunt reminds you, and offers three choices:
  - **Delete the case:** it goes to the Trash.
  - **Put it on legal hold:** nothing is removed.
  - **Remove unused media and keep the case:** the photos and videos nobody kept, reported or noted go to the Trash. Empty the Trash to finish removing them.

## 10. Updating, checking and removing Hunt

| To | In Terminal | Or |
|---|---|---|
| Check everything Hunt needs | `hunt doctor` | Hunt's start screen |
| Update Hunt | `hunt update` (asks first) | Hunt's start screen shows the version you have |
| Download what's missing | `hunt setup` (shows sizes, asks first) | Hunt's setup screen |
| Remove Hunt | `hunt uninstall` | |

`hunt uninstall`:
- stops background watching
- moves Hunt.app to the Trash
- removes Hunt itself
- **asks separately** before moving `~/Hunt`, with your cases, to the Trash. Say no to keep them.

It leaves the vision model and the browser in place, since other apps may share them, and tells you how to remove them.

If you use a **proxy**, after setting or changing it run `hunt setup --launcher` and turn background watching off and on again. Both remember the proxy as it was when they were made.
