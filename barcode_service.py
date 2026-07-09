"""Extension point for PDF417/AAMVA barcode decoding."""

from __future__ import annotations

import logging
import re

LOGGER = logging.getLogger("oci_license_poc.barcode")

_AAMVA_LABELS = {
    "DAQ": "License number",
    "DCS": "Last name",
    "DAC": "First name",
    "DAD": "Middle name",
    "DAA": "Full name",
    "DBD": "Issue date",
    "DBB": "Date of birth",
    "DBA": "Expiration date",
    "DAG": "Street address",
    "DAH": "City",
    "DAI": "State",
    "DAJ": "Postal code",
    "DBC": "Sex",
    "DAY": "Eye color",
    "DAU": "Height",
    "DAW": "Weight",
    "DCF": "Document discriminator",
    "DCG": "Country",
    "DCK": "Inventory control number",
}


def _format_aamva(oci_text: str) -> str:
    """Format common AAMVA PDF417 tags while preserving unknown content."""
    normalized = re.sub(r"[\x1c\x1d\x1e\r\n]+", "\n", oci_text).strip()
    if not normalized:
        return ""

    lines: list[str] = []
    for raw_line in normalized.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("ANSI ") or line.startswith("@ANSI "):
            lines.append(f"AAMVA header: {line.removeprefix('@')}")
            continue
        tag_match = re.match(r"^(D[A-Z]{2})(.*)$", line)
        if tag_match and tag_match.group(1) in _AAMVA_LABELS:
            tag, value = tag_match.group(1), tag_match.group(2).strip()
            if value:
                lines.append(f"{_AAMVA_LABELS[tag]}: {value}")
            continue
        matches = list(re.finditer(r"(?<![A-Z])(D[A-Z]{2})([^D]*?)(?=(?:D[A-Z]{2})|$)", line))
        if matches:
            for match in matches:
                tag, value = match.group(1), match.group(2).strip()
                if value:
                    lines.append(f"{_AAMVA_LABELS.get(tag, tag)}: {value}")
        else:
            lines.append(line)
    return "\n".join(lines)


def extract_barcode_text(oci_text: str) -> str:
    """Return barcode content currently available from OCI analysis.

    Args:
        oci_text: Text returned from the analysis of the license back.

    Returns:
        OCI-supplied barcode-like content. A dedicated PDF417/AAMVA decoder can
        replace this implementation later without changing the UI or client.
    """
    raw_lines = [line.strip() for line in oci_text.splitlines() if line.strip()]
    tag_matches = re.findall(r"(?<![A-Z])(D[A-Z]{2})", oci_text)
    known_tags = sorted({tag for tag in tag_matches if tag in _AAMVA_LABELS})
    has_aamva_header = any(line.lstrip("@").startswith("ANSI ") for line in raw_lines)
    barcode_text = _format_aamva(oci_text)
    LOGGER.info(
        "Barcode formatter diagnostics: input_characters=%d nonempty_lines=%d "
        "aamva_header_detected=%s known_aamva_tags=%s formatted_characters=%d",
        len(oci_text),
        len(raw_lines),
        has_aamva_header,
        ",".join(known_tags) or "none",
        len(barcode_text),
    )
    return barcode_text
