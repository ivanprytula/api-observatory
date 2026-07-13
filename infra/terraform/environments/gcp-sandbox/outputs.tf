output "backup_bucket" {
  description = "GCS backup bucket name (floci-gcp)"
  value       = google_storage_bucket.backups.name
}

output "events_topic" {
  description = "Pub/Sub events topic (floci-gcp)"
  value       = google_pubsub_topic.events.id
}

output "events_subscription" {
  description = "Pub/Sub events subscription (floci-gcp)"
  value       = google_pubsub_subscription.events_sub.id
}
