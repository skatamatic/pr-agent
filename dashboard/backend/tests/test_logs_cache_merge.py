"""Logs cache+DB merge: unique ids per log row after create."""
def test_get_logs_returns_unique_ids_after_inserts(client_app, auth_headers):
    """Merged cache+DB log list should not duplicate ids for distinct creates."""
    ids = []
    for i in range(3):
        r = client_app.post(
            "/logs/immediate",
            json={"level": "INFO", "message": f"merge-test-{i}", "source": "t"},
            headers=auth_headers,
        )
        assert r.status_code == 200
        ids.append(r.json().get("id"))
    assert len(set(ids)) == 3

    r = client_app.get("/api/logs?limit=100", headers=auth_headers)
    assert r.status_code == 200
    logs = r.json()["data"]["logs"]
    seen = set()
    for log in logs:
        lid = log.get("id")
        if lid is not None:
            assert lid not in seen
            seen.add(lid)
