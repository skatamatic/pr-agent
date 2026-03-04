terraform {
  backend "gcs" {
    bucket = "pr-agent-test-deploy-tfstate"
    prefix = "pr-agent-dash/dev/state"
  }
}
