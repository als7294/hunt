# The new frontend

Aaron's new design replaces the app's screens. It is one flow: describe the person, watch the investigation, confirm it's them, read the results and the report.

- **The design:** a mockup kept outside git. Its data is all mock: a fictional Jordan Ellis and timers.
- **Where it goes:** `hunt/static/v2/`, served at `/v2/` next to the current app at `/`. Signing in now lands here. The old app stays at `/`, reached by "Classic" in the nav, until everything under the avatar has moved; nothing in `hunt/static/app.js`, `app.css` or `cluster.js` changes.
- Each screen is a vanilla ES module on `core.js`'s `html` template, with no build step. New API routes go in `hunt/api2/<name>.py` with a `ROUTES` list.
- **Icons:** the design loads them from cdn.simpleicons.org and unpkg. The CSP forbids that (`img-src 'self'`), so vendor the SVGs you use into `hunt/static/v2/icons/` (Lucide is ISC, Simple Icons CC0).

Run it: `HUNT_HOME=<a scratch folder> HUNT_PORT=<free port> BROWSER=true uv run hunt app`, then open the printed sign-in link and go to `/v2/`.

## Real data only

The design promises things in its mock data that Hunt doesn't do, or mustn't. Build the look; show only what's true.

- **No fake numbers.** Every count, percentage, ETA and "posts read" comes from real events. If it's unknown, say so or leave it out.
- **Match %** is the score Hunt computed (`probability`), per account, and for a person the score of their best-supported account. "How we linked them" shows the real reasons, in order, from `reasons`.
- **Instagram, Facebook, X:** Hunt's own requests never go to these (C1), but with the investigator's Apify token they're found and read automatically through Apify (`hunt/vendor.py`). When that ran, show the real counts labelled "via Apify", and the cost and credit left. Without a token, or for a private account, show "Open in Hunt Browser" and what was captured. Never invented post counts. **LinkedIn and Threads:** Hunt Browser only.
- **Faces:** "Same face · 96%" and "Reverse image" don't exist. Hunt has no face search. Show a face result only when the case has the opt-in 1:1 check on (`face` in `/person`).
- **Risk:** derived only from flagged items the scan or leads produced. It means how much there is to review, not the chance of fraud. It's never printed in a report and never shown on a background case.
- **Evidence grade** (B2 and so on): only if computed from real fields (source kind and scan confidence). Otherwise leave it off.
- **Exposure:** Hunt holds no breach data and never will read breach dumps. Show what it does know: which sites each email is registered on (`user-scanner`, `holehe`) and where emails were published (`published_emails`). Leave a "Connect Have I Been Pwned (optional, your own key)" row unbuilt.
- **"Ask about them"** runs on the local model only, answers only from the case's own facts, and cites them. "I don't have that" is a correct answer.

## Rules the flow must keep

From `docs/research/legal.md`. These aren't style.

- **A purpose on record before any search (K1).** The Ask screen's Purpose and Case need a required "who asked, and why it's lawful" line.
- **Purposes map onto case kinds:** Insurance claim and Benefits fraud → `insurance`; Employee misconduct → `background` (it decides someone's job, so it gets the screening version); Due diligence → `diligence`. Keep Journalism as a fifth.
- **`subject_residence` is required** (F4): use the state the description names, otherwise send `unknown`.
- **Keep the gates:** blocked cases, abroad basis, retention prompts, face gate, guided-mode acknowledgement.
- **The review step is real.** The scan starts only after decisions are made. Theirs and Not them post to `/decisions`.
- **Background cases** drop what screening drops: relationships, voter data, people-search links, age.
- Children are never named. People around the subject are listed, never searched (C13). Everything else in Hunt's rules still applies.

## The rest of the app

Nothing is lost. Everything the design doesn't show goes under the avatar menu, re-skinned as time allows and linking to Classic until then: startup checks, Accounts and the Hunt Browser, the worklist, free keys, report settings, the training answer key, the Downloads inbox, notes, watch and alerts, move a case, retention, demo.
