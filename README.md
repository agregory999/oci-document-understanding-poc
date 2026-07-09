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

## Build, deploy, redeploy, and delete in OCI

The `infra/` Terraform stack creates a private Container Instance in an existing
private subnet, a public flexible Load Balancer in an existing public subnet, and
dedicated NSGs. It does not create or modify the VCN, subnets, route tables, or
security lists. The private subnet must already have outbound HTTPS via a NAT
gateway so the container can reach OCIR and OCI Document Understanding.

The Container Instance uses the OCI SDK resource-principal signer already
implemented by this app; no OCI user credentials are put in the image.

### One-time Terraform inputs

Copy `infra/terraform.tfvars.example` to `infra/terraform.tfvars`, supply the
existing-network and certificate OCIDs, and reserve an unused private IP in the
private subnet for `container_private_ip`. Set `home_region` to your tenancy's
home region; it can differ from the app's `region`, and Terraform uses it only
for tenancy-level IAM dynamic groups and policies.

Use a dedicated runtime compartment. Terraform creates a compartment-scoped
dynamic group and grants it permission to read the private OCIR repository and
use OCI Document Understanding. All Container Instances in `compartment_ocid`
are members of that dynamic group. If a tenancy administrator creates the
Dynamic Group separately, set `create_container_dynamic_group = false` and
provide its exact `container_dynamic_group_name`; Terraform will retain
management of the runtime policy.

### Build and push the image

Build and push an immutable OCIR image before the first deploy and before every
redeploy. The helper script uses your local OCI CLI profile and asks Docker to
log in with your OCIR username and auth token:

```bash
export OCI_REGION=us-ashburn-1
export OCIR_REPOSITORY=oci-document-understanding-poc-repo
./scripts/deploy-image.sh
```

The script emits an image URI using the OCIR alias form, for example:

```text
us-ashburn-1.ocir.io/idxhxzdpc23m/oci-document-understanding-poc-repo:cd3315f7936f
```

If OCI Container Instances rejects that alias or fails to pull from it, set
`image_uri` in `infra/terraform.tfvars` to the regional OCIR endpoint form
instead. This is the form confirmed to deploy behind the Load Balancer:

```hcl
image_uri = "ocir.us-ashburn-1.oci.oraclecloud.com/idxhxzdpc23m/oci-document-understanding-poc-repo:cd3315f7936f"
```

Keep the namespace, repository, and tag the same when converting between the two
hostnames.

By default the stack uses `CI.Standard.E5.Flex`, which is compatible with the
deployment script's default `linux/amd64` image. `CI.Standard.A1.Flex` is also
supported, but requires rebuilding and pushing an ARM image first:

```bash
DOCKER_PLATFORM=linux/arm64 ./scripts/deploy-image.sh
```

Then set that emitted image URI and `container_shape = "CI.Standard.A1.Flex"`
in `infra/terraform.tfvars` before applying.

### First deploy

Initialize Terraform once, then validate, review, and apply the stack:

```bash
terraform -chdir=infra init
terraform -chdir=infra validate
terraform -chdir=infra plan
terraform -chdir=infra apply
```

After apply completes, Terraform prints the Container Instance OCID and the Load
Balancer public IP. Point DNS at the Load Balancer IP if you want to use a
certificate-backed hostname.

### Rebuild and redeploy

For code changes, build and push a new immutable tag, update only `image_uri` in
`infra/terraform.tfvars`, then apply Terraform again:

```bash
export OCI_REGION=us-ashburn-1
export OCIR_REPOSITORY=oci-document-understanding-poc-repo
./scripts/deploy-image.sh

terraform -chdir=infra validate
terraform -chdir=infra plan
terraform -chdir=infra apply
```

If you need a manual tag instead of the current Git SHA, set `IMAGE_TAG` before
running the script:

```bash
IMAGE_TAG=e4-v2 ./scripts/deploy-image.sh
```

Changing `image_uri` is the redeploy trigger. Review the Terraform plan before
applying; depending on the OCI provider behavior, the Container Instance may be
updated in place or replaced. The Load Balancer backend remains pointed at
`container_private_ip`, so keep that IP unchanged.

### Delete the deployment

To delete the Terraform-managed deployment, run:

```bash
terraform -chdir=infra destroy
```

Destroying this stack only removes the Terraform-managed Container Instance,
Load Balancer, NSGs, dynamic group, and IAM policy; it does not delete the
existing VCN/subnets or OCIR image.
