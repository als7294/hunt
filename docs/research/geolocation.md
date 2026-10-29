# Local image geolocation and on-device ML

_Research date: 2026-10-29. **Licensing caveat:** investigators running paid background checks are commercial users even though Tessera is free, so non-commercial weights (CC-BY-NC, "research only") are out._

## Dedicated geolocation models

Accuracy figures are Im2GPS3k at 1 km / 25 km / 200 km / 750 km / 2500 km (street / city / region / country / continent).

| Model | Licence (code / weights) | Im2GPS3k | YFCC4k 1/25 km | Local? |
|---|---|---|---|---|
| **GeoCLIP** (NeurIPS 2023) | MIT; `pip install geoclip` 1.3.0 (2026-10-25) | 14.1 / 34.5 / 50.7 / 69.7 / 83.8 | 9.6 / 19.3 | **Yes.** PyTorch, CLIP ViT-L/14 + 100k GPS gallery, ~2 GB (est.). MPS expected to work (**untested**); ONNX port exists. |
| GeoRanker (NeurIPS 2025) | Apache-2.0; LoRA on Qwen2-VL-7B | **18.8 / 45.0 / 61.5 / 76.3 / 89.3** | **32.9 / 43.5** | Best open option; NVIDIA, phase 2 |
| G3 (NeurIPS 2024) | Apache-2.0; checkpoint released | 16.7 / 40.9 / 55.6 / 71.2 / 84.7 | 24.0 / 35.9 | CUDA-oriented |
| OSV-5M baseline | MIT | OSV-5M country 68.0% | n/a | Yes; street-view-trained, not social photos |
| Img2Loc (SIGIR 2024) | MIT (mirror) | 15.3 / 39.8 / 53.6 / 69.7 / 82.8 | 19.8 / 30.7 | Needs GPT-4V unless swapped |
| StreetCLIP | **CC-BY-NC-4.0 weights** | zero-shot classifier | n/a | **Excluded** (non-commercial) |
| PIGEON / PIGEOTTO | **Weights withheld** (ethics) | 11.3 / 36.7 / 53.8 / 72.4 / 85.3 | 10.4 / 23.7 | No |
| Pinpoint (2026 preprint) | **Weights withheld** | 20.5 / 47.4 / 63.5 / 79.0 / 90.2 | 33.0 / 44.4 | No; shows retrieve-and-rerank is state of the art |
| REVERSE (2026) | Release status unchecked | 22.5% @1km, 48.3% @25km | n/a | Qwen3-VL-4B agent; watch |
| NAVIG (2025) | Licence unchecked | 14% lower median error vs prior best | n/a | Worth reading |

**Caveats:**
- These benchmarks are Flickr/tourist-heavy and may overlap with training data.
- Expect much worse results on indoor selfies, which are typical social media content.
- Withheld weights (PIGEON, Pinpoint) signal real dual-use risk.

## Local vision-language models (VLMs)

- **Zero-shot country accuracy** ([arXiv 2604.16248](https://arxiv.org/html/2604.16248v1)):

  | Model | GeoGuessr-50k | OSV5M |
  |---|---|---|
  | Qwen3-VL-4B | 74.8% | 45.5% |
  | Qwen3-VL-2B | 73.9% | 46.5% |
  | Qwen3-VL-8B | 67.3% | 41.8% |
  | InternVL2.5-8B | 65.0% | 36.3% |

  Bigger isn't always better.
- **[GeoArena](https://arxiv.org/html/2509.04334v2)** (pairwise ranking): best open models are Qwen2.5-VL-72B (#3), Gemma-3-12B (#4), Gemma-3-27B (#5), Qwen2.5-VL-32B (#8).
- **Weakness:** GeoRC (ACL 2026) found that open Llama/Qwen models "catastrophically fail" at expert-quality reasoning chains and hallucinate clues ([paper](https://aclanthology.org/2026.acl-long.1883.pdf)). **VLM clues are hypotheses, not evidence.**
- **Current local candidates:**
  - Qwen3-VL (2B–32B, Apache-2.0; Ollama and MLX)
  - Gemma 4 (E2B–31B, Apache-2.0)
  - Skip Llama 3.2 Vision in Ollama (reported broken)
  - Qwen 3.5/3.6 vision is reportedly not working in Ollama as of Jul 2026 (**unverified**)
- **VLM + retrieval beats either alone** (all with GPT-4V):
  - Im2GPS3k @1km: GeoCLIP 14.1 → G3 16.7 → GeoRanker 18.8
  - YFCC4k @1km: 9.6 → 24.0 → 32.9

  The cost of swapping in a local VLM is **not yet measured**. REVERSE and NAVIG are the only local evidence.

## Supporting techniques

- **EXIF/GPS:** `exiftool` subprocess, Pillow fallback. Platforms usually strip EXIF; originals sent as files often keep it.
- **OCR:**
  - **Apple Vision** via `ocrmac` (free, Neural Engine, ~50 MB RAM)
  - PaddleOCR (Apache-2.0) on PC
  - Tesseract is weak on scene text
  - The VLM can also read signs
- **Language/script ID:** stdlib `unicodedata` script detection narrows country cheaply; `lingua-py` (Apache-2.0) for language.
- **Sun/shadow:** SunCalc and Bellingcat's [ShadowFinder](https://bellingcat.com/resources/2024/08/22/shadow-geolocate-geolocation-locate-image-tool-open-source-bellingcat-measure); both need a date/time and output a band, not a point ([guide](https://www.bellingcat.com/resources/2020/12/03/using-the-sun-and-the-shadows-for-geolocation/)).
- **Verifying a candidate:**
  - [Mapillary API v4](https://www.mapillary.com/developer/api-documentation): free token, CC-BY-SA imagery with attribution ([terms](https://help.mapillary.com/hc/en-us/articles/115001770409-CC-BY-SA-license-for-open-data)); compare locally with CLIP/DINOv2.
  - Overpass/OSM (ODbL): match OCR'd business names near candidates.
  - KartaView: maintenance uncertain.
  - These see candidate *coordinates* only, not the image. The UI must disclose this.
- **Reverse image search** (Google Lens, Bing, Yandex, TinEye): no free APIs, and the image leaves the machine. Offer only as an explicit investigator-chosen "open in browser" action.

## Commercial comparables

- **GeoSpy (Graylark):**
  - Its Superbolt model is trained on 46M street-level images, with a claimed meter-level accuracy where references exist ([blog](https://geospy.ai/blog/superbolt-the-future-of-visual-place-recognition)).
  - The **public version was shut down** after 404 Media reported users trying to locate specific women; it's now law-enforcement-only ([summary](https://booksbikesboomsticks.blogspot.com/2025/01/stalkerbot.html)).
  - Lesson for Tessera: geolocation must be case-bound and audited.
- **Picarta:** claims 44.8% @1km on Im2GPS3k (**unverified**; likely benchmark overlap) ([V2](https://picarta.ai/picarta-v2)).

## Other on-device wins

| Memory | Local LLM/VLM suggestion |
|---|---|
| 16 GB | 7–9B at Q4: Qwen3-VL-8B or Gemma 4 E4B (~10–11 GB usable) |
| 32 GB | Qwen3-VL-32B at Q4 (~20 GB) or Gemma 4 26B-A4B (MoE, fast). **Practical default** |
| 64 GB | 70B-class, or a 32B VLM plus a text LLM loaded together |

([memory guide](https://www.promptquorum.com/prompt-bites/best-local-llm-32gb-unified-memory-mac))

- **One VLM covers text and vision**, so only one model stays resident. Use structured JSON outputs for entity resolution and report drafting.
- **Same photo / avatar across platforms:**
  - `imagehash` pHash/dHash (BSD) or Meta's PDQ for near-duplicates
  - CLIP/SigLIP embeddings in `sqlite-vec` for crops and edits
- **Face matching:** **excluded from MVP.**
  - InsightFace's `buffalo_l`/`antelopev2` weights are non-commercial ([licensing](https://www.insightface.ai/services/models-commercial-licensing)).
  - DeepFace model licences vary.
  - Permissive options if ever needed: YuNet (MIT) + AuraFace (Apache-2.0).
  - Legal context in `legal.md`.

## Tessera MVP pipeline (M3)

1. **Intake:** SHA-256 + pHash, then `exiftool`. If GPS is present, show it first and still verify it.
2. **Cheap signals in parallel:**
   - GeoCLIP top-20 coordinates with probabilities, reverse-geocoded offline (GeoNames / `reverse_geocoder`)
   - OCR (Apple Vision on Mac, PaddleOCR on PC)
   - Script/language ID
3. **Local VLM via Ollama:**
   - Qwen3-VL 4B/8B on 16 GB; Qwen3-VL-32B or Gemma 4 26B on 32 GB+
   - Prompt returns JSON clues (driving side, script, plates, bollards, vegetation), then reranks the GeoCLIP candidates plus its own guess (the G3/Img2Loc pattern, run locally)
4. **Fuse:** VLM country agrees with a GeoCLIP cluster → confidence up; otherwise show both. **Always ranked hypotheses with a radius, never a single pin.**
5. **Investigator-triggered verification:** Overpass name search, Mapillary imagery compared locally, SunCalc/ShadowFinder. A human confirms.
6. **Later:** GeoRanker "accuracy mode" for NVIDIA users.

**Minimum hardware:**
- Apple Silicon with 16 GB (GeoCLIP ~2 GB + 8B VLM at Q4 ~6 GB); 32 GB recommended
- NVIDIA with 8 GB VRAM (16–24 GB recommended)
- CPU-only works for GeoCLIP/EXIF but makes the VLM step take minutes

## Sources

[GeoRanker paper](https://arxiv.org/html/2505.13731), [GeoRanker repo](https://github.com/Applied-Machine-Learning-Lab/GeoRanker), [Pinpoint](https://arxiv.org/html/2606.04133v1), [REVERSE](https://arxiv.org/pdf/2605.26861), [GeoCLIP](https://github.com/VicenteVivan/geo-clip), [geoclip on PyPI](https://pypi.org/project/geoclip/), [StreetCLIP](https://huggingface.co/geolocal/StreetCLIP), [PIGEON](https://github.com/LukasHaas/PIGEON), [OSV-5M baseline](https://huggingface.co/osv5m/baseline), [G3](https://github.com/Applied-Machine-Learning-Lab/G3), [GeoReasoner](https://arxiv.org/html/2406.18572v3), [GaGA](https://arxiv.org/html/2412.08907v2), [Img2Loc](https://arxiv.org/abs/2403.19584), [NAVIG](https://arxiv.org/abs/2502.14638), [Georgia Tech GeoRC summary](https://news.research.gatech.edu/2026/07/06/researchers-use-geoguessr-champion-test-geolocation-accuracy-vlms), [PaddleOCR-VL on Apple Silicon](https://www.paddleocr.ai/latest/version3.x/pipeline_usage/PaddleOCR-VL-Apple-Silicon.html), [local vision models 2026](https://www.promptquorum.com/power-local-llm/local-vision-models-llava-ollama-2026)
