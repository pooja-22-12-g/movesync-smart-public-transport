"""
Authentication and Role-Based Authorization Module
Part of Module 7: Firebase Backend Development
Smart Public Transport Occupancy and Fleet Monitoring System

Capabilities:
1. Passenger and Authority registration & login backed by persistent Firestore storage.
2. 3-Tier Role Evaluation: 'passenger', 'authority', 'administrator'.
3. Salted PBKDF2-HMAC-SHA256 password hashing (zero plaintext password storage).
4. Signed, expiring JWT session tokens (PyJWT HS256) using JWT_SECRET env var.
5. Enforces RBAC at the backend API layer and prevents self-role escalation.
"""

import os
import sys
import time
import hmac
import hashlib
import secrets
import logging
from typing import Optional, Dict, Any, Tuple, List
from dataclasses import dataclass

import jwt

from config.firebase_config import get_firebase_app, is_production_env

logger = logging.getLogger("AuthService")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

VALID_ROLES = ["passenger", "authority", "administrator"]
TOKEN_TTL_SECONDS = 3600  # 1 hour
_EPHEMERAL_DEV_SECRET = secrets.token_hex(32)


def _get_jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET", "").strip()
    if is_production_env():
        if len(secret) < 32:
            raise RuntimeError("Production startup failed: JWT_SECRET (minimum 32 characters) is mandatory in production.")
        return secret
    if not secret:
        return _EPHEMERAL_DEV_SECRET
    return secret


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"pbkdf2_sha256${salt}${dk.hex()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        scheme, salt, expected_hex = stored_hash.split("$", 2)
        if scheme != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
        return hmac.compare_digest(dk.hex(), expected_hex)
    except Exception:
        return False


@dataclass
class UserSession:
    uid: str
    email: str
    role: str
    display_name: str
    expires_at: float
    token: str


class AuthenticationService:
    def __init__(self, credentials_path: Optional[str] = None):
        self.db, self.status = get_firebase_app(credentials_path)
        if is_production_env():
            _get_jwt_secret()  # Enforce mandatory JWT_SECRET at startup
            self._bootstrap_production_admin()
        else:
            if not os.getenv("JWT_SECRET"):
                logger.warning("JWT_SECRET not set; using ephemeral in-process signing key (local dev only).")
            self._ensure_seed_accounts()
        logger.info(f"AuthenticationService initialized in {self.status.mode} mode.")

    def _bootstrap_production_admin(self) -> None:
        """In production, never seed default demo passwords; only bootstrap an explicit admin if configured."""
        admin_email = os.getenv("ADMIN_BOOTSTRAP_EMAIL", "").strip().lower()
        admin_pass = os.getenv("ADMIN_BOOTSTRAP_PASSWORD", "")
        if not admin_email or len(admin_pass) < 10:
            return
        if not self._find_user_by_email(admin_email):
            uid = "usr_admin_bootstrap"
            self.db.collection("users").document(uid).set({
                "uid": uid,
                "email": admin_email,
                "password_hash": _hash_password(admin_pass),
                "role": "administrator",
                "display_name": "System Administrator",
                "created_at": time.time(),
            })
            logger.info("Production administrator account bootstrapped from environment configuration.")

    def _find_user_by_email(self, email_clean: str) -> Optional[Dict[str, Any]]:
        """Lookup user record in Firestore (live or shared mock)."""
        try:
            col = self.db.collection("users")
            if hasattr(col, "where"):
                docs = col.where("email", "==", email_clean).limit(1).stream()
                for d in docs:
                    return d.to_dict()
            else:
                for d in col.stream():
                    data = d.to_dict()
                    if str(data.get("email", "")).strip().lower() == email_clean:
                        return data
        except Exception as e:
            logger.error(f"Error querying user by email: {type(e).__name__}")
        return None

    def _ensure_seed_accounts(self) -> None:
        """Seed demo passenger/authority/admin accounts only if they do not exist yet."""
        seeds = [
            {
                "uid": "usr_pass_001",
                "email": "passenger@demo.com",
                "password": os.getenv("DEMO_PASSENGER_PASSWORD", "pass123"),
                "role": "passenger",
                "display_name": "Demo Commuter",
            },
            {
                "uid": "usr_auth_001",
                "email": "dispatcher@demo.com",
                "password": os.getenv("DEMO_AUTHORITY_PASSWORD", "auth123"),
                "role": "authority",
                "display_name": "Control Room Dispatcher",
            },
            {
                "uid": "usr_admin_001",
                "email": "admin@demo.com",
                "password": os.getenv("DEMO_ADMIN_PASSWORD", "admin123"),
                "role": "administrator",
                "display_name": "System Administrator",
            },
        ]
        for s in seeds:
            try:
                doc_ref = self.db.collection("users").document(s["uid"])
                if not doc_ref.get().exists and not self._find_user_by_email(s["email"]):
                    doc_ref.set({
                        "uid": s["uid"],
                        "email": s["email"],
                        "password_hash": _hash_password(s["password"]),
                        "role": s["role"],
                        "display_name": s["display_name"],
                        "created_at": time.time(),
                    })
            except Exception as e:
                logger.warning(f"Could not seed account {s['email']}: {type(e).__name__}")

    def register_user(
        self,
        email: str,
        password: str,
        display_name: str,
        requested_role: str = "passenger",
        caller_role: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Register a new user in persistent Firestore storage.
        Public registration defaults strictly to 'passenger'.
        Only an existing 'administrator' can create 'authority' or 'administrator' accounts.
        """
        email_clean = email.strip().lower()
        if not email_clean or "@" not in email_clean:
            return False, "Invalid email address format.", None

        if len(password) < 6:
            return False, "Password must be at least 6 characters.", None

        if requested_role in ["authority", "administrator"]:
            if caller_role != "administrator":
                return False, f"Unauthorized: Public registration cannot create '{requested_role}' accounts. Role must be 'passenger'.", None
            final_role = requested_role
        else:
            final_role = "passenger"

        if self._find_user_by_email(email_clean):
            return False, "User with this email already exists.", None

        uid = f"usr_{final_role}_{int(time.time() * 1000)}_{secrets.token_hex(2)}"
        user_record = {
            "uid": uid,
            "email": email_clean,
            "password_hash": _hash_password(password),
            "role": final_role,
            "display_name": display_name.strip(),
            "created_at": time.time(),
        }

        try:
            self.db.collection("users").document(uid).set(user_record)
        except Exception as e:
            logger.error(f"Failed to persist user to Firestore: {type(e).__name__}")
            return False, "Database error while registering user.", None

        logger.info(f"User registered successfully: {email_clean} with role '{final_role}' (UID: {uid})")
        return True, "User registered successfully.", {k: v for k, v in user_record.items() if k != "password_hash"}

    def authenticate_user(self, email: str, password: str) -> Tuple[bool, str, Optional[UserSession]]:
        """Verify credentials against Firestore user record and issue a signed JWT."""
        email_clean = email.strip().lower()
        user = self._find_user_by_email(email_clean)

        if not user or not _verify_password(password, str(user.get("password_hash", ""))):
            return False, "Invalid email or password.", None

        now = time.time()
        expires_at = now + TOKEN_TTL_SECONDS
        payload = {
            "sub": user["uid"],
            "email": user["email"],
            "role": user["role"],
            "display_name": user.get("display_name", "MoveSync User"),
            "iat": int(now),
            "exp": int(expires_at),
        }
        token = jwt.encode(payload, _get_jwt_secret(), algorithm="HS256")
        if isinstance(token, bytes):
            token = token.decode("utf-8")

        session = UserSession(
            uid=user["uid"],
            email=user["email"],
            role=user["role"],
            display_name=user.get("display_name", "MoveSync User"),
            expires_at=expires_at,
            token=token,
        )
        logger.info(f"Session established for {user['email']} (Role: {user['role']})")
        return True, "Authentication successful.", session

    def verify_session(self, token: Optional[str]) -> Tuple[bool, str, Optional[UserSession]]:
        """Statelessly verify signed JWT signature and expiration."""
        if not token:
            return False, "Missing authorization token.", None

        if token.startswith("Bearer "):
            token = token[7:]

        try:
            decoded = jwt.decode(token, _get_jwt_secret(), algorithms=["HS256"])
            session = UserSession(
                uid=decoded["sub"],
                email=decoded["email"],
                role=decoded["role"],
                display_name=decoded.get("display_name", "MoveSync User"),
                expires_at=float(decoded["exp"]),
                token=token,
            )
            return True, "Session verified.", session
        except jwt.ExpiredSignatureError:
            return False, "Session has expired. Please log in again.", None
        except jwt.InvalidTokenError:
            return False, "Invalid or unrecognized session token.", None

    def authorize_endpoint(self, token: Optional[str], required_roles: List[str]) -> Tuple[bool, str, Optional[UserSession]]:
        """Backend API Authorization Guard enforcing RBAC permissions."""
        is_valid, msg, session = self.verify_session(token)
        if not is_valid or not session:
            return False, f"Authentication required: {msg}", None

        if session.role not in required_roles:
            return False, f"Access denied: User role '{session.role}' is not authorized. Requires: {required_roles}", session

        return True, "Authorized.", session

    def prevent_self_role_escalation(self, session: UserSession, target_uid: str, new_role: str) -> Tuple[bool, str]:
        """Enforce invariant: Users cannot change their own role or promote themselves."""
        if session.role != "administrator":
            return False, "Forbidden: Only an administrator can modify user roles."

        if target_uid == session.uid and new_role != "administrator":
            return False, "Forbidden: Administrator cannot revoke their own admin status."

        if new_role not in VALID_ROLES:
            return False, f"Invalid role '{new_role}'. Must be one of {VALID_ROLES}."

        return True, "Role change approved."
