# Runners

Part of the [Dashboard API](README.md) reference.

Self-hosted Azure DevOps / GitHub runner connections and GCE VM provisioning.

---

| Method | Path | Notes |
|--------|------|-------|
| GET/POST | `/api/action-runner-connections` | List/create ADO/GitHub runner groups |
| PUT | `/api/action-runner-connections/{id}` | Update connection |
| GET | `.../azure-agent-pools` | List agent pools |
| POST | `.../provision` | Start GCE VM; optional `ProvisionRunnerRequest` body |
| GET | `.../provision-status` | Milestones + serial console hints |
| POST | `.../deprovision` | Tear down VM |
| DELETE | `/api/action-runner-connections/{id}` | Delete connection + VM |

[Self-hosted runners](../self-hosted-runners.md) covers bootstrap and env-file details.
