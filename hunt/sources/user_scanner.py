"""Email → sites it's registered on (user-scanner, MIT, github.com/kaifcodec/user-scanner).

Passive only: a module runs only once its code has been read and judged silent.
Modules that notify the subject, or could (password resets, login codes, sign-ups
that might go through, password login attempts), never run; they are only counted.
Re-audit after upgrading user-scanner: `uv run python -m hunt.sources.user_scanner`.
"""

import asyncio
import os
import re
from importlib.metadata import version
from pathlib import Path

from user_scanner.core.engine import check
from user_scanner.core.helpers import get_site_name, is_loud, load_categories, load_modules, set_proxy_manager
from user_scanner.core.result import Status

from ..seed import Finding

NAME = "user-scanner"
KINDS = {"email"}
AUDITED = "1.5.2.3"  # user-scanner release the two sets below were read against

# Never run. A login attempt with a password counts (failed-login alerts, lockouts).
# A sign-up counts unless a field it can't succeed without is blank or absurdly short.
# If the code can't rule out a mail or SMS to the address, it counts.
NOTIFIES = {
    "addictinggames",  # full sign-up; only someone else's taken username stops it
    "aiscore",  # full sign-up with a valid password; any reply but "existed" reads as available
    "amazon",  # submits the sign-in form; Amazon's A/B-tested /ax/claim flow can send a one-time code
    "anilist",  # calls the ResetPassword mutation; only a server-side check stops the reset mail
    "bunny",  # full sign-up; only the password composition rule stops account + verification mail
    "classmates",  # password login attempt
    "cnn",  # POSTs a new email+password identity; the "available" reply carries new-profile rights
    "dollarfix",  # password login attempt
    "dreame",  # password login attempt
    "evolveyou",  # password login attempt
    "facebook",  # "find your account" recovery step; the next step sends the code, server picks it
    "fixderma",  # Shopify customerCreate mails guest-checkout customers an activation link
    "flickr",  # full Cognito sign-up; only the captcha pre-check stops the verification code
    "globaltimes",  # password login attempt; counts toward account lockout
    "hackerone",  # full sign-up; only a mismatched password confirmation stops it
    "hackthebox",  # user/email/verify may be the step that mails a code; unconfirmed
    "hautesauce",  # Shopify customerCreate, as fixderma
    "hubspot",  # login POST; even a blank password is judged INVALID_PASSWORD
    "iyoni",  # Firebase verifyPassword login attempt
    "lespark",  # password login attempt
    "letsporn",  # full sign-up with an email_link; only mismatched passwords stop it
    "letterboxd",  # full sign-up; only the empty captcha stops it
    "locanto",  # email-only register_attempt; success likely mails a sign-up link
    "lovescape",  # full sign-up; only someone else's taken username stops it
    "mastodon",  # full sign-up on mastodon.social; only someone else's taken username stops it
    "meeff",  # login attempt; empty password is judged a mismatch
    "mondly",  # password login attempt
    "nextdoor",  # OAuth password-grant login attempt
    "numsify",  # full sign-up; only the password-needs-a-digit rule stops it
    "patreon",  # drives the real auth flow; passwordless accounts get an emailed code here; unconfirmed
    "premom",  # full sign-up; only the missing first name stops it
    "qiita",  # full sign-up; only the empty reCAPTCHA stops it
    "stackb",  # password login attempt
    "stackoverflow",  # password login attempt
    "stremio",  # password login attempt
    "sweat",  # Auth0 password login; Auth0 brute-force protection emails the owner
    "thegay",  # full sign-up; only a missing token stops it
    "vedantu",  # preLoginVerification precedes the login OTP; can't rule out that it sends it
    "vivino",  # password login attempt; can lock the account
    "whering",  # Firebase verifyPassword login attempt
    "womanlog",  # password login attempt
    "xda",  # check-user-exists sent with subscribe=true (newsletter flow)
}

# Read and judged silent: lookups, field validators, identifier-first steps, and
# sign-ups missing a field they can't succeed without.
AUDITED_SILENT = {
    "adobe",  # users/accounts lookup
    "aljazeera",  # Firebase createAuthUri lookup
    "alison",  # sign-up with blank password
    "allen",  # user identities lookup
    "alza_at", "alza_cz", "alza_de", "alza_hu", "alza_sk",  # CheckLoginAvailability lookup
    "annaabi",  # register.php?emailcheck validator
    "anydo",  # check_email lookup
    "appletv",  # idmsa federate lookup
    "aslbloom",  # searchForUser lookup
    "atlassian",  # check-username lookup
    "axonaut",  # GET onboarding?email, reads the redirect
    "babbel",  # sign-up with blank password, terms unaccepted
    "bbc",  # identifier/check lookup
    "besoccer",  # sign-up with blank password
    "cakeapp",  # email/validate
    "canva",  # user-authentication-methods lookup
    "chess_com",  # EmailValidationService/Validate
    "classdojo",  # emailValidation lookup
    "codecademy",  # register/validate
    "codepen",  # duplicate_check
    "codewars",  # sign-up with blank username and password
    "coursera",  # getLoginMethods lookup
    "crazygames",  # Firebase createAuthUri lookup
    "deezer",  # user_checkRegisterConstraints validator
    "deviantart",  # sign-up with blank password
    "devrant",  # sign-up with blank username and password
    "dirbam",  # email validator
    "disqus",  # sign-up with blank password
    "dropbox",  # check_user_with_email_exists lookup ("recover" is a reply field)
    "duolingo",  # users?email lookup
    "ekontakti",  # validate-email-address
    "emirates",  # validate-email
    "envato",  # validate_email
    "espn",  # Disney guest-flow lookup (login vs registration)
    "etsy",  # users/by-identity lookup
    "eventbrite",  # users/lookup
    "fapfolder",  # sign-up with a 1-character password
    "faproulette",  # userCheckEmail
    "femometer",  # user_location lookup
    "figma",  # available_auth_methods lookup
    "firefox",  # account/status lookup
    "fitnessblender",  # validate/unique-email
    "flipboard",  # checkEmail
    "foxnews",  # status lookup
    "freelancer",  # users/check
    "gaana",  # Times SSO checkUserExists
    "girlslife",  # sign-up with blank password
    "github",  # email_validity_checks and public user search
    "glow",  # signup_email validator
    "gravatar",  # public profile by email hash
    "gumroad",  # sign-up with a 3-character password
    "hackerearth",  # sign-up with blank password
    "hackerrank",  # valid_email
    "happypancake",  # validateemail
    "howtogeek",  # check-user-exists
    "huggingface",  # check-user-email
    "indiatimes",  # Times SSO checkUserExists
    "insightly",  # isemailvalid
    "instagram",  # check_email
    "jiosaavn",  # user.isRegisteredEmail
    "justwatch",  # Firebase createAuthUri lookup
    "kandideeri",  # sign-up field validator
    "kick",  # signup/verify/email field validator; codes go via a separate send endpoint
    "komoot",  # signin identifier step (login vs register)
    "leanpub",  # sign-up with a 1-character password
    "lingq",  # validate-field
    "locket",  # validateEmailAddress
    "lovenudge",  # register/check
    "marca",  # usuarios/comprobacion lookup
    "medal",  # users/email lookup
    "meetyou",  # email_check
    "mewe",  # check/user/email
    "mixcloud",  # sign-up with blank password
    "moz",  # user.create.validate, the dry-run twin of user.create
    "myanimelist",  # signup/email/validate
    "myfitnesspal",  # user-exists
    "myperiodtracker",  # checkAccount
    "naturabuy",  # register field validator
    "nba",  # registrationStatus lookup
    "nebula_tv",  # sign-up with a 1-character password
    "neocities",  # create_validate field validator
    "nykaaman",  # check_existence
    "nytimes",  # authorize-email/check identifier step ("forgot" is an A/B flag name)
    "office365",  # autodiscover lookup
    "okcupid",  # isEmailValid query
    "otsintood",  # email validator
    "pinterest",  # register/exists lookup
    "playtomic",  # auth/methods lookup
    "plurk",  # isEmailFound
    "polarsteps",  # validation/unique
    "pornhub",  # create_account_check validator, on a +sub-address
    "quizlet",  # validate-email
    "quora",  # validateEmail query
    "rappi",  # check-email; its OTP login runs only if "--allow-loud" is in sys.argv, which hunt never takes
    "redtube",  # create_account_check validator
    "rubygems",  # sign-up with blank password and handle
    "screener",  # sign-up with blank password
    "secondline",  # has_user lookup
    "skout",  # NewUserCheck
    "skyscanner",  # accounts/search lookup
    "speak",  # Firebase createAuthUri lookup
    "spotify",  # signup account/validate
    "start_me",  # check_email
    "sunnxt",  # userAccountStatus
    "superporn",  # signup/check-email
    "tatacliq",  # check-email with sendOtp false
    "threadless",  # sign-up form with validate=true
    "tindie",  # check_email
    "trocvelo",  # check_email
    "tube8",  # register/verify_email field validator (as redtube)
    "tumblr",  # register/account/validate, the dry-run twin of register
    "vimeo",  # join with email_validation=true
    "visidarbi",  # email validator
    "walmart",  # GetLoginOptions read-only query; codes are a separate mutation
    "wisio",  # email/is_registered
    "wix",  # userAccountsByEmail
    "wondershare",  # account/inspect
    "wordpress",  # auth-options lookup
    "x",  # email_available
    "xnxx",  # checkemail
    "xvideos",  # checkemail
    "youporn",  # register/verify_email field validator (as redtube)
    "zoho",  # signin lookup
}

# Fallback for modules the audit hasn't seen: skip anything that looks like a reset,
# code, sign-up or login until someone reads it.
MAY_NOTIFY = re.compile(r"forgot|reset|recover|otp|send-?code|verif|magic|passwordless|invite|subscri"
                        r"|regist|sign.?up|join|creat|login|password|mutation", re.I)


def _modules():
    return [m for path in load_categories(is_email=True).values() for m in load_modules(path)]


def _skip(module) -> str | None:
    """Why this module must not run, or None if it may."""
    name = module.__name__  # the file stem, e.g. "alza_cz"
    if is_loud(get_site_name(module), is_email=True):
        return "upstream"
    if name in NOTIFIES:
        return "audit"
    if name in AUDITED_SILENT and version("user-scanner") == AUDITED:
        return None
    return "heuristic" if MAY_NOTIFY.search(Path(module.__file__).read_text()) else None


async def search(seed):
    proxy = os.environ.get("HUNT_PROXY")
    set_proxy_manager(proxies=[proxy] if proxy else None)
    if proxy:  # most modules open their own httpx client, which only sees a proxy via the environment
        os.environ.update(http_proxy=proxy, https_proxy=proxy, all_proxy=proxy)
    modules = _modules()
    why = {m: _skip(m) for m in modules}
    quiet = [m for m in modules if not why[m]]
    sem = asyncio.Semaphore(20)

    async def one(module):
        async with sem:
            try:
                return await asyncio.wait_for(check(module, seed.value), 30)
            except TimeoutError:
                return None

    results = [r for r in await asyncio.gather(*map(one, quiet)) if r]
    found = [Finding(NAME, seed, r.site_name, r.url or "", {"category": r.category, **r.extra})
             for r in results if r.status == Status.TAKEN]
    errors = sum(r.status == Status.ERROR for r in results) + len(quiet) - len(results)
    checked = sum(r.status in (Status.TAKEN, Status.AVAILABLE) for r in results)
    n = {k: sum(w == k for w in why.values()) for k in ("upstream", "audit", "heuristic")}
    stale = "" if version("user-scanner") == AUDITED else f"; user-scanner {version('user-scanner')} is unaudited"
    return found, checked, (f"checked {len(quiet)} sites, {errors} errors; skipped {len(modules) - len(quiet)} "
                            f"that may notify the subject ({n['upstream']} flagged by user-scanner, "
                            f"{n['audit']} by Hunt's audit, {n['heuristic']} unaudited){stale}")


if __name__ == "__main__":  # audit coverage check; executes no module
    mods = _modules()
    names = {m.__name__ for m in mods}
    assert len(names) == len(mods) and not NOTIFIES & AUDITED_SILENT
    loud = {m.__name__ for m in mods if is_loud(get_site_name(m), is_email=True)}
    assert all(_skip(m) for m in mods if m.__name__ in NOTIFIES)
    print(f"user-scanner {version('user-scanner')} (audited {AUDITED}), {len(mods)} modules: "
          f"{len(loud)} upstream-loud, {len(NOTIFIES - loud)} noisy, {len(AUDITED_SILENT - loud)} silent; "
          f"unaudited {sorted(names - loud - NOTIFIES - AUDITED_SILENT) or 'none'}; "
          f"gone {sorted((NOTIFIES | AUDITED_SILENT) - names) or 'none'}")
