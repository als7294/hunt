# Hunt

**One search, every source, the right person, with proof.**

Hunt is a free, open-source, local-first investigation tool for **background checks, insurance claims, due diligence and social media reports**. It's built for investigators who know their trade, not their terminal.

Start with whatever you have: a name, username, email, phone number, address or profile link. Hunt:
- finds the person's accounts
- shows which ones really belong to them, and why
- looks through what they post for what your client needs to know (for example, lifting after an injury date)
- hands you a report where every sentence cites its evidence

Your cases, evidence and the AI that reads photos and videos stay on your Mac.

**→ [The user guide](docs/user-guide.md)**: install, first run, a case from start to report, and handing over evidence.

## What it does

| Step | What happens |
|---|---|
| **Find a person** | Checks over a thousand sites and public records at once (including federal and some state and city court records), and logs every source asked, including the empty ones |
| **Is it them?** | Scores each account against everything the case knows, explains every point, and sets namesakes aside. The investigator decides |
| **Posts** | Reads public posts logged out (Bluesky, Mastodon, YouTube, TikTok's public pages). Takes in what the investigator views in the **Hunt Browser** and the files they saved, and optionally public Instagram and Facebook posts through Apify on their own paid account. Scans every photo and video on the Mac with a local vision model for the case's look-for list, dated before or after the injury |
| **Report** | Written from the case's records, with no language model. Every sentence is cited; ICD 203 confidence wording; a screening version for employment (FCRA); a hashed evidence bundle anyone can check with `shasum -c` |

**Everyday helpers:**
- File messy downloads (`ssstik.io_1745821072612.mp4`) under clear names, with the post time read from its ID.
- Check the subject's accounts again over the life of a claim, or watch them on a schedule with local notifications. On Instagram, Facebook, X, LinkedIn and TikTok, Check again is a worklist you open yourself, and Hunt compares each capture with the last.
- Timestamped notes you can cite.
- "Have we seen this person before?" across your cases.
- Move a case between Macs in one encrypted, hash-checked archive.

See [docs/qol.md](docs/qol.md) for these.

## Guardrails

Built in, not bolted on. The full list, with the reasoning behind each, is [Hunt's rules](docs/research/legal.md#hunts-rules).

- **A purpose is required for every case,** and every case keeps an audit log of each search, decision, import and export.
- **No software-caused request to a login-walled platform.** On Facebook, Instagram, TikTok, X and LinkedIn, the investigator browses as themselves in the Hunt Browser, and Hunt Capture records only what they open. Hunt never logs in and never drives their account. Hunt's own collection elsewhere is passive and logged out.
- **The investigator's own real account only:** no fake accounts, sock puppets or pretexting.
- **The subject and their associates are never contacted or notified:** no following, friending, liking or messaging, and no checks that could notify anyone. All 220 email-check modules were read and classified.
- **No getting around a limit:** no CAPTCHA solving, and no proxies, IP rotation or spoofing to get past a block. Hunt stops at the first refusal, and on any sign that a platform has revoked access.
- **No face search.** A one-to-one face check against the investigator's own reference photo is built, opt-in and allowed only where the subject's home state or country permits it; its screen is coming.
- **Nothing fetched from Instagram or Facebook by Hunt itself** (except an Apify run on the investigator's own account). TikTok videos are fetched only from public pages TikTok lets software read, and only when the uploader allows downloads.
- **Machine verdicts stop at "likely",** and a handle alone can't pass "roughly even chance" (two-identifier rule).
- **Employment screening mode** drops protected traits, sensitive records and relationships, and background cases always get it. Screenings are kept apart from other investigations.
- **Associates are a name and a citation:** never searched, never contacted, never labelled ("mother", "brother"); Hunt quotes what was observed. A child is never named.
- **Retention is a reminder:** at 90 days from opening Hunt asks you to delete, hold or trim the case. Deleting moves files to the Trash; Hunt never deletes them.
- **Flagged media where a child may be visible** are blurred in the app and the report. The evidence bundle keeps originals for chain of custody.
- **Guided mode** (one key press, one step on the subject's profile) is off until you turn it on and acknowledge the trade-off.

If you furnish reports for employment, tenancy, credit or insurance decisions, you are likely a consumer reporting agency under the FCRA, whatever software you use. Hunt helps you comply; it does not exempt you. Hunt runs free on public sources; the only paid option is an Apify connector on the investigator's own account. It **complements** licensed data-broker tools (TLOxp, Accurint and the like); it doesn't replace them. Why each line is where it is: [legal.md](docs/research/legal.md).

## Install

You need a Mac with Apple Silicon and about 6 GB free. In Terminal, once:

```bash
brew install uv
```

```bash
uv tool install --python 3.12 git+https://github.com/als7294/hunt && hunt setup
```

`hunt setup` puts **Hunt** in Applications, then shows the size of each download (the browser, about 0.2 GB; the vision model, 3.3 GB) and asks before fetching it.

Then install [Ollama](https://ollama.com/download), which runs the vision model, and open it once. Double-click **Hunt** to start. To see a finished investigation first, run `hunt demo`: it adds a fictional case, marked DEMO everywhere. On first run, Hunt checks itself, asks you to sign in to the platforms you use in the Hunt Browser, and offers optional free keys (GitHub, Gravatar, OpenFEC, CourtListener, state open-data portals) that unlock more from some sources. Use `hunt doctor` to check everything, `hunt update` to update, and `hunt uninstall` to remove Hunt (it asks before moving your cases to the Trash). No `brew`? See [uv's installation page](https://docs.astral.sh/uv/getting-started/installation/).

**From source:**

```bash
git clone https://github.com/als7294/hunt && cd hunt && uv sync && uv run hunt setup
```

## How matching works

Every hit is scored against everything the case knows, Fellegi-Sunter style. Each signal adds or subtracts bits, and the result maps to an [ICD 203](https://www.dni.gov/files/documents/ICD/ICD-203.pdf) verdict, from "almost no chance" to "almost certain".

| Signal | How it's judged |
|---|---|
| Username | Rarity is measured, not guessed: "taken on 469 of 788 sites checked" means common. |
| Name | Nickname-aware (Bob ↔ Robert). Graded match / similar / part of / conflicts. A display name that only repeats the handle counts for nothing. |
| Location | Geocoded and compared by distance: same area, region or country, or a conflict. Placeholders like "Unknown" or "Earth" are ignored. |
| Email | A Gravatar hash or listed email matching the subject's email is near-conclusive. |
| Links | Links to the subject's known profiles, or to accounts carrying their handle, count. Links back to the same site don't. |
| Profile photo | Sharing the same picture with a likely match, or with a photo supplied in the case, is a second identifier. Site default avatars are ignored. |

## Status

**0.1.0, the first release.** [CHANGELOG.md](CHANGELOG.md) lists what it does and what isn't built yet. Coming next:
- **Guided mode:** how much of each profile you've covered, and what's left to open. Built; held back until tried live.
- **The reference-photo screen** for the face check.
- **Locate a photo:** photo geolocation. It works and is benchmarked, but is on hold.

See the [roadmap](docs/roadmap.md).

## Docs

| Doc | What's in it |
|---|---|
| [user-guide.md](docs/user-guide.md) | For investigators: install, first run, a case from start to report, verdicts, handing over evidence |
| [CHANGELOG.md](CHANGELOG.md) | What each release does, and what isn't built yet |
| [qol.md](docs/qol.md) | Everyday helpers: the Downloads inbox, evidence bundle, Check again, watching, notes, moving cases, seen before, setup |
| [capture.md](docs/capture.md) | The Hunt Browser and Hunt Capture |
| [api.md](docs/api.md) | The local app's API |
| [research/pain-points.md](docs/research/pain-points.md) | What investigators struggle with, and what a good report contains |
| [research/legal.md](docs/research/legal.md) | FCRA, DPPA/GLBA, state data-broker laws, scraping case law, biometrics, human-driven capture, and Hunt's rules |
| [research/automation-legal.md](docs/research/automation-legal.md) | How far collection from Facebook, Instagram and TikTok can lawfully be automated, platform by platform |
| [for-counsel.md](docs/for-counsel.md) | Two pages for a lawyer: what Hunt does and doesn't do, and the open questions |
| [research/report-format.md](docs/research/report-format.md) | What clients expect in a report |
| [research/tools.md](docs/research/tools.md) | Open-source tools and free APIs, with licences and maintenance status |
| [research/geolocation.md](docs/research/geolocation.md) | Local photo geolocation models and on-device ML |

**Self-checks** (offline, fictional subjects only):

```bash
for t in test_*.py; do uv run python "$t"; done
```

## Credits

Hunt builds on [Maigret](https://github.com/soxoj/maigret), [WhatsMyName](https://github.com/WebBreacher/WhatsMyName) (CC BY-SA 4.0), [user-scanner](https://github.com/kaifcodec/user-scanner), [GeoCLIP](https://github.com/VicenteVivan/geo-clip) and others listed in [tools.md](docs/research/tools.md).

## Licence

[AGPL-3.0](LICENSE).
