"""Streamlit interface for identity-document capture and OCI analysis."""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter
from typing import Any

import streamlit as st

from config import ConfigurationError, DocumentModel, Settings
from logging_config import configure_logging
from models import DocumentResult, ExtractedField
from oci_client import analyze_document_image, create_document_client

st.set_page_config(page_title="OCI Identity Document Capture", page_icon="🪪", layout="wide")
LOGGER = logging.getLogger("oci_license_poc.app")


@st.cache_resource(show_spinner=False)
def get_client(settings: Settings) -> Any:
    """Initialize and cache the OCI SDK client for this Streamlit process."""
    LOGGER.info("Initializing OCI Document Understanding client")
    return create_document_client(settings)


def image_input(label: str, key: str) -> Any:
    """Render capture/upload controls and return the selected image.

    Args:
        label: User-facing name for the license side.
        key: Unique Streamlit widget key prefix.

    Returns:
        Streamlit uploaded-file object, or ``None`` when no image is selected.
    """
    source = st.radio(f"{label} source", ("Upload", "Camera"), horizontal=True, key=f"{key}_source")
    if source == "Camera":
        st.caption("Use good light, tap the license to focus, and move back if it becomes blurry.")
        return st.camera_input(
            f"Capture {label.lower()}",
            key=f"{key}_camera",
            resolution="1080p",
        )
    return st.file_uploader(
        f"Upload {label.lower()}", type=["jpg", "jpeg", "png", "webp"], key=f"{key}_upload"
    )


def model_label(model: DocumentModel | None, document_label: str) -> str:
    """Create the compact label shown in the model selector."""
    return model.name if model else f"Pretrained {document_label.lower()}"


def select_document_model(settings: Settings, document_label: str) -> DocumentModel | None:
    """Let an operator choose the extraction model before analysis."""
    options: list[DocumentModel | None] = [None, *settings.document_models]
    selected_index = next(
        (
            index
            for index, model in enumerate(options)
            if model and model.model_id == settings.document_model_id
        ),
        0,
    )
    selected = st.selectbox(
        "Extraction model",
        options,
        index=selected_index,
        format_func=lambda model: model_label(model, document_label),
        help=(
            f"Choose the built-in {document_label.lower()} model or a named custom-model revision. "
            "Configure revisions with OCI_DOCUMENT_MODELS."
        ),
    )
    if selected and selected.description:
        st.caption(selected.description)
    if selected and selected.region:
        st.caption(f"Model region: {selected.region}")
    return selected


def minimal_display_fields(result: DocumentResult) -> list[ExtractedField]:
    """Return every structured field for the compact results view.

    Custom model schemas evolve over time, so this view must not hide fields
    based on a fixed list of names or a display limit.
    """
    return result.fields


def render_minimal(result: DocumentResult) -> None:
    """Render compact, demo-friendly fields and a confidence summary.

    Args:
        result: Normalized OCI analysis for one license side.
    """
    if not result.fields:
        st.info("No structured fields returned. See the Full view for OCR and raw response.")
    else:
        for field in minimal_display_fields(result):
            confidence = f" ({field.confidence:.0%})" if field.confidence is not None else ""
            st.write(f"**{field.name}:** {field.value}{confidence}")

    confidences = [field.confidence for field in result.fields if field.confidence is not None]
    if result.fields and (not confidences or min(confidences) >= 0.7):
        st.success("PASS — document fields were extracted with acceptable confidence.")
    elif result.fields:
        st.warning("REVIEW — one or more extracted fields have low confidence.")
    else:
        st.error("FAIL — no structured fields were extracted.")

    if result.side.lower() == "back":
        st.subheader("OCR text")
        if result.text:
            st.code(result.text, language="text")
        else:
            st.info("No OCR text was returned from the back-image analysis.")


def render_full(result: DocumentResult) -> None:
    """Render all normalized fields, metadata, and raw OCI data.

    Args:
        result: Normalized OCI analysis for one license side.
    """
    st.subheader("Extracted fields")
    st.json([{"name": f.name, "value": f.value, "confidence": f.confidence} for f in result.fields])
    st.subheader("Document metadata")
    st.json(result.metadata)
    st.subheader("Raw OCI response")
    st.code(json.dumps(result.raw_response, indent=2, default=str), language="json")


def main() -> None:
    """Run the interactive capture, analysis, and presentation flow."""
    configure_logging()
    LOGGER.info("Rendering identity-document capture app")
    st.title("OCI Identity Document Capture & Verification")
    document_label = st.segmented_control(
        "Document type",
        ["Driver license", "Passport"],
        default="Driver license",
        key="document_type",
    )
    is_passport = document_label == "Passport"
    document_type = "PASSPORT" if is_passport else "DRIVER_LICENSE"
    st.caption(
        "Capture or upload a passport image, then analyze it with OCI Document Understanding."
        if is_passport
        else "Capture or upload both sides, then analyze them with OCI Document Understanding."
    )
    mode = st.segmented_control("Output mode", ["Minimal", "Full"], default="Minimal")
    try:
        base_settings = Settings.from_environment()
        selected_model = select_document_model(base_settings, document_label)
        settings = base_settings.for_document_model(selected_model)
    except ConfigurationError as exc:
        LOGGER.warning("OCI configuration error: %s", exc)
        st.error(f"OCI configuration error: {exc}")
        return

    if is_passport:
        st.subheader("Passport photo page")
        front_image = image_input("Passport image", "passport")
        back_image = None
        if front_image:
            st.image(front_image, width="stretch")
    else:
        front_column, back_column = st.columns(2)
        with front_column:
            st.subheader("Front of license")
            front_image = image_input("Front image", "front")
            if front_image:
                st.image(front_image, width="stretch")
        with back_column:
            st.subheader("Back of license")
            back_image = image_input("Back image", "back")
            if back_image:
                st.image(back_image, width="stretch")

    ready_to_analyze = bool(front_image) if is_passport else bool(front_image and back_image)
    if st.button(
        f"Analyze {document_label.lower()}", type="primary", disabled=not ready_to_analyze
    ):
        try:
            LOGGER.info("%s analysis requested", document_label)
            client = get_client(settings)
            image_suffix = "" if is_passport else "s"
            with st.spinner(f"Analyzing {document_label.lower()} image{image_suffix} with OCI…"):
                start_time = perf_counter()
                if is_passport:
                    front_result = analyze_document_image(
                        client, settings, front_image, "passport", document_type
                    )
                    back_result = None
                else:
                    with ThreadPoolExecutor(
                        max_workers=2, thread_name_prefix="oci-document"
                    ) as executor:
                        front_future = executor.submit(
                            analyze_document_image,
                            client,
                            settings,
                            front_image,
                            "front",
                            document_type,
                        )
                        back_future = executor.submit(
                            analyze_document_image,
                            client,
                            settings,
                            back_image,
                            "back",
                            document_type,
                        )
                        front_result = front_future.result()
                        back_result = back_future.result()
                analysis_duration_seconds = perf_counter() - start_time
            st.session_state["document_results"] = tuple(
                result for result in (front_result, back_result) if result is not None
            )
            st.session_state["document_result_model"] = model_label(selected_model, document_label)
            st.session_state["document_result_type"] = document_label
            st.session_state["document_analysis_duration_seconds"] = analysis_duration_seconds
            LOGGER.info(
                "%s document calls completed in %.2f sec: primary_fields=%d secondary_fields=%d",
                document_label,
                analysis_duration_seconds,
                len(front_result.fields),
                len(back_result.fields) if back_result else 0,
            )
        except ConfigurationError as exc:
            LOGGER.warning("OCI configuration error: %s", exc)
            st.error(f"OCI configuration error: {exc}")
        except ValueError as exc:
            LOGGER.warning("Invalid image submitted: %s", exc)
            st.error(f"Invalid image: {exc}")
        except Exception as exc:  # Surface OCI service failures without exposing secrets.
            LOGGER.exception("OCI Document Understanding request failed")
            st.error(f"OCI Document Understanding request failed: {exc}")

    results = st.session_state.get("document_results")
    if results and st.session_state.get("document_result_type") == document_label:
        st.divider()
        result_model = st.session_state.get("document_result_model", "Unknown")
        st.caption(f"Results produced by: {result_model}")
        duration = st.session_state.get("document_analysis_duration_seconds")
        if duration is not None:
            st.caption(f"Analyzed in {duration:.2f} sec")
        result_columns = st.columns(len(results))
        for column, result in zip(result_columns, results, strict=True):
            with column:
                st.header(f"{result.side.title()} results")
                if mode == "Minimal":
                    render_minimal(result)
                else:
                    render_full(result)


if __name__ == "__main__":
    main()
