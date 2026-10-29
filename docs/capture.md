# Hunt Capture

Hunt reads logged-out pages only, and Facebook, Instagram, TikTok, X and LinkedIn show logged-out
visitors almost nothing. Hunt Capture closes that gap the way Hunchly does:
- **The investigator browses the platforms herself, logged in as herself**, under her own lawful access.
- **A browser extension records what she views** into the open case.
- **Hunt does everything else:** evidence hashing, post extraction, the media scan, the checklist and
  the report.

Why this is lawful, and what risk remains, is in [legal.md](research/legal.md#human-driven-capture-hunt-capture-browser-extension).

**Code:**
- `extension/`: Chrome Manifest V3, for any Chromium browser (Chrome, Edge, Brave, Arc).
- `hunt/extension.py`: the server half. `hunt/capture.py` was already taken by the headless evidence
  screenshots that search uses.
- The `/api/capture/*` and `/api/pairing` routes in `hunt/app.py`.
- `test_capture.py`, with fictional fixtures in `fixtures/capture/`.

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

**For the main session.** `hunt app` binds a random port, so a paired extension must be paired
again after Hunt restarts. Its popup says so. Having `serve()` try the last port first (remember it
in `~/Hunt`) would let one pairing last. That's a one-line change I didn't make, because `serve()`
isn't mine.

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
- `GET`/`POST /api/pairing`
- `POST /api/pairing/forget`
- `GET /api/cases/{slug}/checklist`
- `GET /api/cases/{slug}/captures`

**For the extension (key Guard):** POST
`/api/capture/pair | hello | checklist | view | page | recording`.

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

- **Re-pairing after every Hunt restart** (the port), until `serve()` remembers its port.
- **Only what was on screen and loaded.** Scroll to load more; open "See more" and comments before
  capturing.
- **Screenshots are of the visible tab only.** A background tab is skipped; switching to it
  captures it.
- **Recording needs her click each time** (Chrome's rule for tab capture). The tab must stay in
  front.
- **Parsers follow today's markup** and fail soft. When a platform changes, the archive and
  screenshot are still kept, even if fewer posts are read.

## Manual test plan

Use test accounts you own, or public organisation pages, never a private person.

1. Start `uv run hunt app`. Create a case and confirm at least one account (for example a public
   Page you follow) as "him".
2. Open `chrome://extensions`, turn on Developer mode, choose **Load unpacked**, and pick `extension/`.
   The toolbar shows Hunt Capture with no badge.
3. In Hunt, **Pair a browser**. Paste the code into the popup and press **Pair**. The popup now
   lists your cases, and the `hunt app` terminal prints "Hunt Capture paired".
   - Paste a wrong code five times: the popup reports it, and the right code then fails too.
     Make a new one.
4. Choose the case and **Start capturing**. The badge shows REC.
5. Open the confirmed account's profile, wait 3 s, and scroll a screen and stop. In Hunt's capture
   feed, a screenshot and a page appear. The checklist ticks Posts.
6. Open the Photos tab: Photos ticks. Open an unrelated site, such as example.com: nothing is
   captured.
7. Play a video on the profile for 10 s: about 5 video-frame screenshots arrive. Then **Record
   video**, let it play 15 s, and **Stop recording**: a recording arrives and plays in Hunt with
   sound.
8. Switch the mode to **Only when I press Capture this**. Scrolling now records nothing; Alt+Shift+H
   records one screenshot and one page.
9. **Stop capturing**: the badge clears, and scrolling records nothing. Quit and reopen the browser:
   capture is off.
10. Run a scan in Hunt. Captured posts' pictures and frames are scanned, and captured posts show
    under counts.captured.
11. **Unpair** in Hunt. The popup's next action reports the extension isn't paired, and
    `/api/capture/*` returns 403.
12. In DevTools for the extension's service worker, Network shows requests only to
    `127.0.0.1:<port>`. Throughout, the extension never moved the page, opened a tab or clicked
    anything by itself.
