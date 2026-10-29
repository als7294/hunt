# Legal and ethical constraints (US)

_Research date: 2026-10-29. This is engineering research, not legal advice. **[S]** = sourced; **[I]** = our inference._

## FCRA

- **What makes someone a consumer reporting agency (CRA):** regularly assembling or evaluating consumer information "for monetary fees, dues, or on a cooperative nonprofit basis" to furnish to third parties. Whether something is a consumer report turns on *use*: employment, tenancy, credit, insurance [S] ([15 U.S.C. §1681a](https://law.justia.com/codes/us/2010/title15/chap41/subchapiii/sec1681a/)).
- **FTC precedent:**
  - Social media screening sold to employers makes the seller a CRA [S] ([FTC, Social Intelligence 2011](https://www.ftc.gov/sites/default/files/documents/closing_letters/social-intelligence-corporation/110509socialintelligenceletter.pdf)).
  - Instant Checkmate/TruthFinder paid $5.8M (2023). "Not for FCRA purposes" disclaimers didn't help. Failures cited: no permissible-purpose checks, weak access controls, inaccurate reports, ignored disputes [S] ([FTC](https://www.ftc.gov/news-events/news/press-releases/2023/09/ftc-says-truthfinder-instant-checkmate-deceived-users-about-background-report-accuracy-violated-fcra)).
  - FTC to background-check app makers: "not for employment" disclaimers do not remove FCRA duties [S] ([ZwillGen](https://www.zwillgen.com/general/ftc-sends-fcra-warning-letters-to-mobile-app-background-check-providers/)).
- **[I] For Hunt:**
  - If an investigator's firm delivers social media reports to employers, *the firm* is the CRA, whatever software it uses.
  - Hunt should help it comply: purpose record, accuracy, dispute-friendly evidence, FCRA-mode redaction. It shouldn't pretend FCRA doesn't apply.

## DPPA / GLBA

- **DPPA:** DMV-derived data is available only for permitted uses (18 U.S.C. §2721(b)) [S] ([Vice](https://vice.com/en/article/dmv-dppa-drivers-privacy-protection-act-buy-data-private-investigators)).
- **GLBA:** commercial databases (Accurint, TLO) require a permissible-use certification per search. Retaining the justification for 5 years is advised [S] ([Accurint FAQ](https://secure.accurint.com/bps/516/html/glb_dppa_faq.html), [eInvestigator](https://www.einvestigator.com/navigating-privacy-laws-a-compliance-guide-for-the-modern-investigator/)).
- **[I]** Open-web collection doesn't trigger either law. Any future broker or DMV connector should be bring-your-own-licence, behind a permissible-purpose selector.

## State laws

- **California Delete Act:**
  - Data brokers had to register by 2026-01-31.
  - The DROP deletion platform has been live since 2026-01-01, with enforcement since 2026-08-01.
  - Brokers must process deletion requests every 45 days; penalty $200/day per request [S] ([Manatt](https://www.manatt.com/insights/newsletters/client-alert/california-s-first-of-its-kind-data-deletion-platform-goes-live-what-businesses-should-know), [Mondaq](https://www.mondaq.com/unitedstates/privacy-protection/1732128/is-your-business-a-data-broker-californias-drop-goes-live-and-calprivacy-continues-to-enforce-delete-act)).
- **New Jersey Daniel's Law:**
  - Atlas Data Privacy has sued 40+ brokers and people-search firms over the home addresses of covered persons.
  - The NJ Supreme Court held no mental-state requirement applies to damages; the Third Circuit constitutional challenge is pending [S] ([NJ Monitor](https://newjerseymonitor.com/2026/08/12/nj-supreme-court-daniels-law-ruling/), [NJ Globe](https://newjerseyglobe.com/judiciary/third-circuit-tosses-daniels-law-fight-to-n-j-supreme-court/amp/)).

## CFAA, scraping, platform ToS

- **Van Buren (2021) and hiQ v. LinkedIn (9th Cir. 2022):** scraping public pages is likely not "without authorization". But hiQ ultimately lost on contract and stipulated to a $500k judgment, including CFAA liability for fake accounts [S] ([Proskauer](https://newmedialaw.proskauer.com/2022/12/08/hiq-and-linkedin-reach-proposed-settlement-in-landmark-scraping-case/)).
- **Meta v. Bright Data (2024):** logged-off scraping of public data didn't breach Meta's terms. Meta dropped the case [S] ([TechCrunch](https://techcrunch.com/2024/02/26/meta-drops-lawsuit-against-web-scraping-firm-bright-data-that-sold-millions-of-instagram-records)).
- **X v. Bright Data:** partially revived in Nov 2024 on server-access and fraud theories; current status unknown [S] ([Bloomberg Law](https://news.bloomberglaw.com/ip-law/x-partially-revives-lawsuit-against-israeli-data-scraping-firm)).
- **[I] Rule for Hunt:** logged-out collection of public data only. Logged-in automation through sock puppets is the hiQ loss pattern, so it's never automated by Hunt.

## Biometrics (relevant to photo features)

- **Illinois BIPA:** $1k negligent / $5k reckless per violation. Since SB 2979 (Aug 2024), damages are counted per person [S] ([DWT](https://dwt.com/blogs/privacy--security-law-blog/2024/08/illinois-bipa-biometrics-law-amended-for-damages)).
- **EU AI Act Art. 5(1)(e):** bans *untargeted* scraping to build face databases (in force 2025-02-02). GDPR Art. 9 treats biometrics as special-category data [S] ([FPF](https://fpf.org/blog/red-lines-under-the-eu-ai-act-understanding-the-ban-of-the-untargeted-scraping-of-facial-images-and-facial-recognition-databases/)).
- **[I] Decision:** no face recognition in the MVP. If it's ever added: off by default, 1:1 comparison of investigator-supplied images only, no persistent face index, purpose recorded per use, permissive-licence models only.

## Hosted public site vs self-hosted tool

| Risk | Free public hosted site | Self-hosted OSS (Hunt) |
|---|---|---|
| FCRA CRA status | Plausible, especially if marketed for screening | User's own use; the developer furnishes nothing |
| CA data broker / Daniel's Law | Exposed: the operator collects and displays addresses | The developer collects nothing |
| Platform ToS / CFAA | The operator scrapes at volume from one IP | Each user accesses under their own responsibility |
| Abuse (stalking, doxxing) | Anonymous public access is the scenario behind the DPPA | Setup effort filters casual abuse; guardrails built in |

**Decision:**
- Hunt is self-hosted, local-first software.
- The public website is a landing page plus a demo on fictional data only.
- Precedent: GeoSpy's public geolocation tool was pulled after stalking misuse (see `geolocation.md`).

## Guardrails Hunt ships

Disclaimers alone are not enough: the FTC has said so, and OpenOSINT was criticised for shipping a disclaimer without guardrails. These guardrails are real features:

- **Case purpose attestation** before any search, modelled on GLBA/DPPA permissible-use selectors [S].
- **Audit log** of target, scope, justification and every query [S] ([Knogin](https://knogin.com/api/docs/modules/analyst-driven-osint)).
- **Passive-only collection:** no follow, like, message or contact ([Trace Labs rules](https://tracelabs.org/about/search-party-rules)). No bundled sock-puppet automation.
- **Minors flag** that halts or limits collection [I; no published standard found].
- **Per-source rate limits.**
- **Retention and purge** per case [S].
- **FCRA mode:** consent record, redaction, no scores [S, Ferretly].

## FBI / IC portfolio relevance

- The FBI analyst process includes a timed writing test simulating intelligence products ([fbijobs.gov](https://fbijobs.gov/intelligence-analysts)).
- The IC OSINT Strategy 2024–2026 aims to professionalise tradecraft ([ODNI](https://www.dni.gov/index.php/newsroom/reports-publications/reports-publications-2024/3785-the-ic-osint-strategy-2024-2026)).
- Hiring managers prefer "how you investigated X, overcame Y, found Z" stories ([osintme](https://osintme.com/index.php/2022/06/19/getting-a-job-in-osint-interview-with-lorand-bodo/)).
- **[I] Strongest signals for Hunt:** ICD 203 confidence language, provenance and hashing, built-in legal and ethical guardrails, and a written methodology. A public doxxing-style site could hurt a suitability review.
