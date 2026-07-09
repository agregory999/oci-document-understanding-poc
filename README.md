# OCI Identity Document Capture POC

Streamlit app for capturing driver licenses or passports and extracting fields with OCI Document Understanding.

## Run

Prerequisites: Python 3.11+, an OCI compartment, and OCI credentials configured locally (`oci setup config`) or an OCI workload principal.

```bash
uv sync --extra dev
export OCI_COMPARTMENT_ID='ocid1.compartment.oc1..example'
export OCI_AUTH_MODE=config                 # local OCI CLI/SDK profile
uv run streamlit run app.py
```

Open the URL printed by Streamlit, capture or upload the document image(s), select a model, and choose **Analyze**. For instance or resource principals, set `OCI_AUTH_MODE` and `OCI_REGION` instead of using a local profile.

## Create and train a custom model

For a trained (classic) key-value model:

1. In OCI Document Understanding, create a project and dataset.
2. Collect representative document images and label every field to extract (for example, `Height`, `Weight`, and `Eyes`) with OCI Data Labeling.
3. Create a **Custom Classic Key-Value** model from that dataset and wait for it to become active. Review its metrics before using it.
4. Add the model OCID and its region, then restart the app:

```bash
export OCI_DOCUMENT_MODELS='[
  {"name":"NH license v1","model_id":"ocid1.aidocumentcustommodel.oc1....","region":"us-chicago-1"}
]'
```

Select the named revision in the app before analyzing a document. OCI also offers prompt-based generative key-value models; those define fields in a schema and do not require training data. See Oracle's guides for [datasets](https://docs.oracle.com/en-us/iaas/Content/document-understanding/using/custom-model-create-dataset.htm), [custom models](https://docs.oracle.com/en-us/iaas/Content/document-understanding/using/custom-models-about.htm), and [generative extraction](https://docs.oracle.com/en-us/iaas/Content/document-understanding/using/custom-kv-generative-extraction.htm).

## Checks

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```
