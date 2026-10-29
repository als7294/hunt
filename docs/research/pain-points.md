# Investigator pain points

_Research date: 2026-10-29. **[S]** = stated in the cited source; **[I]** = our inference. Reddit was only reachable through mirrors, and some vendor surveys are form-gated, so treat the vendor figures as indicative. Validate against [`practitioner-interview.md`](practitioner-interview.md)._

## Ranked by how often they come up

1. **Same-name false positives / identity disambiguation**
   - Namesakes, common handles and reused avatars are a major source of error [S] ([ShadowDragon](https://shadowdragon.io/blog/what-are-the-common-struggles-of-osint-investigations)).
   - SpiderFoot has tied a common username to an unrelated, offensive account [S] ([SANS](https://sans.org/blog/spiderfoot-and-the-dangers-of-doxing)).
   - Sherlock and Maigret false-positive on short handles and after sites change [S] ([Bellingcat toolkit](https://bellingcat.gitbook.io/toolkit/more/all-tools/maigret)).
   - Practitioner convention: require **≥2 independent identifiers**, label single-attribute matches "uncertain", and record why each lead was discarded [S] ([altss](https://altss.com/glossary/identity-disambiguation), [triage notes](https://ldamoredev.github.io/cibersecurity-notes/en/cybersecurity/osint/osint-triage.html)).
   - People-search social matching is "largely manual and only partly accurate" [S] ([Diligentia](https://diligentiagroup.com/?p=11721)).

2. **Evidence capture and provenance**
   - A bare screenshot is weak evidence. Investigators need the URL, capture time, handle, platform and a hash [S] ([PageFreezer](https://blog.pagefreezer.com/how-to-preserve-social-media-content-for-court), [Hunchly](https://hunch.ly/)).
   - SANS OSINT Summit 2026 headline theme: "provenance over plausibility" [S] ([SANS](https://www.sans.org/blog/a-summary-of-2026-sans-osint-summit)).
   - The Berkeley Protocol sets minimum standards for preservation and chain of custody [S] ([Berkeley HRC](https://humanrights.berkeley.edu/programs/investigations/berkeley-protocol)).

3. **Data overload / manual processing**
   - Data is the biggest barrier to effective investigations [S] ([Blackdot State of OSINT, via SecurityBrief](https://securitybrief.co.uk/story/osint-investigators-battle-data-glut-scarcity-with-ai)).
   - ~50% cite time-consuming data processing and ~33% complicated tools [S, vendor survey, unverified].
   - Manual pivoting takes 1–2 weeks vs 1–3 days automated [S, vendor estimate].

4. **Tools break; platform access shrinks**
   - API and HTML changes break tools [S].
   - SANS 2026 examples: TikTok "@" false 404s, ad blockers hiding data, "death of the open web" [S].
   - The X academic API ended in 2023; X moved to pay-per-use in Feb 2026 [S] ([xpoz](https://www.xpoz.ai/blog/guides/understanding-twitter-api-pricing-tiers-and-alternatives/)).

5. **OPSEC and attribution risk**
   - Personal or corporate accounts and networks expose the investigator, and clicking live links can tip off the subject [S].
   - 85% of 338 CTI practitioners report little or no OSINT/risk training [S, Authentic8-sponsored] ([PRNewswire](https://prnewswire.com/news-releases/cyber-threat-intelligence-analysts-undertrained-unsupported-301026530.html)).

6. **Reporting and documentation**
   - "So many analysts entering the field struggle with reporting" [S] ([Rae Baker talk](https://www.letsplayindex.com/video/once-upon-a-crime-a-novel-approach-to-osint-through-storytelling-X8cHL0RuEjA)).
   - Text-file notes don't scale as a case grows [S] ([DEF CON 26 Recon Village](https://media.defcon.org/DEF%20CON%2026/DEF%20CON%2026%20villages/DEF%20CON%2026%20villages%20captions/DEF%20CON%2026%20-%20RECON%20VILLAGE%20-%20WebBreacher%20-%20Core%20OSINT%20Keeping%20Track%20of%20and%20Reporting%20All%20the%20Things.eng.txt)).
   - r/OSINT recommends BLUF (bottom line up front) and citing every source [S, mirror].

7. **Tool sprawl**
   - Mostly vendor framing; practitioners push back that more tools rarely help, and r/OSINT is sceptical of "vibe-coded OSINT dashboards" [S] ([secjuice](https://secjuice.com/the-osint-toolkit/)).
   - **[I]** The real complaint is having no shared case record across tools.

8. **Deleted content**
   - The Wayback Machine often replays an empty shell for dynamic social pages; archive.today does better but has no preservation guarantee [S] ([Bellingcat](https://bellingcat.gitbook.io/toolkit/more/all-tools/archive.today), [EBU](https://spotlight.ebu.ch/p/advanced-wayback-machine-and-archival)).

9. **AI-era risks**
   - AI tools hallucinating supporting URLs, analysts losing tradecraft to over-reliance on AI, scope creep, confirmation bias [S, SANS 2026].

## Design implications [I]

- The two differentiators are **explainable identity resolution** (show which identifiers agree and conflict, and record ruled-out candidates) and **automatic capture + timestamp + SHA-256 feeding directly into the report**. Raw source count matters less.
- Every AI-written sentence must cite a captured finding. Uncited claims are blocked.
- Record "searched, nothing found", because methodology sections need it.
- Collection is passive and logged-out by default, with proxy/VPN routing available.

## What a good report contains

Synthesised from the sources above:

1. **BLUF / executive summary** that answers the client's actual question.
2. **Scope and purpose:** requester, permissible purpose, date range.
3. **Seeds and identity-resolution rationale:** matched identifiers, plus ruled-out candidates and why.
4. **Methodology and sources checked, including empty results** ([Lekati / SANS](https://sans.org/blog/high-value-cfp-submissions-example-successful-proposal)).
5. **Findings:** URL, platform, handle, post time, capture time, SHA-256, exhibit reference.
6. **Confidence:**
   - [ICD 203](https://www.dni.gov/files/documents/ICD/ICD-203.pdf) estimative language ("likely", "very likely")
   - [Admiralty code](https://en.wikipedia.org/wiki/Intelligence_source_and_information_reliability): source reliability A–F and information credibility 1–6, graded separately
7. **Limitations:** private or deleted content, possible namesakes.
8. **Exhibits and hash manifest.**
9. **Employment screening only (FCRA mode):**
   - redact protected-class information
   - only job-relevant flags, no scores ([Ferretly](https://www.ferretly.com/best-social-media-screening-software-compared-ferretly-vs-others))
   - keep the screener separate from the decision-maker ([SHRM](https://shrm.org/ResourcesAndTools/hr-topics/talent-acquisition/Pages/Screening-Social-Media-Discrimination-Claims.aspx))
