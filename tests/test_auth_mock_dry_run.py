import os
import time
from fastapi.testclient import TestClient

os.environ.setdefault("ENV", "development")

from config.firebase_config import _SHARED_MOCK_STORE
from sync.auth_service import AuthenticationService
from sync.main_api import app


def test_register_login_and_protected_endpoint_in_mock_dry_run():
    email_raw = f"  Passenger_{int(time.time() * 1000)}@MoveSync.Test "
    email_norm = email_raw.strip().lower()
    password = "StrongPass!123"

    with TestClient(app) as client:
        # 1. Register passenger (201 Created)
        reg = client.post(
            "/api/auth/register",
            json={
                "email": email_raw,
                "password": password,
                "display_name": "Test Passenger",
                "requested_role": "passenger",
            },
        )
        assert reg.status_code == 201, reg.text
        reg_data = reg.json()
        assert reg_data["user"]["email"] == email_norm
        assert reg_data["user"]["role"] == "passenger"

        # 2. Wrong password fails with 401
        bad_login = client.post(
            "/api/auth/login",
            json={"email": email_norm, "password": "WrongPassword!"},
        )
        assert bad_login.status_code == 401

        # 3. Login succeeds with normalized email & issues JWT
        login = client.post(
            "/api/auth/login",
            json={"email": email_norm, "password": password},
        )
        assert login.status_code == 200, login.text
        login_data = login.json()
        token = login_data["access_token"]
        assert token
        headers = {"Authorization": f"Bearer {token}"}

        # 4. Access protected passenger endpoints
        profile = client.get("/api/auth/profile", headers=headers)
        assert profile.status_code == 200, profile.text
        assert profile.json()["email"] == email_norm
        assert profile.json()["role"] == "passenger"

        saved = client.get("/api/trips/saved", headers=headers)
        assert saved.status_code == 200, saved.text

        # 5. RBAC: passenger is blocked from authority endpoint
        forbidden = client.get("/api/authority/route-demand", headers=headers)
        assert forbidden.status_code == 403

        # 6. Public registration cannot self-escalate to authority
        esc = client.post(
            "/api/auth/register",
            json={
                "email": f"esc_{int(time.time() * 1000)}@movesync.test",
                "password": password,
                "display_name": "Escalator",
                "requested_role": "authority",
            },
        )
        assert esc.status_code == 400

        # 7. Simulate server reload / separate worker by clearing in-memory store
        _SHARED_MOCK_STORE.clear()
        reloaded_auth = AuthenticationService()
        ok, msg, session = reloaded_auth.authenticate_user(email_norm, password)
        assert ok is True, msg
        assert session is not None and session.email == email_norm

        # 8. Verify PBKDF2-HMAC-SHA256 hash format (no plaintext storage)
        user_doc = reloaded_auth._find_user_by_email(email_norm)
        assert user_doc is not None
        assert str(user_doc["password_hash"]).startswith("pbkdf2_sha256$")
        assert password not in str(user_doc["password_hash"])

        # 9. Verify registering another user in a fresh instance preserves previous users on disk
        second_email = f"second_{int(time.time() * 1000)}@movesync.test"
        ok2, msg2, _ = reloaded_auth.register_user(second_email, password, "Second Passenger")
        assert ok2 is True, msg2

        _SHARED_MOCK_STORE.clear()
        fresh_auth = AuthenticationService()
        ok_first, _, _ = fresh_auth.authenticate_user(email_norm, password)
        ok_second, _, _ = fresh_auth.authenticate_user(second_email, password)
        assert ok_first is True
        assert ok_second is True


if __name__ == "__main__":
    test_register_login_and_protected_endpoint_in_mock_dry_run()
    print("TEST_AUTH_MOCK_DRY_RUN_PASSED")
