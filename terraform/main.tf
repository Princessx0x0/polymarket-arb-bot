terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ── APIs ──────────────────────────────────────────────────────────────────────
resource "google_project_service" "apis" {
  for_each = toset([
    "compute.googleapis.com",
    "secretmanager.googleapis.com",
    "bigquery.googleapis.com",
    "iap.googleapis.com",
    "logging.googleapis.com",
  ])
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

# ── Networking ────────────────────────────────────────────────────────────────
# Router enables Cloud NAT - VM gets outbound internet without external IP
resource "google_compute_router" "router" {
  name    = "poly-router"
  region  = var.region
  network = "default"
}

# NAT gateway - handles all outbound traffic (Polymarket API, Telegram, etc)
resource "google_compute_router_nat" "nat" {
  name                               = "poly-nat"
  router                             = google_compute_router.router.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
}

# ── Firewall ──────────────────────────────────────────────────────────────────
# Only allow SSH from Google's IAP range - no direct internet access
resource "google_compute_firewall" "allow_iap" {
  name    = "allow-ssh-iap"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  # Google IAP source IPs only - this is the ONLY way in
  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["polymarket-bot"]
}

# Internal VM communication only
resource "google_compute_firewall" "allow_internal" {
  name    = "allow-internal"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["0-65535"]
  }
  allow {
    protocol = "udp"
    ports    = ["0-65535"]
  }
  allow {
    protocol = "icmp"
  }

  source_ranges = ["10.128.0.0/9"]
}

# Delete default open rules that GCP creates automatically
resource "google_compute_firewall" "deny_default_ssh" {
  name      = "deny-default-ssh"
  network   = "default"
  direction = "INGRESS"
  priority  = 500

  deny {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["0.0.0.0/0"]
}

# ── Service Account ───────────────────────────────────────────────────────────
# Dedicated identity for the VM - principle of least privilege
resource "google_service_account" "bot_sa" {
  account_id   = "poly-bot-sa"
  display_name = "Polymarket Bot Service Account"
  description  = "Runtime identity for the bot VM - minimal permissions only"
}

# Only 4 roles - exactly what the bot needs, nothing more
resource "google_project_iam_member" "bot_sa_roles" {
  for_each = toset([
    "roles/bigquery.dataEditor",      # Write opportunities to BigQuery
    "roles/bigquery.jobUser",         # Run BigQuery queries
    "roles/logging.logWriter",        # Write structured logs
    "roles/secretmanager.secretAccessor", # Read API keys from Secret Manager
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.bot_sa.email}"
}

# ── VM Instance ───────────────────────────────────────────────────────────────
resource "google_compute_instance" "bot_vm" {
  name         = var.vm_name
  machine_type = var.machine_type
  zone         = var.zone

  # Tag links to firewall rule - only tagged VMs get IAP access
  tags = ["polymarket-bot"]

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2404-lts"
      size  = 20
      type  = "pd-standard"
    }
  }

  network_interface {
    network = "default"
    # No access_config block = no external IP
  }

  # Attach the minimal service account
  service_account {
    email  = google_service_account.bot_sa.email
    scopes = ["cloud-platform"]
  }

  # Shielded VM - secure boot, vTPM, integrity monitoring
  shielded_instance_config {
    enable_secure_boot          = true
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }

  # OS Login - disables SSH key auth, uses Google identity only
  metadata = {
    enable-oslogin = "TRUE"
  }

  labels = {
    project    = "polymarket-bot"
    managed-by = "terraform"
    env        = "production"
  }

  # VM depends on NAT existing first - otherwise no internet on boot
  depends_on = [
    google_compute_router_nat.nat,
    google_project_service.apis,
  ]
}

# ── BigQuery ──────────────────────────────────────────────────────────────────
resource "google_bigquery_dataset" "polymarket" {
  dataset_id  = "polymarket"
  location    = "US"
  description = "Polymarket arbitrage bot - opportunities and price ticks"
}

resource "google_bigquery_table" "market_ticks" {
  dataset_id          = google_bigquery_dataset.polymarket.dataset_id
  table_id            = "market_ticks_v2"
  deletion_protection = false

  schema = jsonencode([
    { name = "ts",        type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "market_id", type = "STRING",    mode = "REQUIRED" },
    { name = "price",     type = "FLOAT",     mode = "REQUIRED" },
    { name = "raw",       type = "STRING",    mode = "NULLABLE" },
  ])
}

resource "google_bigquery_table" "paper_trades" {
  dataset_id          = google_bigquery_dataset.polymarket.dataset_id
  table_id            = "paper_trades"
  deletion_protection = false

  schema = jsonencode([
    { name = "ts",                type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "event_title",       type = "STRING",    mode = "NULLABLE" },
    { name = "event_slug",        type = "STRING",    mode = "NULLABLE" },
    { name = "direction",         type = "STRING",    mode = "NULLABLE" },
    { name = "yes_sum",           type = "FLOAT",     mode = "NULLABLE" },
    { name = "profit_per_dollar", type = "FLOAT",     mode = "NULLABLE" },
    { name = "num_conditions",    type = "INTEGER",   mode = "NULLABLE" },
    { name = "volume_24hr",       type = "FLOAT",     mode = "NULLABLE" },
  ])
}

# ── Secret Manager ────────────────────────────────────────────────────────────
# Creates the secret containers - you fill the values separately
resource "google_secret_manager_secret" "secrets" {
  for_each  = toset([
    "polymarket-api-key",
    "polymarket-api-secret",
    "polymarket-api-passphrase",
    "polymarket-private-key",
    "telegram-bot-token",
    "github-pat",
  ])
  secret_id = each.value
  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}
