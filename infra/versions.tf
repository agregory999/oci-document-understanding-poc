terraform {
  required_version = ">= 1.5.0"

  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 7.0"
    }
  }
}

provider "oci" {
  region = var.region
}

# IAM dynamic groups and tenancy policies are managed through the tenancy's
# home-region Identity endpoint, which can differ from the app's runtime region.
provider "oci" {
  alias  = "home"
  region = var.home_region
}
