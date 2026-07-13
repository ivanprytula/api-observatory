terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_storage_bucket" "backups" {
  name          = "${var.project}-backups"
  location      = var.region
  force_destroy = true

  labels = {
    project = var.project
  }
}

resource "google_pubsub_topic" "events" {
  name = "${var.project}-events"

  labels = {
    project = var.project
  }
}

resource "google_pubsub_subscription" "events_sub" {
  name  = "${var.project}-events-sub"
  topic = google_pubsub_topic.events.id

  ack_deadline_seconds = 20

  labels = {
    project = var.project
  }
}
