output "maps_api_key" {
  description = "The restricted API key string. Sensitive: read it once with `terraform output -raw maps_api_key`, store it in the Keychain, never write it to a file in this repository."
  value       = google_apikeys_key.maps_grounding_lite.key_string
  sensitive   = true
}

output "mcp_endpoint" {
  description = "The hosted MCP endpoint .mcp.json points at."
  value       = "https://mapstools.googleapis.com/mcp"
}
