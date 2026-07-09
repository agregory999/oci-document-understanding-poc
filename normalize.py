"""Normalize OCI Document Understanding responses into app-facing data."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from barcode_service import extract_barcode_text
from models import DocumentResult, ExtractedField

LOGGER = logging.getLogger("oci_license_poc.normalize")


def _walk_values(value: Any) -> Iterable[str]:
    """Yield text values from OCI's nested page and line structures."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"text", "word", "value"} and isinstance(item, str):
                yield item
            yield from _walk_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_values(item)


def _find_barcode_values(value: Any) -> Iterable[str]:
    """Yield explicit barcode values, when OCI includes them in a response."""
    if isinstance(value, dict):
        for key, item in value.items():
            if "barcode" in key.lower().replace("_", ""):
                if isinstance(item, str):
                    yield item
                elif isinstance(item, dict):
                    candidate = item.get("text") or item.get("value") or item.get("data")
                    if isinstance(candidate, str):
                        yield candidate
                    else:
                        yield from _walk_values(item)
                elif isinstance(item, list):
                    yield from _walk_values(item)
            yield from _find_barcode_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _find_barcode_values(item)


def _field_from_item(item: dict[str, Any]) -> ExtractedField | None:
    """Map OCI key-value field variants into one extracted field."""
    label = item.get("field_label") or item.get("label")
    field_value = item.get("field_value")
    name = item.get("field_name") or item.get("name")
    if name is None and isinstance(label, dict):
        name = label.get("name") or label.get("value")

    value = field_value or item.get("value") or item.get("text")
    if isinstance(value, dict):
        value = value.get("value") or value.get("text")
    if not name or value is None:
        return None
    confidence = item.get("confidence")
    if confidence is None and isinstance(label, dict):
        confidence = label.get("confidence")
    if confidence is None and isinstance(item.get("field_value"), dict):
        confidence = item["field_value"].get("confidence")
    normalized_confidence = float(confidence) if confidence is not None else None
    return ExtractedField(str(name), str(value), normalized_confidence)


def normalize_document_response(raw: dict[str, Any], side: str) -> DocumentResult:
    """Create a stable result from OCI's versioned response schema.

    Args:
        raw: The SDK response data converted with ``oci.util.to_dict()``.
        side: The analyzed license side.

    Returns:
        App-friendly document result retaining the original response.
    """
    fields: list[ExtractedField] = []
    for page in raw.get("pages") or []:
        document_fields = page.get("document_fields") or []
        fields_on_page = page.get("fields") or []
        for item in document_fields + fields_on_page:
            if isinstance(item, dict) and (field := _field_from_item(item)):
                fields.append(field)
    text = "\n".join(dict.fromkeys(part.strip() for part in _walk_values(raw) if part.strip()))
    metadata = {key: value for key, value in raw.items() if key not in {"pages", "document_fields"}}
    explicit_barcode_values = list(dict.fromkeys(_find_barcode_values(raw)))
    explicit_barcodes = "\n".join(explicit_barcode_values)
    # The general OCI analysis may expose barcode content as OCR rather than a
    # dedicated barcode object. Preserve that useful back-side output for the
    # future decoder seam when no explicit barcode value is present.
    has_explicit_barcode = bool(explicit_barcodes)
    barcode_text = extract_barcode_text(explicit_barcodes or text) if side.lower() == "back" else ""
    barcode_source = ""
    if side.lower() == "back" and barcode_text:
        barcode_source = (
            "OCI barcode object" if has_explicit_barcode else "OCR fallback (not barcode-verified)"
        )
    if side.lower() == "back":
        LOGGER.info(
            "Barcode source diagnostics: explicit_values=%d explicit_characters=%d "
            "ocr_characters=%d barcode_text_present=%s",
            len(explicit_barcode_values),
            len(explicit_barcodes),
            len(text),
            bool(barcode_text),
        )
        if not has_explicit_barcode:
            LOGGER.warning(
                "OCI returned no explicit barcode object for the back image; "
                "showing OCR fallback instead of a barcode-verified result."
            )
        elif not barcode_text:
            LOGGER.warning(
                "OCI returned an explicit barcode object, but it contained no "
                "formatable barcode text."
            )
    result = DocumentResult(
        side=side,
        fields=fields,
        text=text,
        barcode_text=barcode_text,
        barcode_source=barcode_source,
        metadata=metadata,
        raw_response=raw,
    )
    LOGGER.info(
        "Normalized OCI response for %s image: fields=%d text_characters=%d "
        "barcode_present=%s barcode_source=%s",
        side,
        len(fields),
        len(text),
        bool(barcode_text),
        barcode_source or "not_applicable",
    )
    return result
