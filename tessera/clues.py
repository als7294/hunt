"""Photo clues → per-country evidence, from the text in a photo and a vision model's observations.

Only clues that hold in an ordinary phone photo are here: what the text says (script,
rare letters, web addresses, phone numbers, currency signs, postcodes, mph), which side
traffic drives on, and a few
well-established road-marking, sign and plate conventions. Street-View-only "meta"
(camera generation, Google car, blur, coverage) never applies to a real photo, and
poles, bollards, architecture and vegetation are too fine-grained to trust from a
vision model's free text. See docs/research/geoguessr-meta.md.

Weights are Fellegi-Sunter bits, as in match.py: log2(m/u), where m is how often the
clue shows up when the photo IS from a country and u how often it shows up elsewhere.
Every country sharing a clue gets the same bits (Cyrillic doesn't separate Russia
from Bulgaria; other clues do that). A misread is always possible: OCR confuses
look-alike letters, the vision model guesses and can invent text, and front-camera
selfies are often mirrored, which flips the apparent driving side.
"""

import re
import unicodedata
from collections import defaultdict

import phonenumbers

from .match import bits

COUNTRIES = {c.lower() for c in phonenumbers.SUPPORTED_REGIONS}  # ISO 3166-1 alpha-2, plus a few territories

# (m, u) per clue. Calibrated for photo.fuse(), where a 3-5 bit gap between countries is decisive.
SCRIPT = (0.9, 0.05)  # 4.2 bits: a distinctive script on signs
ADDRESS = (0.8, 0.05)  # 4.0: a national web domain or phone code (foreign ads and tourists exist)
MARKER = (0.7, 0.05)  # 3.8: a currency sign, postcode or 'mph' in the text
LETTER = (0.6, 0.06)  # 3.3: a letter only a few languages use (OCR can misread one)
HANZI = (0.8, 0.1)  # 3.0: simplified vs traditional Chinese characters
DRIVING = (0.8, 0.2)  # ±2.0, a 4-bit swing: mirrored selfies and empty roads mislead
LANGUAGE = (0.6, 0.12)  # 2.3: the vision model's language guess, read from the same text
WEAK = (0.6, 0.35)  # 0.8: road-marking, sign and plate conventions in the vision model's prose
GUESS = [(0.4, 0.1), (0.2, 0.1), (0.15, 0.1)]  # 2.0, 1.0, 0.6: the vision model's own country guesses

# Left-hand traffic (en.wikipedia.org/wiki/Left-_and_right-hand_traffic); everywhere else drives on the right,
# Gibraltar included. Judge it by traffic flow, not the steering wheel: the Bahamas, Caymans, Turks and
# Caicos and British Virgin Islands keep left in mostly left-hand-drive cars imported from the US.
LEFT = set("ac ag ai au bb bd bm bn bs bt bw cc ck cx cy dm fj fk gb gd gg gy hk id ie im in je jm jp ke ki kn ky "
           "lc lk ls mo ms mt mu mv mw my mz na nf np nr nu nz pg pk sb sc sg sh sr sz ta tc th tk tl to tt tv tz "
           "ug vc vg vi ws za zm zw".split())

# Language (ISO 639-1, as the vision model reports it) → countries where it's on everyday signs.
# English is left out: it's on signs almost everywhere. Official-language lists per Wikipedia's
# "List of official languages by country and territory".
LANGUAGES = {k: v.split() for k, v in {
    "ja": "jp", "ko": "kr kp", "zh": "cn tw hk mo sg", "th": "th", "vi": "vn", "km": "kh", "lo": "la", "my": "mm",
    "si": "lk", "dv": "mv", "ne": "np", "hi": "in", "bn": "bd in", "ta": "in lk sg my", "te": "in", "kn": "in",
    "ml": "in", "mr": "in", "gu": "in", "pa": "in pk", "ur": "pk in", "fa": "ir af", "ps": "af", "he": "il",
    "ar": "sa ae eg ma dz tn ly iq jo lb sy ye om qa kw bh sd mr ps km dj",
    "el": "gr cy", "ka": "ge", "hy": "am", "am": "et", "ti": "er et", "tr": "tr cy", "az": "az", "ru": "ru by kz kg",
    "uk": "ua", "be": "by", "kk": "kz", "ky": "kg", "mn": "mn", "uz": "uz", "tg": "tj", "bg": "bg", "sr": "rs ba me",
    "mk": "mk", "bs": "ba", "hr": "hr ba", "sl": "si", "cs": "cz", "sk": "sk", "pl": "pl", "hu": "hu", "ro": "ro md",
    "lt": "lt", "lv": "lv", "et": "ee", "fi": "fi", "sv": "se fi ax", "no": "no", "nb": "no", "nn": "no", "da": "dk",
    "is": "is", "fo": "fo", "de": "de at ch lu li be", "nl": "nl be sr", "it": "it ch sm va", "ca": "es ad",
    "eu": "es", "gl": "es", "ga": "ie", "cy": "gb", "mt": "mt", "sq": "al xk", "id": "id", "ms": "my bn sg",
    "tl": "ph", "sw": "ke tz ug", "af": "za na", "zu": "za", "xh": "za", "so": "so", "ha": "ng ne", "yo": "ng",
    "ig": "ng", "mg": "mg", "rw": "rw", "ht": "ht", "mi": "nz", "sm": "ws", "to": "to", "fj": "fj",
    "fr": "fr be ch lu mc ca sn ci ml bf ne td cm cd cg ga gn bj tg mg ht dj km cf rw bi sc vu re gp mq gf yt nc "
          "pf pm wf bl mf",
    "es": "es mx gt hn sv ni cr pa cu do pr co ve ec pe bo cl ar py uy gq",
    "pt": "pt br ao mz cv gw st tl mo",
}.items()}

# Script (first word of each character's Unicode name) → countries whose everyday signs use it.
# Latin is everywhere, so it says nothing. Han and Arabic also turn up on shopfronts worldwide; u allows for that.
SCRIPTS = {k: v.split() for k, v in {
    "HIRAGANA": "jp", "KATAKANA": "jp", "CJK": "cn tw hk mo sg my jp", "HANGUL": "kr kp", "THAI": "th", "LAO": "la",
    "KHMER": "kh", "MYANMAR": "mm", "SINHALA": "lk", "THAANA": "mv", "TIBETAN": "cn bt np in", "MONGOLIAN": "mn cn",
    "DEVANAGARI": "in np", "BENGALI": "bd in", "GURMUKHI": "in", "GUJARATI": "in", "ORIYA": "in", "TAMIL": "in lk sg my",
    "TELUGU": "in", "KANNADA": "in", "MALAYALAM": "in", "GEORGIAN": "ge", "ARMENIAN": "am", "ETHIOPIC": "et er",
    "HEBREW": "il", "GREEK": "gr cy", "TIFINAGH": "ma dz", "CANADIAN": "ca", "BALINESE": "id", "JAVANESE": "id",
    "SUNDANESE": "id", "CYRILLIC": "ru ua by bg rs mk ba me kz kg tj uz mn",
    "ARABIC": " ".join(LANGUAGES["ar"]) + " ir af pk",
}.items()}

# Characters that differ between simplified Chinese (mainland, Singapore, Malaysia) and traditional
# (Taiwan, Hong Kong, Macau), chosen so that neither set is used in modern Japanese, whose kanji
# would otherwise pass for traditional.
SIMPLIFIED = "们这说让门东车马华长书时见电话发应对经产广开关业银报进动鱼饭馆汤铁药厅县价卖读欢"
TRADITIONAL = "們這說讓發應對經產廣關號樓灣臺區國會學體鐵圖醫藥廳縣價賣讀歡"

# Letters only a few languages use → where those languages are on signs. Common accents
# (é, ä, ö, ü, ç) are shared too widely to help, and ë is on every Citroën dealership.
LETTERS = {k: v.split() for k, v in {
    "őű": "hu", "łźśń": "pl", "ż": "pl mt", "ąę": "pl lt", "ć": "pl hr ba rs me", "řůě": "cz", "ťďň": "cz sk",
    "ľĺŕ": "sk", "ėįų": "lt", "ģķļņ": "lv", "āēī": "lv nz us", "ō": "nz jp us", "ū": "lv lt nz jp us",
    "ıİğ": "tr az", "ş": "tr az ro md", "ə": "az", "șț": "ro md", "ă": "ro md vn", "đ": "hr ba rs me vn",
    "ơưếềểễệốồổỗộớờởỡợứừửữựậặ": "vn", "õ": "ee pt br vn", "ã": "pt br vn", "ß": "de at lu",
    "å": "se no dk fi ax", "æ": "no dk is fo", "ø": "no dk fo", "þ": "is", "ð": "is fo", "ħġċ": "mt", "ŵŷ": "gb",
    "ñ¿¡": " ".join(LANGUAGES["es"]),
    "їєґ": "ua", "і": "ua by kz", "ў": "by uz", "ђћ": "rs ba me", "џљњј": "rs mk ba me", "ѓќѕ": "mk",
    "әұһ": "kz", "ғқ": "kz uz tj", "ң": "kz kg", "өү": "mn kz kg", "ыэ": "ru by kz kg mn",
}.items()}

# Country-code domains used worldwide as brand names (.io, .co, .tv, .me, .ai ...) say nothing about place.
VANITY = set("ac ag ai am cc cd co cx dj fm gd gg gl im io la ly md me ms nu pw sh so st sx tk to tv vc ws".split())
DOMAIN = re.compile(r"(?<![\w.-])((?:[a-z0-9-]+\.)+)([a-z]{2})(?![\w-])", re.I)
PHONE = re.compile(r"(?<![\w+])\+(\d[\d\s().-]{6,})")

EU = "at be bg cy cz de dk ee es fi fr gr hr hu ie it lt lu lv mt nl pl pt ro se si sk"
# Euro users (en.wikipedia.org/wiki/Eurozone; Bulgaria joined 2026-01-01), with their French territories.
EURO = "at be bg hr cy ee fi fr de gr ie it lv lt lu mt nl pt sk si es ad mc sm va xk me gp mq gf re yt pm bl mf"

# National markers in shop, menu and street text, as regexes → countries.
# Currency signs: en.wikipedia.org/wiki/Currency_symbol. A bare '$' is too widely shared to help.
CURRENCIES = {re.compile(p): c.split() for p, c in {
    "₩": "kr kp", "₹": "in", "₽": "ru", "₺": "tr", "₫": "vn", "₱": "ph", "฿": "th", "₴": "ua", "₪": "il ps",
    "₦": "ng", "₵": "gh", "₸": "kz", "₾": "ge", "₼": "az tm", "₮": "mn", "៛": "kh", "₭": "la", "₲": "py",
    "₡": "cr", "¥": "jp cn", "円": "jp", "€": EURO, "£": "gb gg je im gi fk sh",
    r"(?<![A-Za-z])R\$": "br", r"(?<![A-Za-z])S\$": "sg", r"HK\$": "hk", r"NT\$": "tw", r"(?<![A-Za-z])AU?\$": "au",
    r"NZ\$": "nz", r"MX\$": "mx", r"(?<![A-Za-z])Rp\.?\s?\d": "id", r"(?<![A-Za-z])Rs\.?\s?\d": "in pk lk np mu sc",
    r"\d\s?Kč": "cz",
}.items()}
# Postcode formats distinctive enough to recognise (most countries' 4-6 digit codes look like any number).
# Formats per Wikipedia's "Postcodes in the United Kingdom", "Postal codes in Canada", "Eircode",
# "Postal codes in Brazil" and "Postal codes in Japan".
POSTCODES = {re.compile(p): c.split() for p, c in {
    r"\b[A-Z]{1,2}\d[A-Z\d]? \d[ABD-HJLNP-UW-Z]{2}\b": "gb gg je im",
    r"\b[ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z] ?\d[ABCEGHJ-NPRSTV-Z]\d\b": "ca",
    r"\b(?:[AC-FHKNPRTV-Y]\d{2}|D6W) (?=[0-9AC-FHKNPRTV-Y]*[AC-FHKNPRTV-Y])[0-9AC-FHKNPRTV-Y]{4}\b": "ie",
    r"\b\d{5}-\d{3}\b": "br",
    r"〒\s?\d{3}-?\d{4}": "jp",
}.items()}
# Speed limits in mph (en.wikipedia.org/wiki/Miles_per_hour; Liberia only occasionally, so left out).
MPH = re.compile(r"\bmph\b", re.I)
MPH_COUNTRIES = ("us gb ag bs bz dm gd mh fm pw kn lc vc ai vg io ky fk ms sh ac ta tc gg im je as gu mp pr "
                 "vi").split()
# Conventions the vision model may describe in prose: (observation field, pattern, countries, what it means).
# Only countries where Plonk It or Wikipedia say the style is the norm (docs/research/geoguessr-meta.md has
# the sources and the near-misses left out: yellow centre lines that only mean no-passing, snow or
# roadworks; plates that are yellow only on taxis).
NEAR = r"(?:[\s-]+(?!white\b)\w+){0,3}?[\s-]+"  # up to three words between, no punctuation, no other colour
HINTS = [(field, re.compile(pattern), countries.split(), why) for field, pattern, countries, why in [
    ("road_markings", rf"yellow{NEAR}(?:cent(?:er|re)|middle|median)",
     "us ca mx no kr th tw ke gt cr pa do pr co ec pe bo py br gu as mp", "yellow centre lines"),
    ("road_markings", rf"yellow{NEAR}(?:edge|shoulder)", "za bw na ls sz om ae ie il", "yellow edge lines"),
    ("signs", rf"yellow{NEAR}diamond|diamond{NEAR}yellow", "us ca mx au nz ie jp th my id lr",
     "yellow diamond warning signs"),
    ("plates", rf"blue{NEAR}(?:band|strip|stripe)", EU + " no rs me mk ba tr md il", "EU-style blue band on plates"),
    ("plates", rf"yellow{NEAR}(?:licen[cs]e\W+|number\W+|registration\W+)?plates?",
     "nl lu il co la om gb je im gi hk ke ug rw bw lk", "yellow number plates (front, or rear only)"),
]]


def country_evidence(obs: dict, text: str) -> dict[str, list[tuple[float, str]]]:
    """Country code → [(bits, reason)] from a vision model's observation dict and OCR text.

    Positive bits for countries the clues fit, negative where a clue rules a country out
    (only driving side does). Missing or "unknown" fields add nothing; {} means no clue.
    """
    ev = defaultdict(list)

    def add(countries, weight, why):
        for c in countries:
            ev[c].append((weight, why))

    # A clue counts once per country, however often it repeats. The vision model's own
    # transcription may invent text, so it gets half weight and only adds what OCR missed.
    vlm_text = obs.get("text") or []
    vlm_text = " ".join(map(str, vlm_text)) if isinstance(vlm_text, list) else str(vlm_text)
    seen = set()
    for source, clues in (("", _text_clues(text)), (" (read by the vision model, not OCR)", _text_clues(vlm_text))):
        for kind, countries, weight, why in clues:
            if rest := [c for c in countries if (kind, c) not in seen]:
                seen |= {(kind, c) for c in rest}
                add(rest, weight / 2 if source else weight, why + source)

    side = str(obs.get("driving_side")).lower()
    if side in ("left", "right"):
        other = "right" if side == "left" else "left"
        for c in COUNTRIES:
            agree = (c in LEFT) == (side == "left")
            add([c], bits(*DRIVING, agree), f"traffic drives on the {side}" if agree else
                f"traffic drives on the {side}, but here it drives on the {other}")
    if countries := LANGUAGES.get(str(obs.get("language")).lower()):
        add(countries, bits(*LANGUAGE), f"signs are in language '{obs['language']}' (vision model)")
    for field, pattern, countries, why in HINTS:
        if pattern.search(str(obs.get(field) or "").lower()):
            add(countries, bits(*WEAK), f"{why} (vision model: {obs[field]!r})")
    guesses = [g for g in obs.get("countries") or [] if isinstance(g, dict)]
    for (m, u), guess in zip(GUESS, guesses):
        if (code := str(guess.get("code")).lower()) in COUNTRIES:
            add([code], bits(m, u), f"vision model's guess: {guess.get('why') or 'no reason given'}")
    return dict(ev)


def _text_clues(text: str) -> list[tuple[str, list[str], float, str]]:
    """(kind, countries, bits, reason) for every clue in a piece of text. A kind repeats when the clue does."""
    text = unicodedata.normalize("NFC", text)
    out = []
    scripts = defaultdict(list)
    for ch in text:
        name = unicodedata.name(ch, "").split(" ")[0].split("-")[0]
        if name in SCRIPTS:
            scripts[name].append(ch)
    for script, chars in scripts.items():
        # Two characters, so one stray Greek μ or Cyrillic look-alike isn't a clue; one kana is
        # enough, since Japanese place names often carry a lone ヶ or ノ among the kanji.
        if len(chars) >= 2 or script in ("HIRAGANA", "KATAKANA"):
            label = {"CJK": "Han (Chinese-character)", "CANADIAN": "Canadian syllabics"}.get(script, script.title())
            out.append((script, SCRIPTS[script], bits(*SCRIPT), f"{label} script in the text ({''.join(chars[:6])})"))
    for chars, countries, form in ((SIMPLIFIED, ["cn", "sg", "my"], "simplified"),
                                   (TRADITIONAL, ["tw", "hk", "mo"], "traditional")):
        if found := "".join(sorted({c for c in text if c in chars})):
            out.append((form, countries, bits(*HANZI), f"{form} Chinese characters ({found})"))

    # Rare letters count only inside word-shaped tokens: 3+ letters, all lower, ALL UPPER or Title. Latin-only
    # OCR turns kanji into junk like 'İF E' or 'îEĚV^', which would otherwise read as Turkish and Czech.
    words = "".join(w for w in re.findall(r"[^\W\d_]+", text)
                    if len(w) >= 3 and (w.islower() or w.isupper() or w.istitle()))
    letters = defaultdict(set)
    chars = set(words) | set(words.lower()) | {c for c in text if not c.isalpha()}  # ¿ and ¡ are punctuation
    for group, countries in LETTERS.items():
        for c in countries:
            letters[c] |= chars & set(group)
    for c, found in letters.items():
        if found:  # one reason per country, however many of its letters appear: they're one clue
            out.append(("letters", [c], bits(*LETTER), f"letters {', '.join(sorted(found))} in the text"))

    for m in DOMAIN.finditer(text):
        labels, tld = m.group(1).rstrip(".").split("."), m.group(2).lower()
        code = "gb" if tld == "uk" else tld
        # 'qfes.qld.gov.au' and 'kfc.de' count; 'Dr.No' doesn't.
        if code in COUNTRIES and code not in VANITY and (len(labels) > 1 or len(labels[0]) > 2):
            out.append(("domain", [code], bits(*ADDRESS), f"web address {m.group(0)}"))
    for m in PHONE.finditer(text):
        digits = re.sub(r"\D", "", m.group(1))
        # Calling codes are prefix-free: the first 1-3 digits that name a code are the code.
        regions = next((r for n in (1, 2, 3) if (r := phonenumbers.region_codes_for_country_code(int(digits[:n])))), ())
        if codes := [r.lower() for r in regions if r.lower() in COUNTRIES]:
            out.append(("phone", codes, bits(*ADDRESS), f"phone number +{m.group(1).strip()}"))
    for kind, table in (("currency", CURRENCIES), ("postcode", POSTCODES)):
        for pattern, countries in table.items():
            if m := pattern.search(text):
                out.append((kind, countries, bits(*MARKER), f"{kind} '{m.group(0).strip()}' in the text"))
    if MPH.search(text):
        out.append(("mph", MPH_COUNTRIES, bits(*MARKER), "speeds in mph"))
    return out
