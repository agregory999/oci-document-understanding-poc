"""Tests for response normalization and image encoding."""

from __future__ import annotations

import base64
from types import SimpleNamespace

import oci
import pytest

import oci_client
from app import minimal_display_fields
from config import ConfigurationError, Settings
from models import DocumentResult, ExtractedField
from normalize import normalize_document_response
from oci_client import analyze_document_image, analyze_license_image, encode_image_base64


def test_encode_image_base64_encodes_bytes() -> None:
    """Image data is converted to the base64 string expected by OCI."""
    assert encode_image_base64(b"license-image") == base64.b64encode(b"license-image").decode()


def test_settings_loads_selectable_document_model_revisions(monkeypatch) -> None:
    """Named model revisions are parsed from the model registry environment setting."""
    monkeypatch.setenv(
        "OCI_DOCUMENT_MODELS",
        '[{"name":"NH baseline","model_id":"ocid-baseline"},'
        '{"name":"NH fields v2","model_id":"ocid-v2","region":"us-chicago-1"}]',
    )
    settings = Settings.from_environment()

    assert [model.name for model in settings.document_models] == ["NH baseline", "NH fields v2"]
    assert settings.for_document_model(settings.document_models[1]).document_model_id == "ocid-v2"
    assert settings.for_document_model(settings.document_models[1]).region == "us-chicago-1"


def test_settings_rejects_invalid_document_model_registry(monkeypatch) -> None:
    """Malformed model registries surface a useful configuration error."""
    monkeypatch.setenv("OCI_DOCUMENT_MODELS", "not-json")

    with pytest.raises(ConfigurationError, match="valid JSON"):
        Settings.from_environment()


def test_minimal_view_displays_all_fields_from_custom_model_schemas() -> None:
    """Schema additions must not be hidden by the compact results view."""
    result = DocumentResult(
        side="front",
        fields=[
            ExtractedField("FirstName", "Ada"),
            ExtractedField("Height", "5-10"),
            ExtractedField("Weight", "165 lb"),
            ExtractedField("Eyes", "BLU"),
        ],
    )

    assert [field.name for field in minimal_display_fields(result)] == [
        "FirstName",
        "Height",
        "Weight",
        "Eyes",
    ]


def test_normalize_extracts_fields_and_ocr_text_from_back_image() -> None:
    """OCI fields and OCR content are exposed in the app's stable schema."""
    raw = {
        "document_type": "OTHER",
        "pages": [
            {
                "document_fields": [
                    {"field_name": "First Name", "field_value": "Ada", "confidence": 0.99}
                ],
                "lines": [{"text": "OCR text"}],
            }
        ],
    }

    result = normalize_document_response(raw, "back")

    assert result.fields[0].name == "First Name"
    assert result.fields[0].value == "Ada"
    assert result.fields[0].confidence == 0.99
    assert "OCR text" in result.text
    assert result.metadata == {"document_type": "OTHER"}


def test_normalize_extracts_oci_nested_driver_license_fields() -> None:
    """OCI's driver-license key-value response uses nested label/value objects."""
    result = normalize_document_response(
        {
            "pages": [
                {
                    "document_fields": [
                        {
                            "field_label": {"name": "FirstName", "confidence": 0.91},
                            "field_value": {"value": "Ada"},
                        }
                    ]
                }
            ]
        },
        "front",
    )

    assert result.fields[0].name == "FirstName"
    assert result.fields[0].value == "Ada"
    assert result.fields[0].confidence == 0.91


def test_normalize_handles_null_optional_oci_field_lists() -> None:
    """OCI optional field arrays may be returned as null rather than empty lists."""
    result = normalize_document_response(
        {"pages": [{"document_fields": None, "fields": None}]},
        "front",
    )

    assert result.fields == []


def test_analyze_license_image_serializes_oci_response_models(monkeypatch) -> None:
    """OCI response models are flattened through the SDK utility."""

    class FakeClient:
        def analyze_document(self, details):
            return SimpleNamespace(
                data=oci.ai_document.models.AnalyzeDocumentResult(
                    pages=[], text_extraction_model_version="test-model"
                )
            )

    captured: dict[str, object] = {}

    def fake_normalize(raw, side):
        captured["raw"] = raw
        captured["side"] = side
        return DocumentResult(side=side)

    monkeypatch.setattr(oci_client, "normalize_document_response", fake_normalize)

    result = analyze_license_image(
        FakeClient(),
        SimpleNamespace(compartment_id="compartment"),
        b"license-image",
        "front",
    )

    assert result == DocumentResult(side="front")
    assert captured["side"] == "front"
    assert captured["raw"] == oci.util.to_dict(
        oci.ai_document.models.AnalyzeDocumentResult(
            pages=[], text_extraction_model_version="test-model"
        )
    )


def test_analyze_document_image_uses_pretrained_passport_type(monkeypatch, caplog) -> None:
    """Passport selection invokes OCI's separate pretrained passport model."""
    caplog.set_level("INFO", logger="oci_license_poc.oci_client")

    class FakeClient:
        def analyze_document(self, details):
            captured["details"] = details
            return SimpleNamespace(data=oci.ai_document.models.AnalyzeDocumentResult(pages=[]))

    captured: dict[str, object] = {}
    monkeypatch.setattr(
        oci_client,
        "normalize_document_response",
        lambda raw, side: DocumentResult(side=side),
    )

    analyze_document_image(
        FakeClient(),
        SimpleNamespace(compartment_id="compartment"),
        b"passport-image",
        "passport",
        oci.ai_document.models.AnalyzeDocumentDetails.DOCUMENT_TYPE_PASSPORT,
    )

    assert captured["details"].document_type == "PASSPORT"
    assert "key_value=pretrained_passport" in caplog.text
