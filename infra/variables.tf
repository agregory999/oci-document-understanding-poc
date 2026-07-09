variable "region" {
  type        = string
  description = "OCI region containing the application resources."
}

variable "home_region" {
  type        = string
  description = "Tenancy home region for IAM dynamic groups and policies."
}

variable "tenancy_ocid" {
  type        = string
  default     = null
  nullable    = true
  description = "Tenancy OCID, required only when Terraform creates the Dynamic Group."
}

variable "compartment_ocid" {
  type        = string
  description = "Dedicated application/runtime compartment OCID."
}

variable "ocir_repository_compartment_ocid" {
  type        = string
  description = "Compartment containing the private OCIR repository."
}

variable "availability_domain" {
  type        = string
  description = "Availability domain for the Container Instance."
}

variable "vcn_ocid" {
  type        = string
  description = "Existing VCN OCID. Terraform does not alter this VCN."
}

variable "public_subnet_ocid" {
  type        = string
  description = "Existing public subnet OCID for the public load balancer."
}

variable "private_subnet_ocid" {
  type        = string
  description = "Existing private subnet OCID for the Container Instance."
}

variable "container_private_ip" {
  type        = string
  description = "Unused static private IP in private_subnet_ocid; used as the LB backend target."
}

variable "image_uri" {
  type        = string
  description = "Immutable OCIR image URI emitted by scripts/deploy-image.sh."
}

variable "app_name" {
  type    = string
  default = "identity-document-capture"
}

variable "create_container_dynamic_group" {
  type        = bool
  default     = true
  description = "Create the tenancy Dynamic Group. Set false when an administrator created it separately."
}

variable "container_dynamic_group_name" {
  type        = string
  default     = null
  nullable    = true
  description = "Existing tenancy Dynamic Group name when create_container_dynamic_group is false."
}

variable "identity_domain_name" {
  type        = string
  default     = "Default"
  description = "Identity domain that contains the Dynamic Group used by the runtime policy."
}

variable "container_ocpus" {
  type    = number
  default = 1
}

variable "container_memory_in_gbs" {
  type    = number
  default = 4
}

variable "container_shape" {
  type        = string
  default     = "CI.Standard.E5.Flex"
  description = "Container Instance shape. Use CI.Standard.E5.Flex for AMD64 images or CI.Standard.A1.Flex for ARM64 images."
}

variable "document_models_json" {
  type        = string
  default     = ""
  sensitive   = false
  description = "Optional OCI_DOCUMENT_MODELS JSON value. Do not put credentials in this value."
}

variable "allowed_client_cidrs" {
  type        = set(string)
  default     = ["0.0.0.0/0"]
  description = "CIDRs allowed to reach the HTTPS listener. Restrict for non-public deployments."
}

variable "certificate_ids" {
  type        = list(string)
  default     = []
  description = "OCI Certificates service certificate OCIDs. Supply one to enable HTTPS."

  validation {
    condition     = length(var.certificate_ids) <= 1
    error_message = "OCI Load Balancer supports one certificate OCID per listener."
  }
}

variable "freeform_tags" {
  type    = map(string)
  default = {}
}
