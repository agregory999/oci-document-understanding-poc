"""OCI Document Understanding client and image analysis service."""

from __future__ import annotations

import base64
import logging
from typing import Any, BinaryIO

import oci

from config import ConfigurationError, Settings
from models import DocumentResult
from normalize import normalize_document_response

LOGGER = logging.getLogger("oci_license_poc.oci_client")


def encode_image_base64(image: BinaryIO | bytes) -> str:
    """Encode an uploaded image into the base64 form accepted by OCI.

    Args:
        image: Open binary image stream or image bytes.

    Returns:
        Base64-encoded image bytes as UTF-8 text.

    Raises:
        ValueError: If no image data was supplied.
    """
    data = image if isinstance(image, bytes) else image.getvalue()
    if not data:
        raise ValueError("The selected image is empty.")
    LOGGER.info("Encoding uploaded image for OCI request: bytes=%d", len(data))
    return base64.b64encode(data).decode("utf-8")


def _principal_client(settings: Settings, mode: str) -> oci.ai_document.AIServiceDocumentClient:
    """Build an OCI client authenticated with a workload principal.

    Args:
        settings: Validated application settings.
        mode: Principal type to use.

    Returns:
        Configured OCI Document Understanding client.
    """
    signer = (
        oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
        if mode == "instance_principal"
        else oci.auth.signers.get_resource_principals_signer()
    )
    LOGGER.info("Creating OCI client with %s authentication", mode)
    return oci.ai_document.AIServiceDocumentClient({"region": settings.region}, signer=signer)


def create_document_client(settings: Settings) -> oci.ai_document.AIServiceDocumentClient:
    """Create an OCI Document Understanding client using the configured auth.

    ``auto`` first attempts resource principal, then instance principal, and
    finally the local OCI config profile. This allows the same container image
    to run locally and in OCI without embedding credentials.

    Args:
        settings: Application settings.

    Returns:
        An authenticated OCI Document Understanding SDK client.

    Raises:
        ConfigurationError: If all selected authentication mechanisms fail.
    """
    settings.validate()
    if settings.auth_mode == "config":
        LOGGER.info("Creating OCI client with config-profile authentication")
        config = oci.config.from_file(settings.config_file, settings.profile)
        if settings.region:
            config["region"] = settings.region
        return oci.ai_document.AIServiceDocumentClient(config)
    if settings.auth_mode in {"instance_principal", "resource_principal"}:
        return _principal_client(settings, settings.auth_mode)

    failures: list[str] = []
    for mode in ("resource_principal", "instance_principal"):
        if not settings.region:
            break
        try:
            return _principal_client(settings, mode)
        except Exception as exc:  # OCI SDK exposes several auth exception types.
            LOGGER.info("OCI %s authentication was unavailable; trying next mode", mode)
            failures.append(f"{mode}: {exc}")
    try:
        LOGGER.info("Creating OCI client with config-profile authentication")
        config = oci.config.from_file(settings.config_file, settings.profile)
        if settings.region:
            config["region"] = settings.region
        return oci.ai_document.AIServiceDocumentClient(config)
    except Exception as exc:
        failures.append(f"config profile: {exc}")
        message = "Unable to initialize OCI authentication. " + "; ".join(failures)
        raise ConfigurationError(message) from exc


def analyze_document_image(
    client: oci.ai_document.AIServiceDocumentClient,
    settings: Settings,
    image: BinaryIO | bytes,
    side: str,
    document_type: str,
) -> DocumentResult:
    """Submit one identity-document image to OCI Document Understanding.

    Args:
        client: Authenticated OCI Document Understanding client.
        settings: Settings containing the target compartment.
        image: Identity-document image data.
        side: Display label for the image, such as ``front`` or ``passport``.
        document_type: OCI pretrained document type. Ignored when a custom
            key-value model is selected.

    Returns:
        Normalized analysis result.
    """
    encoded_image = encode_image_base64(image)
    LOGGER.info("Submitting %s %s image to OCI Document Understanding", document_type, side)
    document = oci.ai_document.models.InlineDocumentDetails(data=encoded_image)
    model_id = getattr(settings, "document_model_id", None)
    key_value_feature = oci.ai_document.models.DocumentKeyValueExtractionFeature(model_id=model_id)
    details = oci.ai_document.models.AnalyzeDocumentDetails(
        compartment_id=settings.compartment_id,
        document=document,
        document_type=(None if model_id else document_type),
        features=[
            oci.ai_document.models.DocumentTextExtractionFeature(),
            key_value_feature,
        ],
    )
    LOGGER.info(
        "Using %s key-value extraction",
        "custom model" if model_id else f"pretrained {document_type.lower()} model",
    )
    response = client.analyze_document(details)
    # OCI SDK models expose their serializable fields through ``swagger_types``
    # rather than a model-level ``to_dict()`` method.
    raw: dict[str, Any] = oci.util.to_dict(response.data)
    result = normalize_document_response(raw, side)
    LOGGER.info(
        "OCI extraction methods for %s: requested=TEXT_EXTRACTION,KEY_VALUE_EXTRACTION "
        "key_value=%s text_model=%s barcode_model=%s barcode_source=%s",
        side,
        "custom" if model_id else f"pretrained_{document_type.lower()}",
        raw.get("text_extraction_model_version") or "not_reported",
        raw.get("bar_code_extraction_model_version") or "not_reported",
        result.barcode_source or "not_applicable",
    )
    LOGGER.info(
        "OCI analysis completed for %s image: pages=%d fields=%d",
        side,
        len(raw.get("pages") or []),
        len(result.fields),
    )
    return result


def analyze_license_image(
    client: oci.ai_document.AIServiceDocumentClient,
    settings: Settings,
    image: BinaryIO | bytes,
    side: str,
) -> DocumentResult:
    """Submit one driver-license image (backward-compatible wrapper)."""
    return analyze_document_image(
        client,
        settings,
        image,
        side,
        oci.ai_document.models.AnalyzeDocumentDetails.DOCUMENT_TYPE_DRIVER_LICENSE,
    )
