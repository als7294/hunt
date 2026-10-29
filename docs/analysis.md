# Identity analysis: pivots, the account graph and profile-photo matching

Today Hunt ranks each found profile on its own (`match.score`). Three new modules, all pure functions except
CLIP loading, add what practitioners do by hand (see [pain points](research/pain-points.md), #1):

| Module | Does | Network | Model |
|---|---|---|---|
| `hunt/pivot.py` | guesses handles from a name; mines new seeds from the person's profiles | none | none |
| `hunt/graph.py` | links accounts to each other with reasons; splits them into distinct people | none | none |
| `hunt/similar.py` | decides whether two profile photos are the same picture | none | CLIP ViT-L/14, local cache |

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
| 3 | an @mention in the bio | GitHub (very likely) mentions @janed_codes in the bio |

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
