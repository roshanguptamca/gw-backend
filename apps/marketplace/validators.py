import re

from django.core.validators import RegexValidator

validate_whatsapp_phone = RegexValidator(
    regex=r"^\+[1-9][0-9]{7,14}$",
    message="Enter an international phone number in E.164 format, e.g. +31612345678.",
)


def normalize_whatsapp_phone(value: str) -> str:
    normalized = re.sub(r"[\s()-]", "", value)
    validate_whatsapp_phone(normalized)
    return normalized
