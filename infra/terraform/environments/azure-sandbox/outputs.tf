output "storage_account_name" {
  description = "Sandbox storage account name"
  value       = azurerm_storage_account.app.name
}

output "snapshots_container" {
  description = "Container for contract snapshots"
  value       = azurerm_storage_container.snapshots.name
}

output "archives_container" {
  description = "Container for observation archives"
  value       = azurerm_storage_container.archives.name
}

output "drift_events_queue" {
  description = "Queue for drift event notifications"
  value       = azurerm_storage_queue.drift_events.name
}

output "probe_results_queue" {
  description = "Queue for probe result ingestion"
  value       = azurerm_storage_queue.probe_results.name
}
