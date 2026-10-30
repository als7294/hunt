# Media scan: evaluation and speed

_Measured 2026-10-29 on Aaron's Mac (Apple Silicon, MPS). Vision model: `qwen3-vl:4b-instruct` in Ollama. CLIP: ViT-L/14, fp16. Every run asks all eight look-for categories, the worst case. Runs were done at `nice 10` with one model loaded at a time._

## The eval set

`docs/research/scan-eval-manifest.json` lists 213 photos and 40 videos (30 minutes). For each it records the source URL, licence, author, hand labels, video time ranges, a hard-negative tag, and the dev/test split.

**Media.** Media are never committed. `uv run python scripts/eval_scan.py collect` fetches them into `~/Hunt/cache/scan-eval2/`, about 370 MB.

**Sources.**
- **Wikimedia Commons:** freely licensed photos and videos, one per search query, with four or more queries per category plus hard negatives.
- **Bluesky:** public posts from 53 organisation accounts, read logged out the way Hunt reads them. These include removal firms, gyms, football and rugby clubs, parkruns, outdoor centres, kayak outfitters, roofers and scaffolders, driving schools, an airline, tour operators, and physiotherapy bodies. No private individuals' accounts were used.
  - Their posts are what real feeds look like. About half are promotional graphics, event posters, team sheets, or vans with nobody lifting.

**Labels.**
- **How they were made.** Every item was hand-labelled from contact sheets. A label is a look-for category the photo or video visibly shows; video labels carry the time ranges.
- **Hard-negative tags:**
  - things that don't count as evidence: `graphic`, `meme`, `screenshot`, `text`, `old`
  - visible scenes that should not be flagged: `children`, `small item` (holding a cup or a phone, not carrying something heavy), `gym, no lifting`, `nobody`, `selfie`, `group pose`, `pet`, `food`, `machine`
- **Scoring rule.** Items tagged graphic, meme, screenshot, text or old count as negatives even when they show an activity. A club's poster of a footballer, or a 1930s photo of dock workers, is not evidence of what the subject does.

**Split.** Items alternate between dev and test within each group of kind plus main label, so both halves get the same mix. All tuning uses dev only; the test numbers below are held out.

| Split | Photos | Videos | Video minutes | Positives (activity / driving / injury / lifting / other_job / sport / travel / walks) |
|---|---|---|---|---|
| dev | 115 | 25 | 19.2 | 7 / 5 / 5 / 7 / 7 / 13 / 8 / 5 |
| test | 98 | 15 | 11.2 | 5 / 4 / 4 / 6 / 8 / 10 / 7 / 2 |

**Thin categories.** Walks and driving have few positives, especially in test, so their per-category numbers swing with a single item. Read them as indicative.

## How it's measured

`uv run python scripts/eval_scan.py run --split test [--code DIR]` runs the real `scan.run` on a throwaway case, with photos and videos in separate cases. It reports:

- **Precision and recall per category,** item by item.
- **False alarms on negatives,** overall and per hard-negative tag.
- **Video time ranges:** whether each video hit overlaps the labelled range, within 2 seconds.
- **Child blurring:** whether hits on photos with children are blurred.
- **Speed:**
  - seconds per photo, and per minute of video, including model loads
  - time per phase: CLIP and the vision model
- **Peak memory:** this process's RSS, Ollama's model runner, and Apple-GPU memory.
- **Responsiveness:**
  - the event loop's worst and 95th-percentile lag (the app serves its UI from that loop)
  - macOS memory-pressure level: 1 normal, 2 warning, 4 critical

**Speeding up a rescore.** `rescore results.json` scores saved predictions again without rescanning.

## Profile of the scan before any change

Main at `8b5fa6e`, on the earlier 36-photo and 2-video set:

| Phase | Time | Share |
|---|---|---|
| Vision model (97 calls) | 406 s | 97% |
| CLIP (load and score) | 13 s | 3% |
| Video frames | 1 s | under 1% |

The vision model is the cost, and it was asked once per photo or stretch of video **per category**: 2.6 calls per item.

**Where one call's 5.5 s goes**, from Ollama's own timings:
- **Reading:** about 3.5 s for roughly 1,250 tokens, nearly all of them the image.
- **Writing:** about 2 s for roughly 58 tokens of answer.

**What the image size does.** Ollama resizes every image to the same size, so sending 512 px instead of 1280 px changed nothing: 5.3 s against 5.5 s, with identical answers.

**The consequences:**
- **Downscaling** before the vision model doesn't help.
- **Several stills of a video** sent as separate images cost about 3 × 3.5 s of reading.
- **The only levers** are fewer calls and shorter answers.

## Results on the held-out test split

**Configurations compared:**
- **Baseline:** main at `8b5fa6e`, unchanged.
- **After:** this branch. It has:
  - one vision-model call per photo or video stretch for every candidate category
  - video stills tiled into one image
  - "unclear" answers beside a "yes" dropped
  - a 4k-token context
  - the CLIP embedding cache

**How the "after" numbers were produced:** the speed and memory figures come from one run. The accuracy figures replay that run's saved answers with the "unclear" rule applied, and the rule was chosen on the dev split. The rule only filters answers, so it doesn't change the timing.

### Before and after

| | Baseline | After |
|---|---|---|
| **Photos** (98) precision / recall | 0.32 / 0.86 | **0.35 / 0.86** |
| Negative photos flagged (any category) | 32 / 66 | 35 / 66 (the extra three are low-weight "unlikely" hits) |
| **Videos** (15, 11.2 min) precision / recall | 0.17 / 1.00 | 0.17 / 1.00 |
| Negative videos flagged | 7 / 11 | 8 / 11 |
| Video hits inside the labelled range (±2 s) | 5 / 8 | 3 / 4 |
| **Seconds per photo** | **10.1** | **4.7** (2.2× faster) |
| **Seconds per minute of video** | **177** | **14.9** (12× faster) |
| Vision-model calls, photos / videos | 164 / 133 | 71 / 22 |
| Time per call, photos / videos | 6.0 s / 14.6 s | 6.1 s / 5.5 s |
| CLIP, photos / videos | 12 s / 37 s | 22 s / 38 s, then about 0 s on a rescan (cache) |
| Vision-model memory (Ollama) | 8.2 GB (default 32k context) | **3.7 GB** (4k context) |
| This process's peak memory; CLIP on the GPU | 3.0 GB; 1.0 GB | 3.0 GB; 1.0 GB |
| Worst event-loop lag, photos / videos (p95) | 300 / 549 ms (3 / 4 ms) | 249 / 22 ms (1 / 1 ms) |
| Worst macOS memory pressure | 4 (critical) | 2 (warning) photos, 1 (normal) videos |

**Was the Mac responsive?**
- **The app's event loop stayed responsive in both.** Its 95th-percentile lag was 1–4 ms. The worst spikes (250–550 ms) happened while CLIP loaded.
- **Memory pressure is what changed.** The baseline reached "critical", and the 8.2 GB model is the likely cause of the lag Aaron saw; other sessions' models were also loaded at times. After the change, the worst was "warning".

### Per category, test split (precision / recall)

| | activity | lifting | sport | walks | travel | other_job | driving | injury |
|---|---|---|---|---|---|---|---|---|
| Positives in test (photos) | 4 | 4 | 9 | 2 | 5 | 6 | 3 | 4 |
| Baseline, photos | 0.17 / 1.0 | 0.33 / 1.0 | 0.53 / 0.89 | 0.25 / 1.0 | 0.22 / 0.4 | 0.26 / 0.83 | 0.43 / 1.0 | 0.57 / 1.0 |
| After, photos | 0.20 / 1.0 | 0.44 / 1.0 | 0.53 / 0.89 | 0.25 / 1.0 | 0.29 / 0.4 | 0.29 / 0.83 | 0.43 / 1.0 | 0.50 / 1.0 |

The test videos have only four positives (activity, travel, other_job, driving), and every one was found in both runs.

**Hard negatives flagged in test, before → after:**

| Tag | Before | After |
|---|---|---|
| graphic | 14/21 | 14/21 |
| old | 7/13 | 7/13 |
| nobody | 5/18 | 7/18 |
| group pose | 2/3 | 3/3 |
| children | 1/3 | 1/3 |
| small item | 0/2 | 0/2 |
| portrait | 2/2 | 2/2 |
| pet | 1/1 | 1/1 |
| selfie | 0/1 | 0/1 |

Child photos that got a hit were blurred in 1 of 2 cases (test) and 2 of 2 (dev).

**Dev split, "after" configuration (where the rule was chosen):**
- Photos: 0.29 / 0.86, 6.6 s each.
- Videos: 0.22 / 0.82, 19.4 s per minute.
- Dropping "unclear" beside a "yes" moved dev from 0.25 / 0.89 to 0.29 / 0.86 on photos, and from 0.17 / 0.82 to 0.22 / 0.82 on videos. Dropping every "unclear" cost too much recall (videos 0.82 → 0.73).

## What changed, and what didn't help

**Changes that stayed:**
- **One call per photo or video stretch.** Each call answers every candidate category, under neutral keys `q1`, `q2`…. The image is read once (about 3.5 s) and each extra answer costs about 0.2 s.
- **Tiled video stills.** Up to four stills of a stretch go into one 2×2 image, the cost of a single image instead of three.
- **At most 8 stretches per video.**
- **"Unclear" answers beside a "yes" are dropped.** When the model hedges "unclear" on categories the image plainly doesn't show, that's noise.
- **4k-token context:** `num_ctx` set to 4096 for `observe()` and `judge()`. That cuts the model from 8.2 GB to 3.7 GB; a call needs about 1,300 tokens.
- **CLIP embedding cache by media SHA-256** (and frame time; prompts by their text), in `case.db`. A rescan, or an extra look-for item, no longer reloads CLIP or re-embeds photos. 115 photos take 0 s instead of about 12 s, or 0.7 s for one new look-for item.
- **OCR timeout.** Apple Vision OCR on screenshots gives up after 30 s; Vision can block forever when several processes use it, and that must not hang the scan.

**Measured, and left as they were:**
- **Downscaling before the vision model.** Ollama resizes every image to the same size: 1280 px and 512 px gave about 1,250 tokens and the same time.
- **Bigger CLIP batches on MPS.** Batch 4, 8, 16 and 32 all gave 18–19 photos/s. CLIP is limited by image decoding on the CPU, not the GPU. CLIP stays at fp16, batch 8.
- **Scene-change frame sampling, and decoding video while the vision model works.** Frames plus CLIP cost about 3.4 s per minute of video, against 10.8 s for the vision model. The 1 fps sampling with near-duplicate frames dropped already removes static stretches: a 47 s clip keeps 37 frames, a static 19 s clip keeps 2. Extraction takes 0.3–0.5 s per clip, so there's nothing to overlap.

## What's achievable on this Mac

**An account of 200 photos and 20 one-minute videos, all eight categories asked:**

| Part | Time |
|---|---|
| 200 photos × 4.7 s | about 16 min |
| 20 min of video × 14.9 s | about 5 min |
| **Total** | **about 20 min**, down from about 93 min (200 × 10.1 s + 20 × 177 s) |

With three categories asked, fewer photos pass the CLIP gate, and I'd expect about 10 min. That figure is not measured.

**Why "a few minutes" isn't reachable yet:**
- Each call costs about 4.5–6 s, and about 3.5 s of that is the model reading the image, which Ollama fixes.
- Getting there needs fewer calls or a faster model. The candidates for the next round, measured on dev first:
  - tiling 2–4 photos per call
  - a stricter CLIP gate, which costs recall
  - a smaller vision model

## Round 2: accuracy where it was weakest

_Tuned on the dev split only; the held-out test split was run once per candidate configuration._

**Targets**, from round 1:
- **Over-flagging.** 35 of 66 negative test photos were flagged.
- **Travel recall:** 0.4.
- **Activity and other_job precision:** about 0.2–0.3.

The dev errors traced to five causes:
- old photos (24 false category flags)
- scenes with nobody in them (19)
- promotional graphics (16)
- photos of children (8)
- travel photos never reaching the vision model at all

### Held-out test split: round 1 versus round 2

| | Baseline (main before round 1) | Round 1 (main `8327131`) | **Round 2** |
|---|---|---|---|
| Photos, precision / recall | 0.32 / 0.86 | 0.35 / 0.86 | **0.41 / 0.95** |
| Negative photos flagged | 32 / 66 | 35 / 66 | **27 / 66** |
| Old photos flagged | 7 / 13 | 7 / 13 | **2 / 13** |
| Graphics flagged | 14 / 21 | 14 / 21 | 11 / 21 |
| Empty scenes flagged | 5 / 18 | 7 / 18 | 6 / 18 |
| Videos, precision / recall | 0.17 / 1.00 | 0.17 / 1.00 | 0.19 / 1.00 |
| Negative videos flagged | 7 / 11 | 8 / 11 | 6 / 11 |
| Seconds per photo | 10.1 | 4.7 | **3.7** |
| Seconds per minute of video | 177 | 14.9 | **11.8** |
| Worst event-loop lag; worst memory pressure | 549 ms; critical | 249 ms; warning | 178 ms; normal |

| Test photos, precision / recall | activity | lifting | sport | walks | travel | other_job | driving | injury |
|---|---|---|---|---|---|---|---|---|
| Round 1 | 0.20 / 1.0 | 0.44 / 1.0 | 0.53 / 0.89 | 0.25 / 1.0 | 0.29 / **0.4** | 0.29 / 0.83 | 0.43 / 1.0 | 0.50 / 1.0 |
| Round 2 | 0.21 / 1.0 | **0.67** / 1.0 | 0.50 / 0.89 | 0.29 / 1.0 | **0.45 / 1.0** | **0.38** / 0.83 | 0.50 / 1.0 | 0.57 / 1.0 |

**Why the answers got shorter.** Each answer now carries two short fixed-option fields (`image` and `people`) instead of free prose, so a photo costs 3.7 s, not 4.7 s.

### What changed

- **`image` field in the judge's answer.** The options are photo, poster or advert, cartoon or illustration, screenshot or text, and old photo or artwork. Only a photo, or a video still, can produce hits.
  - On dev, old photos flagged fell from 12 to 4 of 17.
  - A plain instruction to "answer no for posters and old photos" had done nothing (graphics stayed at 11 of 21). The small model follows a fixed-option field, not a rule in prose.
- **`people` field:** none, adults, children only, or adults and children.
  - It drives blurring, as `child_visible` did before; `judge` still returns `child_visible`.
  - When nobody, or only children, is in the picture, lifting, sport and other_job hits are dropped: those need an adult to be visible.
  - Driving, walks and activity are exempt. A first-person dashcam drive or a walk filmed by the walker shows no one, and requiring a person lost both on dev.
- **Travel's CLIP prompts were broadened** to airports and plane cabins, train platforms, sightseeing, beach or ski resorts, and cruise ships or cable cars. Every travel miss had been blocked at the CLIP gate, before the vision model saw it.
  - On dev, 5 of 6 travel photos now reach the model (4 before), with no extra non-travel items asked about travel.
  - A broader set reached 6 of 6 but doubled the non-travel questions, so it wasn't used.
- **The travel question names those cases too.**

### Tried on dev and dropped

- **Dropping "activity" when the same call says sport, lifting or walks.** It lost chopping wood (the raised axe read as "lifting") and an outdoor-centre video. They're legitimately both.
- **Extra CLIP negatives for posters, flyers, cartoons and old photographs.** Graphics went from 10 to 9 flagged on dev, but one positive was blocked. Club posters often contain real photos of people, which CLIP and the vision model reasonably treat as photos.

### Grid thumbnails (640 px)

The capture extension and the Apify connector bring in grid thumbnails of about 640 px, and CDN-sized media. To see what that size does, the test photos were re-run as 640 px centre-cropped squares, saved as JPEG at quality 80 (`eval_scan.py run --grid 640 --photos`):

| Test photos | Full size | 640 px grid |
|---|---|---|
| Round 1 code, precision / recall | 0.35 / 0.86 | 0.32 / 0.84 |
| Round 2 code (before the travel prompts), precision / recall | 0.37 / 0.86 | 0.36 / 0.81 |
| Seconds per photo (round 2) | 3.8 | 3.4 |

**What the size costs:** precision holds, but recall drops by one or two items. The losses were activity and other_job, where a centre crop can cut out what the person is doing.

**How hits on grid thumbnails are shown:** a hit carries `from_grid: true` when its media is a grid thumbnail, or its post was seen only in a grid (`extra.from == "grid"`). The app then shows "from a grid thumbnail; open the post to confirm" until the post is captured in full.

## Where accuracy is still weak

**Promotional graphics with real photos in them.** 11 of 21 test graphics are still flagged, because club posters and team sheets contain real photos of people.

**Group poses and portraits.** These sit at 3 of 3 and 2 of 2 on test: a posed team photo reads as sport.

**Children-only photos.** The kids' boxing class is no longer flagged, which is intended, since children aren't the subject. The visual labels count that as one missed sport item on dev.

**Next candidates, tuned on dev:**
- a "posed photo" value in a fixed-option field
- a CLIP prompt set for team sheets and fixture posters

**What can't change:** machine verdicts stay capped at "likely", and the investigator decides on every hit.
