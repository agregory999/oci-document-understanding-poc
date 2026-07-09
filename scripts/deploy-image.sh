#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Build and push the OCI Identity Document Capture image to OCIR.

Required environment variables:
  OCI_REGION                 OCI region, for example us-ashburn-1
  OCIR_REPOSITORY            Repository name, for example identity-document-capture

Optional environment variables:
  IMAGE_TAG                  Image tag (defaults to the current Git SHA)
  OCI_NAMESPACE              Object Storage namespace (looked up when omitted)
  OCI_CLI_PROFILE            OCI CLI profile (defaults to DEFAULT)
  DOCKER_PLATFORM            Platform to build (defaults to linux/amd64)

The active OCI CLI user must be allowed to push images to the target repository.
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

: "${OCI_REGION:?OCI_REGION is required}"
: "${OCIR_REPOSITORY:?OCIR_REPOSITORY is required}"

OCI_CLI_PROFILE="${OCI_CLI_PROFILE:-DEFAULT}"
OCI_NAMESPACE="${OCI_NAMESPACE:-$(oci os ns get --profile "$OCI_CLI_PROFILE" --query data --raw-output)}"
IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short=12 HEAD)}"
DOCKER_PLATFORM="${DOCKER_PLATFORM:-linux/amd64}"
REGISTRY="${OCI_REGION}.ocir.io"
IMAGE_URI="${REGISTRY}/${OCI_NAMESPACE}/${OCIR_REPOSITORY}:${IMAGE_TAG}"

echo "Log in to ${REGISTRY} with your OCIR username (<namespace>/<username>) and auth token."
docker login "$REGISTRY"
docker build --platform "$DOCKER_PLATFORM" --tag "$IMAGE_URI" .
docker push "$IMAGE_URI"

printf '\nPushed immutable image:\n%s\n' "$IMAGE_URI"
