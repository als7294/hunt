# Identity analysis: pivots, the account graph, photo and face matching, learning

Today Hunt ranks each found profile on its own (`match.score`). These modules add what practitioners do by hand
(see [pain points](research/pain-points.md), #1):

| Module | Does | Network | Model |
|---|---|---|---|
| `hunt/pivot.py` | guesses handles from a name; mines new seeds from the person's profiles | none | none |
| `hunt/graph.py` | links accounts to each other with reasons; splits them into distinct people | none | none |
| `hunt/similar.py` | decides whether two profile photos are the same picture | none | CLIP ViT-L/14, local cache |
| `hunt/face.py` | opt-in 1:1 check: is the face in this picture the one in the case's reference photo? | `download()` once | YuNet + AuraFace via OpenCV; CLIP for the child gate |
| `hunt/learning.py` | learns face calibration and matcher weights from the investigator's decisions | none | none |
| `graph.associates` | family and associates named in the case's own posts, bios, records and photo marks | none | none |
| `hunt/leads.py` | the claim against the evidence: a timeline, and ranked leads per stated restriction | none | none |

**Dependencies:** `similar.py` imports `scipy`, `torch`, `transformers` and `huggingface_hub` (the test only).
All are installed today only as dependencies of `reverse-geocoder` and `geoclip`; declare `scipy` and
`transformers` in `pyproject.toml` when wiring this in.

Tests: `uv run python test_analysis.py` (offline; the CLIP check runs only if the weights are cached).
Benchmark: `uv run python scripts/eval_similar.py` (fetches public organisations' avatars and public-domain
NASA portraits once into `~/Hunt/cache/similar-eval/`).

## Interfaces

```python
pivot.username_guesses(name: str, limit=10) -> list[str]
pivot.suggestions(report: dict, min_p=0.55) -> list[{value, kind, why, source_url}]
pivot.facts(attrs: dict, own_url="") -> list[{kind, value, how, rank, platform?, url?}]   # used by graph
pivot.gravatar(attrs: dict) -> set[str]                                                  # Gravatar email hashes

similar.matches(images: {key: PIL image | path}) -> {frozenset({key_a, key_b}): clip_similarity}
similar.same_photo(img_a, img_b) -> (bool, clip_similarity)
similar.embed(images) -> np.ndarray   # unit CLIP rows; loads and unloads the model
similar.aligned(a, b) -> float        # the pixel check alone

graph.build(candidates, same_photos=None) -> {nodes, edges}
graph.people(g) -> list[{accounts, sites, name, probability, verdict, reasons}]
graph.evidence(g, likely: set[normalised url]) -> {url: [(bits, tag, reason)]}   # match.score's `extra`
```

`candidates` and `report` are `search.build()`'s (`cli.build()` on main). `same_photos` is `similar.matches()` over
the candidates' stored profile photos, keyed by profile URL; a value of `None` marks an exact re-post found by dHash.

## 1. Handle guesses: `pivot.username_guesses`

"Dorian James Vell" → `dorianvell, dorian.vell, dvell, dorian_vell, djvell, dorianv, velldorian, vell.dorian,
d.vell, dorian-vell`. Nicknames come from `nicknames` (shortest first, then the ones sharing the most letters with
the name), so "Robert Smith" gets `robsmith, bobsmith`. Accents are folded, apostrophes and hyphens joined, and
titles and suffixes dropped. The pattern order is hand-ranked (a `ponytail:` note says how to re-rank it).

These are guesses, with a low prior. A hit on a guessed handle is not evidence that the account is the subject's.

**Plug in:**
- **`search.run` (new step, opt-in):** when the case has a `name` seed and the investigator ticks "also try likely
  usernames" in the wizard, fan out the top guesses. Use one cheap source only (WhatsMyName or Maigret's top 100);
  ten guesses × 500 Maigret sites is 5,000 requests. Log each as a run with
  `note="guessed from the name 'Dorian Vell'"`, and don't `case.add_seeds` them: a guess is not something the
  investigator knows.
- **`match.score`:** when `seed.kind == "username"` and the handle isn't one of the subject's `username` seeds,
  the handle adds 0 bits. Reason text:
  > username 'dvell' was guessed from the name, so it isn't counted

  The profile then has to earn its verdict on name, place, photo and links. The two-identifier cap still applies.
- **UI (wizard):** a checkbox under the name field: "Also try likely usernames (dorianvell, dvell, dorian.vell…)".

## 2. New leads: `pivot.suggestions`

Mines the person's profiles for seeds the case doesn't have, strongest first:

| rank | what | example `why` |
|---|---|---|
| 0 | an email in any field or bio | GitHub (very likely) lists the email jane@janedoe.dev |
| 0 | the handle of an account found by email or phone | Gravatar (likely) account is named 'janedoe42' |
| 1 | a `<site>_username` field | GitHub (very likely) names the Twitter account 'janedoe_tw' |
| 1 | a link to a social profile (31 hosts, plus `*.github.io`, `*.substack.com`…) | GitHub (very likely) links to the LinkedIn account https://www.linkedin.com/in/jane-doe-42/ |
| 2 | Maigret's `other_usernames` | GitHub (very likely) lists the other username 'janed' |
| 2 | a website that isn't a social profile | GitHub (very likely) lists the website https://janedoe.dev |
| – | ~~an @mention in the bio~~ | dropped (AN8): it names someone else, never a lead to search |

"The person" follows `search.in_person`: `min_p` (0.55, "likely") or better, minus accounts marked `not him`, plus
those marked `him`. The function leaves out:
- anything already in the case (seed values, URL seeds and their handles)
- links to the profile's own site
- image URLs, `noreply` addresses, and org or intent pages (`/company/…`, `/r/…`)
- bare domains in free text ("node.js")

**Plug in:**
- **`search.build`:** replace `pivots` (other_usernames only) with
  `report["suggestions"] = pivot.suggestions(report)`, called after the dict is assembled (it reads `subject_seeds`
  and `candidates`). Keep `pivots` as `[s["value"] for s in suggestions if s["kind"] == "username"]` until the
  report and CLI stop reading it.
- **`/api/cases/{slug}/person`:** add `leads: report["suggestions"]`. Each lead gets an "Add" button that POSTs
  `{seeds: [value]}` to `/api/cases/{slug}/seeds`. `url` leads become `url` seeds, so `match.score` counts them as
  the subject's known profiles. The UI shows `why` under each lead:
  > New leads from his accounts · janedoe_tw: GitHub (very likely) names the Twitter account 'janedoe_tw' · [Add]

## 3. The account graph and distinct people: `graph`

`graph.build` links every pair of candidates and gives each edge a reason.

**Strong edges** (one owner):

| kind | when | reason |
|---|---|---|
| `link` | A links to B's profile, or names it in a `<site>_username` field (same platform and handle) | GitHub names the Twitter account 'jdoe' / Keybase links to the Twitter account twitter.com/jdoe / GitHub and Twitter link to each other |
| `email` | both list one email | GitHub and Keybase list the same email jane@janedoe.dev |
| `gravatar` | the same Gravatar hash, or A's email hashes (MD5 or SHA-256) to B's Gravatar | Gravatar is tied to jane@janedoe.dev by its Gravatar hash, the email Keybase lists |
| `website` | the same URL, whose address carries either account's handle or name (`janedoe.dev`) | GitHub and Twitter list the same personal website https://janedoe.dev |
| `avatar` | the same profile photo (`similar.matches`, or dHash) | GitHub and Twitter use the same profile photo (similarity 0.96) |

**Weak edges** (namesakes share these, so they never join people):

| kind | reason |
|---|---|
| `name` | GitHub and Instagram use the same display name 'Jane Doe' (namesakes do too) |
| `mention` | GitHub mentions @acme in the bio, the Twitch handle (could be anyone's) |
| `shared site` | GitHub and Instagram both link to https://acme.com (could be an employer or a popular site) |

`graph.people` takes connected components over strong edges only. Groups are sorted by their best account's
probability, so the subject's group comes first. Each group's `reasons` say why its accounts were joined. A lone
account says "no strong link to any other account found".

**Demo (in `test_analysis.py`):** two people both use `jdoe` and both display "Jane Doe". The subject links her
GitHub, Twitter and Keybase, lists janedoe.dev, and has a Gravatar on her email. The namesake reuses one photo on
Instagram and Flickr and lists janedoephoto.com on Flickr and Reddit. Both mention `@acme` and link `acme.com`.
Result:

```
[GitHub, Twitter, Keybase, Gravatar]  0.9   GitHub names the Twitter account 'jdoe'
                                             GitHub and Twitter list the same personal website https://janedoe.dev
                                             GitHub and Twitter use the same profile photo (similarity 0.96)
                                             Keybase links to the Twitter account twitter.com/jdoe
                                             Gravatar is tied to jane@janedoe.dev by its Gravatar hash, the email Keybase lists
[Instagram, Flickr, Reddit]           0.45  Instagram and Flickr use the same profile photo (similarity 0.93)
                                             Flickr and Reddit list the same personal website https://janedoephoto.com
[Twitch]                              0.2   no strong link to any other account found
```

The shared name, the @acme mentions and the acme.com link stay weak edges, so the two people don't merge.

**Plug in:**
- **`search.run`:** after `avatars()`, run the photo check once under the heavy lock and keep the result:
  ```python
  async with HEAVY:
      pairs = await asyncio.to_thread(similar.matches, {c["url"]: case.dir / "evidence" / Path(a["evidence"]).name
                                                         for c in report["candidates"] if (a := stored.get(avatar_url(c["attrs"])))})
  case.set_same_photos(pairs)   # new table same_photos(a, b, score); build() must not load CLIP
  ```
  Also add case photos (keyed `photo:<name>`) to the same `matches()` call. That replaces the dHash check for
  "profile photo is the case photo" at no extra model load.
- **`search.build`:** replace the dHash second pass (`twin`, `faces`) with:
  ```python
  g = graph.build(candidates, case.same_photos())
  ev = graph.evidence(g, {match.norm_url(c["url"]) for c in candidates if in_person(c)})
  for c in candidates:
      if extra := ev.get(c["url"], []) + shot_extra(c):   # shot_extra: today's "profile photo is the case photo"
          rate(c, extra)
  report["people"] = graph.people(graph.build(candidates, case.same_photos()))   # re-built: probabilities changed
  ```
  `evidence` returns `(bits, tag, reason)` triples with tags `link`, `email` or `photo`, so the `/person` summary
  counts them under the existing `SUMMARY` texts. Weights: link 9.2, website 8.2, email/Gravatar 13.1, photo 6.6
  bits. All of them clear `CORROBORATES`, so a linked account escapes the handle-only cap. One pass only, as
  today. New account reasons read:
  > GitHub names the Twitter account 'jdoe'; GitHub is a very likely match
  > GitHub and Twitter use the same profile photo (similarity 0.96); GitHub is a very likely match
- **`/api/cases/{slug}/person`:** add
  `groups: [{accounts, sites, name, verdict, reasons}]` from `report["people"]`.
  - **The person's group(s):** those containing an `in_person` account. Show their `reasons` under the heading
    ("Why these are one person: …").
  - **Namesakes:** other groups with a name or handle in common. Show them as "Other people using 'jdoe'", one
    card per group, not one per account. Each card lists its sites and reasons, plus this line:
    > Not joined to the subject: they share only the handle and the name 'Jane Doe'.

    That line is built from the weak edges crossing to the person's group (`graph.build(...)["edges"]` where
    `not strong`).
  - A "him" decision on a group applies to every account in it (`POST /decisions` per URL). A "not him" on a
    namesake group rules all of its accounts out in one click.

## 4. Same profile photo: `similar`

Two checks, both on the whole image. No face detection and no face recognition.
1. **CLIP ViT-L/14:** cosine of the image embeddings ≥ `CLIP_MIN`. CLIP compares content, so two different
   studio portraits score as high as a re-crop of one. It is the tolerant first pass.
2. **Pixel alignment:** after trimming solid padding, the central 90% of one picture is searched over 12 scales
   (50–100% of the other's width) and every position in the other. The score is normalised cross-correlation at
   128 px of high-passed (σ 3) and locally contrast-normalised (σ 8) images, and must be ≥ `ALIGN_MIN`. Only the
   same photograph lines up edge for edge. A picture under 40 px after trimming never matches: there's too little
   in it to tell.

How the pixel check was arrived at (all on this set):
- **CLIP alone fails.** Two different NASA studio portraits (different astronauts) reach 0.89–0.90, as high as a
  padded or downscaled copy of one picture. Zero false links needs ≥ 0.97, which keeps 8% of same-picture pairs.
- **Plain high-passed NCC:** two ISS photos of Earth's limb lined up on their horizon at 0.90.
- **Contrast normalisation** stopped one strong edge from outvoting the rest: the hardest different pair fell from
  0.90 to 0.77.
- **The size gate** removed the remaining chance matches. Those were a 7:1 panorama shrunk to 128×18 and a logo
  trimmed to 32 px.
- **Rejected:**
  - Block-consistency voting: no better.
  - Searching down to 35% of the width (to catch tight re-crops): different pictures then aligned at 0.89.
  - 96 or 160 px instead of 128, a 60% template instead of 90%: all measured worse.

The pixel check also found seven pairs of Commons files that are one photograph under two names (re-scans and
re-crops), at first labelled "different". I confirmed them by eye; they are now `SAME_PICTURE` real-world
positives. Different photos of one astronaut (Hoshide, Allen, Fisher) stay "different pictures", and the check
keeps them apart.

**Measured** (`scripts/eval_similar.py`, 2026-10-29). The set:
- 180 base pictures: 41 public-organisation GitHub avatars, 59 public-domain NASA portraits, 80 Commons and OSV-5M
  street photos
- six variants of each: 90% crop, off-centre 75% crop, padded, 64 px, JPEG q25, all combined
- 3,780 same-picture pairs and 789,390 different-picture pairs

`ALIGN_MIN` was picked on the even-numbered pictures and measured on the odd ones:

| | precision | recall |
|---|---|---|
| **CLIP ≥ 0.75 + pixel ≥ 0.79, held-out half** | **1.0000** (0 false links in 196,245) | **0.657** (1,241 / 1,890) |
| CLIP alone at its zero-false-link threshold (0.97), held-out half | 1.0000 | 0.080 |
| CLIP + pixel, all pairs | 1.0000 (0 in 789,390) | 0.662: logos 0.72, portraits 0.77, photos 0.55 |
| CLIP + pixel ≥ 0.75 (for comparison) | 0.9993 (2 false links) | 0.759 |

Recall by change, against the original:

| change | recall |
|---|---|
| JPEG q25 | 99% |
| padded | 97% |
| 90% crop | 75% |
| 64 px | 68% |
| off-centre 75% crop | 65% |
| all combined (crop, 128 px, JPEG 40, border) | 33% |

The hardest different pair is two ISS photos of Earth's limb at 0.766. Two different astronauts' studio portraits
never get near the line.

**Real re-uploads (Commons):** 16 of 22 matched (one photo uploaded twice, labelled by eye). The misses:
- tight "3x4" re-crops showing under half the original's width
- two re-scans with different tone and border

dHash put these same pairs 11–36 bits apart; it links ≤ 6.

**Organisations' GitHub vs Bluesky avatars:** 2 of 5 matched.
- Matched: Mozilla, and EFF, the same artwork recoloured.
- Missed: NPR (logo placed smaller inside a grey circle), Signal (re-scaled), GitHub (the Octocat inverted).
- Brand assets reworked per site remain mostly unlinked. That is the price of the precision-first threshold.

CLIP loads from the local cache only (`local_files_only=True`), runs fp16 on MPS, batches 8, and is unloaded
(model freed, `torch.mps.empty_cache()`) before `embed` returns. The pixel check is CPU-only, ~24 ms per pair (16,045 pairs in 376 s), and
runs only on pairs CLIP passed.

**Known limits:**
- A stock picture or team logo used by two different people is "the same photo". Site defaults are filtered by URL
  (`DEFAULT_AVATAR`). The upgrade is to treat a picture seen on many unrelated handles across cases as a default.
- Low-detail scenes with one layout (empty roads, Earth from orbit) are the pixel check's hardest negatives.
- **Not linked:**
  - a re-crop showing under half the other picture's width
  - an inverted logo
  - a thumbnail under 40 px

  They read as "no shared photo", never as a conflict.
- `scan.py` has its own CLIP loader (`_Clip`). Once both are on main, `similar.embed` can share it.

## 5. Face check against a reference photo: `face`

Opt-in, 1:1, nothing kept: the guardrails and their legal reasoning are in
[legal.md](research/legal.md#biometrics-relevant-to-photo-features). `similar.same_photo` stays separate and
whole-image only: a reference photo that literally appears as an avatar is found by `similar`, not by `face`.

**Gate first** (rules F1–F2 in [legal.md](research/legal.md#hunts-rules)): `face.gate(case) -> (allowed, rule)` reads the
case detail `subject_residence` (ISO 3166) against an allow-list (AN2). Only a known ISO 3166-1 code, or `US-` plus a
state, DC or a territory, can pass. An unknown or unrecognised code (`EU`, `XX`, `US-ZZ`) is blocked, and so are IL, TX,
WA, CO and CA (always, decision D5), and the EU/EEA with its outermost regions, the UK (`UK` means GB), Canada and the
Crown dependencies. `face.verify_all` is the only public way to compare faces (AN11). Each decision is audited as `face gate {allowed, residence, rule}`. `enable()` and every
`verify_all()` refuse with `PermissionError("face comparison is blocked for this subject: <rule>")`.
A `US-WA` subject also sets `case.mhmda` (the report words findings as observed activity; `mhmda_basis` records the fraud
basis). Face results are **leads, never evidence**.

```python
face.gate(case) -> (allowed, rule)         # by the subject's residence; audited every time
face.enable(case, basis: str)              # per case, with the investigator's legal basis; audited
face.disable(case)
face.basis(case) -> str | None             # None = off (the default)
face.add_reference(case, path) -> sha256   # the picture, stored as case evidence; several allowed (best of)
face.remove_reference(case, sha)
face.references(case) -> [Path]
face.verify(case, image_path, url=None) -> {result, score, quality, reason, match, why, faces_found, model}
face.verify_all(case, [(url, image_path)]) -> [same]   # many images, one load of each model
face.results(case) -> {url: latest result}             # stored in the case's face_checks table
face.reason(result) -> (bits, "face", why)             # match.score `extra`
face.download()                                        # the models, 261 MB, pinned revisions
```

**Pipeline**, one model at a time, each dropped after use:
1. **YuNet** finds faces, at 640 px and then 320 px for close-ups. Faces smaller than 60% of the largest are people
   in the background.
2. **Quality gate.** Exactly one face, at least 40 px across, detector confidence ≥ 0.85, turned ≤ 45° (from the
   eyes and nose), and sharp enough (Laplacian variance of the aligned face).
3. **CLIP zero-shot gates** on a loose crop, over "a photo of a person / child / baby / a drawing or cartoon / a dog
   or cat or other animal":
   - P(child or baby) ≥ 0.5: not compared
   - P(drawing or animal) ≥ 0.8: not compared

   Logos, scenery and cartoons almost never get this far (no face, or detector confidence under 0.85). The gate
   is for pets and drawings that do.

   **First prompt set, dropped:** it also asked about logos and statues, and flagged 25% of real LFW faces as "not
   a real face", and 76% of sunglasses copies ("a statue or mask").

   **The child gate's recall is unmeasured:** no licensed set of children's photos was used. It errs toward
   stopping: it stops ~5% of LFW's adults. On the 44 freely licensed pet photos, it stopped one real child
   photographed with her dog at P = 0.96.
4. **AuraFace** embeds the face, aligned to the 112 px ArcFace template, for the cosine with each reference photo.
   The best reference wins.

Several faces return "unclear", and no bystander is ever embedded. The reference photo goes through the same
gates. If none is usable, every result is "unclear: no usable reference photo (why)".

**Results:**
- `yes`: the score is ≥ `YES`
- `no`: the score is < `NO`
- `unclear`: in between ("too close to call"), or not compared, with the reason

The reason texts:
> the same face as your reference photo (0.71) · a different face from your reference photo (0.12) ·
> too close to call (0.38) · no face found · 2 faces: can't tell which one is the account's ·
> face too small (31 px) · face turned away (about 60°) · face too blurred (sharpness 12) ·
> not sure it's a face (detector 0.71) · may be a child: not compared ·
> doesn't look like a real face (a drawing, animal or graphic)

**Measured** (provisional; `scripts/eval_face.py`):
- LFW View 2: 6,000 pairs, news photos of public figures.
- The reference photo stays clean; the other photo is "Facebook-ified".
- Clean runs on all ten folds; each of 13 degraded conditions on fold 1 (tuning) and fold 6 (held out).
- These numbers are from the first run: 4,800 pairs that both gates passed. The full re-run with the final gates
  replaces them (`results.json`).
- `YES` = 0.35 (picked at 0.32 on tuning, raised above the one held-out false match at 0.33), `NO` = 0.18.

| held out | true pairs | true match (≥ YES) | false "no" | different pairs | false match |
|---|---|---|---|---|---|
| clean | 694 | 98.7% | 0.3% | 575 | 1 at 0.32 (0 at 0.35) |
| 160 px thumbnail | 133 | 98.5% | 0% | 115 | 0 |
| 96 px thumbnail (most stopped: face too small) | 27 | 96.3% | 0% | 24 | 0 |
| circle crop | 117 | 97.4% | 0% | 97 | 0 |
| JPEG ×3, q30–60 | 122 | 96.7% | 0% | 118 | 0 |
| photo of a screen | 152 | 98.0% | 0.7% | 133 | 0 |
| screenshot of a screenshot | 131 | 98.5% | 0.8% | 125 | 0 |
| filter | 138 | 97.1% | 0% | 129 | 0 |
| low light | 125 | 91.2% | 0% | 103 | 0 |
| mirror selfie | 143 | 98.6% | 0% | 129 | 0 |
| sunglasses | 46 | 84.8% | 0% | 43 | 0 |
| hat | 126 | 96.0% | 0% | 129 | 0 |
| mask | 114 | **43.0%** | **11.4%** | 94 | 0 |
| group photo (3 people) | – | – | – | – | 0: every one "couldn't compare" |

**ROC** (first run):

| | FMR 1% | FMR 0.1% |
|---|---|---|
| Clean | TMR 0.998 | TMR 0.979 |
| Degraded | TMR 0.979 | TMR 0.955 |

**Avatars with no face** got no score, ever:
- logos (41): no face found
- street scenes (80): no face found, or too small
- generated cartoons (40): no face found, or "not sure it's a face" (detector 0.62–0.76)
- pets (44, freely licensed Commons photos): 41 stopped before the gate. Of the 3 that reached it, the two dogs
  were stopped as animals (0.88, 0.84) and the third was a child: not compared.

**"Couldn't compare"** is mostly LFW's crowded news crops: a second face at 60% or more of the subject's size in
about 8% of photos. Then faces too small (96 px thumbnails) and turned faces.

**Worst failures:**
- **Masks:** half the face is gone, so true pairs fall to "unclear" or "no". A masked photo should never count
  against an account; the learning store's quality buckets will show it. A mask detector is the upgrade.
- **The held-out false match (0.33):** two different men in similar news shots. `YES` sits above it.

**Not yet measured:**
- **Cross-age and cross-pose** (CALFW, CPLFW): waiting on Aaron's OK for the 546 MB download.
- **The child gate's recall:** no licensed set of children's photos.
- **Real Facebook compression:** waiting on volunteers' own photos, with consent.

### Plug in

- **Install:** `uv sync --extra face` (OpenCV, 48 MB). Then `face.download()` (YuNet 0.2 MB + AuraFace 261 MB), run
  from a button on the startup screen. Add a startup check `{id: "face", ok, detail}`: OpenCV installed and models
  cached.
- **Wizard: where the subject lives** (`subject_residence`, required before the face step shows): a country list, plus a US
  state. While it's blocked or unknown, the face step shows the rule from `face.gate` and no switch.
- **Wizard: reference photo** (a new optional step after the seeds; off by default):
  - A switch, "Compare faces with a reference photo", which needs a legal basis typed in. Placeholder: "e.g.
    claimant signed the consent form, file 4521". It POSTs `/api/cases/{slug}/face {basis}` → `face.enable`.
    `DELETE /api/cases/{slug}/face` → `face.disable`.
  - Upload: `POST /api/cases/{slug}/reference`, multipart `files[]`, with the same streaming, hashing, HEIC→JPEG
    and SVG rejection as `/media`. It calls `face.add_reference` per file → `{references: [{sha256, url}]}`, and
    returns 409 while face comparison is off. `DELETE /api/cases/{slug}/reference/{sha}` → `face.remove_reference`.
  - `GET /api/cases/{slug}` gains `face: {on, basis, references: [evidence url]}`. The references are ordinary
    evidence files, served by the existing `/evidence/{slug}/{sha}.{ext}` route.
- **`search.run`:** after `avatars()`, if `face.basis(case)` and `face.references(case)`, run under `HEAVY`:
  ```python
  await asyncio.to_thread(face.verify_all, case, [(c["url"], case.dir / a["evidence"]) for c, a in with_avatars])
  ```
  `with_avatars` is the candidates with a stored, non-default avatar. Emit a `log` event: "compared faces on
  12 profile photos". Kept post media can go through the same call, keyed by the post's account URL. On
  `face.FaceUnavailable`, log the message and carry on.
- **`search.build`:**
  ```python
  faces = face.results(case) if face.basis(case) else {}
  # in rate(): extra + ([face.reason(faces[c["url"]])] if c["url"] in faces else [])
  # each candidate: c["face"] = {k: faces[url][k] for k in ("match", "score", "why", "quality")} if url in faces
  report["learning"] = learning.versions()
  ```
- **`/api/cases/{slug}/person`:**
  - each account gains `face: {match, score, why} | null`
  - the top level gains `reference: [evidence url]` and `calibration` (below)
- **"Is it them?" side-by-side:** for each account with a face result, show the reference photo and the account's
  profile photo side by side, with a chip:
  - "Same face · 0.71"
  - "Different face · 0.12"
  - "Couldn't compare: 2 faces"

  Caption, once per screen:
  > Face comparison is one reason among the others; it can't confirm an account on its own.

  Never show the chip as the verdict.
- **Reverse image search and face-search plug-in hits** (data-sources session): every hit image goes through
  `face.verify(case, path, url=hit_url)` *before* it can become a candidate. Its result enters `match.score` only
  as the capped `face` reason, beside whatever else the matcher finds for that account. Label the candidate
  "found by face search" or "found by reverse image search" (its `found_by`). A face-search hit without a
  reference photo, or with face comparison off, is shown as a lead to check, never scored.
- **Matcher:** `face.reason(result)` gives one reason tagged `face`:
  > +3.4 profile photo shows the same face as your reference photo · 0.71

  `match.py` caps it at +4 / −3 bits, and it never counts as the second identifier. If only the handle and a face
  agree, the profile stays at "roughly even chance":
  > …; capped, a face alone isn't a second identifier

## 6. Learning from decisions: `learning`

The local store, what it keeps (no names, URLs, images or embeddings) and why its numbers aren't biometric
identifiers: [legal.md, "The learning store"](research/legal.md#the-learning-store-huntlearningpy).

```python
learning.record(case, candidate, decision, face=None, face_shown=False)  # from POST /decisions
learning.match_scales() -> {tag: multiplier}     # read by match.score; {} = hand-set weights
learning.face_bits(score, quality) -> bits       # read by face.reason; capped +4 / -3
learning.versions() -> {enabled, match: {version, decisions, scales}, face: {version, learned_buckets, decisions}}
learning.status(), learning.set_enabled(on), learning.reset()    # hunt learning [--on|--off|--reset]
```

**What is learned:**
- **Matcher:** one multiplier per evidence type (username, name, place, email, link, photo) on the hand-set
  Fellegi–Sunter weights. It's a weighted logistic regression, logit P(him) = prior + Σ multiplier × bits.
  - The prior sits at 1 for every multiplier (worth about 8 decisions), the result is clipped to 0.25–2, and only
    types seen on 10 or more decided accounts are learned.
  - Nothing is learned until there are 30 "him" and 30 "not him" decisions; "unsure" teaches nothing.
  - `confirmed` (the investigator's own call) and `face` are never learned this way.
  - In the self-check, a name that's right 80% of the time (hand-set as if 99%) learns 0.28, an uninformative
    username 0.65, and a small, always-right place weight goes up.
  - The upgrade, once there are hundreds of decisions, is full per-level m/u estimates (Splink's EM, as
    `match.py`'s `ponytail:` note says).
- **Face:** score → P(same person) as a logistic fit per quality bucket. "Good" means ≥ 80 px, sharp, and turned
  ≤ 25°. It starts from the benchmark calibration (`face.CALIBRATION`) and is shrunk toward it. A bucket is
  learned only from 30 decisions each way.
- **Feedback loop:** a decision made while the face result was on screen may just repeat it. `record` stores
  `face_shown`, and such decisions count half in both fits. The risk remains: if investigators rubber-stamp the
  face chip, the learned face weight drifts toward itself. Compare learned and benchmark curves before trusting a
  big shift.

**Plug in:**
- **`POST /api/cases/{slug}/decisions`:** after `case.decide`, for each decided URL:
  ```python
  learning.record(case, candidate, decision, face=face.results(case).get(url), face_shown=bool(face.basis(case)))
  ```
  `candidate` is the URL's entry in `search.snapshot(case)["candidates"]`, holding the reasons the investigator
  saw. Recording the pattern at decision time keeps the learning store independent of case retention.
- **`hunt learning`** (done in `cli.py`): prints `status()`; `--off`, `--on` and `--reset` are audited in the
  store's own `audit` table.
- **Reproducibility:** `report["learning"] = learning.versions()` in `search.build`. The report session should
  cite it in the methodology section:
  > Match weights: as set by Hunt (version default) | calibrated from 74 of your decisions (m-1a2b3c4d).
  > Face calibration: LFW benchmark (default) | learned from 41 decisions (f-9e8d7c6b). Face model
  > yunet-2023mar+auraface-v1, thresholds YES/NO.
- **UI: where "calibrated from N of your decisions" shows:**
  - in the "Is it them?" footer, beside the verdict summary: "Weights calibrated from 74 of your decisions ·
    Settings". Until there are enough decisions: "Weights as set by Hunt (learns from your decisions after 30
    each way)".
  - on a Settings card, "Learning: on/off · Forget what Hunt learned", showing the `status()` counts
  - in the report's methodology

## 7. Records against what the case knows

Public-record sources search by name, so every namesake comes back. `match.score` now handles a finding found by searching a
name differently:
- **The name barely counts:** +0.1 bits instead of +6.5, with the reason
  > name 'John Smith' matches 'John Smith' (the name searched for, so it barely counts; namesakes share it)
- **The record's own facts decide**, scored against the subject's seeds (typed in the search bar, e.g. `dob:1981-04-12`,
  `age:43`, `employer:Acme Freight`) and the report's `subject_dob` detail, which `search.build` passes as `facts`:

| subject's | record field | agree | disagree |
|---|---|---|---|
| `dob` seed or `subject_dob` | `dob`, `date_of_birth`, `birth_date`, `born`… (`YYYY-MM-DD` or `MM/DD/YYYY`) | exact: +13.2 (`dob`) | another full date: −4.3 |
| `dob` or `age` seed | a birth year, or `age` | within a year: +4.2 | off by 2+ years: −3.2 |
| `employer` seed | `employer`, `company`, `organization`, `work` | +5.9 (`employer`) | not counted: people change jobs |
| `location` / `address` seeds (city/state, prior addresses) | `address`, else `location`/`city`/`state`/`country` | the geocoded place tiers, as for profiles | as for profiles |

A name-only "John Smith" record scores "very unlikely" and joins the namesakes. One whose age fits rises to "likely", and an exact date of
birth gives "almost certain". A wrong birth year sinks it to "almost no chance". The new tags `dob` and `employer`
go into the learning store's patterns, so their weights are re-learned from decisions like the rest.

**Why a record was kept or set aside:** the record's `reasons`, already in the report data. The report session can print,
for each record, its verdict and top reasons ("kept: date of birth 1981-04-12 matches the subject's"; "set aside: 1962
doesn't fit the subject's birth year 1981"). The fixture records in `test_report.py` and `test_e2e.py` now each carry
an employer that the case knows, because a name alone no longer makes them the subject's.

## 8. Family and associates

`graph.associates(posts, candidates, subject, photo_labels, case_key) -> {notice, people}` connects the people the case
already names. It runs on what's stored and searches nothing. `GET /api/cases/{slug}/people` serves it; see
[api.md](api.md).

**Where associates come from**, as observed wording, never a generated relationship (legal.md A6, decision D7(a)):

| from | example | `labels` (observed) | confidence |
|---|---|---|---|
| the subject's own posts (the person's accounts, or posts the investigator added) | "my brother Dan", "mi esposa Ines", "with mom" | "my brother", "mi esposa", "with mom" | 0.9 named, 0.8 unnamed, 0.7 "with mom" |
| post tags | `extra.with`, `extra.tagged`, "— with Rafa Ortiz" | "tagged" | 0.8 |
| a plain caption | "Gym with Rafa Ortiz and Kim Vell" (two-word names; could be a place) | "tagged" | 0.6 |
| the person's bios | "Married to Ines Vell", "Proud dad of 2", "Dad to Leo and Emma" | "Married to", or a child | 0.9 / 0.8 |
| the person's public records | "Vell v. Example Builders LLC", `parties` | "co-party" | 0.9 |
| the investigator's marks on kept photos (`label_photo`; the same label = one person; no face search) | "Dan" in two photos | "marked in a photo" | 1.0 |
| a shared surname with the subject, for someone found by a tag or a photo only | "Kim Vell" | "shares the surname" | 0.3 (a hint) |

There are about 130 English and Spanish relationship words. They're used to find the wording and to merge mentions of one
person, and are never shown as a label. A first name merges into the one full name that fits ("Ines" → "Ines
Vell"). The subject is never their own associate, and posts from accounts that aren't the subject's are ignored.
Entry ids are salted with the case, so they mean nothing outside it (AN9).

**Minimisation** (`legal.md` C4 and C13; compliance audit AN1, AN6):
- **Name and citation only:** an associate is a name, the observed wording and the exact sentence, with its post, bio,
  record or photo reference. Nothing is searched or collected on them. The screen offers "Open as a new case…", which
  starts the wizard with its own purpose field.
- **Possible minors**, in two passes:
  - **Who counts:** a child, son, daughter, grandchild, niece or nephew; boy, girl, toddler, teen, mijo or mija;
    "dad to …" or "mom to …"; or anyone given an age under 18 ("age 9", "(16yo)", "is 15", "16th birthday",
    "5-year-old", "9 años").
  - **First pass:** collects every name tied to a minor, from posts, bios, tags and photo labels. That includes a name
    beside the word ("Leo Vell, my stepson") and a lower-case one ("my daughter emma").
  - **Second pass:** folds every other mention of those names into the minor's entry. The entry is labelled "a child",
    with no name and no wording.
  - **Every quote**, anyone's, has those names replaced with "[name withheld]", case-insensitively.
- **No contact details, addresses or health in quotes:** emails, phone numbers, street addresses, links and health words
  (hospital, surgery, chemo, therapy, pregnancy…, and the Spanish terms) become "[detail withheld]". There are no
  "same address" entries: a record of someone else at the subject's address names a stranger.
- **Pivots skip associates (AN8):** `pivot.suggestions` never suggests a bio @mention, or an email in a sentence that
  names a relationship.

**The screen** ("People around the subject", a tab beside "Is it them?"):
- **Header:** the `notice`.
- **Cards,** most confident first:
  - the name, or "a child", with the observed wording as chips ("my brother", "tagged")
  - and each citation: its quote, with a link to the exhibit
  - no profile links or photos of associates
- **Actions:**
  - "Not relevant" hides a card, audited.
  - "Open as a new case…" is never offered for a child.
- **"Mark people in this photo"** sits on kept photos: a free-text label, posted to `POST /api/cases/{slug}/people/photo`.

**Report sentences** (for `report.py`, a "People around the subject" section). Each is the observed wording with its
citation, never a generated relationship:
> The subject's own posts, bios and public records name 5 people; none of them was searched. [method]
> A post of 2026-06-01 says "Lake day with my brother Dan…". [E-1] Dan was also marked by the investigator in a kept photo.
> The Facebook bio says "Married to Ines Vell". [A-3]
> A post of 2026-05-12 names a child (name withheld). [E-2]
> Vell v. Example Builders LLC names Example Builders LLC as a party. [Rec. 2]

In screening mode, leave the section out. In MHMDA mode, quote as observed, never inferring health.

## 9. The claim against the evidence: leads and timeline

`hunt/leads.py`, pure functions over what the case holds: `timeline(details, posts, hits, candidates)` and
`leads(details, posts, hits, candidates, people)`. They're served by `GET /api/cases/{slug}/timeline` and `/leads`
([api.md](api.md)).

**Restrictions.** The case's `limits` text is split into clauses ("No lifting over 5 kg; no long walks; can't drive
far; not working"). Each clause maps to a restriction and to what would contradict it:

| restriction | the claim says (en/es) | contradicted by |
|---|---|---|
| lifting | lift, carry, levantar, cargar | `lifting` hits; published competition results after the injury (`activity`: OpenPowerlifting meets, with total and place); captions "moving day", "helped … move", "mudanza" |
| walking | walk, stand, hike, caminar | `walks` hits; "hike", "10 km walk", "caminata" |
| running / sport | run, jog, gym, exercise, correr, gimnasio | `sport` hits; competition results (sport); "ran", "5k", "leg day", "workout" |
| bending | bend, kneel, squat, climb, agachar | `activity` hits |
| driving | drive, manejar, conducir | `driving` hits; FMCSA carrier records registered or updated after the injury; "road trip", "drove" |
| travel | travel, fly, viajar | `travel` hits; "flight to", "vacation" |
| working | work, job, employ, duty, trabajar | `other_job` hits; a licence issued or renewed, a business formed or registered, or a carrier record updated after the injury; a court filing after it that names an employer; "first day at the new job", "my shift", "back to work", "nuevo trabajo"; the importer's `life_event`; a co-worker named in a post (associates) |

Without `limits`, the wizard's `look_for` categories become restrictions, marked `stated: false` ("The case asks about
lifting or carrying").

**What counts as a lead:**
- dated after the injury
- not marked "not relevant"
- a hit that doesn't show someone else (`who: "other"`)
- a record only from the person (search.in_person), never a namesake's

**Confidence:**
- scan hits: the scan's `p`, × 0.6 while who it shows isn't confirmed, × 0.8 until the investigator keeps it
- the subject's own captions: 0.7
- a published competition result: 0.8
- a licence or business event: 0.7 (a renewal 0.6)
- a carrier record: 0.5
- a co-worker named in a post, or a court filing naming an employer: 0.5

One lead per piece of evidence per restriction, ranked by confidence. Each lead reads as facts only (report-format.md
"Wording"):
> **Claim:** No lifting over 5 kg. **Evidence:** A photo posted on 2026-04-02 (32 days after the injury) appears to show
> carrying a couch (scan: likely). [E-2]
> **Claim:** No lifting over 5 kg. **Evidence:** A post on 2026-04-18 (48 days after the injury) has the caption "Carried
> the sofa down three flights" (scan: likely). [E-9]
> **Claim:** Not working. **Evidence:** Texas TDLR licence (Electrician) issued on 2026-04-15 (45 days after the injury).
> [A-7]

Never "fraud", "lied", "faked" or "exaggerated": the self-check enforces it.

**Timeline:**
- The injury date is one event.
- Each post appears with the categories of its live scan hits.
- The person's public records add their dated fields (issued, renewed, registered, formed, filed, carrier updated).
- Each competition result in `attrs.meets` is its own event: "OpenPowerlifting: competed in Spring Open (deadlift
  only), total 182.5 kg, place 1".
- Life events stated in captions or by the importer are listed separately ("Stated in a post: 'first day at the new
  job'").
- `after_injury` lets the screen shade everything after the line.

**The screen** ("Claim vs evidence", the first tab once a scan has run):
- **Left:** the restrictions as cards, each with its claim text and lead count.
  - A restriction with 0 leads reads "Nothing found that contradicts this", so the absence is recorded too.
  - Clicking a card filters the leads.
- **Centre: the leads list,** each lead shown as
  - "Claim: … / Evidence: …"
  - a thumbnail of the cited post or record
  - the date and days after the injury
  - confidence in words (≥ 0.7 strong, 0.5–0.7 moderate, below 0.5 weak)
  - **Actions:** Keep (sets the hit's status to kept, which raises its confidence), Not relevant (hides it,
    audited), Open evidence.
- **Below: the timeline,** a horizontal strip with a vertical line at the injury date.
  - Posts are dots coloured by hit category, records are squares, stated life events are flags.
  - Hovering shows the event; clicking opens its exhibit.

**Report section** ("Claim and evidence", after Findings; for `report.py`, every sentence cited):
> The claim states: no lifting over 5 kg; no long walks; can't drive far; not working. [case details]
> Lifting: a photo posted on 2 April 2026, 32 days after the injury, appears to show carrying a couch. [E-2] A post the
> same day says "Moving day." [E-2]
> Working: a Texas electrician's licence was issued on 15 April 2026, 45 days after the injury. [A-7]
> Walking: nothing found after the injury that bears on this. [method]

Only leads the investigator kept, or put in the report, go in it, worded exactly as `shows`. In MHMDA mode, keep
`shows` to observed activity: never a word about physical condition.

## Not yet

- **Face thresholds are provisional.**
  - `YES` 0.35 and `NO` 0.18 come from the first eval run, which had the early CLIP gate.
  - The full re-run with the final gates was paused partway, at Aaron's request: the process is stopped, not killed.
  - To finish: `kill -CONT` that process, or run `uv run --extra face python scripts/eval_face.py --fresh`, then set the
    printed values in `face.py`.
- **Not measured:**
  - cross-age and cross-pose (CALFW, CPLFW: 546 MB, waiting for Aaron's OK)
  - the child gate's recall (no licensed set of children's photos)
  - real Facebook compression (volunteers' own photos, with consent)
- **Not wired (main session):**
  - the face, reference and learning API routes and the startup check
  - `search.run` calling `face.verify_all`
  - `search.build` adding `face.reason` to `extra` and `report["learning"]`
  - `POST /decisions` calling `learning.record`
  - the wizard fields and the side-by-side on "Is it them?"

  Everything above specifies them; nothing is half-wired. The case facts are wired: `search.build` passes them, and the
  details route accepts `subject_residence` and `mhmda_basis`.
- **Report wording:** MHMDA mode (observed activity, not physical condition) and "kept or set aside because…" for records
  belong to the report session. `case.mhmda` and each record's `reasons` are ready for it.
- **Associates:**
  - Facebook's parser reads "is with Mara Quill" out of post headers but doesn't keep the names. Storing them as
    `post_extra.with` (facebook session) lets `associates` cite them as tags.
  - Comments aren't stored, only counted, so "tagged or named in comments" waits on that.
  - The "People around the subject" screen and its report section are for the app-screens and report sessions.
    The API is wired.
- **Leads:**
  - Records and captions can't show a weight, so "over 5 kg" only matters to the investigator looking at a lifting
    lead.
  - Leads from records count only the person's records.
  - The "Claim vs evidence" screen and report section are for the app-screens and report sessions. The API is wired.
- **Name commonness:** a searched name always counts +0.1, whatever the name. A name-frequency table would let a rare name
  count for more.
