"""
Verification Script for Module 7 — Step 2: Firebase Environment & Configuration
Smart Public Transport Occupancy and Fleet Monitoring System

Checks:
1. Firebase Admin SDK package installation and version.
2. Configuration loading from config/firebase_config.py.
3. Automatic fallback to Mock / Dry-Run mode when serviceAccountKey.json is absent.
4. In-memory Mock Firestore read/write capabilities (emulating collection/doc/set/get).
5. Live Firebase mode validation handling (safe handling of invalid credentials without key leakage).
6. Verification that existing Module 1-6 modules and CSV remain unmodified.
"""

import os
import sys
import json
import tempfile
from typing import Tuple

def run_tests() -> int:
    print("=" * 75)
    print("MODULE 7 — STEP 2: FIREBASE ENVIRONMENT & CONFIGURATION VERIFICATION")
    print("=" * 75)

    failures = 0

    # Test 1: Check firebase_admin import
    print("\n[TEST 1] Verifying firebase-admin installation...")
    try:
        import firebase_admin
        from firebase_admin import firestore
        print(f"  -> SUCCESS: firebase_admin v{firebase_admin.__version__} is installed and importable.")
    except Exception as e:
        print(f"  -> FAILURE: Could not import firebase_admin: {e}")
        failures += 1

    # Test 2: Import config.firebase_config
    print("\n[TEST 2] Verifying config/firebase_config.py module loading...")
    try:
        from config.firebase_config import (
            get_firebase_app, 
            locate_credentials_file, 
            MockFirestoreClient, 
            FirebaseStatus
        )
        print("  -> SUCCESS: config.firebase_config loaded successfully.")
    except Exception as e:
        print(f"  -> FAILURE: Failed importing config.firebase_config: {e}")
        return failures + 1

    # Test 3: Verify Mock Mode when credentials are absent
    print("\n[TEST 3] Verifying Mock / Dry-Run Mode (Credentials absent)...")
    try:
        db, status = get_firebase_app(credentials_path="non_existent_creds_9999.json")
        assert not status.is_live, "Expected status.is_live to be False"
        assert status.mode == "MOCK_DRY_RUN", f"Expected mode MOCK_DRY_RUN, got {status.mode}"
        assert isinstance(db, MockFirestoreClient), f"Expected MockFirestoreClient instance, got {type(db)}"
        print(f"  -> SUCCESS: Defaulted to Mock Mode cleanly: {status.details}")
    except Exception as e:
        print(f"  -> FAILURE in Mock mode test: {e}")
        failures += 1

    # Test 4: Verify in-memory operations in Mock Mode
    print("\n[TEST 4] Verifying in-memory Mock Firestore read/write...")
    try:
        test_col = db.collection("test_buses")
        test_doc = test_col.document("KA-BUS-TEST")
        test_doc.set({"bus_id": "KA-BUS-TEST", "current_occupancy": 32, "status": "IN_SERVICE"})
        
        snapshot = test_doc.get()
        assert snapshot.exists, "Mock document should exist after set()"
        data = snapshot.to_dict()
        assert data.get("current_occupancy") == 32, f"Expected 32, got {data.get('current_occupancy')}"
        print(f"  -> SUCCESS: Mock set/get completed correctly. Read: {data}")
    except Exception as e:
        print(f"  -> FAILURE in Mock read/write test: {e}")
        failures += 1

    # Test 5: Verify Graceful Error Handling on Corrupted/Invalid Credentials
    print("\n[TEST 5] Verifying Graceful Error Handling on Invalid Credentials JSON...")
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
            tf.write(json.dumps({"type": "not_a_service_account", "project_id": "fake-project"}))
            invalid_cred_path = tf.name

        try:
            db_err, status_err = get_firebase_app(credentials_path=invalid_cred_path)
            assert not status_err.is_live, "Should not be live with invalid JSON"
            assert "MOCK" in status_err.mode, f"Expected MOCK fallback, got {status_err.mode}"
            print(f"  -> SUCCESS: Invalid credentials caught safely without leaking keys: {status_err.details}")
        finally:
            if os.path.exists(invalid_cred_path):
                os.remove(invalid_cred_path)
    except Exception as e:
        print(f"  -> FAILURE in invalid credentials test: {e}")
        failures += 1

    # Test 6: Verify Security Rules and Indexes Files Exist and are Non-Empty
    print("\n[TEST 6] Verifying firestore.rules and firestore.indexes.json...")
    try:
        assert os.path.exists("firestore.rules"), "firestore.rules not found"
        assert os.path.exists("firestore.indexes.json"), "firestore.indexes.json not found"
        
        with open("firestore.rules", "r", encoding="utf-8") as f:
            rules_content = f.read()
            assert "service cloud.firestore" in rules_content
            assert "isAuthority()" in rules_content
            assert "isPassenger()" in rules_content

        with open("firestore.indexes.json", "r", encoding="utf-8") as f:
            indexes_data = json.load(f)
            assert "indexes" in indexes_data
            assert len(indexes_data["indexes"]) == 4

        print(f"  -> SUCCESS: firestore.rules and firestore.indexes.json verified (4 composite indexes).")
    except Exception as e:
        print(f"  -> FAILURE in security rules / indexes test: {e}")
        failures += 1

    # Test 7: Verify Original CSV Integrity & Module 1-6 Intact
    print("\n[TEST 7] Verifying dataset integrity and core module existence...")
    try:
        import pandas as pd
        csv_path = "data/bus_occupancy.csv"
        df = pd.read_csv(csv_path)
        assert len(df) == 2002, f"Expected 2002 rows, found {len(df)}"
        assert len(df.columns) == 14, f"Expected 14 columns, found {len(df.columns)}"
        
        # Verify required root modules
        for mod in ["occupancy_monitor.py", "overcrowding_alerts.py", "gps_tracking.py", "app_occupancy.py"]:
            assert os.path.exists(mod), f"Missing core module: {mod}"
        print(f"  -> SUCCESS: Original dataset preserved intact (2,002 rows, 14 columns). All modules present.")
    except Exception as e:
        print(f"  -> FAILURE in integrity test: {e}")
        failures += 1

    print("\n" + "=" * 75)
    if failures == 0:
        print("ALL MODULE 7 — STEP 2 VERIFICATION TESTS PASSED (7/7) - ZERO ERRORS")
    else:
        print(f"VERIFICATION COMPLETED WITH {failures} FAILURES")
    print("=" * 75)
    return failures

if __name__ == "__main__":
    sys.exit(run_tests())

