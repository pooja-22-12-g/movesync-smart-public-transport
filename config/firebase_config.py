"""
Firebase Configuration and Client Initialization Module
Part of Module 7: Firebase Backend Development
Smart Public Transport Occupancy and Fleet Monitoring System

Supports two operational modes:
1. Mock / Dry-Run Mode:
   - Activated automatically when 'serviceAccountKey.json' (or custom path) is absent or invalid.
   - Allows safe offline local operation with simulated in-memory responses.
   - Prevents unhandled network exceptions and performs no real cloud writes.
2. Live Firebase Mode:
   - Activated only when valid service account credentials JSON exists.
   - Initializes Firebase Admin SDK safely.
   - Never logs or exposes private keys, client secrets, or full credential contents.
"""

import os
import json
import logging
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass

logger = logging.getLogger("FirebaseConfig")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# Default credentials filename looked up in root or config/
DEFAULT_CREDENTIALS_FILE = "serviceAccountKey.json"

@dataclass
class FirebaseStatus:
    is_live: bool
    mode: str
    project_id: Optional[str]
    credentials_path: Optional[str]
    details: str


_SHARED_MOCK_STORE: Dict[str, Dict[str, Any]] = {}


class MockFirestoreClient:
    """
    In-memory mock client representing Cloud Firestore during local dry-run mode.
    Uses a shared in-memory dictionary so bridge, auth, and notification services
    see consistent state without network calls.
    """
    def __init__(self):
        self._store: Dict[str, Dict[str, Any]] = _SHARED_MOCK_STORE
        logger.info("[MOCK MODE] MockFirestoreClient initialized in-memory.")

    def collection(self, collection_name: str):
        return MockCollectionReference(self._store, collection_name)

    def document(self, path: str):
        parts = path.split("/")
        if len(parts) >= 2:
            return MockDocumentReference(self._store, parts[0], parts[1])
        return MockDocumentReference(self._store, path, "default")


class MockCollectionReference:
    def __init__(self, store: Dict[str, Dict[str, Any]], name: str):
        self._store = store
        self.name = name
        if name not in self._store:
            self._store[name] = {}

    def document(self, document_id: Optional[str] = None):
        if not document_id:
            import uuid
            document_id = str(uuid.uuid4())
        return MockDocumentReference(self._store, self.name, document_id)

    def stream(self):
        for doc_id, data in self._store.get(self.name, {}).items():
            yield MockDocumentSnapshot(doc_id, data, True)


class MockDocumentReference:
    def __init__(self, store: Dict[str, Dict[str, Any]], collection: str, doc_id: str):
        self._store = store
        self.collection_name = collection
        self.id = doc_id

    def set(self, data: Dict[str, Any], merge: bool = False):
        if self.collection_name not in self._store:
            self._store[self.collection_name] = {}
        if merge and self.id in self._store[self.collection_name]:
            self._store[self.collection_name][self.id].update(data)
        else:
            self._store[self.collection_name][self.id] = dict(data)
        return {"write_time": "MOCK_TIMESTAMP"}

    def get(self):
        data = self._store.get(self.collection_name, {}).get(self.id)
        exists = data is not None
        return MockDocumentSnapshot(self.id, data if exists else {}, exists)

    def update(self, data: Dict[str, Any]):
        if self.collection_name in self._store and self.id in self._store[self.collection_name]:
            self._store[self.collection_name][self.id].update(data)
            return {"write_time": "MOCK_TIMESTAMP"}
        raise KeyError(f"Mock document {self.id} does not exist in {self.collection_name}")


class MockDocumentSnapshot:
    def __init__(self, doc_id: str, data: Dict[str, Any], exists: bool):
        self.id = doc_id
        self._data = data
        self.exists = exists

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._data)


def locate_credentials_file(custom_path: Optional[str] = None) -> Optional[str]:
    """
    Search for service account credentials file in standard project locations.
    Never exposes path or keys in logs unnecessarily.
    """
    candidates = []
    if custom_path:
        candidates.append(custom_path)
    
    # Environment variable check
    env_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if env_path:
        candidates.append(env_path)

    # Standard relative locations
    cwd = os.getcwd()
    candidates.extend([
        os.path.join(cwd, DEFAULT_CREDENTIALS_FILE),
        os.path.join(cwd, "config", DEFAULT_CREDENTIALS_FILE),
        os.path.join(os.path.dirname(__file__), DEFAULT_CREDENTIALS_FILE),
    ])

    for path in candidates:
        if path and os.path.exists(path) and os.path.isfile(path):
            return os.path.abspath(path)
    return None


def is_production_env() -> bool:
    """Detect production deployment (explicit ENVIRONMENT=production or Render runtime)."""
    return (
        os.getenv("ENVIRONMENT", "").strip().lower() == "production"
        or os.getenv("APP_ENV", "").strip().lower() == "production"
        or os.getenv("RENDER", "").strip().lower() == "true"
    )


def get_firebase_app(credentials_path: Optional[str] = None) -> Tuple[Any, FirebaseStatus]:
    """
    Initialize Firebase Admin SDK or return a mock handle.
    In production (ENVIRONMENT=production or RENDER=true), missing or invalid
    credentials fail startup immediately instead of falling back to mock mode.
    Returns (firestore_client, FirebaseStatus).
    """
    prod_mode = is_production_env()
    env_json = None if credentials_path else os.getenv("FIREBASE_CREDENTIALS_JSON")
    cred_file = locate_credentials_file(credentials_path) if (credentials_path or not env_json) else None

    if not env_json and not cred_file:
        if prod_mode:
            raise RuntimeError("Production startup failed: FIREBASE_CREDENTIALS_JSON is required and cannot fall back to MockFirestoreClient.")
        status = FirebaseStatus(
            is_live=False,
            mode="MOCK_DRY_RUN",
            project_id=None,
            credentials_path=None,
            details="No serviceAccountKey.json or FIREBASE_CREDENTIALS_JSON located. Operating in safe in-memory mock mode."
        )
        logger.info(f"Firebase Mode: {status.mode} — {status.details}")
        return MockFirestoreClient(), status

    try:
        if env_json:
            cred_dict = json.loads(env_json)
        else:
            with open(cred_file, "r", encoding="utf-8") as f:
                cred_dict = json.load(f)

        project_id = cred_dict.get("project_id", "unknown-project")

        # Verify required service account structure without logging private keys
        if "type" not in cred_dict or cred_dict.get("type") != "service_account":
            raise ValueError("Credentials payload is not a valid Google Service Account JSON.")

        import firebase_admin
        from firebase_admin import credentials, firestore

        if not firebase_admin._apps:
            cred = credentials.Certificate(cred_dict if env_json else cred_file)
            firebase_admin.initialize_app(cred, {
                "projectId": project_id
            })
            logger.info(f"Firebase Admin SDK initialized successfully for project: {project_id}")
        else:
            firebase_admin.get_app()

        db = firestore.client()
        status = FirebaseStatus(
            is_live=True,
            mode="LIVE_FIREBASE",
            project_id=project_id,
            credentials_path="ENV:FIREBASE_CREDENTIALS_JSON" if env_json else cred_file,
            details=f"Connected to live Firebase project '{project_id}' via Service Account."
        )
        return db, status

    except Exception as e:
        if prod_mode:
            raise RuntimeError(f"Production startup failed: invalid Firebase credentials ({type(e).__name__}).") from None
        status = FirebaseStatus(
            is_live=False,
            mode="MOCK_FALLBACK_ON_ERROR",
            project_id=None,
            credentials_path="ENV:FIREBASE_CREDENTIALS_JSON" if env_json else cred_file,
            details=f"Live initialization failed ({type(e).__name__}). Fallback to mock mode."
        )
        logger.warning(f"Could not initialize live Firebase ({type(e).__name__}). Falling back to safe mock mode.")
        return MockFirestoreClient(), status

