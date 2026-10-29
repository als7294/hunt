# Report format: how insurance and online-activity investigation reports are laid out

_Research date: 2026-10-29. Public sources only. No firm's branding, logo or template text is reused: the
structure below is generic, and each investigator sets their own firm name, investigator name and licence number._

**How solid this is:**
- One complete published sample social media report exists: Compex Legal's, 26 pages [S1].
- One insurer SIU manual publishes its vendor report standards: Allied Universal's, inside Companion Life's 2023
  SIU manual, pp. 34–43 [S2].
- The rest comes from statutes, court rules, case law, the Berkeley Protocol and vendor descriptions.
- "Universal" below is a reading of those sources, not a survey.

## The usual structure

| # | Section | What it carries | How common |
|---|---|---|---|
| 1 | Header | Report title; client (carrier or TPA); adjuster or requestor; claim number and the investigator's file number; claimant; date of loss or injury; assignment date; report date; investigator; licence number; agency | Universal; licence number common [S1, S2] |
| 2 | Synopsis | Accounts found, key observations, a one-line result | Universal; S2 wants it on page 1 [S1, S2] |
| 3 | Assignment and scope | What was asked; platforms in scope; special instructions; budget | Universal [S1, S2] |
| 4 | Subject identifiers | What the client supplied vs. what the search developed: name, date of birth, aliases, phones, addresses, relatives, employer | Universal [S1, S2] |
| 5 | Methodology / search log | Sources and platforms checked, including "no account found"; search terms; the date, day and start and end time of each work session; tools; who collected; a public-only statement | Strongly advised [S2, S5] |
| 6 | Online presence table | Platform, URL, username, public or private, last visible activity, match confidence, relevant yes/no | Common practice, not required [S1] |
| 7 | Findings by platform | One subsection per account: how it was matched, the link, neutral observations, exhibit references | Universal [S1] |
| 8 | Identity confirmation | Per account: which identifiers tie it to the claimant (photo against the file photo, date of birth, location, relatives, employer, username reuse, linked email or phone) and how confident. Name-only matches are labelled as such | Universal [S1, S6, S9] |
| 9 | Conclusion / recommendations | Only further investigative steps, e.g. surveillance dates and places suggested by the posts. No fraud opinions | Optional; S2 limits it this way [S2, S4] |
| 10 | Status / closing | File closed; full captures kept and available on request | Common [S1] |
| 11 | Certification / signature | Signer, licence number, date, a statement of diligence and accuracy | Common; mirrors CA BPC 7539(c) [L1] |
| 12 | Disclaimers | See below | Universal [S1] |
| 13 | Exhibits | Numbered captures with their metadata, inline or appended | Universal [S1, S2] |

**Wording.** Facts only. No opinions, no words like "pain", and nothing implying fraud [S2]. Public content only:
no friending, following or contact [S3, S4, S10].

## Exhibits and capture metadata

- **Numbering:**
  - There's no universal rule. Courts commonly have plaintiffs number exhibits and defendants letter them [S11], and
    multi-page exhibits are page-numbered 1-1, 1-2 [S12].
  - Bates numbering belongs to document production, not to investigator reports.
  - The practical default is sequential "Exhibit 1…n", cited inline, with an index.
- **Per capture:**
  - The Berkeley Protocol ¶155 minimum is the URL, the page's HTML source, and a full-page capture with its date and time.
  - Best practice adds platform metadata (post ID, upload time), context, and who collected it and when, with a hash
    applied at collection [S5].
  - Every capture carries two dates: the post date as displayed, and the capture time. An ISO 8601 time with its
    UTC offset avoids time-zone doubt (our choice; no source mandates one).
- **Authentication:**
  - FRE 902(13)/(14) allow self-authentication by a qualified person's certification, and hash matching shows an exact
    copy [S8].
  - A page capture proves what the page said, not who wrote it. *Vayner* (2d Cir. 2014) held that a name, photo and
    biographical details alone did not attribute a profile [S6]; *Browne* (3d Cir. 2016) agrees [S7].
  - So the identity section matters as much as the screenshots.
- **Chain of custody.** S2 requires custody forms, secure originals, and no copies without the client's permission.

## What the rules require

- **Licence numbers.** No state checked requires the licence number on the investigative report itself (UNVERIFIED for
  each state). The rules cover advertising, contracts and bids:
  - CA: BPC 7534 (ads), 7524 (the written agreement must show the licence and say how a report will be delivered),
    and 7539 (no false reports; reports in the licensee's name; diligence) [L1–L3].
  - TX: 37 TAC §35.9 (ads) [L4].
  - FL: §493.6111(6) (ads and written bids) [L6].
  - NY: GBL Art. 7 (no false reports; licensed name only) [L8].
  - IL: 225 ILCS 447/35-15 (ads) [L9].
  - GA: Rule 509-4-.08 (ads) [L10].

  Printing it in the header is good practice; Hunt prints whatever the investigator enters.
- **No pretexting:**
  - GLBA (15 USC 6821) and 18 USC 1039 bar obtaining financial and phone records by false pretences [L11, L12].
  - SIU standards bar misleading pretext with claimants [S2].
- **No friending or following:**
  - NYSBA Op. 843 and NYC Bar 2010-2 allow viewing public pages but not friending, directly or through an agent [E1, E2].
  - ABA Formal Op. 466 treats an access request as a communication [E3].
  - Claimants are usually represented by counsel.
- **FCRA:**
  - Reports used only to assess a claim aren't consumer reports [F1].
  - A social media screening report sold to employers is [F2].
  - Employment use brings obsolete-item limits, disclosure, and accuracy duties [F3–F5].
  - So: screening mode drops protected characteristics, and a background case carries an FCRA caution.

## Disclaimers and certification (in our own words)

- **Confidentiality:** prepared for the named client and claim only; not for redistribution. A work-product label is
  only for work at counsel's direction, and routine claim files are often discoverable anyway [E7].
- **Not a consumer report:** not for credit, underwriting, employment or housing decisions [S1, F1].
- **Method:** public content only, viewed logged out; nobody followed, friended or contacted; private accounts noted,
  not accessed.
- **Point in time:** content can change or vanish after capture; dates are as each platform shows them [S1].
- **Certification:** the signer personally conducted or supervised the work and, after diligent inquiry, believes the
  facts true and correct, with printed name, licence number, date and signature [L1]. For court, add a declaration in
  28 USC 1746 form [L13] or an FRE 902(13)/(14) certification [S8].

## What Hunt's report does with this

`hunt/report.py`; API in `docs/api.md` ("Report", "Report settings").

- **Header** (1): the investigator's settings (firm, investigator, licence, contact, logo, time zone,
  confidentiality line) plus the case's client, adjuster, claim number, file number, subject, date of birth, date of
  loss, assignment and report dates.
- **Synopsis** (2), **assignment and scope** (3): the assignment, the case type, the identifiers supplied (seeds and
  date of birth), what to look for, the stated restrictions, the date of injury.
- **Search methodology** (5): who ran the searches, when (day, date, time and zone), with which tool and version, and
  logged out. Then each source per seed, latest run shown, with its time and result. Also the captures, the post
  collection and scan, and the files added by hand.
- **Online presence** (6): the table, plus the most recent public post found.
- **Identity confirmation** (8): for each account, what tied it to the subject, without weights. Also the
  investigator's dated decision, accounts ruled out, namesakes, identifiers developed during the search (other
  usernames), and accounts resting on a single identifier.
- **Findings** (7): the items the investigator kept, grouped by platform, each "Exhibit n" with its post date, how long
  after the date of injury, what it shows, the category it relates to, and the machine reading capped at "likely".
- **Conclusion and recommendations** (9, 10):
  - the date range the kept items cover;
  - a weekday pattern turned into a surveillance suggestion, cited to those items;
  - the investigator's own recommendation;
  - the "likely" ceiling;
  - originals kept and available as an evidence bundle.
- **Limitations** (what we couldn't see): sources that don't search a kind of detail, failed sources, platforms whose
  posts aren't read (login-only or private), email registrations with no public profile, items ruled out, undated
  items, the point-in-time caveat, and that public records weren't searched.
- **Disclaimers** (12), **certification** (11), **Appendix A: Exhibits** (13), **Appendix B: Search and case log**.
  - Each exhibit gets its own page with its evidence-bundle file name, SHA-256, page source, URL, account, posted and
    captured times (local and UTC), relevance, and the image.
  - The log lists every method citation.
- **Kept guarantees:** every sentence is cited; machine readings stay at "likely" or below; neutral "a person matching
  the details supplied" until an account is confirmed; exports re-hash every evidence file. Screening mode drops
  protected characteristics, the date of birth, the date of loss, injury items and screenshots.

## For the frontend (report screen and wizard)

The main session owns `hunt/static/`; these are the pieces to wire.

**Wizard inputs** (all optional; send them in `POST /api/cases`):
- client: the carrier, TPA or law firm
- adjuster
- claim number: already `reference`
- file number: the investigator's own
- assignment date
- subject's date of birth
- date of injury or loss: already `injury_date`

They can also be filled in later with `POST /api/cases/{slug}/details`.

**Report settings form** (once per investigator; `GET`/`POST /api/settings`):
- firm, investigator, licence number, contact line
- time zone: a select of IANA names; it defaults to this computer's
- confidentiality line: it has a default
- logo upload: `POST /api/settings/logo` with a `file` field, PNG or JPEG only; "remove" sends `{logo: null}`

Surface `checks.missing` as to-dos that open this form, or the case details.

**Report screen:**
- **Sections:** render `sections` in order. The ids changed: `summary`, `scope`, `method`, `presence`, `identity`,
  `found`, `conclusion`, `couldnt_see`, `disclaimers`. The old `confidence` id is gone; its content is now in
  `identity` and `conclusion`.
- **Findings:** sentences carry `platform`; head each group.
- **Header:** show `header` as a two-column block at the top. Hide null fields (screening nulls `subject_dob` and
  `injury_date`).
- **Online presence:** under that section, render `presence` as a table: #, Platform, Username, URL, Public/private,
  Last activity, Relevant, Status, Exhibit.
- **Exhibits:** `exhibits` replaces the evidence list. Show "Exhibit n", the bundle file name, platform, the posted and
  captured times, and a View link to `/evidence/<slug>/<basename of file>`.
- **Citation chips:** print `E-`/`A-` ids that have an exhibit as "Ex. n" (look the id up in `exhibits`), other `A-`
  ids as "Acct. n" (`presence[].row`), and `M-` ids as "Log n" (the position in `log`, 1-based).
- **Certification:** render `certification` as a block with a signature line.

## Sources

- S1 Compex Legal sample social media report: https://www.compexlegal.com/hubfs/CPX%20-%20Sales%20-%20Documents/Social%20Media%20Canvassing%20Sample%20Report.pdf
- S2 Companion Life 2023 SIU manual (Allied Universal vendor standards): https://www.companionlife.com/images/uploads/documents/Companion_Life_2023_SIU_Policies_and_Procedures_Manual.pdf
- S3 Bricker Graydon on social media in workers' comp: https://www.bricker.com/insights/publications/Using-social-media-to-detect-workers-compensation-fraud
- S4 Ethos Risk Services, what a social media investigation is: https://ethosrisk.com/blog/what-is-a-social-media-investigation-and-why-does-it-matter/
- S5 Berkeley Protocol on Digital Open Source Investigations: https://www.ohchr.org/sites/default/files/2024-01/OHCHR_BerkeleyProtocol.pdf
- S6 United States v. Vayner (2d Cir. 2014): https://www.leagle.com/decision/infco20141003047
- S7 United States v. Browne (3d Cir. 2016): https://cases.justia.com/federal/appellate-courts/ca3/14-1798/14-1798-2016-08-25.pdf
- S8 Federal Rule of Evidence 902: https://www.law.cornell.edu/rules/fre/rule_902
- S9 UNC School of Government on social media authorship: https://www.sog.unc.edu/blogs/nc-criminal-law/how-can-party-show-authorship-social-media-post-or-other-electronic-communication-0
- S10 Hodson PI in Claims Journal: https://www.claimsjournal.com/sponsored/hodsonpi/2026/08/10/339321.htm
- S11 D. Vt. Local Rule 40.0: https://www.courtrules.net/courts/federal/district-vermont/local-rules/rule-40-0
- S12 N.D. Ohio civil jury trial order: https://www.ohnd.uscourts.gov/sites/ohnd/files/DCN-civiljurytrialorder.pdf
- L1 Cal. Bus. & Prof. Code §7539: https://california.public.law/codes/business_and_professions_code_section_7539
- L2 Cal. Bus. & Prof. Code §7524: https://california.public.law/codes/business_and_professions_code_section_7524
- L3 Cal. Bus. & Prof. Code §7534: https://california.public.law/codes/business_and_professions_code_section_7534
- L4 37 Tex. Admin. Code §35.9: https://www.law.cornell.edu/regulations/texas/37-Tex-Admin-Code-SS-35-9
- L6 Fla. Stat. §493.6111: https://www.flsenate.gov/Laws/Statutes/2025/493.6111
- L8 NY licensing law (GBL Art. 7): https://dos.ny.gov/system/files/documents/2026/03/pi-bea-wgp-sg-licensing-law_03.2026.pdf
- L9 225 ILCS 447/35-15: https://codes.findlaw.com/il/chapter-225-professionsoccupations-and-business-operations/il-st-sect-225-447-35-15/
- L10 Ga. Comp. R. & Regs. 509-4-.08: https://www.law.cornell.edu/regulations/georgia/Ga-Comp-R-Regs-R-509-4-.08
- L11 15 USC 6821: https://www.law.cornell.edu/uscode/text/15/6821
- L12 18 USC 1039: https://www.law.cornell.edu/uscode/text/18/1039
- L13 28 USC 1746: https://www.law.cornell.edu/uscode/text/28/1746
- E1 NYSBA Ethics Opinion 843: https://nysba.org/ethics-opinion-843/
- E2 NYC Bar Formal Opinion 2010-2: https://www.nycbar.org/pdf/report/uploads/20071997-FormalOpinion2010-2.pdf
- E3 ABA Formal Opinion 466 (reported): https://www.abajournal.com/news/article/jurors_electronic_social_media_ethics_opinion
- E7 Discoverability of claim-file surveillance: https://www.wilsonelser.com/publications/nevada-clarifies-discovery-of-surveillance-in-claim-file
- F1 FTC, 40 Years of Experience with the FCRA: https://www.ftc.gov/sites/default/files/documents/reports/40-years-experience-fair-credit-reporting-act-ftc-staff-report-summary-interpretations/110720fcrareport.pdf
- F2 FTC closing letter, Social Intelligence Corp.: https://www.ftc.gov/sites/default/files/documents/closing_letters/social-intelligence-corporation/110509socialintelligenceletter.pdf
- F3 15 USC 1681c: https://www.law.cornell.edu/uscode/text/15/1681c
- F4 15 USC 1681d: https://www.law.cornell.edu/uscode/text/15/1681d
- F5 CFPB withdrawn guidance: https://www.consumerfinance.gov/compliance/guidance/withdrawn-guidance/
