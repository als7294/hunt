"""Florida's official bulk records, loaded into local tables (_bulk): licences (DBPR) and businesses (Sunbiz).

Florida publishes no records API. Its Department of Business and Professional Regulation posts
each profession's licensee file as a free public-records download, refreshed weekly, on a host
whose robots.txt allows it ("DBPR provides copies of electronic records to the public through
free download", its Public Records ReadMe). `python -m hunt.sources.records update fl-dbpr` fetches the
licensee files below (about 270 MB) and indexes them; `licences` then searches them.

The Division of Corporations (Sunbiz) offers free quarterly files "for informational purposes",
but only behind a login whose shared password it publishes, and its search site answers scripts
with a Cloudflare challenge. Hunt enters neither. The investigator downloads the files herself
(https://dos.fl.gov/sunbiz/other-services/data-downloads/quarterly-data/: doc > quarterly > cor >
cordata.zip, and doc > quarterly > fic > ficdata.zip) and loads them:
`python -m hunt.sources.records load fl-sunbiz-cor ~/Downloads/cordata.zip` (and fl-sunbiz-fic for ficdata.zip).
`businesses` then searches every officer and registered agent who is a person, and every
fictitious-name owner. The Department of Health's licence data portal needs a sign-in, so
doctors and nurses are a by-hand lookup (docs/research/tools.md, "State records").
"""

import csv
import io
import zipfile
from pathlib import Path

from ._bulk import Table
from ._socrata import day, joined, place

DBPR = "https://www2.myfloridalicense.com/sto/file_download/extracts/"
DBPR_FILES = {  # licensee file → profession; the real-estate file has a layout of its own (_dbpr)
    "CONSTRUCTIONLICENSE_1.csv": "construction", "REALESTATE2501LICENSE_1.csv": "real estate",
    "COSMETOLOGYLICENSE_1.csv": "cosmetology", "lic08el.csv": "electrical contracting", "lic03bb.csv": "barbering",
    "lic02ai.csv": "architecture and interior design", "lic04home.csv": "home inspection", "lic07mold.csv": "mold services",
    "lic13la.csv": "landscape architecture", "lic23hp.csv": "harbour pilotage", "lic26vt.csv": "veterinary medicine",
    "lic38cam.csv": "community association management", "lic48auc.csv": "auctioneering", "lic53gl.csv": "geology",
    "lic59asb.csv": "asbestos abatement", "lic60ath.csv": "athlete agency", "lic63elc.csv": "employee leasing",
    "lic64appr.csv": "real estate appraisal", "BuildingCodeLicensee.csv": "building code administration and inspection",
}
DBPR_VERIFY = "https://www.myfloridalicense.com/wl11.asp?mode=0&SID="  # its search form posts; no record has a link of its own
PRIMARY = {"C": "current", "P": "probation", "S": "suspended"}  # DBPR's "Understanding DBPR Codes"
SECONDARY = {"A": "active", "I": "inactive"}
SUNBIZ = "https://search.sunbiz.org/Inquiry/CorporationSearch/ByDocumentNumber"  # the investigator's browser, never Hunt
SUNBIZ_FILES = "https://dos.fl.gov/sunbiz/other-services/data-downloads/quarterly-data/"
FILING = {"DOMP": "domestic profit corporation", "DOMNP": "domestic non-profit corporation",
          "FORP": "foreign profit corporation", "FORNP": "foreign non-profit corporation",
          "DOMLP": "domestic limited partnership", "FORLP": "foreign limited partnership",
          "FLAL": "Florida limited liability company", "FORL": "foreign limited liability company",
          "NPREG": "non-profit registration", "TRUST": "declaration of trust", "AGENT": "designation of registered agent"}
TITLES = {"P": "president", "T": "treasurer", "C": "chairman", "V": "vice president", "S": "secretary", "D": "director"}
FIC_STATUS = {"A": "active", "C": "cancelled", "E": "expired"}


def _status(primary, secondary) -> str | None:
    return ", ".join(s for s in (PRIMARY.get(primary, primary.lower()), SECONDARY.get(secondary, secondary.lower())) if s) or None


def _dbpr(path: Path):
    """One licensee per row. Layout (the download pages' "File Layout Information"): board, occupation code, name, DBA,
    class, three address lines, city, state, zip, county code, licence number, primary and secondary status, original
    licensure, effective and expiration dates, blank, renewal period, alternate licence number (e.g. CBC1234567)."""
    profession = DBPR_FILES.get(path.name, path.stem)
    with open(path, encoding="latin-1", newline="") as f:
        for row in csv.reader(f):
            if len(row) < 18:
                continue
            body = io.StringIO()
            csv.writer(body, quoting=csv.QUOTE_ALL).writerow(row)
            if row[0].isdigit():
                name, number = row[2].strip(), (row[20] if len(row) > 20 else "").strip() or row[12].strip()
                attrs = {"licence": f"{profession.capitalize()} ({row[1].strip()})", "licence_number": number,
                         "status": _status(row[13].strip(), row[14].strip()), "issued": day(row[15]),
                         "expires": day(row[17]), "business": row[3].strip().title(),
                         "address": joined(row[5], row[6], row[7]), "location": place(row[8], row[9])}
            else:  # real estate: licence code and description, name, DBA, rank, three address lines, city, state, zip,
                # county name, licence number, primary and secondary status (words), three dates (dd-MON-yy), alternate
                # licence number, self-proprietor's name, employer's name and licence number
                name, number = row[1].strip(), row[17].strip() or row[11].strip()
                code, _, rank = row[3].strip().partition(" ")  # "SL Sales Associate", "BK Broker"
                attrs = {"licence": f"Real estate {rank.lower()} ({code})" if rank else row[0].strip(), "licence_number": number,
                         "status": ", ".join(s.strip().lower() for s in row[12:14] if s.strip()) or None,
                         "issued": day(row[14]), "expires": day(row[16]), "business": row[2].strip().title(),
                         "address": joined(row[4], row[5], row[6]), "location": place(row[7], row[8]),
                         "sponsor": row[19].strip() if len(row) > 19 else None}  # the broker they work under
            if name:
                yield (f"{DBPR}{path.name}#{number}", body.getvalue().strip(), {"verify": DBPR_VERIFY},
                       [(name, "licence holder", attrs)])


def _lines(path: Path):
    """The fixed-width lines of a Sunbiz .txt, or of every .txt inside its .zip."""
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            for member in z.namelist():
                if member.lower().endswith(".txt"):
                    with z.open(member) as f:
                        yield from (line.decode("latin-1").rstrip("\r\n") for line in f)
    else:
        with open(path, encoding="latin-1", newline="") as f:
            yield from (line.rstrip("\r\n") for line in f)


def _cut(line: str, start: int, length: int) -> str:  # positions as the file definitions give them: 1-based
    return line[start - 1:start - 1 + length].strip()


def _corporations(path: Path):
    """Corporate data file (record length 1440): the entity, its registered agent and up to six officers."""
    for line in _lines(path):
        doc = _cut(line, 1, 12)
        if not doc:
            continue
        record = {"business": _cut(line, 13, 192), "document_number": doc,
                  "status": {"A": "active", "I": "inactive"}.get(_cut(line, 205, 1)),
                  "entity_type": FILING.get(_cut(line, 206, 15), _cut(line, 206, 15)), "formed": day(_cut(line, 473, 8)),
                  "last_filing": day(_cut(line, 496, 8)), "business_location": place(_cut(line, 305, 28), _cut(line, 333, 2)),
                  "business_address": joined(_cut(line, 221, 42), _cut(line, 263, 42))}
        people = []
        if _cut(line, 545, 42) and _cut(line, 587, 1) != "C":  # (P) person, (C) corporation
            people.append((_cut(line, 545, 42), "registered agent",
                           {"address": _cut(line, 588, 42).title(), "location": place(_cut(line, 630, 28), _cut(line, 658, 2))}))
        for i in range(6):
            at = 669 + 128 * i  # title 4, type 1, name 42, address 42, city 28, state 2, zip 9
            if _cut(line, at + 5, 42) and _cut(line, at + 4, 1) != "C":
                code = _cut(line, at, 4)
                people.append((_cut(line, at + 5, 42), TITLES.get(code, f"officer ({code})" if code else "officer"),
                               {"address": _cut(line, at + 47, 42).title(),
                                "location": place(_cut(line, at + 89, 28), _cut(line, at + 117, 2))}))
        yield f"{SUNBIZ}#{doc}", line, record, people


def _fictitious(path: Path):
    """Fictitious name data file (record length 2098): the trade name and up to ten owners."""
    for line in _lines(path):
        doc = _cut(line, 1, 12)
        if not doc:
            continue
        record = {"business": _cut(line, 13, 192), "document_number": doc, "entity_type": "fictitious name",
                  "status": FIC_STATUS.get(_cut(line, 352, 1)), "registered": day(_cut(line, 339, 8)),
                  "expires": day(_cut(line, 361, 8)), "county": _cut(line, 205, 12).title(),
                  "business_location": place(_cut(line, 297, 28), _cut(line, 325, 2))}
        people = []
        for i in range(10):
            at = 389 + 171 * i  # document number 12, name 55, format 1, address 40, city 28, state 2, zip 10, …
            if _cut(line, at + 12, 55) and _cut(line, at + 67, 1) != "C":  # (P) person, (C) corporation
                people.append((_cut(line, at + 12, 55), "fictitious-name owner",
                               {"address": _cut(line, at + 68, 40).title(),
                                "location": place(_cut(line, at + 108, 28), _cut(line, at + 136, 2))}))
        yield f"{SUNBIZ}#{doc}", line, record, people


LOAD = "download {} from " + SUNBIZ_FILES + ", then `python -m hunt.sources.records load {} <file>`"
LICENCES = Table("Florida licence (DBPR)", "fl-dbpr", _dbpr, tuple(DBPR + f for f in DBPR_FILES),
                 "`python -m hunt.sources.records update fl-dbpr`, about 270 MB")
CORPORATIONS = Table("Florida corporation (Sunbiz)", "fl-sunbiz-cor", _corporations,
                     how=LOAD.format("cordata.zip", "fl-sunbiz-cor"))
FICTITIOUS = Table("Florida fictitious name (Sunbiz)", "fl-sunbiz-fic", _fictitious,
                   how=LOAD.format("ficdata.zip", "fl-sunbiz-fic"))

