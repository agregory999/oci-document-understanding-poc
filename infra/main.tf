locals {
  app_port = 8501
  tags     = merge(var.freeform_tags, { ManagedBy = "Terraform", Application = var.app_name })
  container_environment = merge(
    {
      OCI_AUTH_MODE      = "resource_principal"
      OCI_COMPARTMENT_ID = var.compartment_ocid
      OCI_REGION         = var.region
    },
    var.document_models_json == "" ? {} : { OCI_DOCUMENT_MODELS = var.document_models_json },
  )
  container_dynamic_group_name      = var.create_container_dynamic_group ? oci_identity_dynamic_group.container_instances[0].name : var.container_dynamic_group_name
  container_dynamic_group_principal = "${var.identity_domain_name}/${local.container_dynamic_group_name}"
}

resource "oci_core_network_security_group" "load_balancer" {
  compartment_id = var.compartment_ocid
  vcn_id         = var.vcn_ocid
  display_name   = "${var.app_name}-lb"
  freeform_tags  = local.tags
}

resource "oci_core_network_security_group" "container" {
  compartment_id = var.compartment_ocid
  vcn_id         = var.vcn_ocid
  display_name   = "${var.app_name}-container"
  freeform_tags  = local.tags
}

resource "oci_core_network_security_group_security_rule" "lb_ingress_https" {
  for_each                  = length(var.certificate_ids) == 0 ? toset([]) : var.allowed_client_cidrs
  network_security_group_id = oci_core_network_security_group.load_balancer.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = each.value
  source_type               = "CIDR_BLOCK"
  stateless                 = false
  tcp_options {
    destination_port_range {
      min = 443
      max = 443
    }
  }
}

resource "oci_core_network_security_group_security_rule" "lb_egress_to_container" {
  network_security_group_id = oci_core_network_security_group.load_balancer.id
  direction                 = "EGRESS"
  protocol                  = "6"
  destination               = oci_core_network_security_group.container.id
  destination_type          = "NETWORK_SECURITY_GROUP"
  stateless                 = false
  tcp_options {
    destination_port_range {
      min = local.app_port
      max = local.app_port
    }
  }
}

resource "oci_core_network_security_group_security_rule" "container_ingress_from_lb" {
  network_security_group_id = oci_core_network_security_group.container.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = oci_core_network_security_group.load_balancer.id
  source_type               = "NETWORK_SECURITY_GROUP"
  stateless                 = false
  tcp_options {
    destination_port_range {
      min = local.app_port
      max = local.app_port
    }
  }
}

resource "oci_core_network_security_group_security_rule" "container_egress_https" {
  network_security_group_id = oci_core_network_security_group.container.id
  direction                 = "EGRESS"
  protocol                  = "6"
  destination               = "0.0.0.0/0"
  destination_type          = "CIDR_BLOCK"
  stateless                 = false
  tcp_options {
    destination_port_range {
      min = 443
      max = 443
    }
  }
}

resource "oci_identity_dynamic_group" "container_instances" {
  count          = var.create_container_dynamic_group ? 1 : 0
  provider       = oci.home
  compartment_id = var.tenancy_ocid
  name           = "${var.app_name}-container-instances"
  description    = "Resource principals for ${var.app_name} Container Instances."
  matching_rule  = "ALL {resource.type='computecontainerinstance', resource.compartment.id='${var.compartment_ocid}'}"
}

resource "oci_identity_policy" "container_instance_runtime" {
  provider       = oci.home
  compartment_id = var.compartment_ocid
  name           = "${var.app_name}-container-runtime"
  description    = "Runtime access for ${var.app_name} Container Instances."
  statements = [
    "Allow dynamic-group ${local.container_dynamic_group_principal} to read repos in compartment id ${var.ocir_repository_compartment_ocid}",
    "Allow dynamic-group ${local.container_dynamic_group_principal} to manage ai-service-document-family in compartment id ${var.compartment_ocid}",
  ]
}

resource "oci_container_instances_container_instance" "app" {
  availability_domain      = var.availability_domain
  compartment_id           = var.compartment_ocid
  display_name             = var.app_name
  container_restart_policy = "ALWAYS"
  shape                    = var.container_shape
  freeform_tags            = local.tags

  shape_config {
    ocpus         = var.container_ocpus
    memory_in_gbs = var.container_memory_in_gbs
  }

  containers {
    display_name          = var.app_name
    image_url             = var.image_uri
    environment_variables = local.container_environment

  }

  vnics {
    subnet_id             = var.private_subnet_ocid
    private_ip            = var.container_private_ip
    is_public_ip_assigned = false
    nsg_ids               = [oci_core_network_security_group.container.id]
  }

  depends_on = [oci_identity_policy.container_instance_runtime]
}

resource "oci_load_balancer_load_balancer" "app" {
  compartment_id             = var.compartment_ocid
  display_name               = "${var.app_name}-lb"
  shape                      = "flexible"
  subnet_ids                 = [var.public_subnet_ocid]
  is_private                 = false
  network_security_group_ids = [oci_core_network_security_group.load_balancer.id]
  freeform_tags              = local.tags

  shape_details {
    minimum_bandwidth_in_mbps = 10
    maximum_bandwidth_in_mbps = 100
  }
}

resource "oci_load_balancer_backend_set" "app" {
  load_balancer_id = oci_load_balancer_load_balancer.app.id
  name             = "streamlit"
  policy           = "ROUND_ROBIN"

  health_checker {
    protocol          = "HTTP"
    port              = local.app_port
    url_path          = "/_stcore/health"
    return_code       = 200
    interval_ms       = 10000
    timeout_in_millis = 3000
    retries           = 3
  }
}

resource "oci_load_balancer_backend" "app" {
  load_balancer_id = oci_load_balancer_load_balancer.app.id
  backendset_name  = oci_load_balancer_backend_set.app.name
  ip_address       = var.container_private_ip
  port             = local.app_port
}

resource "oci_load_balancer_listener" "https" {
  count                    = length(var.certificate_ids) == 0 ? 0 : 1
  load_balancer_id         = oci_load_balancer_load_balancer.app.id
  name                     = "https"
  default_backend_set_name = oci_load_balancer_backend_set.app.name
  port                     = 443
  protocol                 = "HTTP"
  ssl_configuration {
    certificate_ids         = var.certificate_ids
    verify_peer_certificate = false
    verify_depth            = 1
  }
}
