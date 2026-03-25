"""Phone number validation using the ``phonenumbers`` library."""

from __future__ import annotations

import phonenumbers


class PhoneValidator:
    def validate(self, phone: str) -> dict:
        try:
            parsed = phonenumbers.parse(phone, None)
        except phonenumbers.NumberParseException as e:
            return {"valid": False, "error": str(e), "raw": phone}

        valid = phonenumbers.is_valid_number(parsed)
        possible = phonenumbers.is_possible_number(parsed)

        carrier_name = ""
        line_type = ""
        try:
            from phonenumbers import carrier, number_type
            carrier_name = carrier.name_for_number(parsed, "en")
            nt = phonenumbers.number_type(parsed)
            type_map = {
                phonenumbers.PhoneNumberType.MOBILE: "mobile",
                phonenumbers.PhoneNumberType.FIXED_LINE: "fixed_line",
                phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE: "fixed_line_or_mobile",
                phonenumbers.PhoneNumberType.TOLL_FREE: "toll_free",
                phonenumbers.PhoneNumberType.PREMIUM_RATE: "premium_rate",
                phonenumbers.PhoneNumberType.VOIP: "voip",
            }
            line_type = type_map.get(nt, "unknown")
        except Exception:
            pass

        return {
            "valid": valid,
            "possible": possible,
            "country_code": parsed.country_code,
            "national_number": str(parsed.national_number),
            "international": phonenumbers.format_number(
                parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL
            ),
            "e164": phonenumbers.format_number(
                parsed, phonenumbers.PhoneNumberFormat.E164
            ),
            "carrier": carrier_name,
            "line_type": line_type,
            "region": phonenumbers.region_code_for_number(parsed),
        }
