# Automate the scan, not the scroll

_How far Hunt can lawfully automate collecting and scanning a subject's social media, with the weight on Instagram, Facebook and TikTok._

_Research date: 2026-10-29. This is research, not legal advice. **[S]** = sourced; **[I]** = our inference. "(secondary)" marks a law-firm blog, news report, vendor or quotation-in-another-source rather than the primary text. "(unconfirmed)" marks what the research notes could not verify. This builds on [legal.md](legal.md) and does not repeat it._

## Summary for Aaron

**Bottom line.** Hunt can be almost fully automated. The one thing that stays human is *causing the requests* to a login-walled platform. That's not because a bot would be a crime before a ban (it probably wouldn't). It's because a bot is a plain breach of every platform's terms, the fastest way to lose her account, and a crime once access is revoked. Laura doesn't have to look at each post. She has to be the one who loads each page, scrolls and opens posts in her own Hunt Browser. Everything after the bytes arrive can be automatic: recording, hashing, parsing, OCR, video frames, CLIP scoring, timing against the injury date, change detection and the report. That is where the scan's value is.

**In practice** [I]: she opens each account from Hunt's worklist and scrolls through it at her own speed, without stopping to read. Hunt records every post, photo and video that loads, scans all of them, and shows her the hits and what she hasn't opened yet.

- **Her browsing doesn't make the scan useless** [I]. Nothing found in criminal law, ethics, licensing or evidence turns on whether a human *looked* at each post. The lines turn on who caused the request to the platform, and on whether anyone was contacted or deceived. A court held that passive capture of data Meta had already sent to a user's browser is not CFAA "access" [S] ([Meta v. BrandTotal, slip op. 43](https://law.justia.com/cases/federal/district-courts/california/candce/3:2020cv07182/367276/344/)).
- **A bot driving her own real account at human pace is probably not a crime. It is still a plain contract breach and the surest way to lose the account.**
  - Before any revocation, breaching the terms "without more" isn't a CFAA violation [S] ([Power Ventures, slip op. 15–16](https://cdn.ca9.uscourts.gov/datastore/opinions/2016/12/09/13-17102.pdf)).
  - Every platform's terms ban automated access in words that cover it. *Meta v. Bright Data* won because Bright Data was *not* a logged-in "user". Laura would be one [S] ([Goldman blog, secondary](https://blog.ericgoldman.org/?p=26009)).
  - No reported case has sued or charged an individual for automating her own account. Meta's pattern against individuals is to disable the account and send a letter to the tool's author [S] ([Barclay](https://knightcolumbia.org/content/facebook-banned-me-for-life-because-i-help-people-use-it-less)).
- **After any ban, checkpoint or cease-and-desist letter, continuing becomes real CFAA and Cal. Penal Code §502 exposure** [S] ([Power Ventures, slip op. 17–18](https://cdn.ca9.uscourts.gov/datastore/opinions/2016/12/09/13-17102.pdf)).
- **Ethos would be the defendant, and Aaron would get the letter.** The party with money and a business purpose gets sued. The tool's author gets the cease-and-desist and the lifetime ban [I, from the cases below].
- **Logged-out automation stays lawful but shallow.** Instagram gives little logged out, Facebook almost nothing. TikTok is the exception: profiles, captions, dates and stats are in the public page [S] (vendor, [Scrapfly](https://scrapfly.io/blog/posts/how-to-scrape-tiktok-python-json)).
- **Official APIs are closed to this use.** Meta, TikTok, LinkedIn, Reddit and Strava bar it outright. X needs written approval. YouTube is the only open one [S] (section 4, Q4).
- **Guardrail changes:**
  - robots.txt-aware automatic sources: the Facebook logged-out read, Check again's headless screenshots, and the YouTube RSS path.
  - The capture extension off on LinkedIn, Strava and Snapchat.
  - Notification and Story warnings.
  - Flags on audience-restricted content.
  - A hard stop on any sign of revocation.
  - A wider face-check gate.

| What | Automatic? | Why |
|---|---|---|
| Scanning every captured photo and video (OCR, frames, CLIP, injury-date timing) | **Yes, all of it** | It runs on stored copies; no request reaches any platform [I] |
| Recording what the Hunt Browser receives while she browses | **Yes** | Passive capture isn't "access" [S]; contract wording is ambiguous on Meta and TikTok [I] |
| Diffing each new capture against the last (Check again for Instagram, Facebook, TikTok) | **Yes** | Compares stored captures [I] |
| Logged-out reads: TikTok public pages, Bluesky, Mastodon, YouTube via the Data API | **Yes, politely** | Public pages have no CFAA gate [S]; robots.txt allows these paths [S] |
| Logged-out reads of Facebook, Instagram, LinkedIn, X | **One page per click, not in batches** | Their robots.txt says `Disallow: /` to unnamed bots, and there's little to read [S] |
| Loading pages, scrolling, opening posts, "See more" on a logged-in platform | **No: her hand** | Every automation clause; ban risk; Bright Data makes her a bound "user" [S] |
| Follow, friend, like, message, story reaction | **Never** | Contact and deception rules [S] |

## 1. Instagram, Facebook and TikTok, concretely

### Instagram

**(a) Logged out: thin, and getting thinner.**
- **What a logged-out visitor gets** (vendor reports, Oct 2026):
  - The profile endpoint now returns "make sure you are logged in" on a growing set of public profiles. In a test it returned `require_login` for google, nike and nasa [S] ([Scrapfly, secondary](https://scrapfly.io/blog/posts/how-to-scrape-instagram)).
  - Stories are login-only. Highlights stay public. Hashtag browsing went in 2024 [S] (same).
  - Single posts parse from page HTML, but the public single-post route broke on 2026-06-29 and video view counts went with it [S] (same).
  - Consumer blogs put the grid at about 6–12 posts before the login wall. The figures conflict and cite nothing [S] ([PeekStories, low quality](https://peekstories.com/blog/how-to-view-instagram-without-account)).
  - Logged-out clients are capped at about 200 requests per hour per IP, with blocks lasting hours or days [S] ([Scrapfly, secondary](https://scrapfly.io/blog/posts/how-to-scrape-instagram)).
- **Embeds are the official logged-out view of one public post.**
  - They don't cover private, age-restricted or embed-disabled accounts, or Stories [S] ([Meta: Instagram oEmbed](https://developers.facebook.com/docs/instagram-platform/oembed)).
  - The oEmbed endpoint is "only meant to be used for embedding", and storage and analytics are prohibited [S] (same).
  - Since 2025-11-03 it no longer returns thumbnails or author names [S] ([Meta Dev Blog](https://developers.facebook.com/blog/post/2025/04/08/oembed-updates/)).
- **How far automating it is defensible.**
  - **CFAA:** public pages have "no gates to lift or lower" [S] ([hiQ, slip op. 36](https://cdn.ca9.uscourts.gov/datastore/opinions/2022/04/18/17-16783.pdf)). Rate limits and lockouts on public pages "differ in degree rather than in kind" and don't create a gate [S] ([BrandTotal, slip op. 44–45](https://law.justia.com/cases/federal/district-courts/california/candce/3:2020cv07182/367276/344/)).
  - **Contract:** logged-off scraping didn't breach Meta's terms, because the terms contemplate a "user" as an account holder and logged-off scraping was "unrelated to the purpose of its accounts". Instagram's terms had no survival clause [S] ([Goldman blog, secondary](https://blog.ericgoldman.org/?p=26009); [FBM](https://www.fbm.com/technology/publications/major-decision-affects-law-of-scraping-and-online-data-collection-meta-platforms-v-bright-data/)).
  - **The catch for Laura** [I]: she *is* an account holder, and her account serves the same investigation. The "unrelated to its accounts" reasoning is weaker for her than for Bright Data.
  - **robots.txt:** Instagram's file opens with "Collection of data on Instagram through automated means is prohibited unless you have express written permission", and denies all paths to unnamed agents [S] ([instagram.com/robots.txt](https://www.instagram.com/robots.txt)).
  - **Verdict** [I]: defensible in law for single, honest, polite reads. But the yield is too small to feed the scan, so it isn't worth building beyond single-page lookups.

**(b) Her own account, automated at human pace.**
- **Criminal: Low before revocation, High after.**
  - "Exceeds authorized access" covers only areas "off limits to him" [S] ([Van Buren, slip op. 20](https://www.supremecourt.gov/opinions/20pdf/19-783_k53l.pdf)). Her account is a gate that is up for her.
  - A terms violation "without more" isn't a CFAA violation [S] ([Power Ventures, slip op. 15–16](https://cdn.ca9.uscourts.gov/datastore/opinions/2016/12/09/13-17102.pdf)).
  - The open risks are *Van Buren* n.8, which leaves contract-based gates undecided, and *Power Ventures* n.1, "automatic boilerplate revocation" [S] (same sources, slip op. 13 n.8 and 16 n.1).
- **Contract: High.**
  - The clause: "collecting information in an automated way without our express permission" [S] ([Instagram Terms, search snippet of the official page](https://help.instagram.com/581066165581870); current effective date unconfirmed).
  - Open Terms Archive logged the clause being added in November 2021 [S] ([OTA](https://opentermsarchive.org/en/memos/instagram-blocks-data-retrieval-and-clarifies-what-information-it-retrieves/)).
  - Human pace changes the odds of detection, not what the contract says [I].
- **Licensing: Low.** No licensing statute found distinguishes manual from automated collection (Q3).
- **Evidentiary: Medium.** It stays admissible, but she would have to explain on cross-examination that a bot she ran breached the platform's terms, and what the bot chose to load (Q3).
- **Ban: High.**
  - Instagram has announced removing activity from third-party automation apps, with in-app warnings and forced password changes [S] ([Instagram, 2018](https://about.instagram.com/blog/announcements/reducing-inauthentic-activity-on-instagram)).
  - Users report "We suspect automated behavior on your account" warnings even after scheduled posting [S] ([Make.com forum, anecdotal](https://community.make.com/t/we-suspect-automated-behavior-on-your-account-note-on-my-instagram/57057)).
  - Meta permanently disabled both the Facebook and Instagram accounts of a developer whose extension automated users' own accounts [S] ([Barclay essay](https://knightcolumbia.org/content/facebook-banned-me-for-life-because-i-help-people-use-it-less)).
- **Enforcement against individual users.** None for own-account viewing.
  - Meta sued Ekrem Ateş, an individual, but for using automated accounts to scrape 350,000+ profiles onto clone sites [S] ([Meta, 2022](https://about.fb.com/news/2022/07/actions-against-scraping-for-hire/)).
  - The Massroot8 operator ran a credential-harvesting scraping service and is now "permanently banned from using Facebook or Instagram" [S] ([Meta, 2020](https://about.fb.com/news/2020/06/automation-software-lawsuits/)).

### Facebook

**(a) Logged out: almost nothing.**
- **Hunt's own live check** (2026-10-29, `facebook.com/NASA`, honest User-Agent) returned HTTP 200 with name, picture, numeric ID, follower count and the About blurb. It returned no posts, photos, category or About fields [S] ([facebook.md](../facebook.md)). Personal profiles weren't tested; expect a login redirect.
- **Embeds:** "Only public posts from Facebook Pages and profiles can be embedded" [S] ([Meta: Embedded Posts](https://developers.facebook.com/docs/plugins/embedded-posts)). oEmbed for Page posts is being deprecated, and author fields were dropped on 2025-11-03 [S] ([Meta Dev Blog](https://developers.facebook.com/blog/post/2025/04/08/oembed-updates/)).
- **Blogs** say "Log in to see more" appears after a few profile views [S] ([Technology.org, low quality](https://www.technology.org/2026/03/12/how-to-view-facebook-profiles-without-revealing-your-identity/)).
- **Defensibility:** as for Instagram. Bright Data covers logged-off reads by a non-user. Facebook's robots.txt denies unnamed agents and states that automated collection needs "express written permission" [S] ([facebook.com/robots.txt](https://www.facebook.com/robots.txt)). Hunt's read is addressed in Q5.
- **Verdict** [I]: logged-out automation cannot feed the scan on Facebook. The numeric ID is worth keeping for attribution, and it can come from the page she opens herself.

**(b) Her own account, automated at human pace.**
- **Criminal: Low before revocation, High after.** As for Instagram. *BrandTotal* shows the after-revocation case: "hijacking a user's logged-in session … to manipulate Meta's servers to divulge further information" violated the CFAA even with the panellists' permission [S] ([BrandTotal, slip op. 52](https://law.justia.com/cases/federal/district-courts/california/candce/3:2020cv07182/367276/344/)).
- **Contract: High.**
  - Meta Terms §3.2.3 (effective 2025-01-01): "You may not access or collect data from our Products using automated means (without our prior permission)" [S] ([Meta Terms](https://www.facebook.com/terms.php)).
  - A court held the terms enforceable as a matter of law and found automated collection to be a breach [S] ([BrandTotal, slip op. 17, 38–39](https://law.justia.com/cases/federal/district-courts/california/candce/3:2020cv07182/367276/344/)).
  - §4.2 lets Meta "suspend or permanently disable your access" for clear, serious or repeated breaches. Venue is N.D. Cal. or San Mateo County, under California law [S] ([Meta Terms](https://www.facebook.com/terms.php)).
- **Licensing: Low. Evidentiary: Medium.** As for Instagram.
- **Ban: High, and documented.**
  - **Barclay ("Unfollow Everything", 2021):** his extension automated users' own accounts. He got a Perkins Coie cease-and-desist, both his accounts were "permanently disabled", and he deleted the tool [S] ([Knight Institute](https://knightcolumbia.org/content/facebook-banned-me-for-life-because-i-help-people-use-it-less)).
  - **NYU Ad Observatory (2021):** Facebook disabled the researchers' personal accounts for "unauthorized means to access and collect data" through a browser extension volunteers installed [S] ([NPR](https://www.npr.org/2021/08/04/1024791053/facebook-boots-nyu-disinformation-researchers-off-its-platform-and-critics)).
  - **Zuckerman v. Meta**, a pre-emptive suit to declare a successor tool lawful, was dismissed as unripe on 2024-11-22. The merits were never reached [S] ([Engadget](https://www.engadget.com/social-media/researchers-unfollow-everything-lawsuit-against-meta-gets-dismissed-133051131.html)).
- **Enforcement against individual users:** none found for viewing through her own account. The individuals Meta sued ran services or sold data: Zaghar, Ateş, and Solonchenko, who scraped 178 million users and sold the data [S] ([The Record](https://therecord.media/facebook-sues-ukrainian-who-scraped-the-data-of-178-million-users)).
- **Ethos-specific:** in 2021 Meta banned seven surveillance-for-hire entities, including the litigation-support firm Black Cube. It described their first, "reconnaissance" stage as automated collection [S] ([Meta, Dec 2021](https://about.fb.com/news/2021/12/taking-action-against-surveillance-for-hire/)). About 300 accounts were tied to Black Cube [S] ([OCCRP, secondary](https://www.occrp.org/en/daily/15709-meta-bans-black-cube-and-other-cyber-mercenaries-from-its-platforms)). An automated program across an investigations firm's claimant files fits that description's surface features [I].

### TikTok

**(a) Logged out: genuinely useful.**
- **Profiles:** page JSON carries bio, verified flag, region, privacy flags, and follower, following, heart and video counts [S] ([Scrapfly, Oct 2026, secondary](https://scrapfly.io/blog/posts/how-to-scrape-tiktok-python-json)).
- **Videos:** caption, `createTime`, hashtags, duration and play, like, comment and share counts. Video URLs are short-lived signed links [S] (same).
- **Depth:** a 124-video profile yielded "over a hundred" with scrolling [S] (same). That vendor used its own unblocking tooling, so an honest client will see less [I].
- **Gating:** comments are partly gated, search needs session cookies, and rate limits arrive "after a few requests" [S] (same). Consumer reports describe a limited number of clips before stalling [S] ([Tokgauge, low quality](https://tokgauge.com/guides/watch-tiktok-without-the-app/)).
- **oEmbed** needs no token, but "Embed Videos will be deprecated soon" [S] ([TikTok for Developers](https://developers.tiktok.com/doc/embed-videos/)).
- **robots.txt** lets generic agents read profile and video pages. It disallows `/embed/@`, `/embed/v2`, `/search?` and `/search/user?q=`, and blocks AI crawlers including ClaudeBot [S] ([tiktok.com/robots.txt](https://www.tiktok.com/robots.txt)).
- **Defensibility:**
  - **CFAA:** low, as for public pages generally.
  - **Contract:** the US terms (updated 2026-07-15; issued by "TikTok USDS Joint Venture") ban extracting data "for any purpose … using any automated system or software" [S] ([TikTok US ToS §3.4](https://www.tiktok.com/legal/page/us/terms-of-service/en)). The Bright Data reasoning was about Meta's wording and is untested for TikTok's [I].
  - **Enforcement:** three searches found no suit by TikTok or ByteDance against any scraper in US court. TikTok appears in scraping cases only as a defendant [S] ([Top Class Actions](https://topclassactions.com/lawsuit-settlements/privacy/tiktok-class-action-claims-company-collects-non-tiktok-users-data-on-third-party-websites/)).
  - **Verdict** [I]: build the logged-out TikTok source. Read only server-rendered pages, back off on any 429, CAPTCHA or login wall, never call signed internal APIs, and skip the disallowed paths.

**(b) Her own account, automated at human pace.**
- **Criminal: Low before revocation, High after.** As above.
- **Contract: High.** §3.4 covers it plainly. The Community Guidelines (effective 2026-09-24) add: "We strictly prohibit automation tools, scripts, or other tricks designed to bypass our systems" [S] ([TikTok CG](https://www.tiktok.com/community-guidelines/en/integrity-authenticity)). Venue is C.D. Cal. or Los Angeles County, after a 60-day informal-resolution step, with a one-year limitation period (§8) [S] ([TikTok US ToS](https://www.tiktok.com/legal/page/us/terms-of-service/en)).
- **Licensing: Low. Evidentiary: Medium.**
- **Ban: Medium–High.** §5.2 allows a ban "at any time and without prior notice" [S] (same). Our searches found no reputable report of a named individual banned for own-account automation, and no TikTok suit or letter against an end user. Say it plainly: on TikTok there are **no enforcement examples at all**, in either direction. The US entity is new, so its posture is unknown [I].

## 2. The six questions, with primary sources

### Q1. Automating her own logged-in account

**CFAA after *Van Buren* and *hiQ*.**
- **The gate test:** "liability under both clauses stems from a gates-up-or-down inquiry" [S] ([Van Buren, 593 U.S. 374, slip op. 13](https://www.supremecourt.gov/opinions/20pdf/19-783_k53l.pdf)).
- **What the Court refused to criminalise:** "everything from embellishing an online-dating profile to using a pseudonym on Facebook" (slip op. 18). It noted DOJ's 2014 policy that terms-only prosecutions "may not be warranted" (slip op. 19) [S].
- **DOJ's charging policy of 2022-05-19** disfavours terms-only CFAA charges. It binds federal prosecutors only, not civil plaintiffs or states [S] ([MoFo, secondary](https://www.mofo.com/resources/insights/220525-cyber-crime-charging-policy)).
- ***hiQ* draws the logged-in line:** areas "that require authorization to access" can still be accessed "without authorization" (slip op. 36 n.17). *Power Ventures* "was gathering user data that was protected by Facebook's username and password authentication system" (slip op. 37) [S] ([hiQ, 31 F.4th 1180](https://cdn.ca9.uscourts.gov/datastore/opinions/2022/04/18/17-16783.pdf)).
- **Users' consent works until revocation.** Users who let Power use their logins acted "akin to allowing a friend to use a computer". After the letter and IP blocks, that consent "was not sufficient to grant continuing authorization" [S] ([Power Ventures, 844 F.3d 1058, slip op. 16–18](https://cdn.ca9.uscourts.gov/datastore/opinions/2016/12/09/13-17102.pdf)).
- **No court has been found** that holds, after *Van Buren*, that a no-automation clause alone makes an account holder's automated viewing unauthorised [I, from the case-law notes; no citator check was run].

**Cal. Penal Code §502.**
- **The provisions:**
  - (c)(2) reaches anyone who "knowingly accesses and without permission takes, copies, or makes use of any data".
  - (b)(1) defines "access" broadly ("instruct, cause input to, cause output from").
  - (e)(1)–(2) give owners damages, injunctions and discretionary fees.
  — [S] ([§502](https://california.public.law/codes/penal_code_section_502))
- **No $5,000 floor**, unlike the CFAA [S] ([BrandTotal, slip op. 50](https://law.justia.com/cases/federal/district-courts/california/candce/3:2020cv07182/367276/344/)).
- **Broader on paper:** *Christensen* says §502 "does not require unauthorized access". But courts have analysed it in step with the CFAA on revocation facts [S] ([Power Ventures, slip op. 20–21](https://cdn.ca9.uscourts.gov/datastore/opinions/2016/12/09/13-17102.pdf)).
- **hiQ's stipulated §502 liability** rested on "fake accounts and other means to evade detection" [S] ([hiQ stipulation, p. 3](https://s3.documentcloud.org/documents/23429042/hiq-stip.pdf)).
- **Other states:**
  - Florida §815.06 reaches access where "the manner of use exceeds authorization". That is broader on its face, and no case applies it to terms-only automation [S] ([Fla. Stat. §815.06](http://www.leg.state.fl.us/statutes/index.cfm?App_mode=Display_Statute&URL=0800-0899/0815/Sections/0815.06.html)).
  - New York §156.05 is "without authorization" [S] ([NY PL §156.05](https://www.nysenate.gov/legislation/laws/PEN/156.05)).
  - Texas §33.02 text wasn't retrieved (unconfirmed).

**Contract: *Bright Data*, *X v. Bright Data*, *BrandTotal*.**
- ***Meta v. Bright Data*** (N.D. Cal. No. 3:23-cv-00077-EMC, 2024-01-23): "there is a strong and compelling argument that Bright Data was not 'using' Facebook" when logged off (slip op. 23). Survival clauses reach only conduct with "a nexus to" the agreement (slip op. 28–29) [S] ([Goldman blog, secondary quoting the order](https://blog.ericgoldman.org/?p=26009)).
  - Logged-in scraping was not decided [S] ([FBM](https://www.fbm.com/technology/publications/major-decision-affects-law-of-scraping-and-online-data-collection-meta-platforms-v-bright-data/)).
  - Meta dropped its remaining claim and waived appeal on 2024-02-23 [S] ([TechCrunch](https://techcrunch.com/2024/02/26/meta-drops-lawsuit-against-web-scraping-firm-bright-data-that-sold-millions-of-instagram-records)).
  - **For Laura** [I]: logging in and running a bot makes her exactly the "user" "using" the service that the ruling distinguished.
- ***X Corp. v. Bright Data*** (N.D. Cal. No. 3:23-cv-03698-WHA):
  - Scraping-based contract claims were held preempted by copyright (2024-05-09, 733 F. Supp. 3d 832) [S] ([Courthouse News](https://www.courthousenews.com/judge-tosses-xs-contract-claims-against-data-scraping-company/)).
  - Server-impairment theories were revived on 2024-11-26 (Dkt. 156) [S] ([Justia](https://docs.justia.com/cases/federal/district-courts/california/candce/3:2023cv03698/415869/156)).
  - It settled in June 2025 and closed 2025-07-01, with no merits ruling on CFAA or §502 [S] ([Bloomberg Law](https://news.bloomberglaw.com/ip-law/musks-x-settles-data-scraping-dispute-against-israeli-data-firm); [CourtListener](https://www.courtlistener.com/docket/67637345/x-corp-v-bright-data-ltd/)).
  - **For Laura** [I]: one investigator at human pace makes server impairment implausible.
- ***BrandTotal*** held Meta's §4.2 survival clause kept a terminated user bound by §3.2.3 [S] ([slip op. 38](https://law.justia.com/cases/federal/district-courts/california/candce/3:2020cv07182/367276/344/)). That conflicts with *Bright Data*, but it matters only for conduct after a ban [I].

**The clauses, with section numbers and dates** [S]:

| Platform | Clause | Effective | Words (short) |
|---|---|---|---|
| Facebook | [Meta Terms §3.2.3](https://www.facebook.com/terms.php); §3.2 item 7 | 2025-01-01 | "access or collect data … using automated means (without our prior permission)"; no circumventing access controls |
| Meta (all) | [Automated Data Collection Terms §2, §8](https://www.facebook.com/legal/automated_data_collection_terms) | 2024-10-07 | No automated collection "without first obtaining Meta's express written permission"; no published application route |
| Instagram | [Terms, "How You Can't Use Instagram"](https://help.instagram.com/581066165581870) | Unconfirmed | "collecting information in an automated way without our express permission" |
| TikTok (US) | [ToS §3.4, §5.2](https://www.tiktok.com/legal/page/us/terms-of-service/en) | 2026-07-15 | "extract any data … for any purpose … using any automated system or software"; ban "without prior notice" |
| TikTok | [Community Guidelines](https://www.tiktok.com/community-guidelines/en/integrity-authenticity) | 2026-09-24 | "automation tools, scripts, or other tricks designed to bypass our systems" |
| LinkedIn | [User Agreement §8.2 items 2, 3, 13](https://www.linkedin.com/legal/user-agreement) | 2025-11-03 | "crawlers, browser plugins and add-ons"; no bypassing "use limits"; no "bots … to access the Services" |
| X | [ToS, Misuse (iii); Liquidated Damages](https://x.com/en/tos) | 2026-10-09 | access only "through our currently available, published interfaces"; $15,000 per 1,000,000 posts in 24 h |
| YouTube | [ToS, Permissions items 1, 3, 4](https://www.youtube.com/t/terms) | 2023-12-15 | no "automated means" except search engines per robots.txt; no harvesting identifying information |
| Reddit | [User Agreement §7](https://redditinc.com/policies/user-agreement) | 2026-07-01 | no access or collection "by any means (automated or otherwise)" except as permitted |
| Snapchat | [Terms §8](https://snap.com/en-US/terms) | 2026-09-21 | no "automated or semi-automated means"; no "unauthorized third-party applications" |
| Strava | [Terms](https://www.strava.com/legal/terms) (section unnumbered) | 2026-09-28 | bans "browser extensions", "regardless of whether you are logged into a Strava account" |

None exempts an account holder automating her own account, or slow pacing [I].

**Enforcement against individuals.**
- **Criminal:** the only end-user terms-of-service prosecution found, *United States v. Drew*, 259 F.R.D. 449 (C.D. Cal. 2009), involved a fake profile. It ended in acquittal on a Rule 29(c) motion [S] ([EFF](https://www.eff.org/cases/united-states-v-drew)).
- **Civil:** every individual sued ran a service or sold data. The account-level cases (Barclay, NYU) ended in bans and letters, not suits [S] (above).
- **Gap:** "none found" means none in public sources. PACER and unpublished letters weren't searched.

**Realistic exposure** [I]:
- **Laura:** loss of the account mid-claim, and probably any linked account. She could not lawfully open another (Nosal, below). She would face awkward cross-examination. Suit risk is low, because damages are tiny: CFAA loss of $5,000 is hard to prove even for big plaintiffs [S] ([Ryanair JMOL, 2025](https://www.ded.uscourts.gov/sites/ded/files/opinions/20-1191_1.pdf)).
- **Ethos:** the natural defendant.
  - Officers who direct the conduct are personally liable [S] ([Power Ventures, slip op. 21](https://cdn.ca9.uscourts.gov/datastore/opinions/2016/12/09/13-17102.pdf)).
  - Injunctions bind "employees" and anyone "in active concert" [S] ([hiQ stipulation, p. 4](https://s3.documentcloud.org/documents/23429042/hiq-stip.pdf)).
  - The worst practical case is a Black Cube-style ban of every Ethos investigator account at once.
- **Aaron, as author:** the Barclay pattern applies: a letter, a lifetime ban, and a demand to "never again create tools that interact with Facebook" [S] ([Knight Institute](https://knightcolumbia.org/content/facebook-banned-me-for-life-because-i-help-people-use-it-less)). X's damages clause reaches those who "induce or knowingly facilitate" breaches, but its trigger is far above human pace [S] ([X ToS](https://x.com/en/tos)).

### Q2. Grey zones

**The test courts use is who causes the request, not whether a human watched.**
- **Passive:** UpVoice 2021 only processed "data that Meta has sent to the individual users". That is not CFAA access, "at least where it is installed by individuals who are not subject to any sort of direction" [S] ([BrandTotal, slip op. 43](https://law.justia.com/cases/federal/district-courts/california/candce/3:2020cv07182/367276/344/)).
- **Active:** extensions that made Meta's servers send more data were "hijacking", once access had been revoked (slip op. 52) [S].
- **A directed real user:** a contractor directed to visit pages with her *own* account didn't make BrandTotal a CFAA violator, because Facebook hadn't denied her access. The court noted it "may violate any number of other laws" (slip op. 54, 57) [S].
- **Contract tension:** footnote 28 flags "some tension" between finding a contract breach and finding no CFAA access for passive capture (slip op. 39 n.28) [S]. Passive capture is safe on the CFAA. On contract it is unsettled.

| Technique | CFAA / §502 (before revocation) | Contract | Ban | Verdict [I] |
|---|---|---|---|---|
| Passive recording of what her own browsing loads | Not "access" [S] | Ambiguous on Meta ("collect … using automated means"); arguable on TikTok ("extract … using … software"); a breach on LinkedIn, Strava, Snapchat | Low for a private single-user recorder [I]; NYU shows Meta acts against distributed extensions [S] | **Build**, off on LinkedIn, Strava, Snapchat |
| Saving a video she has open, on her click ("Save this video") | One human-caused request, like a right-click save [I] | Download licences vary (TikTok §3.5 depends on uploader settings [S]) | Low | **Optional**; prefer the bytes the player already fetched |
| Worklist: one click opens one profile | Her action causes the load [I] | Same as manual browsing | Low | **Build** |
| One click opens many tabs or sections | Software multiplies requests | "Automated means" arguable | Low–Med | **Don't**: keep one action per load |
| Auto-scroll she starts and watches | Untested; no case found [S] | Plainly "automated" or "semi-automated" (Snap §8) | Med–High: uniform behaviour [I] | **Don't build** |
| Auto-clicking "See more", comments, next post | Active: makes servers send more (*BrandTotal* line) | Plainly automated | Med–High | **Don't build** |
| Human-like random pacing to avoid detection | Neutral before notice; evidence of knowing evasion after [S] | TikTok bans "tricks designed to bypass our systems"; Meta §3.2 item 7 [S] | Raises it | **Never** |
| Anything after a ban, checkpoint, IP block or letter | High [S] | Survival may bind [S] | n.a. | **Hard stop** |

**The revocation line.**
- **Express revocation is the trigger.** A cease-and-desist letter and IP blocks were express revocation. The letter mattered because it "plainly put Power on notice", not because it cited the terms (slip op. 17 n.3). "Technological gamesmanship or the enlisting of a third party" doesn't excuse liability afterwards (slip op. 15–16) [S] ([Power Ventures](https://cdn.ca9.uscourts.gov/datastore/opinions/2016/12/09/13-17102.pdf)).
- **Proxies to beat an IP block** after a letter were "without authorization", even on a public site [S] ([3Taps, via The Register, secondary](https://www.theregister.com/2013/08/20/us_court_rules_ip_address_cloaks_can_violate_cfaa/)). *hiQ* has since undercut the public-site part of this in the Ninth Circuit [S] ([BrandTotal, slip op. 43–44](https://law.justia.com/cases/federal/district-courts/california/candce/3:2020cv07182/367276/344/)).
- **No back door:** after revocation, "the user cannot sidestep the statute by going through the back door" [S] (*Nosal III*, quoted in [BrandTotal, slip op. 56](https://law.justia.com/cases/federal/district-courts/california/candce/3:2020cv07182/367276/344/)). A second account or a colleague's login is exactly that [I].
- **Account systems can be gates:** an account system that "permits some users to create accounts but blocks others" can be a gate after letters [S] ([Ryanair, Mem. Op. 4](https://www.ded.uscourts.gov/sites/ded/files/opinions/20-1191_1.pdf)).
- **CAPTCHAs:** getting past a CAPTCHA supported a DMCA §1201 injunction (*Ticketmaster v. RMG*, 507 F. Supp. 2d 1096 (C.D. Cal. 2007)) [S] ([Goldman blog, secondary](https://blog.ericgoldman.org/?p=9383)). It also figured in wire-fraud and CFAA guilty pleas (*Lowson*) [S] ([DOJ](https://www.justice.gov/archive/usao/nj/Press/files/pdffiles/2010/wise0301relFINAL.pdf)).

### Q3. Investigator rules

**PI licensing.** No statute read mentions social media, sock puppets or automation. All discipline "fraud", "deceit" or "misrepresentation" [S]:
- **Florida:** §493.6118(1)(f) covers fraud or deceit "in the practice". §493.6118(1)(k) covers "Knowingly violating … any statute" [S] ([Fla. Stat. §493.6118](https://www.flsenate.gov/Laws/Statutes/2025/493.6118)).
- **Texas:** §1702.361(b)(1)(C) covers fraud or deceit. §1702.361(b)(2)(A) puts the company licence at risk for an employee's "fraud or deceit" [S] ([Tex. Occ. Code §1702.361](https://texas.public.law/statutes/tex._occ._code_section_1702.361)). §1702.104(b) brings "computer-based data not available to the public" into licensed investigation [S] ([§1702.104](https://texas.public.law/statutes/tex._occ._code_section_1702.104)).
- **California:** §7561.4 covers "dishonesty or fraud" [S] ([Cal. B&P §7561.4](https://california.public.law/codes/business_and_professions_code_section_7561.4)).
- **New York:** GBL §79(1)(b) covers "fraud, deceit or misrepresentation" [S] ([N.Y. GBL §79](https://www.nysenate.gov/legislation/laws/GBS/79)).
- **What follows** [I]:
  - Automating passive viewing isn't deceit toward anyone, so licensing law is neutral on it.
  - Florida's (1)(k) is the bridge. Once a CFAA or §502 violation exists after revocation, it becomes a licence ground.
  - Ethos's licensed states are unconfirmed. Its own site claims "All 50 states" coverage and lists none [S] ([Ethos](https://www.ethosrisk.com/)).

**Pretexting.**
- **The federal laws are narrow.** GLBA §6821 covers financial-institution data [S] ([15 U.S.C. §6821](https://www.law.cornell.edu/uscode/text/15/6821)). 18 U.S.C. §1039 covers phone records [S] ([§1039](https://www.law.cornell.edu/uscode/text/18/1039)).
- **State online-impersonation crimes** reach a fake persona built on a *real* person: Cal. Penal Code §528.5 (up to a year in county jail) [S] ([§528.5](https://california.public.law/codes/penal_code_section_528.5)) and Tex. Penal Code §33.07 (a third-degree felony) [S] ([§33.07](https://texas.public.law/statutes/tex._penal_code_section_33.07)).
- **The SCA:** *Ehling* held non-public Facebook posts are SCA-protected. Access was excused only because a genuine friend showed them voluntarily [S] ([Hunton, secondary](https://huntonak.com/privacy-and-information-security-law/federal-court-non-public-facebook-wall-posts-are-protected-under-the-federal-stored-communications-act)).
- **The insurance pattern:** the *Cope* suit alleged an insurer's investigator posed as a minor claimant's friend. It pleaded SCA claims, and no outcome was found [S] ([ABA Journal, secondary](https://www.abajournal.com/news/article/suit_claims_law_firm_hired_investigator_to_access_private_facebook_page_of_)).

**Insurance-privacy pretext rule (NAIC Model 670; Cal. Ins. Code §791.03).**
- **The rule:** no insurer or "insurance-support organization" may use "pretext interviews". The exception is a claim investigation with a reasonable basis to suspect fraud, and only toward people with no privileged relationship to the subject [S] ([Cal. Ins. Code §791.03](https://california.public.law/codes/insurance_code_section_791.03); [Model 670](https://content.naic.org/sites/default/files/model-law-670.pdf)).
- **What counts as a pretext interview:** pretending to be someone else, misrepresenting the purpose, or refusing to identify oneself [S] ([§791.02(u)](https://california.public.law/codes/insurance_code_section_791.02)).
- **Who's covered:** a firm that "regularly engages … in the business of assembling or collecting information about natural persons" for insurers is an insurance-support organization (§791.02(l)) [S].
- **Where it applies:** California, Georgia, Illinois, New Jersey, Ohio and others. Florida, Texas, New York and Pennsylvania show "NO CURRENT ACTIVITY" (chart dated Fall 2021) [S] ([NAIC state page](https://content.naic.org/sites/default/files/model-law-state-page-670.pdf)).
- **What follows** [I]:
  - Passive collection is not an "interview", whether a human or software does it.
  - A bot that friends or messages under a false persona is a pretext interview just as a human would be.
  - The fraud exception never covers background checks.

**Claim-handling and SIU rules.**
- **California's limit:** insurers must not "persist in seeking information not reasonably required for or material to the resolution of a claim dispute" [S] ([10 CCR §2695.7(d)](https://www.law.cornell.edu/regulations/california/10-CCR-2695.7)). SIUs need written procedures including "Preservation of documents and other evidence" [S] ([10 CCR §2698.36](https://www.law.cornell.edu/regulations/california/10-CCR-2698.36)).
- **Florida and New York:** both let insurers contract SIU work out, with the insurer staying responsible [S] ([Fla. Stat. §626.9891](https://www.flsenate.gov/Laws/Statutes/2025/626.9891); [NY DFS FAQ](https://www.dfs.ny.gov/apps_and_licensing/insurance_companies/faqs_fraud_siu)).
- **Immunity:** Florida's fraud-reporting immunity is lost on "fraud or bad faith" [S] ([§626.989(4)(c)](https://www.flsenate.gov/Laws/Statutes/2025/626.989)).
- **What follows** [I]:
  - None of these rules regulates method. They regulate scope and documentation.
  - Scan everything captured, but report what is material to the dispute.
  - Insurers likely flow method limits down by contract.

**FCRA: claims versus eligibility.**
- **Claims reports are outside the FCRA.** In the FTC staff's words, "Reports provided to insurers by claims investigation services solely to determine the validity of insurance claims … are not consumer reports" [S] ([FTC, 40 Years report, PDF p. 29](https://www.ftc.gov/sites/default/files/documents/reports/40-years-experience-fair-credit-reporting-act-ftc-staff-report-summary-interpretations/110720fcrareport.pdf)).
- **Employment and eligibility checks are inside it.** The CRA duties then apply: accuracy (§1681e(b)), public-record notice (§1681k(a)), and interviews, including by "electronic means" (§1681d). So do the employer's §1681b(b) disclosure and pre-adverse-action duties [S] ([§1681k](https://www.law.cornell.edu/uscode/text/15/1681k); [§1681d](https://www.law.cornell.edu/uscode/text/15/1681d); [§1681b](https://www.law.cornell.edu/uscode/text/15/1681b)).
- **Social-media screening:** the FTC treated a social-media screener for employers as a CRA [S] ([Social Intelligence letter, 2011](https://www.ftc.gov/sites/default/files/documents/closing_letters/social-intelligence-corporation/110509socialintelligenceletter.pdf)).
- **Mixed purpose:** a report used "in whole or in part" for a covered purpose is a consumer report (PDF p. 29) [S].
- **CFPB:** its data-broker proposal was withdrawn on 2025-05-15 [S] ([Federal Register](https://www.govinfo.gov/content/pkg/FR-2025-05-15/html/2025-08644.htm)).
- **What follows** [I]: method doesn't change coverage. It matters for accuracy, so automated identity matching needs human confirmation before anything is reported.

**Attorney ethics** (it binds Ethos's work whenever defence counsel directs it, through Rules 5.3 and 8.4(a)).
- **Viewing public content is not a communication**, even when the person is represented [S] ([NYSBA Op. 843](https://nysba.org/ethics-opinion-843/); [NYSBA Guidelines 4.A, p. 20](https://nys-fjc.ca2.uscourts.gov/programs/10-22-19%20-%20NYSBA-Social%20Media%20Ethics%20Guidelines-Final-6-20-19.pdf); [D.C. Op. 371](https://www.dcbar.org/for-lawyers/legal-ethics/ethics-opinions-210-present/ethics-opinion-371); [Colorado Op. 127](https://www.cobar.org/Portals/COBAR/repository/ethicsOpinions/FormalEthicsOpinion_127.pdf); [Oregon 2013-189, rev. 2026](https://www.osbar.org/_docs/ethics/2013-189.pdf)).
- **A friend, follow or connection request to a represented person is.** New Jersey codified this in an official comment to RPC 4.2, effective 2024-09-01 [S] ([NJ Notice](https://www.njcourts.gov/sites/default/files/notices/2024/07/n240724a.pdf)).
- **Deception through agents is barred.** "A lawyer must never use deception to gain access to a restricted portion of a social media profile" [S] ([Colorado Op. 127](https://www.cobar.org/Portals/COBAR/repository/ethicsOpinions/FormalEthicsOpinion_127.pdf)).
- **The profile-view notification split:**
  - **Not a communication:** ABA 466 (jurors), Colorado 127 (extended to represented persons), D.C. 371 and Pa. 2014-300 [S] ([NYSBA Guidelines, pp. 34–35, quoting them](https://nys-fjc.ca2.uscourts.gov/programs/10-22-19%20-%20NYSBA-Social%20Media%20Ethics%20Guidelines-Final-6-20-19.pdf)).
  - **Can be one in New York:** "receipt of an automatic notification can be considered an improper communication with someone who is represented by counsel". Footnote 128 advises LinkedIn's anonymous setting or being "fully logged out" [S] (NYSBA Guideline 4.C comment, pp. 22–23). NYC Bar 2012-2 says it may be a prohibited communication "even if inadvertent" [S] ([NYC Bar 2012-2](https://www.nycbar.org/reports/formal-opinion-2012-2-jury-research-and-social-media/)).
  - **Colorado adds a harassment angle:** repetitive viewing the lawyer knows triggers notices could, in "an extreme situation", breach Rule 4.4(a) [S] ([Colorado Op. 127](https://www.cobar.org/Portals/COBAR/repository/ethicsOpinions/FormalEthicsOpinion_127.pdf)).
- **Bots and scraping:** no opinion addresses them. D.C. 371 declined to say whether breaching a site's terms can be pretexting [S] ([D.C. Op. 371](https://www.dcbar.org/for-lawyers/legal-ethics/ethics-opinions-210-present/ethics-opinion-371)).

**Evidence: FRE 901, 902(13), 902(14), and whether method matters.**
- **902(13)** self-authenticates output of a process "that produces an accurate result", by certification. Its 2017 Note uses a webpage printout as the example and keeps authorship open to challenge [S] ([FRE 902 and notes](https://www.law.cornell.edu/rules/fre/rule_902)).
- **902(14)** covers data authenticated "by a process of digital identification", ordinarily by "hash value" [S] (same).
- **Attribution needs its own evidence.** A profile printout "with no evidence to show that the defendant had created the page" sank a conviction (*Vayner*, 769 F.3d 125, 131 (2d Cir. 2014)). Provider records "are not business records" for 902(11) purposes (*Browne*, 834 F.3d 403 (3d Cir. 2016)) [S] ([Browne](https://cases.justia.com/federal/appellate-courts/ca3/14-1798/14-1798-2016-08-25.pdf)). Courts use a reasonable-juror threshold [S] ([Sublet](https://mdcourts.gov/data/opinions/coa/2015/42a14.pdf)).
- **Method and admissibility:**
  - The Fourth Amendment doesn't restrain private parties [S] ([Burdeau v. McDowell](https://www.law.cornell.edu/supremecourt/text/256/465)).
  - The SCA has no suppression remedy [S] ([18 U.S.C. §2708](https://www.law.cornell.edu/uscode/text/18/2708)).
  - No case was found excluding social-media evidence because collection breached terms or was automated [S] (ethics-evidence notes).
  - Exclusion has followed an agent's Rule 4.2 or 8.4(c) violation [S] ([Midwest Motor Sports, 347 F.3d 693 (8th Cir. 2003), holding via summaries](https://www.courtlistener.com/opinion/3032706/midwest-motor-sports-v-arctic-cat-sales-inc/)).
- **AI output:** proposed FRE 707 was withdrawn as published on 2026-05-07, in favour of a modified draft under study. A deepfake 901(c) exists only as an unpublished draft [S] ([Advisory Committee agenda book, Oct 2026, pp. 4–5, 82–83](https://www.uscourts.gov/sites/default/files/document/2026-10-evidence-rules-agenda-book.pdf)).
- **What follows** [I]:
  - Method doesn't decide admissibility. It decides how hard the cross-examination is.
  - A documented passive pipeline with capture-time hashes fits 902(13)/(14) better than ad hoc screenshots.
  - Scan hits should stay leads. The captures are the evidence.

### Q4. Official APIs and licensed vendors

**Official APIs bar the use case, whoever's key is used** [S]:

| Platform | Route | Why it fails for claimant work |
|---|---|---|
| Meta | [Platform Terms](https://developers.facebook.com/terms/dfc_platform_terms/) (updated 2026-02-03) | §3.a.ii bans "eligibility determinations about people, including for … insurance"; §3.a.iii bans "surveillance" |
| Meta | [Content Library](https://transparency.meta.com/researchtools/meta-content-library) | Academic or not-for-profit research only |
| Instagram | [Business Discovery](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/business_discovery) | Business and Creator accounts only. Basic Display, the personal-account route, ended 2024-12-04 ([Meta forum](https://developers.secure.facebook.com/community/threads/1089913112732648)) |
| Meta | [oEmbed](https://developers.facebook.com/docs/instagram-platform/oembed) | Embedding only; no storage or analytics |
| TikTok | [Research API terms](https://www.tiktok.com/legal/page/global/terms-of-service-research-api/en) (2026-01-22); [Developer Terms](https://www.tiktok.com/legal/page/global/tik-tok-developer-terms-of-service/en) (2025-12-26) | Academics only; §III.2 no "commercial" use; §III.4 no "profiles of individual users"; Developer Terms §III.3(h) no profiles "on any individual" |
| LinkedIn | [API Terms](https://www.linkedin.com/legal/l/api-terms-of-use) | §3.1(17) no eligibility decisions for "insurance, employment"; §3.1(19) no surveillance |
| X | [Developer Agreement](https://docs.x.com/developer-terms/agreement) (2026-04-27) | §XIV.B(a) no "surveillance or gathering intelligence" without written approval. [Pay-per-use](https://docs.x.com/x-api/getting-started/pricing) is $0.005 per post read, so cost isn't the barrier |
| Reddit | Public Content Policy (May 2024) | No "background checks" ([TechCrunch, secondary](https://techcrunch.com/2024/05/09/reddit-locks-down-its-public-data-in-new-content-policy-says-use-now-requires-a-contract)) |
| Strava | [API Agreement](https://www.strava.com/legal/api) (2026-06-01) | Data shown only to the athlete who provided it |
| YouTube | [Developer Policies](https://developers.google.com/youtube/terms/developer-policies) (2026-10-15) | **Usable:** no surveillance or eligibility ban; API data kept "no longer than 30 calendar days" (§III.E.4) |

**Claims count as "eligibility"** [I]. California's own insurance-privacy law defines "insurance transaction" to include "eligibility for an insurance coverage, benefit, or payment" [S] ([Cal. Ins. Code §791.02(m)](https://california.public.law/codes/insurance_code_section_791.02)). That supports reading Meta §3.a.ii and LinkedIn §3.1(17) to cover claim decisions.

**Licensed vendors.**
- **Skopenow** says it is not a CRA and that its data "may not be used" for insurance eligibility. Yet it integrates with Guidewire ClaimCenter for claims and SIU [S] ([Skopenow FAQ](https://skopenow.com/faq); [Guidewire](https://www.guidewire.com/about/press-center/press-releases/2023110/guidewire-taps-skopenow-to-deliver-faster-claims-investigations-at-scale)).
- **Carpe Data** sells "always on" claims monitoring [S] ([Carpe Data](https://www.carpe.io/resources/press/carpe-data-announces-launch-of-claimsx-platform/)).
- **Vendors Meta has acted against for fake or automated accounts:** Social Links (2022 threat report), Cobwebs (2021) and Voyager Labs (sued 2023; settled by deleting the data) [S] ([Meta threat report](https://about.fb.com/wp-content/uploads/2022/12/Threat-Report-on-the-Surveillance-for-Hire-Industry.pdf); [MediaPost](https://www.mediapost.com/publications/article/401661/analytics-company-voyager-labs-settles-scraping-ba.html)).
- **Data vendors** market "public data only" and put compliance on the customer [S] ([Apify](https://apify.com/apify/instagram-scraper/issues/does-it-comply-with-xGNlYjplqUvcFOrmz); [Data365](https://data365.co/legality)).
- **No vendor publishes pricing** or API terms on third-party integration [S] (vendor notes).

**Could Hunt plug in a vendor through her own key? Yes.**
- It is a recognised pattern: Maltego's SocialNet transforms require "a SocialNet API license from ShadowDragon" [S] ([Maltego](https://www.maltego.com/transform-hub/socialnet)).
- With her own key, Ethos is the licensee and bound by the vendor's permitted-use terms. Hunt's maintainers never are [I].
- A shared or embedded key would make the project a party [I].
- A vendor's "publicly available" label isn't proof of compliant collection. A Voyager-style finding later would put the provenance of report evidence in play [I].

### Q5. Logged-out automation per platform, robots.txt, rate limits, CAPTCHAs

**robots.txt, fetched 2026-10-29** [S]:

| Site | Unnamed agents (`User-agent: *`) | Note |
|---|---|---|
| [facebook.com](https://www.facebook.com/robots.txt), [instagram.com](https://www.instagram.com/robots.txt), [threads.com](https://www.threads.com/robots.txt) | `Disallow: /` | Opens with "express written permission" notice; points to the ADC Terms |
| [linkedin.com](https://www.linkedin.com/robots.txt) | `Disallow: /` | Permission by email, for "approved publicly available search engines" |
| [x.com](https://x.com/robots.txt), [reddit.com](https://www.reddit.com/robots.txt) | `Disallow: /` | X adds `Crawl-delay: 1` |
| [tiktok.com](https://www.tiktok.com/robots.txt) | Allowed, except `/embed/@`, `/embed/v2`, `/search?`, `/search/user?q=` | AI crawlers blocked |
| [youtube.com](https://www.youtube.com/robots.txt) | Allowed, except `/feeds/videos.xml`, `/results`, `/youtubei/`, `/api/` and others | **Hunt's YouTube source reads `/feeds/videos.xml`** (`hunt/posts.py`, `YT_RSS`) |
| [strava.com](https://www.strava.com/robots.txt) | Summaries allowed; activity sub-pages, follows and search disallowed | Terms ban automation anyway |
| [bsky.app](https://bsky.app/robots.txt) | Allowed | "Up to a handful concurrent requests should be ok" |

**Is robots.txt binding?**
- **The standard itself says no:** "These rules are not a form of access authorization" [S] ([RFC 9309 §1](https://www.rfc-editor.org/rfc/rfc9309.html)).
- **Technical anti-bot measures** on public pages create no CFAA gate [S] ([BrandTotal, slip op. 44–45](https://law.justia.com/cases/federal/district-courts/california/candce/3:2020cv07182/367276/344/)).
- **Platforms write it into contracts.** YouTube's only automation exception is for search engines "in accordance with YouTube's robots.txt". Meta's ADC Terms require following robots.txt. Reddit's crawl permission is conditional on it [S] ([YouTube ToS](https://www.youtube.com/t/terms); [Meta ADC §4](https://www.facebook.com/legal/automated_data_collection_terms); [Reddit §7](https://redditinc.com/policies/user-agreement)).
- **Browsewrap terms** were enforced where the scraper had actual knowledge through letters [S] ([Southwest v. Kiwi, Proskauer, secondary](https://www.proskauer.com/blog/southwest-airlines-wins-injunction-barring-travel-site-from-scraping)).

**Hunt's Facebook logged-out read** (`hunt/sources/facebook.py`) [I]:
- **The law is on its side:** a public page has no gate, *Bright Data* covers logged-off reads, and robots.txt isn't authorisation.
- **But it sends an unnamed agent to a path the file denies,** on a site whose notice says no automated collection without permission.
- **The *Bright Data* shield is thinner for an account holder** whose account serves the same investigation.
- **It yields only preview fields.** The search also fans it out without a click per URL, which is the hardest part to call "user-initiated".
- **Change:** take it out of batch search and Check again. Keep it as a one-account "Read public preview" action on her click, or read the same fields with `facebook.parse_public` from the page she opens in the Hunt Browser.
- **Wider reach:** the same reasoning reaches `recheck._recapture`. On every Check again it drives headless, logged-out Chromium through `capture.screenshots` to every confirmed account, including Instagram, Facebook, X and LinkedIn ones, whose robots.txt deny `*`. TikTok and YouTube profile pages are allowed.
- **Maigret and WhatsMyName** existence checks are one request each, and a standard practice. Keep them, but document the policy.

**YouTube.** The RSS path is robots-disallowed, and the ToS ties its only automation exception to robots.txt. It is the lowest-stakes item here, since the feed exists for feed readers [I]. Move to the YouTube Data API with her own key, which is the one official API that allows this use [S]. Treat the §III.E.4 30-day storage cap as applying to API-returned metadata (unconfirmed for evidence copies; ask counsel).

**Rate limits and CAPTCHAs.**
- **Platform terms make working around limits a breach:** X ("work around any technical limitations"), LinkedIn §8.2 item 3, Meta §3.2 item 7 and TikTok §3.10 [S] ([X ToS](https://x.com/en/tos); [LinkedIn UA](https://www.linkedin.com/legal/user-agreement); [Meta Terms](https://www.facebook.com/terms.php); [TikTok ToS](https://www.tiktok.com/legal/page/us/terms-of-service/en)).
- **Hunt's response** [I]: stop on 429, CAPTCHA or login wall. Never solve a CAPTCHA, rotate IPs or spoof headers. Hunt's Facebook source already declines to add browser headers to get past a 400 ([facebook.md](../facebook.md)); make that the rule everywhere.
- **Reddit:** logged-out `.json` reportedly returns 403 since about late May 2026 [S] ([DEV Community, vendor](https://dev.to/tonywangca/why-reddit-blocked-unauthenticated-json-in-2026-and-how-to-still-get-reddit-data-58b9)).

### Q6. Privacy and biometric law

**CCPA/CPRA.**
- **Who's bound:** it binds a "business" over $26,625,000 in revenue (from 2025-01-01), or one handling PI of 100,000+ California consumers, or one getting 50%+ of revenue from selling or sharing PI. It never binds the employee [S] ([§1798.140(d)](https://california.public.law/codes/civil_code_section_1798.140); [CPPA](https://cppa.ca.gov/announcements/2024/20241217.html)).
- **Public posts are excluded** as "publicly available", but not where "the consumer has … restricted the information to a specific audience". Biometric information "collected … without the consumer's knowledge" is never publicly available [S] (§1798.140(v)(2)).
- **Legal-claims exemption:** "Exercise or defend legal claims" is the main exemption [S] ([§1798.145(a)(1)(E)](https://california.public.law/codes/civil_code_section_1798.145)).
- **ADMT rules** took effect 2026-01-01, with significant-decision compliance due 2027-01-01 [S] ([Hunton, secondary](https://www.hunton.com/privacy-and-information-security-law/cppa-finalizes-ccpa-regulations-on-automated-decision-making-technology-risk-assessments-and-cybersecurity-audits)).
- **What follows** [I]:
  - Logged-in browsing can show Friends or Friends-of-friends posts. Those fall outside the public exclusion, here and in Virginia and Texas, which use the same audience wording [S] ([Va. §59.1-575](https://law.lis.virginia.gov/vacode/title59.1/chapter53/section59.1-575/); [Tex. §541.001(27)](https://texas.public.law/statutes/tex._bus._and_com._code_section_541.001)).
  - Inferring physical capacity may be health PI (§1798.140(ae)(2)(B)).

**BIPA.**
- **What it requires:** a written notice and "written release" before collecting a "scan of … face geometry" (§15(b)). It covers "any individual". It has no fraud or legal-claims exemption; §25(d) only avoids conflict with the PI Act [S] ([740 ILCS 14](https://www.ilga.gov/legislation/ilcs/ilcs3.asp?ActID=3004&ChapterID=57)).
- **Damages:** $1,000 or $5,000 per violation, now one recovery per person per method (P.A. 103-769, 2024) [S] (same).
- **Clearview** (unconfirmed): the Seventh Circuit vacated approval of the Clearview settlement on 2026-07-13 (181 F.4th 785). It found no inherent problem with the equity form [S] ([Leagle excerpt](https://www.leagle.com/decision/infco20260713073); [ID Tech Wire, secondary](https://idtechwire.com/appeals-court-vacates-clearview-ai-biometric-privacy-settlement/)). The full opinion was paywalled.

**Texas CUBI and TRAIGA** (HB 149, effective 2026-01-01).
- **New (b-1):** an image online isn't consent unless the person made it public.
- **New (e)(3):** AI systems "for the purposes of … investigating … fraud" are exempt.
- **Enforcement:** by the AG only, up to $25,000 per violation [S] ([HB 149 enrolled](https://capitol.texas.gov/tlodocs/89R/billtext/html/HB00149F.htm); [§503.001](https://texas.public.law/statutes/tex._bus._and_com._code_section_503.001)).
- **What follows** [I]: (e)(3) might cover a fraud face check, but it is untested, and the AG settled with Meta for about $1.4B in 2024 ([Bracewell, secondary](https://www.bracewell.com/resources/google-agrees-to-1-375-billion-settlement-as-texas-attorney-general-continues-data-privacy-push/)). Keep Texas blocked.

**Washington.**
- **RCW 19.375** excludes photographs "or data generated therefrom", and covers only enrolment for commercial purposes [S] ([RCW 19.375](https://app.leg.wa.gov/RCW/default.aspx?cite=19.375&full=true)).
- **The My Health My Data Act is the real Washington risk:**
  - "Consumer health data" includes data "derived or extrapolated from nonhealth information … including algorithms or machine learning" (.010(8)(b)(xiii)).
  - It has no size threshold (.010(23)) and is privately enforceable through the CPA (.090).
  - There is a fraud exemption (.100(3)), but the entity "bears the burden of demonstrating" it (.100(4)) [S] ([RCW 19.373](https://app.leg.wa.gov/RCW/default.aspx?cite=19.373&full=true)).
- **What follows** [I]: a scan that concludes "the claimant can lift" about a Washington resident is arguably consumer health data.

**Colorado** requires prior consent for biometric identifiers from 2025-07-01, whatever the business's size, with the CPA exemptions preserved [S] ([HB 24-1130](https://www.leg.colorado.gov/bills/hb24-1130)).

**GDPR and UK GDPR.**
- **Scope:** a non-EU controller monitoring EU behaviour is caught by Art. 3(2)(b) [S] ([GDPR](https://eur-lex.europa.eu/eli/reg/2016/679/oj); EDPB 3/2018 paraphrased, not re-verified).
- **The UK reads "monitoring" broadly:** the Upper Tribunal found Clearview's processing "related to monitoring of behaviour of UK residents" [S] ([ICO](https://ico.org.uk/about-the-ico/media-centre/news-and-blogs/2025/10/uk-upper-tribunal-hands-down-judgment-on-clearview-ai-inc)). Commentators say passive collection and classification is enough (secondary). Clearview has permission to appeal [S] (same).
- **The Dutch regulator:** scraping is "almost always" unlawful unless "very targeted" [S] ([Pinsent Masons, secondary](https://www.pinsentmasons.com/out-law/news/dutch-web-scraping-guidance-warn-businesses-gdpr-breach-risk)).
- **The AI Act** bans *untargeted* face scraping to build databases (Art. 5(1)(e)). Targeted collection is outside the ban [S] ([FPF, secondary](https://fpf.org/blog/red-lines-under-the-eu-ai-act-understanding-the-ban-of-the-untargeted-scraping-of-facial-images-and-facial-recognition-databases/)).
- **UK conditions:** legal claims (DPA 2018 Sch. 1 para 33) and a crime exemption from notice "to the extent" notice would prejudice detection (Sch. 2 para 2) [S] ([Sch. 1 Pt 3](https://www.legislation.gov.uk/ukpga/2018/12/schedule/1/part/3); [Sch. 2 para 2](https://www.legislation.gov.uk/ukpga/2018/12/schedule/2/paragraph/2)).
- **What follows** [I]: any EU or UK subject needs a per-case basis (Art. 6(1)(f), 9(2)(f), Art. 10 cover) and a notice-exemption record.
- **Canada:** PIPEDA's "publicly available" exception doesn't fit social media under the OPC's Clearview findings. Collection for a breach or fraud investigation can rely on s.7(1)(b) [S] ([PIPEDA s.7](https://laws-lois.justice.gc.ca/eng/acts/P-8.6/section-7.html); [OPC 2021-001](https://priv.gc.ca/en/opc-actions-and-decisions/investigations/investigations-into-businesses/2021/pipeda-2021-001)).

## 3. Decision tables

Ratings are our synthesis [I] of the sources above. "Practical" means account ban plus how much the method yields.

### Instagram

| Method | Criminal | Civil / contract | Licensing | Evidentiary | Practical |
|---|---|---|---|---|---|
| (a) Logged-out automated | Low: no gate on public pages (*hiQ*) | Low–Med: *Bright Data*; robots.txt notice; she holds an account | Low | Low: no viewer trail | Yield Low: login wall on many profiles; about 200 requests/h/IP |
| (b) Logged-in automated, her account | Low before revocation; High after | High: "automated way without our express permission" | Low; Med after revocation (FL (1)(k)) | Med: cross-examination on breach and on bot selection | High: disable, action blocks; letter to the author |
| (c) Human-driven capture, Hunt Browser | Low: passive isn't "access" (*BrandTotal*) | Low–Med: "collect … using automated means" ambiguous | Low | Low: best fit for 902(13)/(14) | Low–Med: none found against a private single-user recorder |
| (d) Official API | Low | High: §3.a.ii, §3.a.iii | Low | n.a. | n.a.: Business and Creator accounts only |
| (e) Licensed vendor, her key | Low for her | Vendor's risk; Ethos's vendor contract | Low | Med: provenance opaque (Voyager) | Med: vendors get cut off; quote-only |

### Facebook

| Method | Criminal | Civil / contract | Licensing | Evidentiary | Practical |
|---|---|---|---|---|---|
| (a) Logged-out automated | Low | Low–Med: as Instagram; robots `Disallow: /` | Low | Low | Yield ~nil: preview tags only (Hunt's NASA check) |
| (b) Logged-in automated, her account | Low before revocation; High after (*BrandTotal* "hijacking") | High: §3.2.3, held enforceable | Low; Med after revocation | Med | High: Barclay and NYU bans; Black Cube-style firm-wide ban for Ethos |
| (c) Human-driven capture, Hunt Browser | Low | Low–Med: §3.2.3 ambiguous for passive recording; *BrandTotal* n.28 "tension" | Low | Low | Low–Med; video is `blob:`, so capture from what the player fetched |
| (d) Official API | Low | High: §3.a.ii/iii; no route to personal profiles | Low | n.a. | n.a. |
| (e) Licensed vendor, her key | Low for her | Vendor's risk | Low | Med | Med |

### TikTok

| Method | Criminal | Civil / contract | Licensing | Evidentiary | Practical |
|---|---|---|---|---|---|
| (a) Logged-out automated | Low | Med: §3.4 "for any purpose"; *Bright Data* untested on TikTok's wording; no TikTok scraper suits found | Low | Low | Yield Med–High: captions, dates, stats, videos; rate-limited quickly |
| (b) Logged-in automated, her account | Low before revocation; High after | High: §3.4, Community Guidelines | Low; Med after revocation | Med | Med–High: §5.2 ban without notice; no examples found either way |
| (c) Human-driven capture, Hunt Browser | Low | Low–Med: "extract … using … software" arguable | Low | Low | Low–Med |
| (d) Official API | Low | High: Research API academics only; no individual profiles | Low | n.a. | oEmbed only, "deprecated soon" |
| (e) Licensed vendor, her key | Low for her | Vendor's risk | Low | Med | Med |

### The rest, compactly

| Platform | Logged-out automated | Logged-in automated | Capture extension | Official API | Do this |
|---|---|---|---|---|---|
| LinkedIn | Med–High: `Disallow: /`; terms bind Visitors; hiQ's injunction covers "logged in … or not" | High: §8.2 items 2, 13; ProAPIs suit (2025) | High: §8.2 names "browser plugins"; scans 6,236 extension IDs | Barred: §3.1(17), (19) | She browses, logged out or in private mode; manual save and import |
| X | Med: `Disallow: /`; "(automated or otherwise)" | High; damages trigger far off | Med: same wording | Cheap, but needs written approval (§XIV.B(a)) | Ask X for approval, or human capture |
| YouTube | Low–Med: pages allowed; `/feeds/videos.xml` not | n.a.: no login needed | Low | Usable; 30-day storage | Move RSS to the Data API |
| Reddit | Med: `Disallow: /`; `.json` 403 (vendor) | High: §7 | Med | Barred: no background checks | Human capture |
| Strava | Med: terms ban automation logged in or out | High | High: names "browser extensions" | Barred: owner-only display | Human; manual save and import |
| Bluesky / Mastodon | Low: allowed; open firehose | Low for reading; no write actions | Low | Open (AT Protocol); Mastodon per instance, unresearched | Keep automatic |

## 4. Recommendation: the most automated defensible design

**The line.** On any login-walled platform, every request the platform receives is caused by a deliberate human input in the Hunt Browser: one navigation, scroll, click or key press of hers. Hunt never causes one. Everything after the response arrives in her browser is automatic. On public, robots-allowed surfaces, Hunt reads automatically, politely, and stops at the first refusal.

This is a bright line chosen to be defensible, not the minimum the law compels [I]. It puts Hunt on the passive side of *BrandTotal*, outside every pretext and contact rule, and on the cleanest footing for 902(13). It keeps the realistic worst case on Meta and TikTok to a contested contract argument over passive recording, instead of a clear breach and a ban.

### Implementation brief for the build sessions

**1. Hunt Browser**
- **Launch a normal browser** with its own persistent profile and the capture extension. It must not run under WebDriver, Playwright or remote-debugging *control*.
  - A WebDriver-controlled browser announces itself as automated, so she could be flagged as a bot while browsing by hand.
  - Hiding those flags would be evasion [I].
- **Hunt never reads, exports or replays her cookies or tokens.** It never makes a request with her session.
- **Per-site capture switch:**
  - On: Instagram, Facebook, TikTok, X, YouTube, Reddit.
  - Off: LinkedIn, Strava, Snapchat. Their terms name extensions or "semi-automated" tools. There she uses the browser's own Save Page As or a screenshot, and the existing importers.
- **A visible "Recording" indicator,** and a per-tab pause.
- **A revocation watcher** (passive). It reads URLs and page text she has already loaded: checkpoint and challenge paths, "We suspect automated behavior", action-block notices, CAPTCHAs, "account disabled". Any of them triggers the hard stop below.
- **A Story warning** before opening an Instagram or Facebook Story while logged in: "Story viewers can see your account." Whether viewer lists show her is platform behaviour the notes didn't verify, so treat it as likely [I].
- **LinkedIn:** a banner recommending she browse logged out or set private viewing first (NYSBA fn. 128).

**2. Capture extension (a passive recorder)**
- **Records only what the browser has already received:**
  - DOM snapshots after each load and each of her scrolls;
  - viewport screenshots;
  - the image and video bytes the page itself fetched, read from the browser's own network log, read-only.
- **It never initiates a request.** It never scrolls, clicks, expands "See more", advances a post or synthesises input. How it reads bytes the page fetched is the build session's call. The test: the platform receives no request the extension caused [I].
- **Video:** assemble from the segments the player fetched, and mark "partial" if she skipped ahead. An optional **Save this video** button may fetch the media URL the page referenced: one click, one request, audited as `human download`. Prefer the bytes already fetched.
- **One capture record per item:**
  - page URL, platform account ID and post ID;
  - UTC time and time source;
  - "logged in as <her handle>" or "logged out";
  - the audience shown (Public, Friends, Friends of friends, group);
  - extension and Hunt version;
  - SHA-256 at capture, before any transcoding.
- **A coverage counter**, for example "38 of 112 grid posts opened · 6 videos partly loaded". It tells her what's left. It loads nothing.
- **Delivery:** captures go to a local route (like `POST /api/cases/{slug}/facebook`), through per-platform parsers (the `facebook.parse_saved` pattern), into `posts.add_posts(case, items, kind, evidence)`. They become posts the scan reads.

**3. Worklist (discovery and Check again on login-walled platforms)**
- **Shows the links** `facebook.search_links` and its siblings build, plus the subject's confirmed accounts. Each opens on her click: one click, one page load. No "open all".
- **`recheck.py` keeps its automatic path** for Bluesky, Mastodon and YouTube.
- **For Instagram, Facebook, logged-in TikTok, X and LinkedIn,** Check again becomes the worklist. As she opens each account, the new capture is diffed automatically against the last capture of that account, with the same change kinds: `posts gone`, `post back`, `profile changed`, `account gone`. These become audit entries and `change` events.
- **This replaces `recheck._recapture`'s headless logged-out screenshots** of those sites. It also gives Instagram, Facebook and TikTok real change detection, instead of comparing screenshots by eye.
- **Pacing:** show "last opened" per account, and warn on LinkedIn re-views of the same profile within a short window (Colorado 4.4(a); NYSBA 4.C).

**4. `sources/`**
- **Keep automatic:** Bluesky, Mastodon, the 12 public APIs, and Maigret/WhatsMyName existence checks. Document the policy for the checks: one request each, honest UA.
- **TikTok public profiles: build.**
  - Server-rendered profile and video pages only.
  - Honest User-Agent, a polite gap, and stop on 429, CAPTCHA or login wall.
  - No signed internal API calls; reverse engineering needs "explicit written authorization" (§3.4).
  - No proxies to beat blocks. Skip `/embed/@` and `/search?`.
  - Respect the uploader's download setting where the page exposes it (§3.5) [I].
- **YouTube:** replace `/feeds/videos.xml` with the Data API on her own key. Keep API metadata within §III.E.4, and keep evidence copies separately (confirm with counsel).
- **Facebook (`sources/facebook.py`):** remove it from batch search and Check again. Keep a one-account "Read public preview" on her click, or run `facebook.parse_public` on her Hunt Browser capture.
- **Instagram embeds and Facebook post plugins:** render them for her to view on her click, where the capture records them. Don't build an automated embed reader; Meta's embed terms bar storage and analysis.
- **LinkedIn public profiles:** don't build the automated reader.
- **`capture.screenshots` in search:** skip hosts whose robots.txt denies `*`.

**5. `posts.add_posts`, scan, audit log, evidence bundle**
- **`scan.run` runs automatically over every captured photo and video frame.** That covers OCR, CLIP, `scan.video_frames` and per-platform tag maps like `facebook.categories`. It keeps the "likely" cap, and hits wait for human confirmation.
- **Audit:** every capture batch, worklist open, `human download`, hard stop and audience flag.
- **Evidence bundle additions:**
  - capture-record columns in `manifest.csv` (logged in or out, account, audience, tool version);
  - a README paragraph describing the capture process for a 902(13) certification;
  - a separate attribution section per account (numeric ID, matching details; *Vayner*);
  - scan hits labelled as leads, never as evidence.
- **Minimisation:** scan everything, but report only what is material (10 CCR §2695.7(d)). Purge unused raw media on the case's retention date.

### What not to build

- Any bot, macro or script that loads pages, scrolls, clicks or types on a logged-in platform. That includes "assistive" auto-scroll she starts and watches.
- Auto-expanders for "See more", comments or replies, and auto-advance through post modals or Stories.
- Human-like random delays, fingerprint spoofing, stealth plugins, or hiding automation flags.
- CAPTCHA solvers, proxy or IP rotation, or header spoofing to get past a refusal.
- A second, shared, purchased or fake account, or a colleague's login.
- Official Meta, TikTok, LinkedIn, Reddit or Strava API connectors for claimant work.
- A bundled or shared vendor key.
- An automated Instagram embed or LinkedIn public-profile scraper.
- Anything that sends a friend or follow request, like, message, comment or story reaction.

### Hard stops

On any of these, Hunt stops capture and automatic reads for that platform. It audits the event, tells her not to use that account for casework, and tells her to tell Ethos:
- Account disabled or restricted, a checkpoint or login challenge, "suspected automated behaviour", or an action block.
- A CAPTCHA, or an IP block or 429 on any automatic source. Back off. Never retry from a new IP.
- A cease-and-desist letter or platform email to Laura, Ethos or Aaron.
- A platform's notice withdrawing permission for a tool.

**Never fall back to:** a second account, someone else's account, a new browser profile, a proxy, or a vendor bought to get around the block (*Power Ventures*; *Nosal*; *3Taps*).

## 5. Guardrail changes

| Guardrail | Status | What changes, and why |
|---|---|---|
| No bot driving logged-in accounts | **Keep, sharpen** | Restate it as "no software-caused request to a login-walled platform". Passive recording is allowed; auto-scroll and auto-expand are not (*BrandTotal*) |
| No fake accounts or pretexting | **Keep** | hiQ, BrandTotal and Voyager liability; §791.03 pretext interviews; ethics 4.1 and 8.4(c); CA §528.5, TX §33.07 |
| No CAPTCHA bypass | **Keep, widen** | Add: no proxies, IP rotation, header or fingerprint spoofing, or stealth pacing (*RMG*; *3Taps*; TikTok CG; Meta §3.2 item 7) |
| Never contact the subject | **Keep, widen** | Cover associates (FCRA §1681d "electronic means"; Rules 4.2 and 4.3) and every "contact" action (follow, like, story reaction). Treat claimants as represented by default |
| Face check: 1:1 only, blocked in biometric-law states | **Keep, change the gate** | Gate on the *subject's* residence; unknown means blocked. Confirm IL, TX, WA, CO; add CA unless counsel accepts §1798.145(a)(1)(E); add EU, UK, Canada. No template written to disk. TX stays blocked despite TRAIGA (e)(3) |
| "Hunt never logs in" | **Keep, clarify** | Hunt's code never logs in or uses her session. The Hunt Browser holds her session for her own browsing only |
| Logged-out reads with an honest UA | **Change** | robots.txt-aware. Default-deny hosts (Facebook, Instagram, Threads, LinkedIn, X, Reddit) get one-page reads on her click only. No headless recapture of them in Check again. YouTube moves to the Data API |
| Per-source rate limits | **Change** | Add: stop on 429; never rotate IPs |
| Check again | **Change** | Login-walled platforms move to a worklist with automatic diffing. Warn on LinkedIn and Story notifications |
| **New:** capture extension off on LinkedIn, Strava, Snapchat | **New** | Their terms name extensions or semi-automated tools; LinkedIn scans for 6,236 extension IDs ([BleepingComputer](https://www.bleepingcomputer.com/news/security/linkedin-secretely-scans-for-6-000-plus-chrome-extensions-collects-data/)) |
| **New:** revocation hard stop | **New** | The CFAA and §502 line (*Power Ventures*) |
| **New:** audience flag | **New** | Items not shown as Public are flagged and left out of the report unless counsel approves. Public exclusions stop at "restricted to a specific audience" (CCPA, Virginia, Texas). The ethics opinions haven't addressed "putatively private" content |
| **New:** Washington MHMDA mode | **New** | For Washington subjects: record the .100(3) fraud basis per case; word findings as observed activity, not physical condition; minimise |
| **New:** purpose split | **New** | Claims vs employment or eligibility, recorded per case. Employment checks run FCRA mode, with identity confirmed before reporting (*Social Intelligence*; "in whole or in part") |
| **New:** capture record and attribution | **New** | Capture-time hash, account used, audience and tool version (902(13)/(14)). A separate attribution section (*Vayner*, *Browne*). AI hits are leads |
| **New:** vendor connector rules | **New** | Optional, off by default, her own key, provenance per record, vendor's permitted-use clause on file |
| **New:** EU, UK and Canadian subjects | **New** | Per-case basis and notice-exemption record (Art. 14(5)(b); Sch. 2 para 2; PIPEDA s.7(1)(b)) |

## 6. Uncertainty

What the notes could not confirm:
- **Clearview, Seventh Circuit** (2026-07-13, 181 F.4th 785): read only through an excerpt and secondary reports. Rehearing, cert or a revised settlement are unknown.
- **The *Ryanair* appeal** (3d Cir. No. 25-1374): no ruling confirmed as of the docket's 2026-04-25 update. One trade site claims Booking.com won, unverified.
- **The Voyager settlement date:** not confirmed, probably late 2024. Docket number unconfirmed.
- **LinkedIn extension scanning:** the 6,236-ID script is confirmed. Whether it detects a private, unpublished extension is unknown. The 2026 crackdown figures ("close to 40%" restricted) come from vendor blogs and are unverified.
- **Logged-out Instagram and Facebook depth:**
  - Vendor and low-quality blog sources only.
  - No official grid figure.
  - Instagram's `/p/<id>/embed/` content wasn't observed.
  - Facebook personal profiles were untested.
  - TikTok's figures come from a vendor using unblocking tools.
- **Primary texts not read:**
  - the *Meta v. Bright Data* order (quotes are second-hand);
  - the *X v. Bright Data* May 2024 opinion;
  - the *hiQ* Nov 2022 summary-judgment order;
  - *Vayner*, *Parker*, *Tienda*, *Hassan*, *Midwest Motor Sports*, *Gidatex*.
- **Ethics opinions read only as quoted elsewhere:** ABA 466, NYC 2010-2, Philadelphia 2009-02, San Diego 2011-2, New Hampshire, Massachusetts and Pa. 2014-300. There is no 2020–2026 opinion on automated collection or AI agents.
- **Untested doctrine:**
  - No case on auto-scroll a user starts and watches.
  - No post-*Van Buren* appellate ruling applying footnote 8 to terms-only automation.
  - *Power Ventures* n.1, "automatic boilerplate revocation", is unresolved.
  - *BrandTotal* and *Bright Data* conflict on survival after a ban.
  - Florida §815.06's "manner of use" wording is untested. Texas §33.02 wasn't retrieved.
- **Terms not confirmed:**
  - Instagram's current effective date;
  - the Threads supplemental terms;
  - X's automation help page;
  - the YouTube API Services ToS;
  - Reddit's primary Data API terms;
  - vendor API terms.
- **Platform behaviour:**
  - Meta's checkpoint and "automated behaviour" criteria are undocumented.
  - Story-viewer lists and LinkedIn's current notification behaviour weren't verified.
  - Whether a WebDriver-launched Hunt Browser gets flagged is our inference.
  - Enforcement against Hunchly-style passive capture tools wasn't researched.
- **About Ethos:** its licensed states, its CCPA "business" status, whether it is an insurance-support organization, and its insurer contract terms.
- **Regulatory moves:**
  - The Model 670 adoption chart is dated Fall 2021.
  - Model 672's revision status rests on an aggregator.
  - The CCPA ADMT "significant decision" list isn't confirmed to include insurance.
  - Colorado's final Rule 2.02 is unconfirmed.
  - The outcome of the Oct 15, 2026 evidence-rules meeting is unknown.
  - The CCDH appeal (9th Cir. 24-2643) status is unknown.
- **Interpretation:** whether claim decisions are "eligibility determinations" under Meta §3.a.ii, LinkedIn §3.1(17) and Skopenow's FAQ is our inference.
- **GDPR background:** EDPB 3/2018, CJEU cases, the AI Act text and DUAA commencement were not re-fetched.
- **TikTok:** no enforcement history at all, and a new US entity since 2026-07-15.

## 7. Questions for Ethos's counsel

1. Will Ethos accept the contract risk of passive capture in a human-driven browser on Meta and TikTok, given the "automated means" wording? Will it bar capture on LinkedIn, Strava and Snapchat?
2. In which states does Ethos hold agency licences? Do any insurer or SIU contracts restrict social-media methods or tools?
3. Is a claims report ever reused for underwriting, renewal or employment, which would make it a consumer report "in part"?
4. Is Ethos a CCPA "business", an insurance-support organization in Model 670 states, or a service provider under its insurer contracts?
5. Should every claimant be treated as represented? What is the policy on LinkedIn viewing mode and on viewing Stories while logged in, especially in New York matters?
6. Face check: block California, or rely on the legal-claims exemption? Does TRAIGA (e)(3) change anything in Texas?
7. Washington: how should Ethos document the MHMDA fraud exemption for physical-capacity findings?
8. robots.txt: is a single, user-initiated, honest-UA lookup on a default-deny site acceptable, or should Hunt honour robots.txt strictly?
9. Does the YouTube 30-day storage rule reach metadata kept in a case file?
10. Should Ethos seek X's written approval under §XIV.B(a), or a vendor contract with a lawful-collection warranty and indemnity?
11. What is the response plan if Meta or TikTok disables an investigator's account, or sends Ethos or Aaron a cease-and-desist letter?
12. For EU or UK subjects: does Ethos need Art. 27 representatives, a legitimate-interests assessment and a published privacy notice?
