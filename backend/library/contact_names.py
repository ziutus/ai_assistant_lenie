"""Contact names may be incomplete; a label is knowledge, not a fake surname."""


def contact_display_name(contact):
    return " ".join(value for value in (contact.first_name, contact.last_name) if value) or contact.display_label or f"Kontakt {contact.id}"


def validate_contact_name(data, existing=None):
    if not isinstance(data, dict):
        return "Dane kontaktu muszą być obiektem."
    values = {}
    for field, limit in (("first_name", 100), ("last_name", 100), ("display_label", 200)):
        value = data.get(field, getattr(existing, field, None))
        if value is not None and not isinstance(value, str):
            return "Imię, nazwisko i nazwa robocza muszą być tekstem."
        value = (value or "").strip()
        if len(value) > limit:
            return f"Pole {field} może mieć maksymalnie {limit} znaków."
        values[field] = value
    if not any(values.values()):
        return "Podaj imię, nazwisko lub nazwę roboczą kontaktu."
    return None
