"""Self-check for photo clues → per-country evidence. Run: uv run python test_clues.py

Offline. All text here is made up or a public place name.
"""

from hunt import clues
from hunt.clues import COUNTRIES, HINTS, LANGUAGES, LEFT, LETTERS, SCRIPTS, country_evidence
from hunt.match import bits


def totals(ev):
    return {c: sum(w for w, _ in reasons) for c, reasons in ev.items()}


def best(ev):
    """Countries tied for the highest total."""
    t = totals(ev)
    return {c for c, w in t.items() if w == max(t.values())}


# Calibrated for photo.fuse(), where 3-5 bits between countries is decisive
assert all(3 <= bits(*k) <= 5 for k in (clues.SCRIPT, clues.ADDRESS, clues.LETTER, clues.HANZI))
assert 3 <= 2 * bits(*clues.DRIVING) <= 5  # left vs right country
assert 0.5 <= bits(*clues.WEAK) <= 1

# Tables only name real codes
assert LEFT <= COUNTRIES, LEFT - COUNTRIES
for table in (LANGUAGES, SCRIPTS, LETTERS):
    assert all(set(v) <= COUNTRIES for v in table.values()), [v for v in table.values() if not set(v) <= COUNTRIES]
assert all(set(countries) <= COUNTRIES for _, _, countries, _ in HINTS)
assert all(set(c) <= COUNTRIES for t in (clues.CURRENCIES, clues.POSTCODES) for c in t.values())
assert set(clues.MPH_COUNTRIES) <= COUNTRIES and set(clues.EURO.split()) <= COUNTRIES

# Nothing in, nothing out
assert country_evidence({}, "") == {}
unknown = {"text": [], "language": "unknown", "driving_side": "unknown", "road_markings": "unknown", "plates": "unknown",
           "signs": "unknown", "poles_bollards": "unknown", "architecture": "unknown", "vegetation_terrain": "unknown",
           "sun_shadows": "unknown", "countries": [], "place": None, "candidates_ranked": []}
assert country_evidence(unknown, "") == {}

# Script: kanji alone fit China too, the one katakana ヶ makes it Japan
ev = country_evidence({}, "新宿\nShinjuku\n市ヶ谷\nIchigaya")  # Apple Vision lines, as photo.py passes them
t = totals(ev)
assert best(ev) == {"jp"} and t["jp"] > t["cn"] > 0, t
assert any("Katakana" in why for _, why in ev["jp"]), ev["jp"]
assert best(country_evidence({}, "서울역")) == {"kr", "kp"}
assert best(country_evidence({}, "ถนนสุขุมวิท")) == {"th"}
assert best(country_evidence({}, "Київ, вулиця Хрещатик")) == {"ua"}  # Cyrillic, plus ї and і
assert best(country_evidence({}, "北京东路")) == {"cn", "sg", "my"}  # 东 is simplified
assert best(country_evidence({}, "臺灣大學")) == {"tw", "hk", "mo"}  # traditional, and not Japanese 台湾大学

# Driving side: strong both ways
ev = country_evidence({"driving_side": "left"}, "")
t = totals(ev)
assert t["au"] > 0 and t["jp"] > 0 and t["gb"] > 0 and t["us"] < 0 and t["fr"] < 0, t
assert set(ev) == COUNTRIES  # every country is either consistent or contradicted
assert totals(country_evidence({"driving_side": "Right"}, ""))["us"] > 0

# Rare letters
assert best(country_evidence({}, "Győr 12 km")) == {"hu"}
assert best(country_evidence({}, "ŁÓDŹ FABRYCZNA")) == {"pl"}  # capitals too
assert best(country_evidence({}, "Straße")) == {"de", "at", "lu"}  # the Swiss write ss
assert len(country_evidence({}, "Łódź Żółć")["pl"]) == 1  # several Polish letters are one clue

# Web addresses and phone numbers
for text in ("+61 7 5546", "qfes.qld.gov.au", "Call +61 7 5546 1234 or visit qfes.qld.gov.au"):
    assert "au" in best(country_evidence({}, text)), (text, totals(country_evidence({}, text)))
assert len(country_evidence({}, "a.com.au b.com.au")["au"]) == 1  # the same clue twice is still one clue
assert best(country_evidence({}, "www.bbc.co.uk")) == {"gb"}
assert best(country_evidence({}, "info@kfc.de")) == {"de"}
assert country_evidence({}, "+44 20 7946 0000").keys() == {"gb", "gg", "im", "je"}

# Currency signs, postcodes, mph
assert best(country_evidence({}, "ラーメン ¥980")) == {"jp"}
assert best(country_evidence({}, "Phở bò 65.000₫")) == {"vn"}
assert best(country_evidence({}, "Rp 15.000")) == {"id"}
assert best(country_evidence({}, "HK$38")) == {"hk"} and best(country_evidence({}, "R$ 12,90")) == {"br"}
assert best(country_evidence({}, "Кафе-сладкарница €2,50")) == {"bg", "me"}  # Cyrillic and the euro (Bulgaria's since 2026)
assert "gb" in best(country_evidence({}, "10 Downing Street, London SW1A 2AA"))
assert best(country_evidence({}, "Ottawa ON K1A 0B1")) == {"ca"}
assert best(country_evidence({}, "Dublin D02 X285")) == {"ie"}
assert best(country_evidence({}, "〒100-0005")) == {"jp"}
assert best(country_evidence({}, "São Paulo 01310-100")) == {"br"}  # postcode, plus ã
ev = country_evidence({}, "SPEED LIMIT 25 MPH")
assert {"us", "gb", "pr"} <= best(ev) and "fr" not in ev, ev

# Things that look like clues but aren't
for text in ("CA$5", "A1 2345", "Room 12345", "2+2 = 4 km/h", "Rs", "Ft. Worth", "MPHASIS", "D02 1234"):
    assert country_evidence({}, text) == {}, (text, country_evidence({}, text))
# Scripts Apple Vision invented from texture on real Commons photos (Poland, Sri Lanka, Peru, Chile)
for text in ("เพกบอ", "ชงต้อะอ\n8รวงราคี\n52 сообо", "٤٠ امرفا", "A SCENSOR\nات ورا", "区", "РНАРМАСУ"):
    assert country_evidence({}, text) == {}, (text, country_evidence({}, text))
assert best(country_evidence({}, "Аптека Продукты")) <= {"ru", "ua", "by", "bg", "rs", "mk", "ba", "me", "kz", "kg",
                                                          "tj", "uz", "mn"}  # real short Cyrillic words still count
# Latin-only OCR reading kanji (vlm.md): junk letters must not pass for Turkish or Czech
assert country_evidence({}, "İF E\nîEĚV^") == {}
assert best(country_evidence({}, "İSTANBUL")) == {"tr", "az"}  # but real capitals still count
for text in ("Dr.No", "get.io", "watch at twitch.tv", "2+2 4567 8901", "5μ", "Citroën", "e.g. Mt.Fuji", "A to B"):
    assert country_evidence({}, text) == {}, (text, country_evidence({}, text))

# The vision model's transcription counts half, and only where OCR saw nothing
ocr, vlm = country_evidence({}, "東京"), country_evidence({"text": ["東京"]}, "")
assert totals(vlm)["jp"] == totals(ocr)["jp"] / 2, (vlm, ocr)
assert country_evidence({"text": ["新宿"]}, "新宿") == country_evidence({}, "新宿")

# Street and sign words, through case, missing accents and Turkish capitals
assert "fr" in best(country_evidence({}, "3 eme ARRI\nRUE\nPRAVAZ"))  # a Lyon street sign
assert best(country_evidence({}, "BAHNHOFSTRASSE 12")) == {"de", "at", "ch", "lu", "li", "be"}
assert best(country_evidence({}, "Bahnhofstraße 12")) == {"de", "at", "lu"}  # ß: not Swiss
assert best(country_evidence({}, "DROTTNINGGATAN")) == {"se", "fi", "ax"}
assert best(country_evidence({}, "Petőfi utca")) == {"hu"}  # ő and utca, one country
assert best(country_evidence({}, "ÇIKIŞ")) == {"tr"} and best(country_evidence({}, "GİRİŞ")) == {"tr"}  # ş and the word
assert best(country_evidence({}, "Jl. Malioboro")) == {"id"}
assert "pt" in best(country_evidence({}, "SAIDA")) and "pt" not in country_evidence({}, "INGÅNG")
assert "nl" in country_evidence({}, "INGANG") and "se" in country_evidence({}, "INGANG")  # no accents: either
for text in ("Brigade Road", "Gate 12", "Via Rail", "Plaza Hotel", "Entrées $12", "Karl-Marx-Allee", "TRUE STORY"):
    assert country_evidence({}, text) == {}, (text, country_evidence({}, text))
# The vision model's language adds only where sign words said nothing
assert totals(country_evidence({"language": "fr"}, "RUE"))["fr"] == totals(country_evidence({}, "RUE"))["fr"]

# Vision model's language, prose descriptions and own guesses
assert best(country_evidence({"language": "nl"}, "")) == {"nl", "be", "sr"}
assert country_evidence({"language": "en"}, "") == {}  # English is everywhere
ev = country_evidence({"road_markings": "Double yellow center line, white edge lines"}, "")
assert "us" in ev and "za" not in ev, ev
ev = country_evidence({"road_markings": "white centre line and yellow edge lines"}, "")
assert "za" in ev and "us" not in ev, ev
assert "nl" in country_evidence({"plates": "EU plates with a blue band on the left"}, "")
ev = country_evidence({"countries": [{"code": "JP", "why": "kanji signs"}, {"code": "tw"}, "cn", {"code": "xx"}]}, "")
assert totals(ev)["jp"] > totals(ev)["tw"] > 0 and set(ev) == {"jp", "tw"}, ev

# All together, a Queensland street: Australia leads
obs = {"driving_side": "left", "language": "en", "signs": "green directional sign, yellow diamond warning sign",
       "countries": [{"code": "au", "why": "eucalyptus and Queensland signage"}]}
assert best(country_evidence(obs, "Bundaberg Fire Station 000 qfes.qld.gov.au")) == {"au"}
print("ok")
