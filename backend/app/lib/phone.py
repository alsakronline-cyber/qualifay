import re
import phonenumbers


def normalize_egyptian_phone(raw: str) -> str | None:
    """
    Normalize any Egyptian phone format to E.164 (+201XXXXXXXXX).
    Handles: 01X, 201X, 0201X, 00201X, +201X
    """
    if not raw:
        return None

    raw = re.sub(r'[\s\-\(\)\+]', '', str(raw))

    # Handle various prefix formats
    if raw.startswith('00201'):
        raw = '+' + raw[2:]
    elif raw.startswith('0201'):
        raw = '+' + raw[1:]
    elif raw.startswith('201'):
        raw = '+' + raw
    elif raw.startswith('01'):
        raw = '+20' + raw
    elif raw.startswith('1') and len(raw) == 10:
        raw = '+20' + raw

    try:
        parsed = phonenumbers.parse(raw, 'EG')
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except Exception:
        pass

    return None


def jid_to_phone(jid: str) -> str | None:
    """Convert a WhatsApp JID to an E.164 phone number."""
    if not jid:
        return None
    phone = (
        jid.replace("@s.whatsapp.net", "")
        .replace("@g.us", "")
        .replace("@c.us", "")
        .strip()
    )
    if not phone.startswith("+"):
        phone = "+" + phone
    return phone if len(phone) >= 10 else None
