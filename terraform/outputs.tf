output "vm_name" {
  description = "VM instance name"
  value       = google_compute_instance.bot_vm.name
}

output "vm_zone" {
  description = "VM zone"
  value       = google_compute_instance.bot_vm.zone
}

output "service_account" {
  description = "VM service account email"
  value       = google_service_account.bot_sa.email
}

output "ssh_command" {
  description = "Command to SSH into the VM via IAP"
  value       = "gcloud compute ssh ${google_compute_instance.bot_vm.name} --project=${var.project_id} --zone=${var.zone} --tunnel-through-iap"
}

output "next_steps" {
  description = "What to do after deploy"
  value       = <<EOT
Infrastructure deployed. Next steps:
1. Add secrets:
   gcloud secrets versions add polymarket-api-key --data-file=- --project=${var.project_id}
   gcloud secrets versions add polymarket-api-secret --data-file=- --project=${var.project_id}
   gcloud secrets versions add polymarket-api-passphrase --data-file=- --project=${var.project_id}
   gcloud secrets versions add polymarket-private-key --data-file=- --project=${var.project_id}
   gcloud secrets versions add telegram-bot-token --data-file=- --project=${var.project_id}
   gcloud secrets versions add github-pat --data-file=- --project=${var.project_id}

2. SSH into VM:
   gcloud compute ssh ${google_compute_instance.bot_vm.name} --project=${var.project_id} --zone=${var.zone} --tunnel-through-iap

3. Run restore script:
   curl -sSL https://raw.githubusercontent.com/Princessx0x0/polymarket-arb-bot/main/restore.sh | bash
EOT
}
