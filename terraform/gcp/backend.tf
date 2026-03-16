terraform {
  backend "gcs" {
    bucket = "nex-ai-fracgpt-dev-tfstate"
    prefix = "pr-agent-dash/dev-restricted/state"
  }
}
