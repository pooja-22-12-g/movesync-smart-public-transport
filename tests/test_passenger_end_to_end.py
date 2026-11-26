import os
import time
from fastapi.testclient import TestClient

os.environ.setdefault("ENV", "development")

from sync.main_api import app


def test_passenger_end_to_end_flows():
    with TestClient(app) as client:
        # 1. Single common 50-stop route
        routes_r = client.get("/api/routes")
        assert routes_r.status_code == 200
        routes_data = routes_r.json()
        assert routes_data["count"] == 1
        assert routes_data["routes"][0]["route_id"] == "KR_MARKET_ANEKAL_VIA_ECITY"
        assert routes_data["routes"][0]["total_stops"] == 50

        # 2. Available: all 20 buses on the common route
        buses_r = client.get("/api/buses")
        assert buses_r.status_code == 200
        buses_data = buses_r.json()
        assert buses_data["count"] == 20
        for b in buses_data["buses"]:
            assert b["current_route_id"] == "KR_MARKET_ANEKAL_VIA_ECITY"
            assert b["capacity"] == 60
            assert b["last_stop_name"]
            assert b["next_stop_name"]

        # 3. Home/Nearby stop search (50 stops + partial/case-insensitive)
        all_stops = client.get("/api/stops/search?q=").json()
        assert all_stops["count"] == 50
        for q in ["kr market", "MADIWALA", "electronic city"]:
            sr = client.get("/api/stops/search", params={"q": q}).json()
            assert sr["count"] >= 1, f"Missing stop for {q}"

        # 4. Stop details -> buses serving stop
        for sid in ["S01", "S16", "S24"]:
            sd = client.get(f"/api/stops/{sid}/buses")
            assert sd.status_code == 200, sd.text
            sdata = sd.json()
            assert sdata["found"] is True
            assert sdata["count"] == 20

        # 5. Explore journeys (all 20 buses eligible, full intermediate stops, segment-specific route_name)
        expected_journeys = [
            ("KR Market", "Anekal", 48, 50),
            ("Kudlu Gate", "Anekal", 29, 31),
            ("Madiwala", "Electronic City", 7, 9),
            ("Electronic City", "Anekal", 25, 27),
            ("Chandapura", "Anekal", 17, 19),
            ("Bommasandra", "Marsur Gate", 8, 10),
            ("Kudlu Gate", "Chandapura", 11, 13),
        ]
        for src, dst, exp_inter, exp_total in expected_journeys:
            jr = client.get("/api/journeys/search", params={"source": src, "destination": dst})
            assert jr.status_code == 200, jr.text
            jd = jr.json()
            assert jd["valid"] is True
            assert jd["count"] == 20, f"{src}->{dst}: expected 20, got {jd['count']}"
            assert len(jd["intermediate_stops"]) == exp_inter
            assert jd["journeys"][0]["total_stops"] == exp_total
            assert jd["journeys"][0]["boarding_stop"] in jd["journeys"][0]["route_name"]
            assert jd["journeys"][0]["destination_stop"] in jd["journeys"][0]["route_name"]
            if src != "KR Market":
                assert "KR Market" not in jd["journeys"][0]["route_name"]
            print(f"E2E_JOURNEY_OK: {src} -> {dst} | buses={jd['count']} | total_stops={exp_total} | route={jd['journeys'][0]['route_name']}")

        # Reverse journey rejected
        rev = client.get("/api/journeys/search", params={"source": "Anekal", "destination": "KR Market"}).json()
        assert rev["valid"] is False

        # 6. Register -> Login -> Save segment-specific Trip (Kudlu Gate -> Anekal on KA-BUS-007) -> My Trips -> Simulated Restart
        kudlu_j = client.get("/api/journeys/search", params={"source": "Kudlu Gate", "destination": "Anekal"}).json()["journeys"]
        sel_j = next(j for j in kudlu_j if j["bus_id"] == "KA-BUS-007")

        email = f"e2e_pass_{int(time.time() * 1000)}@movesync.test"
        pw = "Password123!"
        reg = client.post("/api/auth/register", json={"email": email, "password": pw, "display_name": "E2E Passenger"})
        assert reg.status_code == 201, reg.text
        tok = client.post("/api/auth/login", json={"email": email, "password": pw}).json()["access_token"]
        headers = {"Authorization": f"Bearer {tok}"}

        save_r = client.post(
            "/api/trips/save",
            headers=headers,
            json={
                "source_stop": sel_j["boarding_stop"],
                "destination_stop": sel_j["destination_stop"],
                "source_stop_id": sel_j["boarding_stop_id"],
                "destination_stop_id": sel_j["destination_stop_id"],
                "bus_id": sel_j["bus_id"],
                "trip_id": str(sel_j["trip_id"]),
                "boarding_time": sel_j["boarding_time"],
                "destination_time": sel_j["destination_time"],
                "intermediate_stops": sel_j["intermediate_stops"],
                "total_stops": sel_j["total_stops"],
            },
        )
        assert save_r.status_code == 200, save_r.text

        saved_r = client.get("/api/trips/saved", headers=headers)
        assert saved_r.status_code == 200
        assert saved_r.json()["count"] == 1
        st = saved_r.json()["saved_trips"][0]
        assert st["selected_bus_id"] == "KA-BUS-007"
        assert st["source_stop"] == "Kudlu Gate"
        assert st["destination_stop"] == "Anekal"
        assert len(st["matching_buses"]) == 20

    # Simulate app restart with fresh TestClient + fresh login
    with TestClient(app) as client2:
        tok2 = client2.post("/api/auth/login", json={"email": email, "password": pw}).json()["access_token"]
        saved2 = client2.get("/api/trips/saved", headers={"Authorization": f"Bearer {tok2}"})
        assert saved2.status_code == 200
        assert saved2.json()["count"] == 1
        st2 = saved2.json()["saved_trips"][0]
        assert st2["source_stop"] == "Kudlu Gate"
        assert st2["destination_stop"] == "Anekal"
        assert st2["selected_bus_id"] == "KA-BUS-007"
        assert st2["selected_journey"]["boarding_stop"] == "Kudlu Gate"
        assert st2["selected_journey"]["destination_stop"] == "Anekal"
        print("E2E_SAVED_TRIPS_RESTART_OK")


if __name__ == "__main__":
    test_passenger_end_to_end_flows()
    print("ALL_PASSENGER_E2E_TESTS_PASSED")
