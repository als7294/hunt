# Tessera: design brief for Claude Design

Paste everything below the line into Claude Design.

---

You're designing **Tessera**, a free, open-source OSINT (open-source intelligence) investigation tool. The visual direction, branding, layout, typography, colour, iconography and interaction patterns are entirely yours. I'm deliberately giving you no direction on any of that. "Tessera" is the working name, and how it's expressed visually is up to you.

Below are the product, the people it's for, and what it needs to do. **Run with these features, and feel free to add more where they'd genuinely help an investigator, within reason.** If you see a better way to combine or present capabilities, do it.

## The product in one paragraph

Investigators who run background checks and social media reports currently juggle dozens of single-purpose tools: one for usernames, another for emails, another for phone numbers, plus court records, archives, maps and reverse image search. They copy results between them by hand and write the report themselves. Tessera replaces that. The investigator enters whatever they have about a subject, whether a name, username, email, phone number, address, social media link or photo. Tessera checks every source at once, works out which results really belong to the same person, captures tamper-evident evidence of everything it finds, estimates where photos were taken using AI running on the investigator's own computer, and produces a professional, fully cited report.

## Who uses it

- **Primary:** professional OSINT investigators doing background checks, due diligence and social media screening for clients. They're detail-oriented, under time pressure, and accountable for accuracy. A wrong identity match can harm an innocent person who happens to share a name.
- **Also:** journalists, researchers, trust & safety teams, and students learning OSINT tradecraft.
- **What they care about:** being certain they have the right person, being able to prove where every fact came from, never alerting the subject they're being researched, and getting the report done faster.

## Platform context

- **The app** is desktop software that runs entirely on the investigator's own computer (macOS first, then Windows and Linux). Case data and photos never leave the machine unless a source requires an online lookup, and the app is transparent about when that happens.
- **The website** is a public landing page that explains and promotes the free download. It does not run searches.

## Features

1. **Cases.** Work is organised into cases. Starting a case requires stating the purpose of the investigation and its scope. Each case keeps an audit log of every search run and why.
2. **Universal intake.** One place to paste or drop anything known about the subject: name, username, email, phone, address, profile URL or photo. Tessera works out what each item is and normalises it.
3. **Live search across every source.** Searching fans out to dozens of sources at once. The investigator can see each source's status (running, found something, found nothing, rate-limited, failed, skipped) as results stream in. "Searched and found nothing" is recorded too, because it matters in a report.
4. **Identity resolution (the core feature).** Results are grouped into candidate identities ranked by how likely each one is to be the subject. Every candidate comes with a plain-language explanation of which details agree and which conflict ("same username and city, different birth year"). The investigator can confirm, reject with a reason, or merge candidates. Tessera warns when a common name makes look-alikes likely.
5. **Pivoting.** Anything discovered, such as a new username, email, linked site or location, can become a new search in one action. The investigator can see how all the discovered people, accounts and identifiers connect.
6. **Evidence locker.** Every finding is automatically preserved: a snapshot of the page, an archived copy, the exact capture time, and a cryptographic fingerprint that proves it hasn't been altered. Each source carries a reliability grade. Archived copies of deleted pages are pulled in where available.
7. **Timeline.** The subject's activity across platforms laid out over time.
8. **Photo analysis and geolocation.** The investigator drops in photos and Tessera estimates where they were taken, GeoGuessr-style, using AI that runs locally:
   - reads hidden location data in the file, if present
   - picks out clues such as signs and their language, which side of the road cars drive on, architecture and vegetation
   - proposes ranked candidate locations, each with a confidence radius, never a single falsely precise pin
   - offers tools to verify a candidate: comparing against street-level imagery near it, nearby businesses and landmarks, and sun and shadow angles
   - spots when the same photo or profile picture appears on different accounts
9. **Map.** Every location signal in one place: known addresses, photo locations, and candidate locations from photo analysis.
10. **Report builder.** Produces a professional investigation report: a bottom-line-up-front summary, scope and purpose, how the identity was confirmed (and which look-alikes were ruled out), methodology including sources that returned nothing, findings with evidence references, confidence statements in standard intelligence language ("likely", "very likely"), limitations, and an evidence appendix with fingerprints.
    - A local AI drafts the summary, and every sentence it writes must link to evidence. Claims without evidence are blocked.
    - Exports to PDF, HTML and structured data.
    - Has a compliance mode for employment screening that removes protected personal characteristics.
11. **Privacy and hardware status.** Shows what the investigator's computer is capable of (e.g. which local AI models are installed and ready), and makes clear for each source whether anything leaves the machine.
12. **Sources and settings.** Turn sources on or off. Add optional API keys. Enable optional advanced plugins, each clearly labelled with its risk. Set rate limits. Route traffic through a VPN or proxy so the investigator's own identity and location stay hidden.
13. **Responsible-use guardrails.**
    - collection is passive only: Tessera never follows, likes, messages or logs in as anyone
    - a flag for subjects who may be minors
    - per-case data retention and permanent purge
    - the purpose statement and audit log from feature 1

    These should feel like part of a professional tool, not nagging.
14. **Startup / loading screen.** What the investigator sees while the app launches: local AI models warming up and sources being health-checked.
15. **Public landing page.** Explains:
    - what Tessera is and the problem it solves
    - that it's free and open source
    - that it runs locally and keeps data private
    - how it works
    - what sources it draws on
    - its responsible-use policy
    - how to download and install

    It may include a demo walkthrough using a fictional case.

## Content rule (non-negotiable)

All sample data must be clearly fictional: invented names, handles, emails, phone numbers, addresses and places. Use no real people, no real faces and no real social media accounts. Placeholder or illustrated imagery is fine.

## What I need from you

**Phase 1: four static concepts.**
- Create **4 distinct design concepts**.
- Each concept covers all three of:
  1. the public **landing page**
  2. the app's main **dashboard** (an investigation in progress, showing the core features above)
  3. the app's **startup/loading screen**
- Make the four concepts genuinely different from each other, not variations on one idea. Give each a short name and a sentence on its thinking.

**Phase 2: full prototype.**
- I'll pick one concept. You then build it out as a **full clickable prototype**: landing page, loading screen, and the app covering the full feature set above (including anything you added), all using the fictional sample case.
