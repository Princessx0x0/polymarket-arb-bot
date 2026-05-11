variable "project_id" {
  description = "GCP Project ID"
  type        = string
  default     = "polymarket-02"
}

variable "region" {
  description = "GCP region - Johannesburg, no geoblocking"
  type        = string
  default     = "africa-south1"
}

variable "zone" {
  description = "GCP zone"
  type        = string
  default     = "africa-south1-a"
}

variable "machine_type" {
  description = "VM size - e2-small is sufficient for scanner + bot"
  type        = string
  default     = "e2-small"
}

variable "vm_name" {
  description = "VM instance name"
  type        = string
  default     = "poly-bot-joburg"
}
