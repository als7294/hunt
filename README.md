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
| **Find a person** | Checks hundreds of sites and public records at once, and logs every source asked, including the empty ones |
| **Is it them?** | Scores each account against everything the case knows, explains every point, and sets namesakes aside. The investigator decides |
| **Posts** | Reads public posts logged out (Bluesky, Mastodon, YouTube). Takes in what the investigator views in the **Hunt Browser** and the files they saved. Scans every photo and video on the Mac with a local vision model for the case's look-for list, dated before or after the injury |
| **Report** | Written from the case's records, with no language model. Every sentence is cited; ICD 203 confidence wording; a screening version for employment (FCRA); a hashed evidence bundle anyone can check with `shasum -c` |

**Everyday helpers:**
- File messy downloads (`ssstik.io_1745821072612.mp4`) under clear names, with the post time read from its ID.
- Check the subject's accounts again over the life of a claim, or watch them on a schedule with local notifications.
- Timestamped notes you can cite.
- "Have we seen this person before?" across your cases.
- Move a case between Macs in one encrypted, hash-checked archive.

See [docs/qol.md](docs/qol.md) for these.

## Guardrails

Built in, not bolted on:
- **A purpose is required for every case,** and every case keeps an audit log of each search, decision, import and export.
- **Hunt's own collection is passive and logged out.** It never logs in by itself, never uses sock-puppet accounts, and never automates a logged-in session.
- **Logged-in viewing is the investigator's,** as themselves, in the Hunt Browser. Hunt Capture records what they choose to view and never clicks, scrolls or follows.
- **The subject is never contacted or notified:** no follows, messages, or email checks that could alert them. All 220 email-check modules were read and classified.
- **No automatic downloads** from Instagram, TikTok or Facebook.
- **Machine verdicts stop at "likely",** and a handle alone can't pass "roughly even chance" (two-identifier rule).
- **Employment screening mode** drops protected traits and sensitive records. Screenings are kept apart from other investigations.
- **Retention:** 90 days from opening, unless on legal hold. Deleting moves files to the Trash; Hunt never deletes them.
- **Flagged media where a child may be visible** are blurred in the app.

If you furnish reports for employment, tenancy, credit or insurance decisions, you are likely a consumer reporting agency under the FCRA, whatever software you use. Hunt helps you comply; it does not exempt you. Hunt uses free and open sources only. It **complements** licensed data-broker tools (TLOxp, Accurint and the like); it doesn't replace them. Why each line is where it is: [legal.md](docs/research/legal.md).

## Install

You need a Mac with Apple Silicon and about 6 GB free. In Terminal, once:

```bash
brew install uv
```

```bash
uv tool install git+https://github.com/als7294/hunt && hunt setup
```

`hunt setup` puts **Hunt** in Applications, then shows the size of each download (the browser, about 0.2 GB; the vision model, 3.3 GB) and asks before fetching it.

Then install [Ollama](https://ollama.com/download), which runs the vision model, and open it once. Double-click **Hunt** to start. Use `hunt doctor` to check everything, `hunt update` to update, and `hunt uninstall` to remove Hunt (it asks before moving your cases to the Trash). No `brew`? See [uv's installation page](https://docs.astral.sh/uv/getting-started/installation/).

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

Under active development: the app's screens are being rebuilt. Photo geolocation works and is benchmarked, but is on hold, shown as "coming soon". See the [roadmap](docs/roadmap.md).

## Docs

| Doc | What's in it |
|---|---|
| [user-guide.md](docs/user-guide.md) | For investigators: install, first run, a case from start to report, verdicts, handing over evidence |
| [qol.md](docs/qol.md) | Everyday helpers: the Downloads inbox, evidence bundle, Check again, watching, notes, moving cases, seen before, setup |
| [capture.md](docs/capture.md) | The Hunt Browser and Hunt Capture |
| [api.md](docs/api.md) | The local app's API |
| [research/pain-points.md](docs/research/pain-points.md) | What investigators struggle with, and what a good report contains |
| [research/legal.md](docs/research/legal.md) | FCRA, DPPA/GLBA, state data-broker laws, scraping case law, biometrics, human-driven capture |
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
