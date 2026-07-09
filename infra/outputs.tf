output "container_instance_id" {
  value = oci_container_instances_container_instance.app.id
}

output "load_balancer_ip_addresses" {
  value = oci_load_balancer_load_balancer.app.ip_address_details
}

output "url" {
  value       = length(var.certificate_ids) == 0 ? null : "https://${oci_load_balancer_load_balancer.app.ip_address_details[0].ip_address}"
  description = "Connect a DNS name to this address before using it as the public application URL."
}
