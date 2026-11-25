import os
import time
from fastapi.testclient import TestClient

os.environ.setdefault("ENV", "development")

from sync.main_api import app


def test_predictions_and_upcoming_stops_for_all_20_buses():
    with TestClient(app) as client:
        # 1. Verify all 20 buses have active trips, remaining 50-stop sequence, and ML predictions
        for i in range(1, 21):
            bus_id = f"KA-BUS-{i:03d}"
            r = client.get(f"/api/buses/{bus_id}/upcoming-stops")
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["bus_id"] == bus_id
            assert data["bus_capacity"] == 60
            assert data["predictions_available"] is True, data
            assert data["current_occupancy_source"] == "DATASET_SIMULATED"
            assert data["expected_occupancy_source"] == "RANDOM_FOREST_ML"
            assert data["actual_occupancy_available"] is False

            c_seq = data["current_stop_sequence"]
            upcoming = data["upcoming_stops"]
            expected_remaining = 50 - c_seq
            assert len(upcoming) == expected_remaining, f"{bus_id}: expected {expected_remaining}, got {len(upcoming)}"
            assert upcoming[0]["is_next_stop"] is True
            assert upcoming[0]["stop_sequence"] == c_seq + 1
            assert upcoming[-1]["stop_sequence"] == 50

            for idx, stop in enumerate(upcoming):
                if idx > 0:
                    assert stop["is_next_stop"] is False
                    assert stop["stop_sequence"] == upcoming[idx - 1]["stop_sequence"] + 1
                assert stop["prediction_available"] is True
                assert stop["prediction_source"] == "RANDOM_FOREST_ML"
                assert 0 <= stop["expected_occupancy"] <= 60
                assert stop["available_seats"] == 60 - stop["expected_occupancy"]
                assert stop["crowd_status"] in {"Low", "Moderate", "High", "Full"}

            if i in (1, 5, 10, 20):
                nxt = upcoming[0]
                print(
                    f"BUS_OK: {bus_id} trip={data['trip_id']} @ #{c_seq} {data['current_stop_name']} "
                    f"(sim={data['current_occupancy']}/60) -> next #{nxt['stop_sequence']} {nxt['stop_name']} "
                    f"expected={nxt['expected_occupancy']}/60 ({nxt['occupancy_pct']}%, {nxt['crowd_status']}, "
                    f"{nxt['available_seats']} seats free) | remaining={len(upcoming)}"
                )

        # 2. Verify refresh when simulated stop position changes
        r10 = client.get("/api/buses/KA-BUS-001/upcoming-stops", params={"current_stop_seq": 10}).json()
        r35 = client.get("/api/buses/KA-BUS-001/upcoming-stops", params={"current_stop_seq": 35}).json()
        r50 = client.get("/api/buses/KA-BUS-001/upcoming-stops", params={"current_stop_seq": 50}).json()
        assert len(r10["upcoming_stops"]) == 40
        assert len(r35["upcoming_stops"]) == 15
        assert r50["predictions_available"] is False
        assert len(r50["upcoming_stops"]) == 0

        # 3. Verify unknown bus returns clean unavailable state
        unk = client.get("/api/buses/KA-BUS-999/upcoming-stops").json()
        assert unk["predictions_available"] is False
        assert "Prediction not available" in unk["message"]

        # 4. Verify authenticated /api/predictions/{bus_id}/{stop_id} endpoint
        email = f"pred_tester_{int(time.time() * 1000)}@movesync.test"
        reg = client.post(
            "/api/auth/register",
            json={"email": email, "password": "Password123!", "display_name": "Pred Tester"},
        )
        assert reg.status_code == 201, reg.text
        tok = client.post(
            "/api/auth/login",
            json={"email": email, "password": "Password123!"},
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {tok}"}

        pred_r = client.get("/api/predictions/KA-BUS-003/S08", headers=headers)
        assert pred_r.status_code == 200, pred_r.text
        pred_data = pred_r.json()
        assert pred_data["bus_id"] == "KA-BUS-003"
        assert pred_data["predictions_available"] is True
        assert len(pred_data["lookahead_forecasts"]) > 0
        print(
            f"PRED_ENDPOINT_OK: KA-BUS-003 trip={pred_data['trip_id']} "
            f"forecasts={len(pred_data['lookahead_forecasts'])} "
            f"first={pred_data['lookahead_forecasts'][0]['target_stop_name']} "
            f"pred={pred_data['lookahead_forecasts'][0]['predicted_occupancy_rounded']}/60"
        )


if __name__ == "__main__":
    test_predictions_and_upcoming_stops_for_all_20_buses()
    print("ALL_PREDICTION_AND_UPCOMING_TESTS_PASSED")
