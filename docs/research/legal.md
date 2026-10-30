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
- **Sharpened 2026-10-29** by [automation-legal.md](automation-legal.md): no software-caused request to a login-walled platform, even on her own real account. The current wording is in [Hunt's rules](#hunts-rules).

## Human-driven capture: Hunt Capture (browser extension)

_Added 2026-10-29. The design is in [capture.md](../capture.md). Since then, [automation-legal.md](automation-legal.md) set capture off on LinkedIn (rule C9 in [Hunt's rules](#hunts-rules)), whose terms name browser extensions; the extension still covers it until that's built._

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
- **[I] Decision (MVP):** no face recognition. If it's ever added: off by default, 1:1 comparison of investigator-supplied images only, no persistent face index, purpose recorded per use, permissive-licence models only.
- **[I] Decision (2026-10-29): 1:1 face verification against a reference photo, built inside those limits** (`hunt/face.py`, details in [analysis.md](../analysis.md)):
  - **Gated on where the subject lives** (`face.gate`, rules F1–F2 below). The case detail `subject_residence` is an ISO 3166 code like `US-AZ` or `GB`.
    - **Blocked:** an unknown residence, or a US residence without a state. Also IL (BIPA), TX (CUBI; TRAIGA (e)(3) untested), WA (My Health My Data Act), CO (HB 24-1130), CA (until counsel accepts §1798.145(a)(1)(E)), the EU/EEA, the UK and Canada (per-case basis records Hunt doesn't keep yet).
    - **Checked at two points:** when the case turns the check on, and again before every run, because the residence can change.
    - **Audited:** every decision is written as `face gate` with `{allowed, residence, rule}`.
  - **Washington MHMDA mode:** a `US-WA` subject sets `case.mhmda`, which the report can read. The fraud basis goes in the case detail `mhmda_basis`, and the report words findings as observed activity, not physical condition.
  - **Off by default.** Each case turns it on with a legal basis the investigator types in; it's stored and audited, and turning it off is audited too.
  - **Leads, never evidence.** A face result is one capped reason in the matcher. The report shouldn't cite it as proof of identity.
  - **1:1 only.** The case's own reference photos are compared with that case's candidate images: profile photos, kept post media, and hits from reverse image search or a face-search plug-in, which only ever get *verified* here. No face index, no searching by face, nothing compared across cases.
  - **No templates kept, not even in a temp file.** Embeddings live in memory for one call; OpenCV runs both models in memory. The case stores only the result (match, score, quality numbers, which image), the reference photo itself (as evidence), and the audit trail. All of it is deleted with the case.
  - **Hard cases go to the investigator.** No face, several faces, a small, blurred or turned face, a drawing or animal, or a probable child (judged by CLIP, and never compared) come back "unclear" with the reason.
  - **Never a verdict alone.** The match is one capped reason in the matcher and can't be the second identifier.
  - **Models:**
    - YuNet: MIT.
    - AuraFace v1: Apache-2.0. Its `glintr100.onnx` hash differs from InsightFace's.
    - Not used: the other files in AuraFace's repository (`genderage.onnx`, `scrfd_10g_bnkps.onnx`). They're byte-identical to InsightFace's non-commercial pack.
  - **Still on the investigator, not the software:** Illinois BIPA (and Texas CUBI, Washington RCW 19.375) require notice and written consent, or another statutory basis, *before* a face geometry scan of an in-state person. The legal-basis field records it; Hunt can't check it. Not legal advice; confirm with counsel per jurisdiction.

### The learning store (`hunt/learning.py`)

Hunt learns from the investigator's him / not-him decisions across cases, in `~/Hunt/learning.db`, which never leaves the machine. Each decided account leaves one row:
- the decision
- the matcher's evidence pattern: bits per evidence type, e.g. `{"username": 3.1, "name": 6.5}`
- if the face check ran: its similarity score, face size in px, sharpness, yaw estimate, detector confidence, faces found, the model name, and whether the result was on screen before the decision

The key is a salted hash of case and profile URL. The store holds no names, URLs, images, face crops or embeddings.

**[I] Why those rows are not biometric identifiers or biometric data:**
- **BIPA** covers a "scan of … face geometry" (a biometric identifier) and information "based on" one that is "used to identify an individual". A row doesn't fit either:
  - A similarity score is one number about a *pair* of images. It describes neither face, can't be reversed into geometry, and can't be compared with a third face: it identifies nothing.
  - Face size, sharpness, yaw and detector confidence describe the *photo's quality*, not the person.
  - The rows are never used to identify anyone. They only tune how much a score counts.
- **GDPR Art. 4(14)** biometric data must "allow or confirm the unique identification" of a person. These numbers can't. The rows are still *personal* data while the case that made them exists:
  - The salted hash can be recomputed from the case's URLs, so a row is pseudonymous, not anonymous.
  - Once the case is deleted (90-day retention unless on legal hold), nothing links a row to anyone.
  - `hunt learning --reset` forgets everything, and `--off` stops recording.
- **The case's own `face_checks` table is different.** It ties a score to an account URL, so it *is* information derived from a face scan about an identifiable person. It's handled as case evidence: kept, exported and deleted with the case, never copied to the learning store with its URL.
- **Feedback loop:** a decision made while the face result was on screen may simply follow it. Those decisions count half in both fits, and the flag is stored so they can be re-weighted later.

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

## Hunt's rules

_The single current statement, as of 2026-10-29. It replaces the earlier "Guardrails Hunt ships" list and folds in the guardrail changes from [automation-legal.md §5](automation-legal.md#5-guardrail-changes). The sections above, and the linked research, keep the reasoning behind each rule._

Disclaimers alone are not enough: the FTC has said so, and OpenOSINT was criticised for shipping a disclaimer without guardrails. These rules are real features, or are being built as real features (see "Not yet enforced" below).

"Login-walled platform" means Facebook, Instagram, Threads, X, LinkedIn, Reddit, Strava, Snapchat, and TikTok whenever she is signed in.

### Collection

| # | Rule | Why | Reasoned in |
|---|---|---|---|
| C1 | **No software-caused request to a login-walled platform.** Every page load, scroll, click and "See more" there comes from her own input in the Hunt Browser. Hunt and Hunt Capture only record what has already loaded. No auto-scroll (not even one she starts and watches), auto-expand, auto-advance or "open all" | Passive recording isn't CFAA "access"; active requests from inside a session are the *BrandTotal* line. Every platform's terms ban automated access, with no own-account or human-pace exception. A bot is the surest way to lose her account | [automation-legal.md Q1](automation-legal.md#q1-automating-her-own-logged-in-account), [Q2](automation-legal.md#q2-grey-zones) |
| C2 | **Hunt's code never logs in or uses her session.** The Hunt Browser holds her sessions for her own browsing only: no automation driver, no remote-debugging port, no automation flags. Hunt never reads her cookies, only whether she is signed in | No program can drive her account through Hunt, and nothing marks her browser as automated | [Human-driven capture](#human-driven-capture-hunt-capture-browser-extension), [capture.md](../capture.md#the-hunt-browser) |
| C3 | **Her own real account only.** No fake, shared, bought or borrowed account, and no second account after a ban | Fake accounts drove hiQ's $500k judgment and the *Voyager* settlement. After revocation, another account is "the back door" (*Nosal*). Online impersonation is a crime in CA (Penal Code §528.5) and TX (§33.07) | [CFAA, scraping, platform ToS](#cfaa-scraping-platform-tos), [automation-legal.md Q1](automation-legal.md#q1-automating-her-own-logged-in-account) |
| C4 | **Never contact the subject or their associates.** No follow, friend, connection request, like, comment, message or story reaction. No email or username check that could notify anyone. Treat every claimant as represented by counsel | Ethics Rules 4.2 and 4.3 bind Ethos's work through counsel (NJ codified it in 2024). FCRA §1681d covers interviews "by electronic means" | [automation-legal.md Q3](automation-legal.md#q3-investigator-rules), [user-scanner audit](../../hunt/sources/user_scanner.py) |
| C13 | **Associates are minimised.** An associate found in the case (a relative in a caption, a tagged friend, a co-party) is a name and the evidence naming them, nothing more. Hunt never searches or collects on them: the investigator opens a separate case, with its own recorded purpose, to do that. A possible minor (a child, grandchild, niece or nephew, or anyone given an age under 18) is shown by relationship only: no name, redacted quotes | Data minimisation (GDPR Art. 5(1)(c), CCPA §1798.100(c)); third parties never consented and aren't the subject of the permissible purpose | [analysis.md §8](../analysis.md#8-family-and-associates) |
| C5 | **No pretexting.** Never a false identity or a false purpose, with anyone | Pretext-interview bans (NAIC Model 670; Cal. Ins. Code §791.03), PI licence "fraud or deceit" grounds, Rule 8.4(c) | [automation-legal.md Q3](automation-legal.md#q3-investigator-rules) |
| C6 | **Logged-out reads follow robots.txt.** Automatic reads only where robots.txt allows: TikTok profile and video pages, Bluesky, Mastodon and the public APIs. Hosts that deny unnamed agents (Facebook, Instagram, Threads, LinkedIn, X, Reddit) get one page on her click: never in batch, never on a schedule, never as headless screenshots. Honest User-Agent and a polite gap | robots.txt isn't access authorisation (RFC 9309), but Meta, YouTube and Reddit write it into their terms. *Bright Data* protects logged-off reads less for an account holder | [automation-legal.md Q5](automation-legal.md#q5-logged-out-automation-per-platform-robotstxt-rate-limits-captchas) |
| C7 | **Never get around a limit.** No CAPTCHA solving. No proxies, IP rotation, or header, User-Agent or fingerprint spoofing to get past a block. No randomised "human-like" pacing. Stop at the first 429, CAPTCHA or login wall. (`HUNT_PROXY` is one fixed proxy she chooses for her own privacy. It is never switched to get past a block.) | CAPTCHA circumvention supported a DMCA §1201 injunction (*Ticketmaster v. RMG*). Proxies after a block were "without authorization" (*3Taps*). TikTok and Meta terms ban "tricks" and circumvention | [automation-legal.md Q2](automation-legal.md#q2-grey-zones), [Q5](automation-legal.md#q5-logged-out-automation-per-platform-robotstxt-rate-limits-captchas) |
| C8 | **Hard stop on revocation.** A ban, disabled account, checkpoint, "automated behaviour" warning, action block, CAPTCHA, IP block, or a platform letter to Laura, Ethos or Aaron stops capture and automatic reads on that platform. It is audited, and she tells Ethos. Never fall back to another account, browser profile, proxy or vendor | After revocation, continued access is a CFAA and Cal. Penal Code §502 violation (*Power Ventures*), and a PI licence ground in FL (§493.6118(1)(k)) | [automation-legal.md Hard stops](automation-legal.md#hard-stops), [Appendix B](automation-legal.md#appendix-b-hard-stop-message) |
| C9 | **Capture off on LinkedIn, Strava and Snapchat.** There she saves pages or screenshots by hand and imports them | Their terms name browser extensions or "semi-automated" tools, and LinkedIn scans for extensions | [automation-legal.md Q2](automation-legal.md#q2-grey-zones) |
| C10 | **Warn before a view the subject can see.** Before an Instagram or Facebook Story while signed in; on LinkedIn, browse logged out or in private mode, with a warning on repeat views of one profile | New York ethics guidance treats a "who viewed you" notice to a represented person as a possible communication. Colorado flags repeated viewing | [automation-legal.md Q3](automation-legal.md#q3-investigator-rules) |
| C11 | **No official API where its terms bar this work.** No Meta, TikTok, LinkedIn, Reddit or Strava API connectors for claimant work. YouTube through the Data API on her own key. X only with X's written approval | Meta Platform Terms §3.a.ii bar "eligibility determinations … including for … insurance". LinkedIn API Terms §3.1(17), (19); X Developer Agreement §XIV.B(a) | [automation-legal.md Q4](automation-legal.md#q4-official-apis-and-licensed-vendors) |
| C12 | **Vendor connectors** are optional and off by default. Her own key only, never a bundled one. Provenance on every record; the vendor's permitted-use terms on file | With her key, Ethos is the licensee and the project isn't. A "public data" label isn't proof of lawful collection (*Voyager*) | [automation-legal.md Q4](automation-legal.md#q4-official-apis-and-licensed-vendors) |

### The case

| # | Rule | Why | Reasoned in |
|---|---|---|---|
| K1 | **A purpose on record before any search,** and the case's kind: claim, or employment and eligibility. Background cases carry the FCRA disclaimer. The report's screening version drops protected traits and the sources that reveal them. She confirms the subject's identity before anything reaches an employment report | Claims reports aren't consumer reports; anything used "in whole or in part" for eligibility is | [FCRA](#fcra), [automation-legal.md Q3](automation-legal.md#q3-investigator-rules) |
| K2 | **Audit log** of every query, capture, import, worklist open, hard stop and export | Retraceable method; GLBA/DPPA-style accountability | [Knogin](https://knogin.com/api/docs/modules/analyst-driven-osint) [S] |
| K3 | **Audience flag.** Anything not shown as Public is flagged and kept out of the report unless counsel approves | The CCPA, Virginia and Texas "publicly available" exclusions stop at content "restricted … to a specific audience" | [automation-legal.md Q6](automation-legal.md#q6-privacy-and-biometric-law) |
| K4 | **Scan everything, report what's material.** Scan hits are leads that she confirms, never findings on their own | Insurers may not seek information "not reasonably required" (10 CCR §2695.7(d)); FCRA accuracy (§1681e(b)) | [automation-legal.md Q3](automation-legal.md#q3-investigator-rules) |
| K5 | **A capture record and separate attribution.** Hash at capture, URL, UTC time, the account it was viewed from, the audience shown and the tool version. Who runs the account is shown separately from what it posted | FRE 902(13) and (14); *Vayner* and *Browne* on authorship | [automation-legal.md Q3](automation-legal.md#q3-investigator-rules), [Appendix A](automation-legal.md#appendix-a-evidence-bundle-readme-paragraph) |
| K6 | **Retention:** 90 days from opening, unless she sets a legal hold. Deleting moves the case to the Trash | Minimisation | [api.md](../api.md) |
| K7 | **Minors:** children in pictures are blurred in the scan | No published standard; our own rule [I] | — |
| K8 | **Per-source rate limits;** stop on 429 (C7) | Courtesy, and the terms | — |

### Faces, health and subjects abroad

| # | Rule | Why | Reasoned in |
|---|---|---|---|
| F1 | **No face search.** A face check, if offered, is 1:1 against her own reference photo, with no template written to disk | A face scan is never "publicly available" under the CCPA; the EU AI Act bans untargeted face scraping | [Biometrics](#biometrics-relevant-to-photo-features), [automation-legal.md Q6](automation-legal.md#q6-privacy-and-biometric-law) |
| F2 | **The face check is gated on where the subject lives;** unknown means blocked. Blocked: IL, TX, WA, CO, the EU, the UK and Canada, and CA unless Ethos's counsel accepts the legal-claims exemption | BIPA has no investigator exemption. Texas's TRAIGA fraud exclusion is untested | [automation-legal.md Q6](automation-legal.md#q6-privacy-and-biometric-law) |
| F3 | **Washington subjects:** record the My Health My Data fraud basis per case. Word findings as observed activity, not physical condition | Health inferences from non-health data are "consumer health data"; the firm bears the burden of the exemption | [automation-legal.md Q6](automation-legal.md#q6-privacy-and-biometric-law) |
| F4 | **EU, UK and Canadian subjects:** a per-case legal basis and a record of why the subject wasn't notified | GDPR Art. 3(2)(b), 6(1)(f), 14(5)(b); DPA 2018 Sch. 2 para 2; PIPEDA s.7(1)(b) | [automation-legal.md Q6](automation-legal.md#q6-privacy-and-biometric-law) |

### Associates and family

_Added 2026-10-29, for the associates map (built from what's already in a case) and for captured comments._

An **associate** is anyone in the case other than the subject: a commenter, someone tagged, a person named in a caption or bio, someone with a shared surname, or a co-party in a public record. They didn't ask to be in an investigation, and nobody has a purpose on record for them.

**Why it matters [S]:**
- **FCRA.** A consumer report bears on a person's "character, general reputation, personal characteristics, or mode of living" ([15 U.S.C. §1681a(d)(1)](https://www.law.cornell.edu/uscode/text/15/1681a)). Who someone keeps company with is that kind of content.
- **FCRA interviews.** Information obtained "through personal interviews with neighbors, friends, or associates" makes a report an *investigative* consumer report (§1681a(e)), with its own disclosure duty ([§1681d](https://www.law.cornell.edu/uscode/text/15/1681d)).
- **Associates' own rights.** Associates are consumers and data subjects in their own right. Collection must be "reasonably necessary and proportionate" to its purpose ([Cal. Civ. Code §1798.100(c)](https://california.public.law/codes/civil_code_section_1798.100); GDPR Art. 5(1)(b)–(c)).
- **Claims.** Insurers may not seek information "not reasonably required" for the claim ([10 CCR §2695.7(d)](https://www.law.cornell.edu/regulations/california/10-CCR-2695.7)).

| # | Rule | Why | Reasoned in |
|---|---|---|---|
| A1 | **Built only from what's already in the case:** captions, captured comments, tags, bios, shared surnames, public-record co-parties. No search on an associate: no username, name, email, phone, records or face search, no Check again, no watch. A person is searched only as the subject of their own case, with its own purpose | Purpose limitation and proportionality (above) | This section |
| A2 | **Name plus citing evidence, nothing else.** An entry holds the name or handle as shown, how they appear (commented, tagged, named, shares a surname, co-party), and the ids of the items that show it. None of their address, phone, email, date of birth, employer, photos or profile details | Minimisation. An associate's home address may be a Daniel's Law covered person's: the definition includes "any immediate family member residing in the same household" of a judge, prosecutor or officer [S] ([N.J.S.A. 56:8-166.1](https://law.justia.com/codes/new-jersey/title-56/section-56-8-166-1/)) | [State laws](#state-laws) |
| A3 | **Their posts only as evidence about the subject.** She may open an associate's public posts to find the subject (tagged, shown or mentioned). Only items that show or mention the subject are kept, scanned or reported. A comment is quoted in a report only when it bears on the dispute (K4) | Same | This section |
| A4 | **Never contact or notify an associate** (C4, C10): no requests, follows or messages. Story and profile-view warnings apply on their accounts too | Interviewing an associate turns a screening into an investigative consumer report (§1681a(e), §1681d). Ethics Rule 4.3 covers unrepresented persons; pretexting rules (C5) | [automation-legal.md Q3](automation-legal.md#q3-investigator-rules) |
| A5 | **Minors are never named.** A child appears as "a child", or by initials where counsel needs a reference. No entry beyond that, nothing collected about them, never face-compared (F1), and blurred in the app (K7) | Federal court filings may include only "the minor's initials" [S] ([Fed. R. Civ. P. 5.2(a)(3)](https://www.law.cornell.edu/rules/frcp/rule_5.2)), and reports become exhibits. 5.2 exempts administrative records such as most workers' comp hearings, so the wider rule is ours [I] | This section |
| A6 | **The report states what was observed, cited. It never asserts a relationship.** It says "@mara_q commented 'proud of you, son' on the subject's 3 May post [E-12]", not "Mara Quill is his mother". Hunt never generates a relationship label. A shared surname is never a relationship: at most "shares the surname", and only where it supports identity (A7). The investigator's own conclusion appears only as her note (`N-`), in her words | FCRA accuracy (§1681e(b)); ICD 203 keeps information apart from judgment. A wrongly asserted relationship about a named third party invites a defamation or false-light claim [I] | [Report format §8](report-format.md) |
| A7 | **Associates support identity, never findings about themselves.** A relative's cited interaction can help show an account is the subject's, as report-format.md §8 lists relatives among identity identifiers. Nothing about an associate's own life is a finding | Purpose limitation | [Report format](report-format.md) |
| A8 | **Employment screening names no associates.** Identity support cites item ids without naming or describing the person. The screening filter must drop relationship sentences outright: the `PROTECTED` regex in `report.py` matches "married" but not "wife", "son" or "mom" | Relationships reveal protected traits: marital and familial status ([Cal. Gov. Code §12940(a)](https://california.public.law/codes/government_code_section_12940); [N.Y. Exec. Law §296(1)(a)](https://www.nysenate.gov/legislation/laws/EXC/296)), and association with a disabled person ([42 U.S.C. §12112(b)(4)](https://www.law.cornell.edu/uscode/text/42/12112)) [S]. GINA's public-sources exception excludes "social networking sites" and intentional searches, so family medical history from social media is a GINA risk [S] ([29 C.F.R. §1635.8(b)(4)](https://www.law.cornell.edu/cfr/text/29/1635.8)) | [FCRA](#fcra), `seen.py` (screenings stay apart) |
| A9 | **An associate's own health or other sensitive details are never kept.** A comment about the *subject's* health is about the subject; for a Washington subject it follows F3 | MHMDA; CCPA sensitive personal information; GINA in screenings | [automation-legal.md Q6](automation-legal.md#q6-privacy-and-biometric-law) |
| A10 | **Associates stay in their case.** They are never identifiers in "Have we seen this person before?" (`seen.py` compares only the subject's; keep it that way), never in the learning store, and are deleted with the case (K6) | Linking third parties across cases would build files on people no case is about [I] | [qol.md](../qol.md) |

### Not yet enforced (main at `9b3ee7a`, 2026-10-29)

Built since `099144c`:
- Check again's worklist for login-walled accounts (`recheck.NO_BOTS`)
- the revocation watcher and the Story warning in Hunt Capture
- capture never on LinkedIn, Strava or Snapchat
- the capture record
- the face gate and MHMDA mode

Still open:
- **C6:** `sources/facebook.py` still runs in every batch search ("Read public preview" is listed as coming next). `search.screenshot` still takes headless screenshots of every likely account, Facebook, Instagram, X and LinkedIn included.
- **C6, C11:** `posts.YT_RSS` reads `/feeds/videos.xml`, which YouTube's robots.txt disallows.
- **F4:** no per-case basis record. EU, UK and Canadian subjects are blocked from the face check for that reason, and collection on them has no record either.
- **A1–A10:** the associates map is being built. A8's relationship filter is not in `report.py` yet.
- **C8 with C12:** the scan route in `app.py` calls `vendor.collect` without checking `browser.stops()`. After a hard stop on Instagram or Facebook, the next scan still reads that platform through Apify, the vendor fallback C8 forbids. The fix is to skip a stopped platform's accounts in `vendor.collect`, or before the call, and to note why. Otherwise the Apify connector meets C12 as documented in [vendors.md](vendors.md): no shipped key, off until a key is added, `origin: vendor`, and each run audited.
- **Not checked here:** whether non-Public items are kept out of reports by default (K3), and the LinkedIn view warning (C10).

## FBI / IC portfolio relevance

- The FBI analyst process includes a timed writing test simulating intelligence products ([fbijobs.gov](https://fbijobs.gov/intelligence-analysts)).
- The IC OSINT Strategy 2024–2026 aims to professionalise tradecraft ([ODNI](https://www.dni.gov/index.php/newsroom/reports-publications/reports-publications-2024/3785-the-ic-osint-strategy-2024-2026)).
- Hiring managers prefer "how you investigated X, overcame Y, found Z" stories ([osintme](https://osintme.com/index.php/2022/06/19/getting-a-job-in-osint-interview-with-lorand-bodo/)).
- **[I] Strongest signals for Hunt:** ICD 203 confidence language, provenance and hashing, built-in legal and ethical guardrails, and a written methodology. A public doxxing-style site could hurt a suitability review.
