"""Internal data models for the driver-license demo."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ExtractedField:
    """A value extracted by OCI Document Understanding.

    Attributes:
        name: Human-readable or service-provided field name.
        value: Extracted field value.
        confidence: OCI confidence score, when supplied by the service.
    """

    name: str
    value: str
    confidence: float | None = None


@dataclass(slots=True)
class DocumentResult:
    """Normalized result returned from one analyzed license image.

    Attributes:
        side: License side represented by this result.
        fields: Key/value fields extracted from the document.
        text: Full OCR text collected from pages and lines.
        barcode_text: Barcode content, if OCI supplied it.
        metadata: Service document and page metadata.
        raw_response: JSON-serializable OCI response for the full view.
    """

    side: str
    fields: list[ExtractedField] = field(default_factory=list)
    text: str = ""
    barcode_text: str = ""
    barcode_source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_response: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-ready representation of this normalized result."""
        return asdict(self)
