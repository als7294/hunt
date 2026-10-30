# Facebook in Hunt

Investigators rely on Facebook more than any other platform, and it shows a logged-out visitor almost
nothing. Hunt's rules ([legal.md](research/legal.md)) stay fixed:

- Hunt never logs in.
- It never automates an account or uses a sock puppet (the hiQ v. LinkedIn loss pattern).
- It never contacts or notifies the subject.
- It's free, and it does no face *search*. The analysis session is adding an opt-in, guarded 1:1 check
  of the investigator's own reference photo against candidate profile photos. It will be described in
  `docs/analysis.md` once it lands. Nothing on this page uses it.

[Hunt Capture](capture.md), the browser extension, now records those pages as she browses: no Save
Page As needed. It feeds the same parser (`parse_saved` reads its MHTML archives). The saved-page
upload below remains the path for a browser without the extension, or for pages saved earlier.

So Hunt's Facebook support is built around the investigator's own browsing. They look at Facebook
under their own lawful access and save what they find, and Hunt reads what they saved. The only
thing Hunt fetches itself is the small public part of a profile or Page that Facebook serves to
anyone who isn't logged in.

Code:
- `hunt/facebook.py`: the importers, links and clue mapping.
- `hunt/sources/facebook.py`: the logged-out read.
- `test_facebook.py`: offline tests.
- `fixtures/facebook/`: fictional pages. Every person, place and post in them is invented. Never commit
  a real page.

## The pieces

### `facebook.parse_saved(path, saved_at=None, media_dir=None) -> [post]`

Reads pages the investigator saved while browsing:

- Chrome or Firefox "Save Page As, complete" (the `.html` plus its `_files` folder)
- Chrome "Webpage, Single File" (`.mhtml`)
- Safari "Web Archive" (`.webarchive`)
- plain HTML

Pictures inside an MHTML or webarchive are written to `media_dir`, a new temporary folder by default.
Every `media` entry is a local file.

**Post shape:**

```
{source: "Facebook", url, post_id, posted_at, posted_at_precision, posted_at_text, author, account_url,
 fb_id, text, truncated, place, activity, life_event, media: [local paths], reactions, comments, shares}
```

Anything not found is `None`.

**What it extracts and where from.** Facebook's markup is obfuscated and changes often, so nothing
keys on class names:

| Field | Anchors, in order |
|---|---|
| Post boundaries | `aria-posinset` feed units, `role="article"`, `<article>`, mobile `data-ft` with `top_level_post_id`. Comments (nested articles, `aria-label="Comment by…"`/"Comentario de…"/"Commentaire de…") are excluded from everything |
| Author, `account_url`, `fb_id` | First profile link in the post's heading (`h2`–`h6`, then `<header>`, then `<strong>`). Profile URLs are recognised in every shape: vanity, `profile.php?id=`, `/people/…/ID`, `/pages/…/ID`, `/groups/…/user/ID`. The ID also comes from `data-hovercard`, mobile `content_owner_id_new`, the JSON actor, or another post on the page by the same account |
| `url`, `post_id` | First post-shaped link (`/posts/`, `permalink.php`, `story.php`, `/videos/`, `/reel/`, `/watch?v=`, `/share/p/`, then photo links). Tracking parameters (`__cft__`, `__tn__`, `refid`) are removed. IDs include `pfbid…` and numeric forms |
| `posted_at` | `data-utime` (exact), mobile `publish_time` (exact), the JSON `creation_time` (exact), then the most precise date text on the post link, `<abbr>`, `title`/`aria-label` tooltips and short spans |
| `text` | `data-ad-preview="message"` / `data-ad-comet-preview="message"`, `data-testid="post_message"`, `userContent`, mobile `data-ft {"tn":"*s"}`. Otherwise everything in the post that isn't interface text, a date, a count or a life event. Emoji images count as their alt text |
| `truncated` | "See more" / "Ver más" / "Voir plus" / "… Plus" was cut off. If the page's JSON has the full text, it's used and `truncated` is false |
| `place`, `activity` | The heading sentence: "is at X", "— at X", "is feeling adventurous at X", "está en X", "se siente agotado en X", "se sent motivé à X", "est à X". "with Mara Quill" is dropped |
| `life_event` | Heading ("started a new job at…", "se mudó a…", "a commencé à travailler chez…") or a life-event line in the post |
| `media` | `<img>` in the post (not emoji, icons, avatars or anything under 64 px), `<video>` sources and posters. Only files that were actually saved; Hunt never fetches a CDN URL |
| `reactions`, `comments`, `shares` | "All reactions: 23", "Like: 17 people", "1.2K", "48 comments", "1 vez compartido", "12 commentaires", and `aria-label`s. "1.2K" becomes 1200 |

**Embedded JSON.** Facebook's Relay payloads in `<script type="application/json">` fill in what the DOM
hides: the exact time behind "3d", the full text behind "See more", and the author's numeric ID.
Stories that are only in the JSON (prefetched, never rendered) become posts of their own.

**A single public post saved logged out** usually has nothing but link-preview tags. It still gives one
post from `og:url`, `og:description`, `og:title`, `og:image` and the `al:` app-link ID.

**Timestamps** (`facebook.parse_date(text, ref)` does the work, in English, Spanish and French):

| Shown | `posted_at` | precision |
|---|---|---|
| `data-utime` / `publish_time` / JSON `creation_time` | `2024-04-12T15:41:00+00:00` | `second` |
| "12 April at 09:41", "April 12 at 9:41 AM", "Friday, 12 April 2024 at 09:41", "12 de abril a las 9:41", "vendredi 12 avril 2024 à 09:41" | `2026-04-12T09:41` | `minute` |
| "Yesterday at 21:15", "Ayer a las 21:15", "Hier à 21:15", "Monday at 8:05 AM" | counted back from the save time | `minute` |
| "5m", "Just now" | counted back | `minute` |
| "2 hrs", "hace 2 horas", "2 h" | counted back | `hour` |
| "3d", "3 d", "3 j", "3 days ago" | counted back | `day` |
| "2w", "il y a 2 semaines" | counted back | `week` |
| "1y" | counted back | `year` |
| "Apr 12, 2023", "12 avr. 2023" | `2023-04-12` | `day` |
| "April 2024", "abril de 2024" (life events) | `2024-04-01` | `month` |

Timestamp rules:
- `posted_at_text` keeps exactly what Facebook showed.
- A date without a year is the latest one not after the save time.
- Relative times count back from `saved_at`: the MHTML `Date:` header, else the file's modification
  time. Pass `saved_at` when the investigator knows better.
- Exact times are UTC. Displayed times are in the saving browser's time zone, so they carry no offset.
- `posted_at` always starts with a full `YYYY-MM-DD`, so `[:10]` is always a date.

**Known gaps:**
- A saved page holds only what was on screen. Scroll to load posts, and open "See more" or comments
  before saving.
- Comments aren't extracted as posts (by choice; the parser already isolates them).
- Facebook plays video from `blob:` URLs, which no browser saves. Only posters come through.
- Stories and Reels viewers aren't covered.
- A shared post's original text can merge into the sharer's post.
- A life-event post whose only date is the event's ("April 2024") gets month precision.
- Plain-HTML saves (Safari "Page Source", "HTML only") keep CDN links, not pictures, so `media` is empty.
- Other interface languages still get structure (URLs, IDs, media, counts in digits, exact JSON and
  `data-utime` times), but not heading sentences or date text.

### `facebook.parse_screenshot(path, lines=None, taken=None) -> post`

One post from a screenshot. Text comes from Apple Vision OCR (`hunt.photo.read_text`); `lines` can be
passed instead.

**What it finds:**
- The date line, OCR noise like "12 April at 09:41 • ©" included.
- The author line above it (two wrapped lines are joined), with "is at…" / "is feeling…" / "está en…" /
  "se sent…" parsed as in saved pages.
- The body up to the counts row. A separate "See more" line sets `truncated`.
- Life-event lines and counts. A bare number at the start of the counts row is the reactions count.

**Relative times** count back from the time in a macOS screenshot's file name ("Screenshot 2026-10-28
at 14.03.12", "Captura de pantalla … a las …", "Capture d'écran … à …"), else EXIF, else the file's
modification time. `media` is the screenshot itself.

**Known gaps:**
- macOS only, because `read_text` is.
- One post per screenshot.
- No URL or IDs.
- Wrapped lines are joined with spaces, since OCR can't tell a wrap from a paragraph.
- Heuristic layout: the author must sit above the date line, as Facebook draws it.

### `hunt/sources/facebook.py`: logged-out public read

The standard source contract: `NAME = "facebook"`, `KINDS = {"username", "url"}`, and
`async search(seed) -> (findings, checked, note)`.

**What it does:**
- One GET per seed to `https://www.facebook.com/<username>`, or to the canonical form of a Facebook
  profile URL.
- At least `GAP_S` (3 s) between requests across seeds, through `HUNT_PROXY`.
- Hunt's own User-Agent.
- Usernames Facebook can't have (anything but letters, digits and dots, or under 5 characters) are
  skipped without a request.
- Post URLs and non-Facebook URLs are skipped.

**What it reads** (`facebook.parse_public(html, url, status)`):
- Name, description, image, URL.
- Numeric ID: from `al:android:url` / `al:ios:url` `fb://profile/<id>`, else `"userID"`, `"pageID"`
  or `entity_id`.
- Followers, likes, "talking about this".
- Page category, when served.
- From the description, "Lives in" / "From" / "Works at" / "Studied at" (and the Spanish and French
  forms) as `location`, `hometown`, `works_at` and `studied_at`.

Keys follow `match.py` (`fullname`, `location`), so identity scoring uses them directly. The raw
response is the finding's `body`, for the evidence locker.

**Honest outcomes:**

| state | When | Result |
|---|---|---|
| found | `og:title` served | 1 finding, `checked=1`, note "read … logged out: name, picture, numeric ID, followers. Facebook showed a login wall; nothing more is public" |
| login wall | sent to `/login` or `/checkpoint`, or a login title or form with no profile tags | no finding, note "…: Facebook showed a login wall; nothing more is public" |
| refused | HTTP 400/403/429 or "Sorry, something went wrong" | no finding, note asks the investigator to open it themselves and use "Add saved posts" |
| unavailable | 404 or "This content isn't available" | no finding (it doesn't exist, or it isn't public) |

`facebook.parse_profile(path)` runs the same extraction on a profile the investigator saved, including
the Intro card ("Works at", "Lives in", "From").

### `facebook.search_links(seeds) -> [{label, url}]`

Takes one `Seed` or a list, and builds links for the investigator to open in their own browser:

- **Names:** Facebook's people, posts, photos and videos search, plus people and posts with each
  `location` seed.
- **Emails and phones:** Facebook's top search, with phones in national, international, digits and
  E.164 forms.
- **Usernames:** the profile, when the username is possible on Facebook, plus search.
- **A Facebook profile URL:** its About, Photos, Videos and Friends tabs.
- **Dorks:** a `site:facebook.com` dork on Google and Bing for each, e.g.
  `site:facebook.com "Dorian Vell" "Port Alder"`.

Hunt never requests any of them.

### `facebook.categories(post) -> [(category_key, why)]`

Maps a post's own Facebook tags onto `scan.CATEGORIES` keys (`activity`, `lifting`, `sport`, `walks`,
`travel`, `other_job`, `driving`, `injury`). It reads three fields:

- **Feeling/activity tag:** "working out" → sport (never other_job), "traveling to Lisbon" → travel,
  "jugando al fútbol" → sport.
- **Life event:** "Started New Job at…" → other_job, "Got a new car" → driving, "Moved to…" / "se
  mudó a…" → activity.
- **Check-in place:** "…Gym" / "Gimnasio…" / "Salle de sport…" → sport, "…Trailhead" / "Sendero…" /
  "Parc national…" → walks, "…Hospital" → injury, "…Airport" → travel.

The post text is left to the scan's own keyword pass. `why` reads like `Facebook check-in: "Iron
Harbor Gym"`. The tables are English, Spanish and French, matched without accents. "feeling blessed"
isn't French "blessé".

**Known gap:** these are keyword tables, not language understanding. An employer's name can trip a
category: "Déménagements Port-Alder", a moving company, also gives `activity`. The `why` shows the
investigator exactly what matched.

## What logged-out Facebook returns today (checked live 2026-10-29, `facebook.com/NASA` only)

**With Hunt's User-Agent** (`Hunt/0.1 (+https://github.com/als7294/hunt)`), Facebook returns HTTP 200
and about 490 KB of HTML. It contains:

- `<title>` and `og:title`: "NASA - National Aeronautics and Space Administration"
- `og:url`, `og:image` (the profile picture), `og:type`
- the `description` / `twitter:description` meta, with the follower count, "talking about this" and
  the About blurb ("28,736,799 followers · 63,343 talking about this. Explore the universe…")
- `al:android:url` / `al:ios:url` = `fb://profile/100044561550831`, plus `"userID":"100044561550831"`
  in the inline JSON

It does not contain:
- posts or `creation_time`
- the page category
- About fields
- photos

The viewer IDs are `"0"` (logged out). The login prompt is drawn by JavaScript, not served in the HTML.

**With a browser User-Agent but none of a browser's other headers**, Facebook returns HTTP 400 and
"Sorry, something went wrong." Hunt doesn't add browser fetch headers to get past that. Doing so would
be bot-check evasion, and the honest User-Agent already works. If Facebook starts refusing it, the
source reports "refused" and the investigator saves the page themselves.

**Personal profiles** weren't tested live: the rule is organisations only. Expect either a redirect to
`/login` (reported as a login wall) or only the preview tags.

## Robustness on the fixtures

| Fixture | Layout | Result |
|---|---|---|
| `Dorian Vell _ Facebook.html` + `_files/` | Modern desktop profile (obfuscated classes, `aria-posinset`, svg avatars, Relay JSON), Save Page As complete | 5 posts, every field above. The friend's wall post keeps her as author. The exact second comes from the JSON behind "3d". The full text replaces "See more". A JSON-only story comes through. The comment's text, date and avatar stay out. Emoji and logo images are excluded. The Intro card gives lives in, from and works at |
| `classic_es.html` | 2019 desktop layout, Spanish, HTML only | 3 posts: `data-utime` exact times with the tooltip kept, "3 h" at hour precision, check-in, feeling, a life event, Spanish counts, IDs from `data-hovercard` and from other posts. No media (CDN links), as expected |
| `mobile_fr.mhtml` | `m.facebook.com`, French, Chrome single file | 3 posts: `publish_time`, "3 j" counted from the MHTML `Date:`, pictures extracted from the archive, "… Plus" truncation, French life event and counts |
| `public_post.webarchive` | One public post saved logged out in Safari | 1 post from link-preview tags, the visible date and the archived picture |
| `public_page.html` | A Page as the logged-out read receives it (structure as seen live) | `parse_public`: name, ID, 2,481 followers, 37 talking about |

**Degraded copies of the modern fixture:**

| Change | Result |
|---|---|
| Every class name randomised | Identical output |
| JSON removed | 4 posts; "3d" stays at day precision |
| `aria-posinset` removed | Identical (`role="article"` still anchors) |
| File cut in half | 4 partial posts |

**Hostile input:**
- A crafted page can't pull files from outside its own folder (`../`, absolute and `file://` sources
  are ignored).
- Only media extensions are accepted.
- 5,000 nested `div`s don't exhaust recursion.

Run `uv run python test_facebook.py`. It is offline, apart from the real Apple Vision OCR check on
macOS. `HUNT_LIVE=1` adds the single NASA read.

## Legal reasoning, piece by piece ([legal.md](research/legal.md))

| Piece | Why it's allowed |
|---|---|
| `parse_saved`, `parse_screenshot`, `parse_profile` | No network at all: Hunt reads a file on the investigator's disk. The browsing was the investigator's own, under their own access and responsibility. Hunt automates no account and holds no session (the hiQ fake-account pattern never arises). The import is audited with file hashes, like any evidence |
| `sources/facebook.py` | Logged-out reads of public pages. *Van Buren* and *hiQ* (9th Cir. 2022): public pages aren't accessed "without authorization". *Meta v. Bright Data* (2024): logged-off collection of public data didn't breach Meta's terms. One request per seed, 3 s apart, through `HUNT_PROXY`, with an honest User-Agent. A refusal is reported, never worked around. No search endpoint, no account-recovery lookup (it can notify the subject, which is why `user_scanner.py` bans Facebook's), nothing that needs a session. Passive only: no follow, like, message or contact |
| `search_links` | Hunt builds URLs and never requests them. Facebook search needs a login, so opening one is the investigator's own search under their own account. Engine dorks go to Google and Bing in the investigator's browser |
| `categories` | A pure mapping over what the investigator imported. The machine only surfaces: hits keep the scan's "likely" cap and never say who is shown |

No face search anywhere: these pieces only pass pictures on to the media scan.

## How it's wired in

**1. Source registry.**
- `hunt/sources/__init__.py` lists `facebook` with the username sources.
- Its finding's URL is the one it asked for, `https://www.facebook.com/<username>`, exactly as Maigret
  reports it. So `search.build` (which groups findings by `match.norm_url`) merges the two into one
  candidate: `found_by: ["facebook", "maigret"]`, with this source's `uid`, followers and intro added
  to the attrs. `search.py` itself needed no change.

**2. Storing imported posts: `posts.add_posts(case, items, kind="image", evidence=None)`.**
- One `added` post per item, with its text, link, account and date.
- Local media is stored as `add_files` does: hashed into `evidence/`, and a picture already in the
  case isn't stored twice. `kind="screenshot"` marks a screenshot's own picture.
- A post already in the case (same source and link, or with no link the same date and words) is
  skipped and audited as `post already added`.
- `posts.store(case, path, ext)` hashes any file into evidence; the route uses it for the saved page.
- **The extra fields live in a side table, `post_extra(post_id, extra)`, not a new `posts` column.**
  `posts.py` inserts into `posts` by position (`insert into posts values (null, ?, …)`), so a ninth
  column would break those inserts in existing cases. The extra fields are precision, `posted_at_text`,
  author, IDs, place, activity, life event, counts and `evidence` (the stored page).
- `list_posts` returns them as `extra` (`null` for other posts).

**3. Upload route: `POST /api/cases/{slug}/facebook`.** Documented in [api.md](api.md).
- Same Guard rules as `/media`: the Guard now accepts `multipart/form-data` on paths ending
  `/facebook` too.
- Each file keeps its relative path inside a streamed temp dir, so `Page.html` finds `Page_files/`.
  Absolute paths, drive letters and `..` return 400.
- SVG, scripts and styles from a `_files` folder are skipped (never stored) and listed in `skipped`,
  instead of failing the whole folder with 415.
- Pages are hashed into evidence first: HTML and MHTML are served as `text/plain` with
  `CSP: sandbox` (MHTML was added to that list), and `.webarchive` is stored as `<sha>.plist`
  (`EVIDENCE_NAME` allows 2–5 letter extensions).
- Parsing runs in a worker thread.
- A screenshot showing a post's date line becomes that post. Any other picture goes through
  `add_files` with platform "Facebook".
- An optional `saved_at` anchors relative dates.

**4. Scan.**
- `scan.run`'s text pass calls `_tag_hits` after the caption keywords. It turns
  `facebook.categories(post["extra"])` into text hits at `P_TEXT`, with the usual "likely" cap and
  `who="unknown"`, for categories in `look_for`.
- Hits are one per post and category, so where the caption already matched (say "15 km" for walks),
  the caption hit stands.
- The tags add what English caption keywords miss: "Salle de sport Fer Rouge" → sport, "a commencé à
  travailler chez…" → other_job.

**5. Links route: `GET /api/cases/{slug}/facebook/links`** returns `{links: search_links(case seeds)}`.
It's a GET, with no network access and no state change.

**6. UI tile (the main session builds it).** A "Facebook" tile in the posts step, and on the person
view when a Facebook account is in the person.
- Line: "Facebook shows almost nothing logged out. Browse it yourself, save what you find, and Hunt
  reads it."
- **Add saved posts:** a file input, `multiple`, with
  `accept=".html,.htm,.mhtml,.mht,.webarchive,.png,.jpg,.jpeg,.heic"`.
  - Add a second input with `webkitdirectory` for "Save Page As, complete" folders.
  - Append each file to the `FormData` with its `webkitRelativePath || name` as the filename.
  - Optionally send `saved_at` from the newest `lastModified`.
  - Hint: "Chrome: File › Save Page As › Webpage, Single File. Safari: File › Save As › Web Archive.
    Or take screenshots. Scroll and open 'See more' first."
  - Show `skipped` quietly.
- **Open search links:** the links route's list, each an `<a target="_blank" rel="noopener noreferrer">`
  with its label. Note: "These open in your browser under your own Facebook account. Hunt doesn't
  visit them."
- Show the source's note ("Facebook showed a login wall; nothing more is public") beside the account,
  so a thin result reads as Facebook's limit, not a failed search.
- An imported post's `extra` can be shown as "at Iron Harbor Gym · feeling adventurous", with the
  date's precision ("3 days before the save, day precision").
