"""Application settings and OCI authentication configuration."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, replace

LOGGER = logging.getLogger("oci_license_poc.config")


class ConfigurationError(ValueError):
    """Raised when required application configuration is absent or invalid."""


@dataclass(frozen=True, slots=True)
class DocumentModel:
    """One selectable document-extraction model revision."""

    name: str
    model_id: str | None
    description: str = ""
    region: str | None = None


def _document_models_from_environment() -> tuple[DocumentModel, ...]:
    """Read named custom model revisions from ``OCI_DOCUMENT_MODELS``.

    The variable contains a JSON list of objects with ``name`` and ``model_id``
    keys. ``description`` and ``region`` are optional. A blank ``model_id`` is
    reserved for the built-in pretrained driver-license model.
    """
    raw_models = os.getenv("OCI_DOCUMENT_MODELS", "").strip()
    if not raw_models:
        legacy_model_id = os.getenv("OCI_DOCUMENT_MODEL_ID", "").strip()
        return (DocumentModel("Custom model", legacy_model_id),) if legacy_model_id else ()

    try:
        items = json.loads(raw_models)
    except json.JSONDecodeError as exc:
        raise ConfigurationError("OCI_DOCUMENT_MODELS must be valid JSON.") from exc
    if not isinstance(items, list) or not items:
        raise ConfigurationError("OCI_DOCUMENT_MODELS must be a non-empty JSON list.")

    models: list[DocumentModel] = []
    names: set[str] = set()
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ConfigurationError(f"OCI_DOCUMENT_MODELS entry {index} must be an object.")
        name = item.get("name")
        model_id = item.get("model_id")
        description = item.get("description", "")
        region = item.get("region")
        if not isinstance(name, str) or not name.strip():
            raise ConfigurationError(f"OCI_DOCUMENT_MODELS entry {index} needs a non-empty name.")
        if model_id is not None and (not isinstance(model_id, str) or not model_id.strip()):
            raise ConfigurationError(
                f"OCI_DOCUMENT_MODELS entry {index} model_id must be a non-empty string or null."
            )
        if not isinstance(description, str):
            raise ConfigurationError(f"OCI_DOCUMENT_MODELS entry {index} description must be text.")
        if region is not None and (not isinstance(region, str) or not region.strip()):
            raise ConfigurationError(
                f"OCI_DOCUMENT_MODELS entry {index} region must be a non-empty string or null."
            )
        normalized_name = name.strip()
        if normalized_name in names:
            raise ConfigurationError("OCI_DOCUMENT_MODELS model names must be unique.")
        names.add(normalized_name)
        models.append(
            DocumentModel(
                name=normalized_name,
                model_id=model_id.strip() if isinstance(model_id, str) else None,
                description=description.strip(),
                region=region.strip() if isinstance(region, str) else None,
            )
        )
    return tuple(models)


@dataclass(frozen=True, slots=True)
class Settings:
    """Settings read from environment variables.

    Attributes:
        compartment_id: OCI compartment used for document analysis.
        auth_mode: ``auto``, ``config``, ``instance_principal``, or
            ``resource_principal``.
        profile: OCI CLI config profile for local authentication.
        config_file: Path to OCI config file for local authentication.
        region: OCI region needed for principal-based authentication.
        document_model_id: Optional custom key-value model OCID used for extraction.
        document_models: Named model revisions available for selection in the app.
    """

    compartment_id: str
    auth_mode: str
    profile: str
    config_file: str
    region: str | None
    document_model_id: str | None = None
    document_models: tuple[DocumentModel, ...] = ()

    @classmethod
    def from_environment(cls) -> Settings:
        """Create settings from environment without reading secret values."""
        auth_mode = os.getenv("OCI_AUTH_MODE", "auto").lower().strip()
        if auth_mode not in {"auto", "config", "instance_principal", "resource_principal"}:
            raise ConfigurationError(
                "OCI_AUTH_MODE must be auto, config, instance_principal, or resource_principal."
            )
        legacy_model_id = os.getenv("OCI_DOCUMENT_MODEL_ID", "").strip() or None
        settings = cls(
            compartment_id=os.getenv("OCI_COMPARTMENT_ID", "").strip(),
            auth_mode=auth_mode,
            profile=os.getenv("OCI_PROFILE", "DEFAULT").strip(),
            config_file=os.path.expanduser(os.getenv("OCI_CONFIG_FILE", "~/.oci/config")),
            region=os.getenv("OCI_REGION", "").strip() or None,
            document_model_id=legacy_model_id,
            document_models=_document_models_from_environment(),
        )
        LOGGER.info(
            "Loaded OCI settings: auth_mode=%s region_configured=%s",
            auth_mode,
            bool(settings.region),
        )
        if settings.document_models:
            LOGGER.info(
                "Configured %d selectable custom OCI document model(s)",
                len(settings.document_models),
            )
        return settings

    def for_document_model(self, model: DocumentModel | None) -> Settings:
        """Return settings configured for the selected model or pretrained extraction."""
        if model is None:
            return replace(self, document_model_id=None)
        return replace(
            self,
            document_model_id=model.model_id,
            region=model.region or self.region,
        )

    def validate(self) -> None:
        """Validate settings required before an OCI request is made."""
        if not self.compartment_id:
            raise ConfigurationError("OCI_COMPARTMENT_ID must be set.")
        if self.auth_mode in {"instance_principal", "resource_principal"} and not self.region:
            raise ConfigurationError("OCI_REGION must be set for principal-based authentication.")
        LOGGER.info("OCI settings validation passed: auth_mode=%s", self.auth_mode)
