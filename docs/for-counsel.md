# Hunt: a summary for counsel

_For Ethos Risk Services' counsel, from the investigator who uses Hunt. It describes the software as of 2026-10-29. Items marked "(being built)" are decided and specified but not yet in the released version. This is a description of a tool and its rules, not legal advice. The research behind it is in [automation-legal.md](research/automation-legal.md) and [legal.md](research/legal.md)._

## 1. What Hunt is

- **Software, not a service.** Hunt is open-source software (AGPL-3.0, [github.com/als7294/hunt](https://github.com/als7294/hunt)) that runs on the investigator's own computer. There is no Hunt server: the developer never receives case data, and the code can be reviewed.
- **What it does.** From a few details, it finds a subject's public accounts, gathers their posts, photos and videos, and scans them for what a claim disputes, such as sport after an injury date. Then it drafts a report.
- **Who decides.** The investigator. She confirms every account and every hit before it reaches a report.

## 2. What it collects, and how

| Source | How | Who causes each request |
|---|---|---|
| Public sites and APIs: Bluesky, Mastodon, YouTube, TikTok public pages (being built), public records (FEC, SEC, professional licences, business registries, motor carriers, court dockets), the Wayback Machine | Read automatically, without signing in. A User-Agent naming Hunt, rate limits, and a stop at the first refusal | Hunt |
| Username and email checks on hundreds of sites | Does an account exist? Any check that could alert the account holder (password reset, login code, sign-up) is excluded; each module was read and classified | Hunt |
| Facebook, Instagram, X, and TikTok when signed in | She browses herself in a separate browser window (the "Hunt Browser"), signed in to her own account. An extension ("Hunt Capture") records what she views: screenshots, the page as loaded, and, on her click, a recording of a video she plays | **She does.** The extension sends nothing to the platform and never loads, scrolls, clicks or opens anything |
| LinkedIn, Strava, Snapchat | Capture off; she saves pages or screenshots by hand and imports them | She does |
| Instagram and Facebook through Apify, a data vendor (optional) | Only if she or Ethos adds their own Apify key. Apify reads the confirmed accounts' public posts under its own terms, which make the customer responsible for the data's legality and indemnify Apify (§5.8, §11.1). Each post is marked as obtained through Apify, and each run is audited with its cost | The vendor, at her request |
| Her own files | Uploads, and files from her Downloads folder | She does |

Hunt then hashes and stores each file, extracts the posts, and scans the media with AI models on her computer. Rechecks over the life of a claim, by hand or on a schedule, run automatically only on public sources whose robots.txt allows it. Login-walled accounts go on a list she opens herself. During a search, Hunt also reads the public preview of a Facebook profile and screenshots likely profiles' public pages, without signing in. Both are being limited to her click (being built).

## 3. Authorisation and platform terms

- **Hunt never logs in and never drives her account.** It doesn't read her passwords or cookies; it only asks whether she is signed in. The Hunt Browser has no automation driver or remote-control port.
- **Her own real account only.** No fake, shared, bought or borrowed accounts, ever.
- **No getting around limits.** No CAPTCHA solving. No proxies, IP rotation, or header or fingerprint spoofing to get past a block. Hunt stops at the first refusal.
- **Hard stop.** On any sign that a platform is limiting her account, Hunt stops recording that platform until she resumes it. It tells her not to use that account for casework and to tell Ethos. The signs: a security check or challenge, a "suspected automated behaviour" warning, an action block, a CAPTCHA, or a disabled account. Hunt never falls back to another account, browser or network.
- **The remaining risk is contractual.** Meta's and TikTok's terms bar collecting data "using automated means" without permission, and a platform could argue that an extension that records automatically does that. On present case law, recording what her browser already received is not unauthorised access (*Van Buren*, 2021; *Meta v. BrandTotal*, N.D. Cal. 2022). The exposure is to her account (a ban), not criminal. A manual mode ("only when I press Capture") is the same act as taking a screenshot.
- **Rejected:** a bot that drives her account. It plainly breaches every platform's terms and is the likeliest way to lose the account.

## 4. Contact and deception

- **Never contacts the subject or their associates:** no friend or follow requests, likes, comments, messages or story reactions.
- **No pretexting:** never a false identity or a false purpose.
- **Notifications.** Before a Story opens while she's signed in to Instagram or Facebook, Hunt asks first, because Story viewers can see who watched. On LinkedIn, Hunt advises browsing logged out or in private mode (being built). Hunt treats every claimant as represented.

## 5. Privacy

- **Public content.** Anything a platform shows with an audience other than Public is flagged and left out of the report unless counsel approves (being built).
- **No face search.** An optional face check compares her own reference photo with candidate profile photos, one to one, and stores no face template. It is blocked unless the subject's home state or country is known and allowed. Blocked: Illinois, Texas, Washington, Colorado, California, the EU, the UK and Canada.
- **Associates** (family, friends, commenters, co-parties in records): Hunt keeps only their name and the items they appear in. It never searches, contacts or profiles them, and never names a child. Reports state what was observed, with citations, never a relationship as fact; employment screenings leave associates out (being built).
- **Washington subjects:** findings are worded as observed activity, not physical condition, with the My Health My Data fraud basis recorded.
- **Retention:** a reminder at 90 days from opening, unless she sets a legal hold. Deleting a case moves it to the Trash, and the deletion log keeps no name or purpose (being built).

## 6. FCRA

Each case has one of four kinds:
- **Insurance claim:** not a consumer report, unless reused for underwriting, renewal or employment.
- **Background:** employment or eligibility, so a consumer report.
- **Due diligence:** not a consumer report when about a business transaction, but one if used for employment or eligibility.
- **Journalism:** not a consumer report.

Claims reports carry a "not a consumer report" statement, and background reports carry an FCRA notice. Background cases always get the screening version (being built), which drops protected traits, relationships and the sources that reveal them.

## 7. Evidence

- **Hashing.** Every file is hashed (SHA-256) when it enters the case and is stored under that hash.
- **The evidence bundle** holds each exhibit, a manifest, a `SHA256SUMS` file anyone can check, the full audit log and her notes.
- **Its README** describes the capture process for a certification under FRE 902(13) and (14). It is in [Appendix A](research/automation-legal.md#appendix-a-evidence-bundle-readme-paragraph).
- **Attribution is shown apart** from content, because a capture shows what was posted, not who posted it (*United States v. Vayner*, 2d Cir. 2014).

## 8. What Hunt doesn't do

Hunt never does any of these:
- log in, or drive any account;
- use a fake account or someone else's;
- contact or deceive anyone;
- solve CAPTCHAs or evade blocks;
- search by face;
- use the Meta, TikTok, LinkedIn, Reddit or Strava APIs, whose terms bar this work;
- use a data vendor on an account of its own: Apify runs only on a key she or Ethos adds;
- send case files or reports anywhere.

Only two things leave her computer. Search terms reach the sites being searched, and the confirmed account addresses reach Apify if she uses it. Place names go to OpenStreetMap to compare locations.

## 9. Questions for you

1. Do you accept the contract risk of Hunt Capture recording automatically on Facebook, Instagram and TikTok, given their "automated means" wording, or should Ethos use manual mode only? Do you agree with keeping capture off on LinkedIn, Strava and Snapchat?
2. In which states does Ethos hold agency licences? Do any insurer or SIU contracts restrict social-media methods or tools?
3. Is a claims report ever reused for underwriting, renewal or employment, which would make it a consumer report "in part"?
4. Is Ethos a CCPA "business", an insurance-support organization in states with the NAIC Model 670 privacy act, or a service provider under its insurer contracts?
5. Should every claimant be treated as represented? What is the policy on LinkedIn viewing mode and on viewing Stories while signed in, especially in New York matters?
6. Face check: Hunt blocks California. Should Ethos instead rely on the CCPA's legal-claims exemption (§1798.145(a)(1)(E))? Does Texas's new fraud exclusion (TRAIGA, effective 2026-01-01) change the Texas block? Is the classification of the four case kinds in §6 right?
7. Washington: how should Ethos document the My Health My Data fraud exemption for findings about physical capacity?
8. robots.txt: is a single lookup she starts, sent under Hunt's own name, acceptable on a site whose robots.txt denies bots? Or should Hunt honour robots.txt strictly?
9. Does YouTube's 30-day storage rule for API data reach metadata kept in a case file?
10. Should Ethos seek X's written approval to use its API, or a vendor contract with a lawful-collection warranty and indemnity?
11. What is the response plan if a platform disables an investigator's account, or sends Ethos or the developer a cease-and-desist letter?
12. For EU or UK subjects: does Ethos need an Article 27 representative, a legitimate-interests assessment and a published privacy notice?
