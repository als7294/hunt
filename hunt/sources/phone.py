"""Phone → offline facts from libphonenumber (Apache-2.0). Nothing leaves the machine."""

import phonenumbers
from phonenumbers import PhoneNumberFormat, PhoneNumberType, carrier, geocoder, timezone

from ..seed import Finding

NAME = "phonenumbers"
KINDS = {"phone"}
LINE_TYPES = {v: k.lower() for k, v in vars(PhoneNumberType).items() if not k.startswith("_")}


async def search(seed):
    n = phonenumbers.parse(seed.value, "US")
    attrs = {
        "e164": phonenumbers.format_number(n, PhoneNumberFormat.E164),
        "valid": phonenumbers.is_valid_number(n),
        "region": phonenumbers.region_code_for_number(n),
        "location": geocoder.description_for_number(n, "en"),
        "original_carrier": carrier.name_for_number(n, "en"),  # number may since have been ported
        "line_type": LINE_TYPES.get(phonenumbers.number_type(n)),
        "timezones": list(timezone.time_zones_for_number(n)),
    }
    return [Finding(NAME, seed, "libphonenumber", "", attrs)], 1, "offline lookup, nothing sent over the network"
