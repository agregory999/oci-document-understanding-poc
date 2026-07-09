"""Normalize OCI Document Understanding responses into app-facing data."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

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
        side: The analyzed document side.

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
    result = DocumentResult(
        side=side,
        fields=fields,
        text=text,
        metadata=metadata,
        raw_response=raw,
    )
    LOGGER.info(
        "Normalized OCI response for %s image: fields=%d text_characters=%d",
        side,
        len(fields),
        len(text),
    )
    return result
