# What GeoGuessr pros and OSINT geolocators know, and what transfers to ordinary photos

_Research date: 2026-10-29. All summaries are in our own words. Sources are linked inline and listed at the end._

## Headline

**Transfers to a phone photo:**
- **What the text says.**
  - Script, rare letters, language, web domains and phone codes on shopfronts.
  - This is the strongest clue a pro uses, and OCR reads it for us.
- **Driving side**, when moving traffic is visible.
- **Standardised road furniture:**
  - sign shape and colour
  - plate colour and band
  - line colours

  These are weaker because a photo seldom frames them, and phone white balance blurs yellow and white.
- **Architecture and vegetation** help at biome or region level. They need expertise, so they stay with the vision model and the investigator.

**Does not transfer:** anything about Google's capture process, which is a large share of what makes pros fast.
- camera generation
- the Google car
- blur patterns
- coverage and season
- which places a GeoGuessr map contains

In Learnable Meta's beginner "Basics" world map, roughly one clue in five is a Google-car tell ([map](https://learnablemeta.com/maps/66fda352ee1c8ee4735e1aa8)). Pros' priors are also shaped by where Street View exists. Tessera must not inherit that: a photo can come from anywhere.

**What to copy from OSINT practice:**
- Go wide to narrow.
- Trust fixed features over movable ones.
- Let one hard contradiction reject a candidate.
- Call a place **confirmed** only when a human has matched several fixed features against dated reference imagery.
- Treat AI output, GeoCLIP included, as a lead.

## How GeoGuessr pros work

1. **Gut read first, within a few seconds.** Pros take in the road surface, line colours, vegetation and light. Rainbolt attributes this to thousands of rounds, and says overthinking makes him worse ([Vice interview](https://www.vice.com/en/article/geoguessr-rainbolt-interview/); [WIRED "Every Trick" transcript](https://rosetta.to/u/wired/every-trick-a-pro-geoguessr-player-uses-to-win-ft-rainbolt-wired)).
2. **Cheap filters that remove most of the world.** These are driving side and script or language ([Plonk It beginner's guide](https://plonkit.net/beginners-guide)). Pros keep the sun for hard rounds, and it misleads between the tropics. [GeoTips](https://geotips.net) lists camera and car tells before these filters; that is the part we drop.
3. **Road furniture to pick the country.** Pros read lines, bollards, poles, sign design and plates.
   - Line colour rarely decides a country alone but is consistent in combination.
   - A single distinctive bollard or pole can decide it ([Plonk It](https://plonkit.net/beginners-guide), [WIRED](https://rosetta.to/u/wired/every-trick-a-pro-geoguessr-player-uses-to-win-ft-rainbolt-wired)).
4. **Country to region.** Pros use:
   - regional scripts (India)
   - road-number schemes (Norway's first digit is regional; [Plonk It Norway](https://plonkit.net/norway))
   - plant ranges
   - pole plates (Japan)
   - area codes and regional plates
5. **Region to town.** Directional signs, road numbers and street names, then matching road angles, coastline and terrain against the map.

Plonk It warns about **"fake metas"**: tells that spread through the community but hold only sometimes. That is the right way to think about weak hints, and why ours carry less than one bit.

We found no first-person method write-ups from Consus, Blinky or zi8gzag, only match reports. Claims about how they play specifically are unverified.

## How OSINT geolocators work

**The workflow:**
1. **Collect** everything in the image, plus provenance: is this the original upload? ([First Draft photo guide](https://firstdraftnews.org/wp-content/uploads/2017/03/FDN_verificationguide_photos.pdf)).
2. **Rank clues by how fixed they are.** Buildings, road layout, terrain and shop signs come before cars and plates ([Exposing the Invisible](https://kit.exposingtheinvisible.org/en/geolocation.html)).
3. **Country and region** from signs, driving side, street furniture and architecture ([GeoHints](https://geohints.com), listed in [Bellingcat's toolkit](https://bellingcat.gitbook.io/toolkit/more/all-tools/geohints)). First Draft treats this level as partial certainty only.
4. **Town.** Look for co-occurring mapped features:
   - [Bellingcat's OpenStreetMap search](https://www.bellingcat.com/resources/how-tos/2023/05/08/finding-geolocation-leads-with-bellingcats-openstreetmap-search-tool/)
   - [Overpass Turbo](https://bellingcat.gitbook.io/toolkit/more/all-tools/overpass-turbo) and its `around` filter ([OSM wiki](https://wiki.openstreetmap.org/wiki/Overpass_API/Language_Guide))

   Sun direction can exclude parts of a town.
5. **Exact spot.** Compare against satellite imagery, Street View, Mapillary or a 3D view. Sketch the layout seen in the image and rotate it against the map ([Bellingcat beginner's guide, 2014](https://www.bellingcat.com/resources/how-tos/2014/07/09/a-beginners-guide-to-geolocation/)).
6. **No match?** Restart from a different clue.

**When a place counts as confirmed:**
- **Several independent, fixed features line up** in the same relative positions. One look-alike is not enough. Strick's 3D-view walkthrough checks a pole, road dividers, trees and a ridgeline together ([Bellingcat](https://www.bellingcat.com/resources/how-tos/2019/03/05/how-to-use-google-earths-three-dimensional-view-feat-syria-yemen-sudan/)).
- **One clear contradiction rejects a candidate.**
- **Reference imagery needs dating too.** Street View may predate the scene, and reference geotags can be wrong ([Bellingcat, Searching the Earth](https://www.bellingcat.com/resources/2015/07/25/searching-the-earth-essential-geolocation-tools-for-verification/)).
- **Publish the breakdown so others can audit it.** [GeoConfirmed](https://geoconfirmed.org/) collects, verifies, then publishes coordinates with sources and an annotated breakdown. The [Berkeley Protocol](https://humanrights.berkeley.edu/wp-content/uploads/archive/2024/02/Berkeley-Protocol.pdf) recommends peer review.
- **AI is a lead, not a finding.** In Bellingcat's October 2026 test, GeoCLIP beat only one of the language models. Even the best models were sometimes confidently wrong and were weakest at the exact spot ([Bellingcat](https://www.bellingcat.com/resources/2026/10/22/can-llms-supercharge-geolocations-our-tests-show-big-improvements-but-humans-remain-key/)).

### Techniques and what Tessera can automate

| Technique | Output | Local automation? |
|---|---|---|
| EXIF | A point and a time, both claims | Yes, already in `photo.py`. Usually stripped, and editable ([toolkit](https://bellingcat.gitbook.io/toolkit/more/all-tools/exiftool)). |
| Country clues (text, driving side, furniture) | Shortlist of countries | Yes: OCR + `clues.py` + vision model, with a human check |
| GeoCLIP / vision model | Candidate points | Yes, but each is a lead only |
| Feature co-occurrence (Overpass / OSM search) | Candidate coordinates | Possible against a local OSM extract. Choosing the features is a human or vision-model step, and OSM coverage is uneven |
| Sun azimuth ([SunCalc method](https://www.bellingcat.com/resources/2020/12/03/using-the-sun-and-the-shadows-for-geolocation/)) | Rules out orientations or areas | The maths is automatable; reading the shadow direction is human. Needs a trusted capture time |
| Shadow length ([ShadowFinder](https://github.com/bellingcat/ShadowFinder), MIT) | A worldwide band | `pip install shadowfinder`. Needs a measured ratio and a trusted time ([Bellingcat 2024](https://www.bellingcat.com/resources/2024/08/22/shadow-geolocate-geolocation-locate-image-tool-open-source-bellingcat-measure)) |
| Skyline matching ([PeakVisor](https://www.bellingcat.com/resources/2023/07/13/more-than-mountaineering-using-peakvisor-for-geolocation)) | Confirms or rejects one candidate | Human step |
| Reverse image search ([guide](https://www.bellingcat.com/resources/how-tos/2019/12/26/guide-to-using-reverse-image-search-for-investigations/)) | Earlier copies, sometimes a named place | Human step, and it sends the image off-machine |
| Satellite / Street View / [Mapillary](https://bellingcat.gitbook.io/toolkit/more/all-tools/mapillary) | The exact spot | Human step |

## Clue by clue: does it hold in an ordinary photo?

| Clue | In a phone photo | In `clues.py`? |
|---|---|---|
| **Script** | Yes, and the strongest. Watch for tourist signage and imported brands | Yes, 4.2 bits. 33 scripts |
| **Rare letters** (ő, ł, ř, ß, þ, ї…) | Yes; this is how pros split languages that share a script ([Plonk It Norway](https://plonkit.net/norway) on Æ/Ø/Å) | Yes, 3.3 bits. Common accents (é, ä, ü, ç, ë) are too widely shared |
| **Simplified vs traditional Chinese** | Yes | Yes, 3.0 bits. Character sets avoid modern Japanese forms |
| **Language** | Yes | From the vision model's language field, 2.3 bits. English is ignored |
| **Domains, phone codes** | Yes, readable by OCR. `.co`, `.io`, `.tv` and similar are global brands, not places ([GeoHints domains](https://geohints.com/meta/domains), [phone numbers](https://geohints.com/meta/phoneNumbers)) | Yes, 4.0 bits. Vanity domains are ignored |
| **Street and sign words** (rue, calle, ulica, utca, -straße, -gatan, jalan, çıkış…) | Yes. Street-type words and exit/entrance/open/closed words are core pro vocabulary ([Plonk It](https://plonkit.net/beginners-guide) country pages) | Yes, 2.3 bits per language. Case and missing accents are tolerated. English look-alikes (via, gate, plaza) are left out |
| **Currency signs** (₩ ₹ ₽ ฿ ₫ ¥ € £, R$, HK$, Rp…) | Yes. Prices on menus, shopfronts and markets are among the most common text in holiday and food photos ([Wikipedia](https://en.wikipedia.org/wiki/Currency_symbol)). € covers 21 eurozone members, Bulgaria since 2026-01-01, plus six non-EU users ([Eurozone](https://en.wikipedia.org/wiki/Eurozone)) | Yes, 3.8 bits. A bare `$` is too widely shared |
| **Postcodes** | Yes where the format is distinctive: UK, Canada, Irish Eircode, Brazil's CEP, Japan's 〒 mark. Most countries' 4–6-digit codes look like any number | Yes, 3.8 bits, those five formats only |
| **mph** | Yes on signs that print the unit. Only the US, the UK and about 30 territories and small states use it ([Wikipedia](https://en.wikipedia.org/wiki/Miles_per_hour)) | Yes, 3.8 bits. Liberia is left out (only occasional) |
| **Driving side** | Partly. Needs traffic in frame. Mirrored selfies flip it. Some left-driving islands (Bahamas, Caymans) run mostly left-hand-drive cars, so judge by traffic flow, not the steering wheel ([Wikipedia](https://en.wikipedia.org/wiki/Left-_and_right-hand_traffic), [GeoHints](https://geohints.com/meta/drivingSide)) | Yes, ±2 bits |
| **Line colours** | Partly. The road must be in frame. White balance and sodium lighting confuse yellow with white. Europe uses yellow for roadworks ([GeoHints lines](https://geohints.com/meta/lines), [Wikipedia](https://en.wikipedia.org/wiki/Road_surface_marking)) | Weak, 0.8 bits. Only countries where it is the norm |
| **Warning-sign shape** | Yes where present. Yellow diamond vs red triangle is standardised ([Wikipedia](https://en.wikipedia.org/wiki/Warning_sign), [MUTCD comparison](https://en.wikipedia.org/wiki/Comparison_of_MUTCD-influenced_traffic_signs)) | Weak, 0.8 bits |
| **Plates** | Partly. Often visible, but foreign and rental cars add noise ([GeoHints plates](https://geohints.com/meta/licensePlates), [European plates](https://en.wikipedia.org/wiki/Vehicle_registration_plates_of_Europe)) | Weak: blue band, yellow plates |
| **Bollards, utility poles** | Partly. Real and distinctive, but small and often out of frame ([GeoHints bollards](https://geohints.com/meta/bollards)) | No. The tables are large, and a 4-billion-parameter vision model's description of a bollard isn't reliable enough to key on |
| **Chevrons** | Rarely in frame (curves only; [GeoHints](https://geohints.com/meta/signs/chevrons)) | No |
| **Architecture** | Yes in towns; modern buildings look alike everywhere | No. Left to the vision model's own country guess |
| **Vegetation, soil** | Partly: biome-level. Filters change colours | No. Same reason |
| **Sun, hemisphere** | Rarely usable: needs heading and time, which photos lack. Fails in the tropics | No. Shadow tools are a separate, human-assisted step |

## Street-View-only meta (left out entirely)

- **Camera:** generation (Gen 1–4, budget and low-mounted cameras), tint and resolution.
- **Google car:** colour, roof rack, snorkel, antenna, visible car parts, follow cars.
- **Blur:** car-blur shape and stitching seams.
- **Coverage:** which roads have imagery, capture season and year, trekker vs car, official vs user-uploaded.
- **Map composition:** which spots a GeoGuessr map contains.

Sources: [GeoTips](https://geotips.net/europe/), [Learnable Meta](https://learnablemeta.com/about), [Plonk It](https://plonkit.net/beginners-guide).

All of this describes Google's publishing process, not the place. The only real-world counterpart is date or season, and that comes from EXIF as its own signal.

## Pitfalls specific to social-media photos

- **EXIF.** It is stripped on most platforms, and whatever survives can be edited. Treat it as a claim ([First Draft](https://firstdraftnews.org/wp-content/uploads/2017/03/FDN_verificationguide_photos.pdf)).
- **Mirrored images.** These flip text, driving side and sun azimuth. Bellingcat suggests searching a flipped copy ([guide](https://www.bellingcat.com/resources/how-tos/2019/12/26/guide-to-using-reverse-image-search-for-investigations/)). That phones save front-camera shots mirrored is a device setting, documented only in forums. **Unverified, but cheap to guard against.**
- **Reposts and false captions.** Old images get relabelled. Test the claimed place, don't start from it ([Bellingcat 2023](https://www.bellingcat.com/news/2023/10/26/separating-fact-from-fiction-on-social-media-in-times-of-conflict/), [Exposing the Invisible](https://kit.exposingtheinvisible.org/en/geolocation.html)).
- **Crops, filters, low resolution.** These weaken reverse search, and filters make colour clues (soil, vegetation, line colour) unreliable.
- **Upload time is not capture time.** That breaks sun methods unless EXIF time survives and is believed.

## How Tessera uses this

**In `tessera/clues.py`:** `country_evidence(obs, ocr_text)` turns OCR text and the vision model's observation dict into per-country Fellegi-Sunter bits, which `photo.fuse()` adds to each hypothesis.
- **Strong clues, 3–4 bits:** script, rare letters, Chinese character forms, domains, phone codes, currency signs, distinctive postcodes, "mph".
- **Invented scripts are filtered out.**
  - **The finding.** Measured on the 58 geotagged Commons photos in `~/Tessera/cache/geo-eval/`, using OCR text only. Apple Vision's automatic language detection invents short Thai, Arabic and Cyrillic lines from texture or scripts it can't read:
    - Thai on photos from Poland and Sri Lanka
    - Arabic on photos from Peru and Chile
    - Cyrillic look-alikes on the Sri Lanka photo

    These lines have the same 0.3 confidence as some real text, so the threshold can't separate them.
  - **The rule.** Alphabetic scripts need a line of 8+ letters, 3+ of which don't look Latin. Han, kana and Hangul keep their per-character rules.
  - **Before the rule:** 8 photos produced clues; 5 were wrong.
  - **After:** 3 produced clues (Lyon "RUE", Nepal's Devanagari, Osaka's station sign), and all 3 were right. The cost: one real short Arabic word on the Egypt photo no longer counts.
- **OCR junk letters are filtered out.** Apple Vision's default Latin-only OCR turns kanji into strings like "İF E" or "îEĚV^". So a rare letter only counts inside a word-shaped token: 3+ letters, all lower, ALL UPPER or Title case.
- **Driving side, ±2 bits.**
- **Weak hints, under 1 bit**, drawn only from the countries sources call the norm. Left out on purpose:
  - **Yellow centre lines** that only mean no-passing (jp, nz, ar, uy), snow (cl, ro), alpine roads (au) or roadworks (continental Europe).
  - **Yellow plates** found only on taxis or commercial vehicles (dk, hu, th, in, se, gr, lv, lt), and Japan's kei cars.
  - **Mercosur plates.** Their blue band runs across the top, not down the side.
- **Vision-model input is discounted:**
  - Text the vision model transcribes but OCR missed gets half weight.
  - Its own country guesses get 2, 1 and 0.6 bits, because they are built from the same clues.

**For `photo.py` and later milestones** (suggestions, not built here):
1. **Mirror check first.** OCR the flipped image too. If it reads better, the photo is mirrored, and the driving side and any sun reading must be flipped.
2. **Confidence tiers in the report:**
   - region-consistent (clues and GeoCLIP agree)
   - candidate (a point from feature co-occurrence or a shadow band)
   - confirmed (a human matched two or more fixed features against dated imagery, with no contradiction)

   Never call AI output alone confirmed.
3. **Local next steps:**
   - [ShadowFinder](https://github.com/bellingcat/ShadowFinder), when EXIF time is trusted.
   - Overpass-style co-occurrence over a local OSM extract, for "petrol station next to a church" questions.
4. **Investigator-triggered only:** reverse image search, Street View, PeakVisor, satellite comparison. They send the image or coordinates off-machine.
5. **Log every step**, as the [Berkeley Protocol](https://humanrights.berkeley.edu/wp-content/uploads/archive/2024/02/Berkeley-Protocol.pdf) asks: original hash, working copy, tool, version, inputs and outputs. Its warning about bias in deep-learning tools applies to GeoCLIP and the vision model.

## Sources

**GeoGuessr community:**
- [Plonk It beginner's guide](https://plonkit.net/beginners-guide), plus country pages, e.g. [Norway](https://plonkit.net/norway), [Ireland](https://plonkit.net/ireland), [South Africa](https://plonkit.net/south-africa), [Japan](https://plonkit.net/japan)
- GeoHints: [lines](https://geohints.com/meta/lines), [plates](https://geohints.com/meta/licensePlates), [bollards](https://geohints.com/meta/bollards), [driving side](https://geohints.com/meta/drivingSide), [domains](https://geohints.com/meta/domains), [phone numbers](https://geohints.com/meta/phoneNumbers), [chevrons](https://geohints.com/meta/signs/chevrons)
- [GeoTips](https://geotips.net), [GeoTips Europe](https://geotips.net/europe/)
- [Learnable Meta "Basics" map](https://learnablemeta.com/maps/66fda352ee1c8ee4735e1aa8), [About](https://learnablemeta.com/about)
- Rainbolt: [Vice interview](https://www.vice.com/en/article/geoguessr-rainbolt-interview/), [WIRED "Every Trick" transcript](https://rosetta.to/u/wired/every-trick-a-pro-geoguessr-player-uses-to-win-ft-rainbolt-wired)

**Reference:**
- Wikipedia: [Left- and right-hand traffic](https://en.wikipedia.org/wiki/Left-_and_right-hand_traffic), [Road surface marking](https://en.wikipedia.org/wiki/Road_surface_marking), [Yellow line](https://en.wikipedia.org/wiki/Yellow_line_(road_marking)), [Warning sign](https://en.wikipedia.org/wiki/Warning_sign), [MUTCD comparison](https://en.wikipedia.org/wiki/Comparison_of_MUTCD-influenced_traffic_signs), [Vehicle registration plates of Europe](https://en.wikipedia.org/wiki/Vehicle_registration_plates_of_Europe), [Vehicle registration plates of Israel](https://en.wikipedia.org/wiki/Vehicle_registration_plates_of_Israel)
- Wikipedia: [Currency symbol](https://en.wikipedia.org/wiki/Currency_symbol), [Eurozone](https://en.wikipedia.org/wiki/Eurozone), [Miles per hour](https://en.wikipedia.org/wiki/Miles_per_hour), [Postcodes in the United Kingdom](https://en.wikipedia.org/wiki/Postcodes_in_the_United_Kingdom), [Postal codes in Canada](https://en.wikipedia.org/wiki/Postal_codes_in_Canada), [Eircode](https://en.wikipedia.org/wiki/Eircode), [Postal codes in Brazil](https://en.wikipedia.org/wiki/Postal_codes_in_Brazil), [Postal codes in Japan](https://en.wikipedia.org/wiki/Postal_codes_in_Japan)
- libphonenumber metadata (calling code → regions), via the `phonenumbers` package

**OSINT tradecraft:**
- Bellingcat: [beginner's guide (2014)](https://www.bellingcat.com/resources/how-tos/2014/07/09/a-beginners-guide-to-geolocation/), [Searching the Earth (2015)](https://www.bellingcat.com/resources/2015/07/25/searching-the-earth-essential-geolocation-tools-for-verification/), [Google Earth 3D (Strick, 2019)](https://www.bellingcat.com/resources/how-tos/2019/03/05/how-to-use-google-earths-three-dimensional-view-feat-syria-yemen-sudan/), [reverse image search (2019)](https://www.bellingcat.com/resources/how-tos/2019/12/26/guide-to-using-reverse-image-search-for-investigations/), [sun and shadows (2020)](https://www.bellingcat.com/resources/2020/12/03/using-the-sun-and-the-shadows-for-geolocation/), [shadow chronolocation (2021)](https://www.bellingcat.com/resources/2021/05/18/unsure-when-a-video-or-photo-was-taken-how-to-tell-by-measuring-the-length-of-shadows/), [OSM search (2023)](https://www.bellingcat.com/resources/how-tos/2023/05/08/finding-geolocation-leads-with-bellingcats-openstreetmap-search-tool/), [PeakVisor (2023)](https://www.bellingcat.com/resources/2023/07/13/more-than-mountaineering-using-peakvisor-for-geolocation), [social media in conflict (2023)](https://www.bellingcat.com/news/2023/10/26/separating-fact-from-fiction-on-social-media-in-times-of-conflict/), [ShadowFinder (2024)](https://www.bellingcat.com/resources/2024/08/22/shadow-geolocate-geolocation-locate-image-tool-open-source-bellingcat-measure), [LLM geolocation test (2026)](https://www.bellingcat.com/resources/2026/10/22/can-llms-supercharge-geolocations-our-tests-show-big-improvements-but-humans-remain-key/)
- Bellingcat toolkit: [GeoHints](https://bellingcat.gitbook.io/toolkit/more/all-tools/geohints), [Overpass Turbo](https://bellingcat.gitbook.io/toolkit/more/all-tools/overpass-turbo), [ExifTool](https://bellingcat.gitbook.io/toolkit/more/all-tools/exiftool), [Mapillary](https://bellingcat.gitbook.io/toolkit/more/all-tools/mapillary)
- [GeoConfirmed](https://geoconfirmed.org/): homepage only; its case pages render client-side
- [Exposing the Invisible: geolocation](https://kit.exposingtheinvisible.org/en/geolocation.html)
- [First Draft photo verification guide](https://firstdraftnews.org/wp-content/uploads/2017/03/FDN_verificationguide_photos.pdf)
- [Berkeley Protocol on Digital Open Source Investigations](https://humanrights.berkeley.edu/wp-content/uploads/archive/2024/02/Berkeley-Protocol.pdf)
- [Reuters Institute on Bellingcat's evidence practice](https://reutersinstitute.politics.ox.ac.uk/news/how-bellingcat-collects-verifies-and-archives-digital-evidence-war-crimes-ukraine)
- [OSM wiki: Overpass language guide](https://wiki.openstreetmap.org/wiki/Overpass_API/Language_Guide)

**Not verified:** Benjamin Strick's GIJN tips page (returned 403); first-person method notes from Consus, Blinky and zi8gzag (none found).
