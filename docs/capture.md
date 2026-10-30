# Hunt Capture

Hunt reads logged-out pages only, and Facebook, Instagram, TikTok, X and LinkedIn show logged-out
visitors almost nothing. Hunt Capture closes that gap the way Hunchly does:
- **The investigator browses the platforms herself, logged in as herself**, under her own lawful access.
  She does it inside the **Hunt Browser**, a browser window Hunt opens, where she signs in once during
  onboarding.
- **A browser extension, preloaded there, records what she views** into the open case.
- **Hunt does everything else:** evidence hashing, post extraction, the media scan, the checklist and
  the report.

Why this is lawful, and what risk remains, is in [legal.md](research/legal.md#human-driven-capture-hunt-capture-browser-extension).

**Code:**
- `extension/`: Chrome Manifest V3. It runs preloaded in the Hunt Browser, or loaded by hand into any
  Chromium browser.
- `hunt/browser.py`: the Hunt Browser.
- `scripts/browser_e2e.py`: checks it end to end on this machine.
- `hunt/extension.py`: the server half. `hunt/capture.py` was already taken by the headless evidence
  screenshots that search uses.
- The `/api/capture/*`, `/api/pairing` and `/api/browser/*` routes in `hunt/app.py`.
- `test_capture.py`, with fictional fixtures in `fixtures/capture/`.

## Status (2026-10-30)

**Works, verified live on this Mac** (signed out, public organisation pages; see "Live QA"):
- **The Hunt Browser starts as a plain process,** with no debugging port and the requested window
  size.
- **The extension pairs itself,** and new extension code reaches an existing profile.
- **Sign-in states are reported,** and so is whether the extension is pinned.
- **Hunt's capture switch works:** archives on each new page, a retry for apps that draw late, hashed
  evidence, and the capture record (`viewed_as`, `capture_version`, `hunt_version`).
- **Grid-first capture:**
  - Instagram: 12 grid posts
  - TikTok: 16 posts in the first screen; 31 once loaded
  - X timeline: 5 full posts

  With coverage `progress` and `todo`, and X's profile post count.
- **The revocation watcher:**
  - a challenge address hard-stops the platform
  - nothing is recorded while it's stopped
  - resume from Hunt works, and both are audited
- **The per-site switch.** LinkedIn is never captured; Reddit pages are archived (no Reddit parser
  yet).
- **Evidence integrity:** every file re-hashes to its name.

**Built, checked by tests only** (each needs a person's input, which QA couldn't give):
- guided mode (Alt+Shift+N, or the popup's Next)
- the popup's controls (case picker, on/off, mode, per-tab pause)
- screenshots (after her click, or the "every view" opt-in), and video frames
- Record video
- the Story warning, and captures made signed in ("logged in as {handle}")
- X's media-tab grid

**Coming (not built):**
- a Reddit post parser, and a Facebook photos-tab grid
- saving videos from the segments the player fetched
- a "Save this video" button
- guided mode's optional blur/overlay
- the Safari port
- a branded-Chrome mode (a decision for Aaron; see below)
- `serve()` remembering its port, so a hand-loaded extension doesn't need re-pairing

## The Hunt Browser

**What it is.** `POST /api/browser/open {url}` starts Playwright's browser as a plain process. That's
the Chrome for Testing build Hunt already installs for its evidence screenshots. It runs:

```
<Chrome for Testing> --user-data-dir=HUNT_HOME/browser/profile --load-extension=HUNT_HOME/browser/extension
                     --no-first-run --no-default-browser-check <url>
```

- **A profile of its own**, so her logins persist across launches and never mix with her everyday
  browser.
- **Hunt Capture preloaded and already paired.** Hunt copies `extension/` beside the profile and
  writes `pairing.json` (this Hunt's port and a capture key, mode 0600). The extension reads it on
  start-up, so there's no code to type.
- **A fixed extension id.** The manifest's public `key` fixes the id at
  `ohkkgdkpojhdjabmfgbkjffmaaacpogh`, so Hunt knows which origin to trust before the browser ever
  runs. Only the public key is in the repo.
- **A second open while it's running hands the page to the open window,** as Chrome does.
- **It follows Hunt.** Hunt binds a new port each start, so `GET /api/browser/status` (the startup
  check) re-points `pairing.json`. If Hunt issues a new key, the extension re-reads the file on its
  next 403.
- **New code reaches the browser.** For an extension loaded with `--load-extension`, Chrome keeps
  running the service worker it cached on the profile. A version bump doesn't change that, so an
  updated Hunt Capture would have kept running old code (found in live QA).
  - Tested on Chrome for Testing 156, a variant per launch:

    | Change | Worker that runs |
    |---|---|
    | Same version | old |
    | Version bumped | old |
    | New worker script name | new |
    | Worker registrations cleared | new |

  - So Hunt names the copy's worker after its code (`background-<sha256[:12]>.js`) and stamps the
    version to match.
  - The worker also pairs and reports when it simply starts, because after a rename neither
    `onInstalled` nor `onStartup` fires.

**Observe-only.** It is a normal browser she drives:
- No Playwright driver.
- No remote-debugging port: a local port would let any process on the machine take over her sessions.
- No `--enable-automation` or other automation flags, so `navigator.webdriver` is false, as in any
  browser.
- No stealth, user-agent or fingerprint tricks.

`test_capture.py` fails if the launch arguments ever gain a debugging, automation, headless or
user-agent flag.

**Why Chrome for Testing, not her Chrome.**
- Branded Chrome 137+ ignores `--load-extension`. This was confirmed on this Mac's Google Chrome
  154.0.8037.98: `scripts/browser_e2e.py "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"`
  fails, because the extension never loads. Chrome for Testing 156.0.8078.4 loads it, and the script
  passes.
- It plays the platforms' video: H.264, AAC, VP9 and AV1 are supported, but not HEVC. TikTok falls
  back to H.264.
- It's already installed (`uv run playwright install chromium`), and it's free.
- The alternatives are worse. A Chromium build would lack H.264, so X and many Instagram and TikTok
  videos wouldn't play. Forcing an extension into branded Chrome needs enterprise policy and a
  packaged, hosted extension.

**What it costs, and macOS updates:**
- **No auto-update.** Chrome for Testing gets security fixes only when Hunt's Playwright is upgraded
  and `uv run playwright install chromium` is run again. A browser that's logged in to social media
  should not fall behind: upgrade Playwright with each Hunt release. `GET /api/browser/status`
  reports `browser.version` so the startup check can show it. After an upgrade, run
  `scripts/browser_e2e.py`.
- **macOS updates don't touch it.** It isn't an App Store or Keystone app. Its signature is ad hoc.
  Playwright downloads it without the quarantine flag, so Gatekeeper doesn't block it. If a future
  macOS tightened that, the status would show the browser failing to start; nothing would be lost.
- **The Keychain.** On first launch macOS asks to let "Google Chrome for Testing Safe Storage" use
  the Keychain; that key encrypts her cookies. Each new Chrome for Testing build has a new signature,
  so macOS may ask again after a Playwright upgrade.
  - Answer **Always Allow**.
  - Denying it leaves the cookies unreadable, and the browser signs her out of everything.
- **It looks like "Google Chrome for Testing"** in the Dock and the window title, not "Hunt".
  Branding it would mean shipping our own build.
- **It carries Google's own warning.** The build contains this notice: "Chrome for Testing v$1 is
  only for automated testing. For regular browsing, use a standard version of Chrome that updates
  automatically." That's Google advising against this use, for the update reason above.

**The alternative to decide on: branded Chrome, same dedicated profile.**
- Hunt would start her installed Google Chrome with `--user-data-dir=HUNT_HOME/browser/profile`.
- Branded Chrome ignores `--load-extension`, so onboarding adds one manual step, once: Developer
  mode → Load unpacked → `HUNT_HOME/browser/extension`.
- Chrome keeps an unpacked extension in that profile across launches. The manifest key keeps the
  same id, and `pairing.json` still pairs it with no code.
- **Gains:** automatic security updates, no testing notice, and Chrome's own branding and codecs.
- **Costs:** the one manual step, and a "developer mode" extension.
- `browser.py` would need only a different executable and that onboarding step. It isn't built: it
  needs Aaron's call, and a live check with a visible window.
- **My recommendation:** branded Chrome where it's installed, and Chrome for Testing only as the
  fallback, because a browser signed in to social media should patch itself.
- **Packaging.** `extension/` sits beside the `hunt` package. Hunt runs from its checkout
  (`uv run hunt app`). A wheel would need `extension/` added to the hatch build.

### Sign-in status

The extension reports, per platform, whether she's signed in. It checks only whether the platform's
sign-in cookie exists, with `chrome.cookies.get`:

| Platform | Cookie |
|---|---|
| Facebook | `c_user` |
| Instagram | `sessionid` |
| TikTok | `sessionid` |
| LinkedIn | `li_at` |
| X | `auth_token` |

- **No value is ever read out, kept or sent.** Only `signed_in` / `signed_out` travels, through
  `POST /api/capture/signins` under the key Guard.
- **When it reports:** at browser start, whenever one of those cookies changes (sign-in, sign-out,
  expiry), and when the popup opens.
- **Where it's kept:** `HUNT_HOME/browser/signins.json`, with `checked_at`. Anything that isn't a
  state is refused, a cookie value included.
- **Never checked: unknown.** A platform the extension hasn't checked (no browser yet, a fresh
  profile) is `unknown`.

### Onboarding and the startup check (for the main session to build)

**"Connect your accounts"** (first boot, each platform skippable):
- **Read** `GET /api/browser/status`. One row per entry in `logins` (Facebook, Instagram, TikTok,
  LinkedIn, X), with its state.
- **Sign in** calls `POST /api/browser/open {url: login.url}`.
  - The Hunt Browser opens (starting if needed), and she signs in there herself.
  - Hunt never sees the password.
  - Capture stays off, so signing in is never recorded.
- **Poll** the status every 3 s while the screen is open. A row turns to "Signed in" when the
  extension reports.
- **Skip** marks the platform skipped. That's the screen's own state; Hunt has nothing to store.
- **No browser** (`browser.available` false): show "Install the Hunt Browser:
  `uv run playwright install chromium`".
- **`503` from `/open`:** the same message.

**Startup check row** per platform:
- "Facebook: signed in" when `signed_in`.
- "Facebook: sign in again" with a **Sign in** button when `signed_out`.
- "Facebook: not checked yet" when `unknown`.
- Show `checked_at` as "checked 2 h ago".
- Add one row for the browser itself: "Hunt Browser {version}". When it's old, add: "Update with
  `uv run playwright install chromium` after upgrading Hunt."

**Open a case's account** (person view, checklist): `POST /api/browser/open {url, case: slug}`.
- `case` makes the extension preselect that case the next time she opens its popup.
- Capture still waits for her to turn it on.

**Sign out of everything:** `POST /api/browser/sign-out`.
- The profile goes to the Trash, never deleted; Put Back restores it.
- The extension copy is rebuilt and re-paired on the next open.
- Returns 409 while the Hunt Browser is open: ask her to quit it first.
- Confirm first: "This signs you out of every platform in the Hunt Browser."

## Hard lines

**Every request a platform receives is caused by one deliberate input of hers.** Everything after the
bytes arrive is automatic.

The extension never:
- opens tabs, clicks, types or searches
- likes, follows, friends or messages anyone
- expands "See more", advances post modals or Stories, or synthesises input

It never scrolls or navigates on its own. The single exception is guided mode, where one press of
Next makes exactly one scroll or one navigation (below).

It records only pages she opens, while capture is on, and never LinkedIn, Strava or Snapchat. It sends nothing anywhere
except Hunt on 127.0.0.1: its Content-Security-Policy is `connect-src 'self' http://127.0.0.1:*`
(`'self'` is its own `pairing.json`). It makes no request to any platform. There are no sock
puppets: it works in her own logged-in browser.

`test_capture.py` reads the extension's code and fails on any of these:
- a `click()`, a scroll call, tab navigation, `location =`, a form submit, a synthetic or constructed
  input event, script injection, or an element added to the page
- the exceptions are guided mode's `guidedScroll` and `guidedOpen`: one call each, no loop, no timer
- a `fetch` to anything but `http://127.0.0.1:` or its own `pairing.json`
- reading a cookie's value (only `chrome.cookies.get` for presence)
- LinkedIn, Strava or Snapchat in its capture sites
- the permissions history, webRequest, debugger, scripting, downloads or management
- `<all_urls>` anywhere but `optional_host_permissions`, which Chrome grants only through its own
  prompt, on her click

## What it records

Capture is **off by default, whenever the browser starts, and whenever Hunt starts**. It's turned on
for one case, either from Hunt's own screens (`POST /api/browser/capture`) or from the extension's
popup; each side follows the other.
- **The badge.** While capture is on, the toolbar shows a red **REC** badge, and **●** while a video
  is being recorded.
- **Pinning.** Chrome shows an extension's badge only when it's pinned to the toolbar, and gives
  extensions no way to pin themselves. The extension reports whether it is (`browser.pinned` in
  `GET /api/browser/status`). When it's `false`, Hunt should say: "Pin Hunt Capture (the puzzle
  icon, then the pin) so you can see when it's recording."

| When | What | Throttle |
|---|---|---|
| A supported page finishes loading, its address changes, you switch to its tab, or you stop scrolling for 1.2 s | A viewport screenshot (`chrome.tabs.captureVisibleTab`, JPEG), **once Chrome allows it** (below) | at most one per 2.5 s per tab |
| Same, for a page new to this tab, or the same page after you've scrolled and 20 s have passed | The page archive (`chrome.pageCapture.saveAsMHTML`): the page plus the pictures her browser already loaded | one at a time per tab |
| An archive that gave no posts (an app still drawing them) | The same page archived once more, 6 s later | once per page |
| A video is playing on screen | A screenshot every 2 s (the frames she watched), once screenshots are allowed | at most 90 per page |
| **Capture this** (popup or Alt+Shift+H) | Screenshot and archive, right away | none |
| **Record video** / **Stop recording** (popup) | A recording of the tab (`chrome.tabCapture` → WebM), with its sound still playing for her | stops itself at 10 min |

**Screenshots need Chrome's permission; archives don't** (found in live QA). `captureVisibleTab`
accepts only `activeTab` or `<all_urls>`; host permissions aren't enough.
- **By default (least privilege):** screenshots start in a tab once she invokes Hunt Capture there,
  by clicking its icon or pressing Alt+Shift+H. That's Chrome's `activeTab` grant, which lasts while
  she stays on that site.
- **"Screenshots on every view" (popup checkbox):** asks Chrome for `<all_urls>` through its own
  prompt, on her click. It still records only the sites below and sends only to Hunt.
- **Archives are saved either way.** They hold the pictures the scan reads. A view with no screenshot
  permission reports once per tab: "No screenshot: click Hunt Capture once in this tab… The page
  archive is still saved."

**The per-site switch** (`docs/research/automation-legal.md` §4):
- **Recorded:** facebook.com, instagram.com, tiktok.com, x.com, twitter.com, youtube.com and
  reddit.com, and their subdomains.
- **Never recorded:** LinkedIn, Strava and Snapchat. Their terms name extensions or "semi-automated"
  tools, and LinkedIn also scans for extension ids.
  - The extension doesn't run there, and Hunt refuses their uploads with 403.
  - On LinkedIn the popup shows a banner: save pages with Save Page As and import them; browse logged
    out, or set LinkedIn's profile viewing to private first.
- LinkedIn sections stay on the checklist as links. She saves those pages by hand; the LinkedIn parser
  is ready for that.
- The extension still checks LinkedIn's sign-in cookie, for the status screen. That touches nothing
  on LinkedIn.

**Two modes**, chosen in the popup:
- **Every page view I settle on** (the default).
- **Only when I press Capture this.** This is the same act as a screenshot or Save Page As; see
  legal.md.

**Where it all lands.** Each capture is hashed into the case's evidence (`evidence/<sha256>.<ext>`;
MHTML is served as `text/plain` with `CSP: sandbox`) and becomes `posts.add_posts(...,
origin="captured")`:
- **A screenshot** is one captured post holding it (`kind: screenshot`), tied to the page and its
  profile: `account_url`, plus `extra.viewed_url`, `viewed_at` and `title`. The same picture again
  adds nothing.
- **A page archive** is kept whole. Its posts are read out by the platform's parser (below), with
  their pictures taken from the archive itself. Posts already in the case are skipped.
- **A recording** is one captured post with the video.

The media scan runs on captured posts like any other: the next scan picks up their new media
automatically, with no extra step. `GET /api/cases/{slug}/posts` counts them as `counts.captured`.

**When something fails, Hunt hears about it.** The extension sends each error to
`POST /api/capture/problem`, and `GET /api/browser/status` lists the latest 20 as
`problems: [{ts, message}]`. That covers a refused screenshot, Hunt unreachable, or an upload that
failed. The capture screen should show the newest one, so a silent failure never passes for "nothing
to capture".

## Grid-first capture

The big platforms need almost no clicking. **Scrolling a profile's grid captures every post in it.**
Each grid image the page loads (Instagram's ~640 px thumbnails and Reels tiles, TikTok's covers, X's
media tab) comes out of the page archive as a captured post, from bytes the page already fetched:
- **Media kind `grid`.** `scan.run` scans it like any photo. The scan's hits on it show "from a grid
  thumbnail; open the post to confirm" until the full post is captured.
- **The post's `extra`** gets:

  | Field | Meaning |
  |---|---|
  | `from` | `"grid"` |
  | `position` | its place in the grid, from 0 |
  | `video` | whether it's a video or reel |
  | `alt` | Instagram's own description, if any |

  It also gets the post URL, the date the grid shows (Instagram's alt text, TikTok's id), and the
  capture record below.

**Opening a post upgrades it in place.** When she opens one, its own page (or a feed item) is captured
"full". `posts.add_posts` then:
- adds the words, the date and the full-size media to the same post
- sets `extra.from` to `"full"`, keeping the grid archive as `extra.grid_evidence`
- audits `post upgraded`

Timeline items (X's posts tab, Facebook's feed) are "full" from the start.

**Coverage, which loads nothing.** Each account in `GET /api/cases/{slug}/checklist` carries:

| Field | Meaning |
|---|---|
| `progress.grid_seen` | posts of this account captured, grid or full |
| `progress.grid_total` | the post count the profile header showed (Instagram, X), else null |
| `progress.flagged` | posts the scan flagged |
| `progress.opened` | flagged posts captured in full |
| `progress.videos` | posts that are videos |
| `progress.played` | videos with a recording, frames, or a full capture |

Shown as: "grid 212/212 · flagged 9 · opened 6 of 9 · videos 14, played 6". The popup shows it for the
account in the current tab.

**"Open these"**: `todo: [{url, kind: "post"|"video", file, why}]` on the same account.
- First, flagged posts seen only as grid thumbnails (`why` is the hit: "walks: a person hiking with a
  pack").
- Then every video not yet played (`why`: "a video: play it to capture its frames"). The player must
  fetch a video's segments before anything can be captured.
- `file` is the thumbnail's evidence path; `url` opens in the Hunt Browser.

**Coming:** a grid parser for Facebook's photos tab. Its posts come through as full items from the
timeline for now.

## Capture record

Every capture, and every captured post, carries these fields. They're in the audit detail of
`capture view|page|recording`, and in each post's `extra` (so in `list_posts`). The names match what
`bundle.py` reads.

| Field | What |
|---|---|
| `url` | the page's address (`viewed_url` on screenshot and recording posts; the post's own `url` otherwise) |
| `post_id`, and `user_id` / `fb_id` | the platform's post id and account id, when the page shows them |
| `viewed_as` | "logged in as {handle}" (the handle she gave Hunt, `POST /api/browser/accounts`), "logged in (account not named in Hunt)", "logged out", or "not known". From the presence of the platform's sign-in cookie at capture time, never its value |
| `audience` | what the platform showed: "Public", "Friends", "Friends of friends", "Custom", "Only me", "Group: {name}" (Facebook); "Followers" for a private or protected account (Instagram, TikTok, X); "Connections" (LinkedIn, hand-saved) |
| `audience_flag` | `true` when the audience isn't shown as Public, unknown included. Such items stay out of the report unless counsel approves |
| `captured_at`, `time_source` | UTC capture time, from "the browser's clock" |
| `received_at` | Hunt's own clock, on arrival |
| `capture_version` | the extension's version (stamped per build) |
| `hunt_version` | Hunt's version |
| `capture_sha256` | SHA-256 of the archive as received, before anything is parsed or transcoded. The archive is stored under that hash (`evidence`), and each picture under its own |
| `posted_at`, `posted_at_precision`, `posted_at_text` | the post's own time, and how it was known |

## Guided mode

One press of **Next** does one step. Next is Alt+Shift+N, or the popup's button; it's never on the
page.

**On the subject's profile, with grid below the screen:** one scroll by about a screen
(`guidedScroll` in `content.js`).
- The scroll loads the next rows, as her own scroll would.
- The step's archive is taken once the view settles.

**Once the grid is all seen, or on a post page:** one navigation to the next item on the account's
"open these" list (`guidedOpen` in `background.js`). Items already opened this session are skipped.

**One press, one step:**
- The next press is locked until this step's capture is recorded (the archive's upload answered), or
  for at most 20 s.
- No auto-repeat, no hold-to-scroll, and no timer that acts on the page. The 20 s timer only releases
  the lock.
- `test_capture.py` fails if either function gains a loop or a timer, or a second scroll or
  navigation, or if any scroll or navigation appears outside those two functions.

**It refuses when:**
- capture is off
- the tab isn't a confirmed account (or an item on its list)
- the page is still loading
- the tab is paused
- the platform is off (LinkedIn, Strava, Snapchat) or stopped

**Nothing on the page.** Guided mode adds no overlay, blur or element. The popup shows the counter,
and Hunt's worklist shows it live (`GET /api/cases/{slug}/checklist`).

**Audit.** Each press is audited as `guided step` `{action: "scroll"|"open", url, to, extension}`,
through `POST /api/capture/guided`.

**Window size.** `/api/browser/open` takes `window: {width, height}` (300–5000 px), applied when the
browser starts, to sit beside Hunt's window. A smaller window means more presses.

**Coming:** the optional blur/overlay toggle (default off in the brief). It would add to the page,
and the refined brief prefers nothing there.

## Hard stops: the revocation watcher

**Passive.** It reads only what she has already loaded.
- **The extension** checks each address she's sent to for checkpoint, challenge or suspension paths
  (Facebook `/checkpoint`, Instagram `/challenge` and `/accounts/suspended|disabled`, X
  `/account/access|suspended|locked`, TikTok `/captcha`, Reddit `/account-suspended`). It reports a
  match with `POST /api/capture/revoked`.
- **Hunt** checks every archive's text (English, Spanish, French): "we suspect automated behavior",
  "your account has been disabled/suspended/locked", "we limit how often you can", "confirm you're
  human", the slider puzzle.

**On a match, that platform stops:**
- Hunt refuses its uploads (403), and the extension stops recording and guiding there (badge
  **STOP**).
- The case is audited `capture hard stop`.
- The message: "{Platform} showed {reason}. Hunt Capture has stopped recording {Platform}. Don't use
  this account for casework, and tell Ethos. Don't switch to another account, browser profile or
  proxy."
- Stops are kept in `HUNT_HOME/browser/stops.json`, so they survive restarts. They're listed as
  `stopped` in `GET /api/browser/status` and in `hello`.
- Only `POST /api/browser/resume {platform}` lifts one, deliberately, from Hunt. It's audited
  `capture resumed`.

**Never a fallback.** Hunt never tries another account, profile or proxy.

## The Story warning, and the per-tab pause

**The Story warning.** When she's signed in to Instagram or Facebook and clicks a Story (a link to
`/stories/`, or a control labelled "story"), the page asks first: "Story viewers can see your account.
Open this Story anyway?"
- Cancel stops that click. OK lets the same click go through; nothing is re-sent.
- Story rings drawn without a link or label may slip past. The warning is a guard, not a guarantee.

**The per-tab pause.** "Pause this tab" in the popup stops recording (and guiding) in that tab only.
Its badge shows **II**.

## Videos: what can and can't be saved

Facebook, Instagram, X and most TikTok players stream video through `blob:` URLs fed by Media Source
Extensions: the page's own code fetches segments and appends them to the player.

**What the extension can't save:**
- **The video file itself.** A page archive never contains it (`pageCapture` saves the document and
  its cached images, not media streams).
- **The segments.** Chrome gives extensions no way to read response bodies except `chrome.debugger`.
- **Anything it would have to fetch.** It may not fetch from the platforms at all.

**What works:**
1. **Frames as she watches.** A screenshot every 2 s while a video plays on screen, once screenshots
   are allowed (above). The media scan (CLIP, then the vision model) works on frames, so "lifting at
   0:16" is found the same way. Frames are what she saw, at her pace; skipped parts are missing.
2. **Record video (on demand, the faithful copy).** `chrome.tabCapture` records the tab exactly as
   she sees and hears it, from her click to her stop (or 10 minutes). It needs her click each time
   (Chrome's rule), and the tab must stay in front.
3. **"Capture this" on a paused frame** gives one screenshot plus the archive, with the poster image.
4. **Posters.** The still shown before playing comes through in the archive, and becomes the post's
   picture.

**Coming, if approved: copying the segments the player appends.** A main-world content script could
wrap `SourceBuffer.appendBuffer` to keep a copy of each segment as the player feeds it. That sends no
request, and Hunt could join the video and audio tracks with ffmpeg. But it changes the page's own
JavaScript, which the platform can detect. It also breaks on quality switches and encrypted
streams. Decide it with the research's "never initiates a request" test in mind before building.

**Rejected:**
- **`chrome.debugger`** (pull the segments from the network log): a "being debugged" banner, every
  request readable, and a far broader permission.
- **Re-downloading the video URL:** it would make the extension talk to the platform, and the signed
  CDN links are tied to her session.

**Not verified live.** Frames and recording need her clicks (screenshot permission, Record), which
QA couldn't give. The code paths are covered by `test_capture.py` and the manual test plan.

## Pairing and the security model

In the Hunt Browser, Hunt pairs the extension itself (above). The code below is for her everyday
Chromium browser, if she loads the extension there by hand. One pairing exists at a time, so opening
the Hunt Browser takes it over.

1. **In Hunt**, *Browser capture* shows a pairing code: `POST /api/pairing` returns
   `{code: "<port>-<8 digits>", expires_in: 300}`.
   - The code is used once, open 5 minutes.
   - Five wrong tries close it.
   - It lives in memory, so restarting Hunt closes it.
2. **In the extension popup**, she pastes it. The extension calls `POST /api/capture/pair {code}` and
   receives a capture key.
   - Hunt keeps only the key's SHA-256, bound to that extension's origin, in
     `~/Hunt/capture-key.json` (mode 0600). One paired extension at a time; pairing again replaces it.
   - The extension keeps the key in `chrome.storage.local`, restricted to its own pages and service
     worker. The content script can't read it.
3. **Every `/api/capture/*` request** passes `extension.problem()` in Guard, before the web app's
   cookie and fetch-metadata rules:
   - exact Host
   - POST only
   - `Origin: chrome-extension://<the paired id>`
   - JSON or multipart
   - `x-hunt-key` matching the stored hash

   `/api/capture/pair` alone has no key: the one-time code is its secret.
4. **The two halves are separate.** The web app's cookie never opens a capture route, and the key
   opens nothing else. The web UI's Guard is unchanged.
5. **No CORS headers.** Extensions with host permission for `http://127.0.0.1/*` don't need them.

**For the main session.** `hunt app` binds a random port. The Hunt Browser follows it (see above),
but an extension paired by hand must be paired again after Hunt restarts; its popup says so. Having
`serve()` try the last port first (remember it in `~/Hunt`) would let a manual pairing last too.
That's a one-line change I didn't make, because `serve()` isn't mine.

## Reading posts from captured pages

The parsers are server-side (`hunt/extension.py`, and `hunt.facebook` for Facebook). They read the
archive the extension sends, not the live DOM. Each turns a viewed post into
`{url, posted_at, text, media: [local files], …}` for `posts.add_posts(..., origin="captured")`, so
captured posts are scanned like fetched ones.

**Chrome's page archives contain no `<script>` contents** (checked live). So the embedded JSON paths
below never fire on Hunt Capture archives. They do fire on pages saved with Save Page As, which keeps
scripts. On captures, times come from what the page shows, `<time>`, or a post id.

| Platform | Anchors (no class names) | Gets |
|---|---|---|
| Facebook | `hunt.facebook.parse_saved` ([facebook.md](facebook.md)) | everything listed there; on captures, times as displayed ("1h" → hour precision) |
| Instagram | `<article>` with `<time datetime>`, `/explore/locations/` links, `h1` or the longest `dir=auto` caption; profile grid links to `/p/` and `/reel/`, whose alt text carries "Photo by X on October 25, 2026"; embedded API JSON on saved pages | URL, exact or day time, caption, author, account, user id, place, likes, comments, pictures, `alt` (Instagram's own image description, which `facebook.categories` maps to scan categories) |
| TikTok | profile tiles linking `/@user/video/<id>` (the id's high 32 bits are its posting time); covers from `<picture><source srcset>` (what the browser actually loads), else `<img src>`; video pages' `data-e2e` description and counts; `__UNIVERSAL_DATA_FOR_REHYDRATION__` JSON on saved pages | URL, exact time, description, author, place, likes, comments, shares, cover |
| X | **Signed in:** `article[data-testid=tweet]`, with `User-Name`, `<time datetime>` on the `/status/` link, `tweetText`, `tweetPhoto`, video posters, `reply`/`retweet`/`like` aria-labels, and `socialContext` ("reposted"). **Signed out**, a different markup: plain `<article>`, the text in `dir=auto`, counts in one `role=group` aria-label ("98 replies, 269 reposts, 1042 likes…"), pictures from `pbs.twimg.com/media/`. Either way the status id is a snowflake, so the time is exact without `<time>` | URL, exact time, text, author, pictures, counts, `reposted_by` |
| LinkedIn | `data-urn="urn:li:activity:<id>"` (the id's top 41 bits are the posting time in ms), the actor's `/in/` link, the longest `dir=ltr` text, `aria-label` counts. For pages she saves by hand; Hunt Capture never records LinkedIn | URL, exact time, text, author, pictures, reactions, comments, reposts; "starting a new position…" as `life_event` (→ `other_job`) |
| YouTube | none: uploads come from its RSS (`posts.collect`) | the archive is still evidence |

**Tested on** `fixtures/capture/`:
- **Fictional pages** (`instagram_*`, `tiktok_*`, `x_profile`, `linkedin_activity`) in the format
  `chrome.pageCapture` writes. They include posts known only from JSON, only from DOM, or only from
  an id.
- **Real markup** (`nasa_instagram`, `nasa_tiktok`, `nasa_x`, `nasa_facebook`). These are NASA's
  public accounts as the Hunt Browser captured them signed out on 2026-10-29, trimmed to the post
  elements the parsers read:
  - sidebars and suggested accounts dropped
  - Facebook's comment, which carried a private person's name, removed
  - pictures re-encoded as 64 px thumbnails

  They caught TikTok's `<picture>` covers and signed-out X's markup.
- Facebook's fictional pages are in `fixtures/facebook/`.

## The guided checklist

For each account confirmed as the subject's, the checklist lists the sections to open, as links.
Confirmed means decided "him" in *Is it him?*, or every account in the person when the whole person
was.

| Platform | Sections |
|---|---|
| Facebook | Posts, Photos (`/photos`), Tagged photos (`/photos_of`), Videos, Reels, Check-ins (`/map`), About, Public friends (`profile.php?id=` profiles use `&sk=`) |
| Instagram | Posts, Reels, Tagged, Followers, Following |
| TikTok | Videos |
| X | Posts, Replies, Media, Followers, Following |
| LinkedIn | Profile, Activity, Images, Videos, Experience |
| YouTube | Videos, Shorts, Posts |

**How sections are ticked.** A section is ticked when a screenshot or archive of it was captured.
The match is on the address, host without `www.`/`m.` and lower-case path (`extension.where`), so
`m.facebook.com/dorian.vell/photos` ticks Facebook › Photos. Ticks come from the audit log, so
deciding an account after browsing it still counts.

Sections with no address of their own aren't listed: Instagram's "About this account", TikTok's
reposts and likes.

**"What we couldn't see"** (for the report session): `extension.couldnt_see(case)` returns
sentences like:

> Facebook dorian.vell: tagged photos, videos, reels, check-ins, about and public friends were not
> opened while Hunt Capture was recording.

An account never browsed at all gets "not opened while Hunt Capture was recording".

**Audit actions**, each with detail JSON:

| Action | Detail |
|---|---|
| `capture view` | `{url, where, platform, kind: view\|frame\|manual, file, sha256, viewed_at, post, extension}` |
| `capture page` | `{url, where, platform, file, sha256, viewed_at, posts, added, extension}` |
| `capture recording` | `{url, where, platform, file, sha256, viewed_at, post, extension}` |
| `post imported` / `post already added` | from `posts.add_posts`, with `origin: "captured"` |

Pairing and unpairing are printed to the `hunt app` terminal. They aren't case events; each
capture's audit row names the extension.

## API

Full shapes are in [api.md](api.md#hunt-capture).

**For the web app (cookie Guard):**
- `GET /api/browser/status`
- `POST /api/browser/open`
- `POST /api/browser/capture` (on or off, for a case)
- `POST /api/browser/sign-out`
- `POST /api/browser/resume` (lift a hard stop)
- `GET`/`POST /api/browser/accounts` (the handles she signs in with, for `viewed_as`)
- `GET`/`POST /api/pairing`
- `POST /api/pairing/forget`
- `GET /api/cases/{slug}/checklist`
- `GET /api/cases/{slug}/captures`

**For the extension (key Guard):** POST
`/api/capture/pair | hello | checklist | view | page | recording | signins | state | problem | revoked | guided`.

## Hunt app screens (for the main session to build)

**Capture switch**, in the case header and beside the checklist: **Start capturing** /
**Stop capturing** → `POST /api/browser/capture {case, on}`.
- Show "Recording into {case}" with a red dot while `GET /api/browser/status`'s `capture.on` is true.
  The extension mirrors it on its next page load, and her popup toggles come back the same way.
- If `browser.pinned` is false, add "Pin Hunt Capture to see its REC badge in the browser (puzzle
  icon → pin)."
- Show the newest `problems` entry under the switch, for example "No screenshot: click Hunt Capture
  once in this tab…".
- **Open** links in the checklist call `POST /api/browser/open {url, case}`, so each opens in the
  Hunt Browser on her click.

**Worklist**: `#/case/<slug>/worklist`, already built on hunt-server, reads these fields.
- Each checklist account's `progress` gives "grid 212/212 · flagged 9 · opened 6 of 9 · videos 14,
  played 6".
- Its `todo` gives the "open these" thumbnails.
- Hits on grid thumbnails (`extra.from == "grid"`) read "from a grid thumbnail; open the post to
  confirm".
- Guided mode's Next lives in the extension; the worklist just shows progress live.

**Hard stops**: when `stopped` is non-empty in `GET /api/browser/status`:
- Show each stop's `message` prominently, with its time and address.
- Offer **Resume {platform}** → `POST /api/browser/resume`, behind a confirmation: "Only resume after
  you've spoken to Ethos, and never with another account."

**Your accounts** (onboarding): an optional handle per platform → `POST /api/browser/accounts`, so
captures read "logged in as {handle}".

**Browser capture** (only for an everyday browser; the Hunt Browser pairs itself), in settings:
- **Not paired:** "Hunt Capture records the pages you open on Facebook, Instagram, TikTok, X and
  YouTube into your case (never LinkedIn). Install it from the `extension` folder (chrome://extensions →
  Developer mode → Load unpacked)."
  - Button: **Pair a browser** → `POST /api/pairing`.
  - Show the code large, with a **Copy** button and a 5-minute countdown. On expiry: "That code
    expired; make a new one."
  - Poll `GET /api/pairing` every 2 s until `paired`.
- **Paired:** "Paired with Hunt Capture since {paired_at}."
  - Button: **Unpair** → `POST /api/pairing/forget`.
  - Note: "If Hunt restarts, pair again (it moves to a new port)."

**Checklist**, on the person view and the posts step: `GET /api/cases/{slug}/checklist`.
- One block per account: platform icon and handle.
- Each section is a row with a tick or an empty circle, its label, and "Open" (opens it in the Hunt
  Browser through `/api/browser/open`).
- For LinkedIn sections: "Save this page by hand; Hunt Capture doesn't record LinkedIn."
- Seen rows show `seen_at` and link their evidence.
- Unticked rows read as "not opened yet". The report's "What we couldn't see" shows the same.
- Empty state: "Confirm the subject's accounts in Is it him? to see what to open."

**Capture feed**: `GET /api/cases/{slug}/captures`, newest first, polled every 5 s while the screen
is open.
- Each row: time, platform, kind (screenshot, page, video frame, recording), the URL, and for pages
  "{posts} posts read, {added} new".
- Thumbnail or evidence link from `file` (`/evidence/{slug}/{basename}`).
- Empty state: "Nothing captured yet. Start capturing, then browse in the Hunt Browser."

## Safari

Safari Web Extensions take the same code: `xcrun safari-web-extension-converter extension/` makes an
Xcode project. But Safari has neither `chrome.pageCapture` (no MHTML) nor `chrome.tabCapture`. The
Safari port would:
- keep screenshots (`browser.tabs.captureVisibleTab` works), and with them frames
- send the page's DOM instead of an archive: `document.documentElement.outerHTML` from the content
  script, which the same parsers read, with pictures only as screenshots
- drop **Record video**, leaving frames only

Extension origins there are `safari-web-extension://<uuid>`, so `EXTENSION_ORIGIN` would need that
pattern too. Not built.

## Known gaps

- **The Hunt Browser doesn't update itself.** It follows Hunt's Playwright version; see above.
- **A hand-loaded extension** in an everyday browser must be paired again after every Hunt restart,
  until `serve()` remembers its port. The Hunt Browser doesn't have this problem.
- **Only what was on screen and loaded.** Scroll to load more; open "See more" and comments before
  capturing.
- **Screenshots need her click** in each tab (`activeTab`), unless she allowed "Screenshots on every
  view". Archives don't. And they're of the visible tab only: a background tab is skipped until she
  switches to it.
- **Pinning is hers.** Chrome lets no extension pin itself, so the REC badge shows only after she
  pins Hunt Capture. Hunt can see whether she has (`browser.pinned`).
- **Coming:** see the Status list at the top. Tab recording covers "Save this video" without any
  request.
- **`viewed_as` names her handle only if she gave it** to Hunt. Hunt never reads it from her cookies.
- **Archives hold what the page had loaded,** and no scripts. Lazy-loaded pictures below the fold
  aren't in them (17 of NASA's 31 TikTok covers were), and embedded JSON isn't either.
- **Recording needs her click each time** (Chrome's rule for tab capture). The tab must stay in
  front.
- **Parsers follow today's markup** and fail soft. When a platform changes, the archive and
  screenshot are still kept, even if fewer posts are read.

## Live QA (2026-10-29)

**Setup.**
- A Hunt server run with `HUNT_HOME` in scratch, never the real `~/Hunt`. A QA case with NASA's
  public accounts confirmed as "him", so the checklist had accounts.
- The Hunt Browser opened through `POST /api/browser/open`, on this Mac (macOS, Apple silicon).
- Signed out throughout; no account was ever signed in to.
- Capture turned on with `POST /api/browser/capture`, as Hunt's switch would, because the popup needs
  a person's click.
- QA could watch the window (read-only screen access) but not click or scroll it, as intended:
  nothing but a person drives the Hunt Browser.

**What was confirmed:**
- **The browser.** Chrome for Testing 156.0.8078.4 starts as a plain process with only the documented
  arguments. It has no listening TCP port (`lsof`), so no remote debugging.
- **The notice.** Google's "Chrome for Testing … is only for automated testing" bar shows under the
  address bar.
- **Branded Chrome.** This Mac's Google Chrome 154.0.8037.98 ignores `--load-extension`, tested
  headless with `scripts/browser_e2e.py`.
- **Pairing.** The extension loads under the expected id and pairs itself. Sign-in states arrive:
  every platform `signed_out`, correctly, since nobody signed in.
- **Pinning.** The extension isn't pinned by default (`pinned: false`), so the REC badge isn't visible
  until she pins it.
- **Archives.** Each one lands as hashed evidence with the page's `url` and `viewed_at`. All 23
  evidence files re-hash to their names (`Case.verify`).
- **Checklist.** Posts ticked for every visited profile. LinkedIn was reported as "not recorded".

**What a signed-out visitor's capture got:**

| Account | Archive | Posts read | Notes |
|---|---|---|---|
| Instagram @nasa | 3 MB | 12 | Grid tiles: URL, day-precision date from the alt text, picture. No captions (signed-out grids have none) |
| TikTok @nasa | yes | 31 | Exact times from the video ids, captions from the alt text; 17 covers, the rest never loaded |
| X @NASA | yes | 5 | After the 6 s retry. Exact times (snowflake ids), text, reply/repost/like counts, 2 pictures |
| Facebook NASA | yes | 1 | Behind the login modal: one post, with text, picture, reaction count and "1h" time |
| YouTube @NASA | yes | 0 | By design: no parser; uploads come from RSS |
| LinkedIn NASA | none | — | Correct: Hunt Capture never records LinkedIn |

**What broke, and was fixed:**
1. **Chrome kept running the old service worker** after the extension's code changed, even with a
   version bump. Hunt now names the copy's worker after its code (see the Hunt Browser section).
2. **Screenshots need `activeTab` or `<all_urls>`.** Host permissions aren't enough, and a refused
   screenshot also blocked the archive. Now the archive is always taken, screenshots follow her click
   or her opt-in, and the reason reaches Hunt.
3. **Errors were silent.** Now they reach Hunt (`problems` in the status).
4. **TikTok covers were missing:** the browser loads `<picture><source srcset>`, not the `<img>`.
5. **Signed-out X uses different markup,** and draws its timeline after the page's "complete"
   event. The parser now reads both markups, and an archive with no posts is retried once.
6. **Facebook was archived twice** for one visit. The same page is now archived again only after she
   scrolls.
7. **The REC badge was invisible unpinned.** Pinning is now reported, so Hunt can prompt.
8. **Category reasons said "Facebook"** for Instagram and LinkedIn tags. They now name the post's
   platform.

**Not verifiable by QA, by design** (each needs her click; see the manual test plan):
- the popup itself
- screenshots under `activeTab` or the opt-in
- frame screenshots while a video plays
- Record video
- signing in, and a real session's sign-in status

### Round two (2026-10-30, after grid-first capture, the capture record and guided mode)

- **Setup.** A fresh case with NASA's public Instagram, TikTok, X, Reddit and Facebook accounts
  confirmed. Capture was switched on from Hunt, and the browser opened at 1100×950.
- **Grid-first.**
  - Instagram: 12 grid posts (media kind `grid`), 3 of them videos, so 3 on "open these".
  - TikTok: 16 grid posts in the first screen, all videos.
  - X: 5 full posts, and `grid_total` 74,500 from the header's "74.5K posts".
- **The capture record.** Every capture carried `viewed_as: "logged out"` (Reddit: "not known", since
  there's no Reddit sign-in check) and the stamped `capture_version`.
- **Reddit.** It first sent the browser through its own JS anti-bot check (`?js_challenge=1`), which a
  normal browser solves by itself. The archive was kept, and the checklist ticked Overview. This isn't
  treated as a hard stop: it isn't about her account.
- **The revocation watcher.** Opening `instagram.com/challenge/` hard-stopped Instagram, with the full
  message and an audit row.
  - Reopening Instagram while stopped recorded nothing.
  - `POST /api/browser/resume` lifted it, also audited.
- **Found and fixed:** TikTok's page showed an unrelated "N posts", which had been read as a profile
  count. Counts now come only from Instagram and X headers.
- **Evidence.** All 19 files verify.
- **Guided mode** wasn't exercised: Alt+Shift+N and the popup need a person's key press or click.
  The rest of the browser was watched read-only.

## Manual test plan

Use test accounts you own, or public organisation pages, never a private person. Start with
`uv run python scripts/browser_e2e.py`, which should print `ok`.

1. **Start and look.** Start `uv run hunt app`. `GET /api/browser/status`, or the startup check
   screen, shows every platform `unknown` and the browser `available` with its version.
2. **Sign in.** `POST /api/browser/open {url: "https://www.facebook.com/login/"}`.
   - Google Chrome for Testing opens with Google's testing notice under the address bar.
   - The first time, macOS asks about "Google Chrome for Testing Safe Storage": choose Always Allow.
   - Sign in to a test account. Within a few seconds the status shows `facebook: signed_in`.
3. **Pin.** Click the puzzle icon, then pin Hunt Capture. The status shows `browser.pinned: true` at
   the next report (open the popup to send one).
4. **Logins persist.** Quit the Hunt Browser and open it again with `/api/browser/open`. You're still
   signed in, and capture is off.
5. **Capture from Hunt.** Create a case and confirm the test account as "him".
   `POST /api/browser/capture {case, on: true}`, then open the profile with
   `/api/browser/open {url, case}`.
   - The badge shows REC.
   - Within about 10 s the capture feed shows a page, with posts read, and the checklist ticks Posts.
   - Without a screenshot, `problems` says "No screenshot: click Hunt Capture once in this tab…".
6. **Screenshots.** Click Hunt Capture's icon on that tab, then scroll a screen and stop: a
   screenshot arrives. Or tick "Screenshots on every view" in the popup and accept Chrome's prompt:
   screenshots then arrive on every settled view, in every tab.
7. **From the popup.** Stop capturing in the popup: Hunt's status shows `capture.on: false`. Start
   it again in Hunt: the badge returns at the next page load.
8. **Sections and other sites.** Open the Photos tab: Photos ticks. Open example.com: nothing is
   captured. Open a LinkedIn page: nothing is captured, and the popup says LinkedIn is never
   recorded.
9. **Video.** With screenshots allowed, play a video for 10 s: about 5 video-frame screenshots
   arrive. Then **Record video**, play 15 s, and **Stop recording**: a recording arrives, and plays in
   Hunt with sound.
10. **Manual mode.** Switch to **Only when I press Capture this**. Scrolling now records nothing;
    Alt+Shift+H records one screenshot and one page.
11. **Hunt restarts.** Restart `hunt app` while the Hunt Browser stays open, and load the startup
    check. The next capture still arrives, because the browser was re-pointed at the new port.
12. **Hunt updates.** Change anything in `extension/` (or upgrade Hunt), quit the Hunt Browser, and
    reopen it from Hunt. The new code runs: check the popup, or a `problems` message.
13. **Sign out.** Sign out of Facebook inside the Hunt Browser: the status turns `signed_out`.
    `POST /api/browser/sign-out` while it's open returns 409. Quit it and retry: the profile is in
    the Trash, and every platform reads `unknown`.
14. **Scan.** Run a scan in Hunt. Captured posts' pictures and frames are scanned, and
    `counts.captured` counts them.
15. **Guided mode.** On a confirmed account's grid, press Alt+Shift+N once: the page moves down one
    screen, a page archive arrives, and only then does Next work again. Holding the keys does no more
    than one press. At the bottom, Next opens the first "open these" item. Each press is a
    `guided step` in the case's audit.
16. **Hard stop (simulated).** `POST /api/capture/revoked {url: "https://www.instagram.com/challenge/x"}`
    from the extension (or open such a URL). The badge shows STOP on Instagram tabs, captures there get
    403, and Next refuses. `POST /api/browser/resume {platform: "Instagram"}` lifts it.
17. **Story warning.** Signed in to a test Instagram account, click a Story ring: the browser asks
    first. Cancel keeps you where you were.
18. **Traffic.** In DevTools for the extension's service worker, Network shows requests only to
    `127.0.0.1:<port>` and the extension's own `pairing.json`. Throughout, nothing moved the page,
    opened a tab or clicked by itself.
