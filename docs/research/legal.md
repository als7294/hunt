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

## Human-driven capture: Hunt Capture (browser extension)

_Added 2026-10-29. The design is in [capture.md](../capture.md)._

**What it is.** The investigator browses Facebook, Instagram, TikTok, X, LinkedIn and YouTube herself, logged in as herself. While she turns capture on, the extension records what she views into the case, on her own computer:
- a screenshot of the screen
- the page as her browser already loaded it (MHTML)
- on her click, a recording of the tab while she plays a video

It never navigates, clicks, scrolls, searches, likes, follows or messages. It sends no request to the platforms and talks only to Hunt on 127.0.0.1.

**Precedent [S]:**
- **Hunchly** is the established tool of this kind. It is a browser extension that automatically collects the URL, timestamps and hashes of every page the investigator visits ([Hunchly, law enforcement](https://www.hunch.ly/hunchly-law-enforcement)).
- Its users include law enforcement, private investigators, journalists and insurance investigators ([eInvestigator](https://www.einvestigator.com/hunchly-online-evidence-collection/)).
- The Bellingcat toolkit notes it captures only what the investigator has seen on the page, not content in motion ([Bellingcat](https://bellingcat.gitbook.io/toolkit/more/all-tools/hunchly)).
- Hunchly is a commercial product, not a court ruling: it shows the practice is established, not that it's immune.

**The contract risk is real [S]:**
- Meta's terms bar collecting data by automated means without permission, logged in or not.
- In *Meta v. BrandTotal* (N.D. Cal., June 2022), the court found that a browser extension collecting Facebook data from logged-in users' sessions breached that clause ([Justia, order no. 344](https://law.justia.com/cases/federal/district-courts/california/candce/3:2020cv07182/367276/344/), [Courthouse News](https://www.courthousenews.com/judge-rules-brandtotals-data-harvesting-violates-metas-terms-of-use-and-anti-hacking-laws/)).
- Its earlier products "automatically caused users' browsers to query Facebook's servers".
- The case settled in September 2022; BrandTotal paid and destroyed the data ([IAPP](https://iapp.org/news/a/meta-settles-its-lawsuit-against-web-advertisers-for-data-scraping)).
- Meta revised its terms on automated collection again in July 2026 ([ConductAtlas](https://conductatlas.com/platform/meta/meta-terms-of-service/automated-data-collection-restrictions/)). Check the live text before relying on a section number.

**[I] Why Hunt Capture is on the Hunchly side of that line, and what risk remains:**
- **No requests of its own.** A screenshot (`captureVisibleTab`) and a page archive (`pageCapture`) copy what is already on her screen and in her browser. Nothing queries the platform, unlike BrandTotal.
- **Her views only.** It records only pages she opens, when she opens them. There is no panel of other people's accounts and no background collection. Capture is off by default, shows a REC badge, and turns off when the browser restarts.
- **One lawful case, kept locally.** Not a dataset, not resold.
- **Manual mode.** "Only when I press Capture this" is the same act as her taking a screenshot or using Save Page As. That's the lowest-risk setting for a firm whose counsel prefers it.
- **What remains.** A platform could still call an automatically recording extension "automated means". The exposure would be contractual (her account), not CFAA. She uses her own credentials to see what she is allowed to see, which is authorized access under *Van Buren*'s gates-up-or-down test. No sock puppets, ever: fake accounts are the hiQ loss pattern.
- **Third parties.** Captures include whatever else is on her screen (friends' comments and photos), as any screenshot does. Case retention and purge, the minors flag and the scan's child blurring apply.

**The Hunt Browser holds her sessions; Hunt never reads them [I].**
- She signs in once, inside the Hunt Browser. Its profile (`HUNT_HOME/browser/profile`) keeps her session cookies the way any browser does.
- On macOS, Chrome encrypts them with a key it keeps in the Keychain (an item named "… Safe Storage").
- Hunt never opens, reads, copies or sends them. The extension asks only whether each platform's sign-in cookie exists (`chrome.cookies.get`), and passes on nothing but `signed_in` / `signed_out`.
- "Sign out" moves the whole profile to the Trash, never deletes it, so a mistake can be put back.
- The browser has no remote-debugging port and no automation driver, so no other program can take over those sessions through Hunt.

**Which account she signs in with [I].** Her employer's policy decides. A work account is usually right:
- It is attributable to the firm and covered by its lawful-purpose policy.
- It keeps her personal network out of the investigation.
- What she can see is what that account is allowed to see.

It is never an invented persona (that's a sock puppet, the hiQ loss pattern), and never someone else's account.

**Evidence value [S]:**
- Bare screenshots get excluded: *United States v. Vayner*, 769 F.3d 125 (2d Cir. 2014). *Commonwealth v. Mangel*, 181 A.3d 1154 (Pa. Super. 2018) turned partly on missing creation metadata.
- Many courts accept hashes plus metadata as circumstantial authentication under FRE 901(b)(4) ([Constellation Research summary](https://www.constellationr.com/research/blog/evidentiary-challenges-social-media-evidence-now-routine-when-best-practices-not); vendor-written, so weigh it accordingly).
- **[I]** Hunt Capture keeps, for each capture:
  - the URL and capture time
  - a SHA-256 taken when it lands
  - the page source (MHTML, with its own `Snapshot-Content-Location` and `Date`) beside the screenshot
  - the paired extension's identity, in the audit log

  That supports the investigator's own testimony. It doesn't replace it.

**The line, and the passive recorder [S/I].** [automation-legal.md](automation-legal.md) §4 sets the line Hunt Capture follows: every request a login-walled platform receives is caused by one deliberate input of hers, and everything after the bytes arrive is automatic.
- Passive capture of data already sent to her browser is not CFAA "access" [S] (*Meta v. BrandTotal*, slip op. 43). On contract it remains unsettled (n.28).
- So the extension sends no request of its own. Grid thumbnails, page archives and screenshots all come from what the page already fetched.
- Because the evidence is a capture of what the platform sent her, the per-item capture record in [capture.md](../capture.md#capture-record) is kept:
  - who it was viewed as, from cookie presence only
  - the audience shown
  - UTC time and its source
  - both versions
  - a SHA-256 taken before any processing

  It suits FRE 902(13), and items not shown as Public are flagged for counsel.

**The per-site switch [I].** The extension never runs on LinkedIn, Strava or Snapchat. Their terms name extensions or "semi-automated" tools, and LinkedIn scans for extension ids. Hunt also refuses their uploads, as a second guard. There she uses Save Page As and the importers.

**Hard stops [I].** A checkpoint, challenge, "suspected automated behaviour", action block, CAPTCHA or "account disabled" stops recording that platform until she resumes it.
- It's seen passively: in the addresses she's sent to, or in an archive's text.
- She's told not to use that account for casework and to tell Ethos.
- Hunt never falls back to another account, profile or proxy: that would be evasion, and the hiQ fake-account pattern.

**The Story warning [I].** Story viewers can see who watched, so a signed-in Story view may be visible to the subject. That would be contact. Before a Story opens, the extension asks; cancelling stops her click, and nothing is re-sent.

**Guided mode: one input, one request, and the tension [I].** Aaron asked for a guided mode so the big platforms need almost no clicking. Each press of Next (a keyboard shortcut or the popup's button; nothing on the page) does exactly one step:
- one scroll by a screen on the subject's grid, which loads the next rows as her own scroll would; or
- one navigation to the next post on Hunt's "open these" list.

The next press is locked until that step's capture is recorded. Nothing repeats or runs on a timer, and each press is audited as `guided step`.

*Reasoning.* The request the platform receives (the grid's next rows, or the post's page) is caused by her one deliberate press, just as by PageDown or a click on a link. So the causal line holds: one input, one request.

*The tension, stated plainly.* automation-legal.md's "What not to build" lists "any bot, macro or script that loads pages, scrolls, clicks or types on a logged-in platform", including "assistive" auto-scroll she starts and watches. Guided mode isn't continuous or self-starting, but it is a script that scrolls and navigates on her press.
- **Contract risk:** a platform could call it "automated means", or "semi-automated" in its terms' words.
- **Detection risk:** a scroll with no wheel or key event behind it can look scripted, which may trigger a checkpoint. The hard stop then ends capture on that platform.
- **The lower-risk path:** she scrolls and clicks herself. That's the default; guided mode only acts when she presses Next.

Firms whose counsel prefers that should not use guided mode. This trade-off should be confirmed with counsel before guided mode is used in casework.

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
