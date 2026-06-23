# Notifications

Part of the [Dashboard API](README.md) reference.

Notification channel configuration and event history. JWT required.

---

| Method | Path | Notes |
|--------|------|-------|
| GET/POST | `/api/notifications/configs` | List / create notification configs |
| PUT/DELETE | `/api/notifications/configs/{config_id}` | Update / delete |
| POST | `/api/notifications/test/{config_id}` | Send test notification |
| GET | `/api/notifications/events` | Notification event history |
