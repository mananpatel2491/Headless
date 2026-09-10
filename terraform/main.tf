# Google Maps connector for Headless (spec 010-google-maps-connector).
# Declares the ONLY cloud resources the connector needs: the Maps Grounding Lite API
# enabled on a Director-chosen project, and one API key restricted to that service.
# Applied by the Director after reviewing `terraform plan` (Lesson 5); nothing here is
# created from the console or an ad-hoc CLI call.

terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
}

# The API key service itself must be enabled before a key can be created.
resource "google_project_service" "apikeys" {
  project            = var.project_id
  service            = "apikeys.googleapis.com"
  disable_on_destroy = false
}

# Maps Grounding Lite: the hosted MCP server at https://mapstools.googleapis.com/mcp.
resource "google_project_service" "mapstools" {
  project            = var.project_id
  service            = "mapstools.googleapis.com"
  disable_on_destroy = false
}

# One key, usable for exactly one API. The key string is a Terraform output marked
# sensitive; the Director stores it in the macOS Keychain and exports it as
# HEADLESS_MAPS_API_KEY for Claude Code's .mcp.json (never a file in the repository).
resource "google_apikeys_key" "maps_grounding_lite" {
  name         = "headless-maps-grounding-lite"
  display_name = "Headless - Maps Grounding Lite MCP"
  project      = var.project_id

  restrictions {
    api_targets {
      service = "mapstools.googleapis.com"
    }
  }

  depends_on = [google_project_service.apikeys, google_project_service.mapstools]
}
