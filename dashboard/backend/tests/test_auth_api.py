"""
Tests for auth API: login, verify, change-password.
Uses in-memory DB; default admin (admin/mobile) is created on app init.
"""
import pytest


class TestAuthAPI:
    """Authentication endpoints."""

    def test_login_success(self, client_app):
        response = client_app.post(
            "/api/auth/login",
            json={"username": "admin", "password": "mobile"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert data["data"].get("token")
        assert data["data"].get("user", {}).get("username") == "admin"
        assert "message" in data and "success" in data["message"].lower()

    def test_login_invalid_password(self, client_app):
        response = client_app.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong"},
        )
        assert response.status_code == 401
        assert "Invalid" in response.json().get("detail", "")

    def test_login_invalid_username(self, client_app):
        response = client_app.post(
            "/api/auth/login",
            json={"username": "nobody", "password": "mobile"},
        )
        assert response.status_code == 401

    def test_verify_without_token_returns_401(self, client_app):
        response = client_app.get("/api/auth/verify")
        assert response.status_code == 401

    def test_verify_with_invalid_token_returns_401(self, client_app):
        response = client_app.get(
            "/api/auth/verify",
            headers={"Authorization": "Bearer invalid-token-not-jwt"},
        )
        assert response.status_code == 401

    def test_verify_with_valid_token_returns_user(self, client_app):
        login = client_app.post(
            "/api/auth/login",
            json={"username": "admin", "password": "mobile"},
        )
        assert login.status_code == 200
        token = login.json()["data"]["token"]
        response = client_app.get(
            "/api/auth/verify",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["user"]["username"] == "admin"

    def test_change_password_requires_auth(self, client_app):
        response = client_app.post(
            "/api/auth/change-password",
            json={
                "current_password": "mobile",
                "new_password": "newpass",
            },
        )
        assert response.status_code == 401

    def test_change_password_success(self, client_app):
        login = client_app.post(
            "/api/auth/login",
            json={"username": "admin", "password": "mobile"},
        )
        token = login.json()["data"]["token"]
        response = client_app.post(
            "/api/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "current_password": "mobile",
                "new_password": "newpass",
            },
        )
        assert response.status_code == 200
        # Verify new password works
        login2 = client_app.post(
            "/api/auth/login",
            json={"username": "admin", "password": "newpass"},
        )
        assert login2.status_code == 200
        # Restore for other tests (optional)
        client_app.post(
            "/api/auth/change-password",
            headers={"Authorization": f"Bearer {login2.json()['data']['token']}"},
            json={"current_password": "newpass", "new_password": "mobile"},
        )
