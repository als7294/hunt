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

**Observe-only.** It is a normal browser she drives:
- No Playwright driver.
- No remote-debugging port: a local port would let any process on the machine take over her sessions.
- No `--enable-automation` or other automation flags, so `navigator.webdriver` is false, as in any
  browser.
- No stealth, user-agent or fingerprint tricks.

`test_capture.py` fails if the launch arguments ever gain a debugging, automation, headless or
user-agent flag.

**Why Chrome for Testing, not her Chrome.**
- Branded Chrome 137+ ignores `--load-extension`. Chrome for Testing doesn't: checked live on
  156.0.8078.4, where `scripts/browser_e2e.py` passes.
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

The extension never:
- navigates, opens tabs, clicks, scrolls, types or searches
- likes, follows, friends or messages anyone

It records only pages she opens, while capture is on. It sends nothing anywhere except Hunt on
127.0.0.1: its Content-Security-Policy is `connect-src http://127.0.0.1:*`, and it makes no request
to any platform. There are no sock puppets: it works in her own logged-in browser.

`test_capture.py` reads the extension's code and fails on any `click()`, scroll call, tab
navigation, `location =`, form submit, synthetic event, script injection, or `fetch` to anything but
`http://127.0.0.1:`. It also fails on permissions like `<all_urls>`, cookies, history, webRequest
or debugger.

## What it records

Capture is **off by default and whenever the browser starts**. While it's on, the toolbar shows a
red **REC** badge, and **●** while a video is being recorded.

| When | What | Throttle |
|---|---|---|
| A supported page finishes loading, its address changes, you switch to its tab, or you stop scrolling for 1.2 s | A viewport screenshot (`chrome.tabs.captureVisibleTab`, JPEG) | at most one per 2.5 s per tab |
| Same, when the page is new to this tab or 20 s have passed | The page archive (`chrome.pageCapture.saveAsMHTML`): the page plus the pictures her browser already loaded | one at a time per tab |
| A video is playing on screen | A screenshot every 2 s (the frames she watched) | at most 90 per page |
| **Capture this** (popup or Alt+Shift+H) | Screenshot and archive, right away | none |
| **Record video** / **Stop recording** (popup) | A recording of the tab (`chrome.tabCapture` → WebM), with its sound still playing for her | stops itself at 10 min |

Sites covered: facebook.com, instagram.com, tiktok.com, x.com, twitter.com, linkedin.com and
youtube.com, including their subdomains.

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

### Videos: what's possible

Facebook, Instagram, X and most TikTok players stream video through `blob:` / Media Source
Extensions. Neither a page archive nor anything the extension may do can save those bytes, and the
extension may not fetch from the platforms at all. What works:

1. **Frames as she watches (on by default).** A screenshot every 2 s while a video plays on screen.
   The media scan (CLIP, then the vision model) works on frames, so "lifting at 0:16" is found the
   same way.
2. **Record video (on demand).** `chrome.tabCapture` records the tab exactly as she sees and hears
   it, stopping at her click or after 10 minutes. This is the faithful copy for evidence.
3. **Rejected: `chrome.debugger`** to pull the MSE segments. It shows a "being debugged" banner,
   reads all network traffic, and needs a far broader permission.
4. **Rejected: re-downloading the video URL.** It would make the extension talk to the platform, and
   the signed CDN links are tied to her session.

**Video posters** (the still shown before playing) do come through in the archive, and become the
post's picture.

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

| Platform | Anchors (no class names) | Gets |
|---|---|---|
| Facebook | `hunt.facebook.parse_saved` ([facebook.md](facebook.md)) | everything listed there |
| Instagram | embedded API JSON (`code`, `taken_at`, `caption`, `user`, `location`, counts); `<article>` with `<time datetime>`, `/explore/locations/` links, `h1` or the longest `dir=auto` caption; profile grid links to `/p/` and `/reel/`, whose alt text carries "Photo by X on October 25, 2026" | URL, exact or day time, caption, author, account, user id, place, likes, comments, pictures |
| TikTok | `__UNIVERSAL_DATA_FOR_REHYDRATION__` JSON (`id`, `desc`, `createTime`, `author`, `stats`, `poi`); profile tiles linking `/@user/video/<id>` (the id's high 32 bits are its posting time); video pages' `data-e2e` description and counts | URL, exact time, description, author, place, likes, comments, shares, cover |
| X | `article[data-testid=tweet]`: `User-Name`, `<time datetime>` on the `/status/` link, `tweetText`, `tweetPhoto`, video posters, `reply`/`retweet`/`like` aria-labels, `socialContext` ("reposted"). The status id is a snowflake, so the time is there even without `<time>` | URL, exact time, text, author, pictures, counts, `reposted_by` |
| LinkedIn | `data-urn="urn:li:activity:<id>"` (the id's top 41 bits are the posting time in ms), the actor's `/in/` link, the longest `dir=ltr` text, `aria-label` counts | URL, exact time, text, author, pictures, reactions, comments, reposts; "starting a new position…" as `life_event` (→ `other_job`) |
| YouTube | none: uploads come from its RSS (`posts.collect`) | the screenshots and archive are still evidence |

**Tested on** `fixtures/capture/*.mhtml`. These are fictional pages in the format
`chrome.pageCapture` writes, including posts known only from JSON, only from DOM, or only from an
id. Facebook is covered by `fixtures/facebook/`.

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
- `POST /api/browser/sign-out`
- `GET`/`POST /api/pairing`
- `POST /api/pairing/forget`
- `GET /api/cases/{slug}/checklist`
- `GET /api/cases/{slug}/captures`

**For the extension (key Guard):** POST
`/api/capture/pair | hello | checklist | view | page | recording | signins`.

## Hunt app screens (for the main session to build)

**Browser capture**, in settings or the case header:
- **Not paired:** "Hunt Capture records the pages you open on Facebook, Instagram, TikTok, X,
  LinkedIn and YouTube into your case. Install it from the `extension` folder (chrome://extensions →
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
- Each section is a row with a tick or an empty circle, its label, and "Open" (a link,
  `target=_blank rel=noopener`).
- Seen rows show `seen_at` and link their evidence.
- Unticked rows read as "not opened yet". The report's "What we couldn't see" shows the same.
- Empty state: "Confirm the subject's accounts in Is it him? to see what to open."

**Capture feed**: `GET /api/cases/{slug}/captures`, newest first, polled every 5 s while the screen
is open.
- Each row: time, platform, kind (screenshot, page, video frame, recording), the URL, and for pages
  "{posts} posts read, {added} new".
- Thumbnail or evidence link from `file` (`/evidence/{slug}/{basename}`).
- Empty state: "Nothing captured yet. Turn on capture in the Hunt Capture popup, then browse."

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
- **Screenshots are of the visible tab only.** A background tab is skipped; switching to it
  captures it.
- **Recording needs her click each time** (Chrome's rule for tab capture). The tab must stay in
  front.
- **Parsers follow today's markup** and fail soft. When a platform changes, the archive and
  screenshot are still kept, even if fewer posts are read.

## Manual test plan

Use test accounts you own, or public organisation pages, never a private person. Start with
`uv run python scripts/browser_e2e.py`, which should print `ok`.

1. **Start and look.** Start `uv run hunt app`. `GET /api/browser/status`, or the startup check
   screen, shows every platform `unknown` and the browser `available` with its version.
2. **Sign in.** `POST /api/browser/open {url: "https://www.facebook.com/login/"}`.
   - Google Chrome for Testing opens a window with no automation infobar.
   - The first time, macOS asks about "Google Chrome for Testing Safe Storage": choose Always Allow.
   - The toolbar shows Hunt Capture with no badge.
   - Sign in to a test account. Within a few seconds the status shows `facebook: signed_in`.
3. **Logins persist.** Quit the Hunt Browser and open it again with `/api/browser/open`. You're still
   signed in, and capture is off.
4. **Capture.** Create a case and confirm the test account as "him". Open its profile from Hunt
   (`/api/browser/open {url, case}`).
   - The popup preselects the case. **Start capturing**: the badge shows REC.
   - Wait 3 s, then scroll a screen and stop. In Hunt's capture feed a screenshot and a page appear,
     and the checklist ticks Posts.
5. **Sections and other sites.** Open the Photos tab: Photos ticks. Open example.com: nothing is
   captured.
6. **Video.** Play a video for 10 s: about 5 video-frame screenshots arrive. Then **Record video**,
   play 15 s, and **Stop recording**: a recording arrives, and plays in Hunt with sound.
7. **Manual mode.** Switch to **Only when I press Capture this**. Scrolling now records nothing;
   Alt+Shift+H records one screenshot and one page.
8. **Off.** **Stop capturing**: the badge clears. Quit and reopen the browser: capture is off.
9. **Hunt restarts.** Restart `hunt app` while the Hunt Browser stays open, and load the startup
   check. The next capture still arrives, because the browser was re-pointed at the new port.
10. **Sign out.** Sign out of Facebook inside the Hunt Browser: the status turns `signed_out`.
    `POST /api/browser/sign-out` while it's open returns 409. Quit it and retry: the profile is in
    the Trash, and every platform reads `unknown`.
11. **Scan.** Run a scan in Hunt. Captured posts' pictures and frames are scanned, and
    `counts.captured` counts them.
12. **Traffic.** In DevTools for the extension's service worker, Network shows requests only to
    `127.0.0.1:<port>` and the extension's own `pairing.json`. Throughout, nothing moved the page,
    opened a tab or clicked by itself.
13. **Everyday browser (optional).** Load `extension/` unpacked in Chrome, Edge or Brave, and pair it
    with the code from Hunt's *Browser capture*. The same capture steps work. The Hunt Browser takes
    the pairing back the next time it's opened.
