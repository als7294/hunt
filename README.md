# Tessera

**One search, every source, the right person, with proof.**

Tessera is a free, open-source, local-first OSINT investigation tool for background checks, due diligence and social media reports.

Start with whatever you have (a name, username, email, phone number, address, profile link or photo):

- Tessera checks dozens of open sources at once.
- It works out which results really belong to the same person, and shows why.
- It captures tamper-evident evidence of everything it finds.
- It estimates where photos were taken using AI running on your own machine.
- It drafts a fully cited report.

> **Status: research and design.** No usable code yet. See the [roadmap](docs/roadmap.md).

## Why

Investigators juggle dozens of single-purpose tools, copy results between them by hand, and fight same-name false positives. Every open-source OSINT framework we surveyed (SpiderFoot, recon-ng, BBOT) is built around infrastructure, not people. Tessera focuses on what practitioners say matters most:

1. **Explainable identity resolution.** Every match shows which identifiers agree and which conflict. Look-alikes that were ruled out are recorded with the reason.
2. **Provenance.** Every finding is captured with URL, timestamp and SHA-256, and flows straight into the report.
3. **Honest confidence.** ICD 203 estimative language. AI-drafted text must cite evidence, or it's blocked.

## Local-first, on purpose

- Tessera runs on the investigator's own computer, and case data and photos stay there.
- Photo geolocation, OCR and report drafting run on local hardware (Apple Silicon or an NVIDIA GPU) through open models.
- There is no hosted people-search service, and there won't be. See [legal research](docs/research/legal.md) for why.

## Responsible use

Tessera is for lawful, purpose-bound investigations. These guardrails are built in, not bolted on:

- A purpose statement and audit log for every case
- Passive, logged-out collection only: no following, messaging or sock-puppet automation
- A minors flag
- Per-source rate limits
- Per-case retention and purge
- An FCRA mode for employment screening

If you furnish reports for employment, tenancy, credit or insurance decisions, you are likely a consumer reporting agency under the FCRA whatever software you use. Tessera helps you comply; it does not exempt you.

Tessera uses free and open sources only. It **complements** licensed data-broker tools (TLOxp, Accurint, etc.); it does not replace them.

## Research

| Doc | What's in it |
|---|---|
| [tools.md](docs/research/tools.md) | Open-source tools and free APIs to build on, with licences and maintenance status |
| [pain-points.md](docs/research/pain-points.md) | What investigators struggle with, and what a good report contains |
| [legal.md](docs/research/legal.md) | FCRA, DPPA/GLBA, state data broker laws, scraping case law, biometrics |
| [geolocation.md](docs/research/geolocation.md) | Local photo geolocation models and on-device ML |

## Credits

Tessera builds on [Maigret](https://github.com/soxoj/maigret), [WhatsMyName](https://github.com/WebBreacher/WhatsMyName) (CC BY-SA 4.0), [user-scanner](https://github.com/kaifcodec/user-scanner), [GeoCLIP](https://github.com/VicenteVivan/geo-clip) and others listed in [tools.md](docs/research/tools.md).

## Licence

[AGPL-3.0](LICENSE).
