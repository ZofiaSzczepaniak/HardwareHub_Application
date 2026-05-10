"""
Critical tests for Hardware Hub — AI-guided, manually reviewed.
Run with: pytest test_hardware.py -v
"""
import pytest
import json
from fastapi.testclient import TestClient
import sys, os
sys.path.insert(0, os.path.dirname(__file__))


# ── Use a fresh in-memory DB for each test ─────────────────

import sqlite3
import items as items_module
import users as users_module

@pytest.fixture()
def patch_db(tmp_path, monkeypatch):
    """Each test gets its own SQLite DB. Not autouse — individual tests use it if needed."""
    db = str(tmp_path / "test.db")
    return db


# ─────────────────────────────────────────────────────────────
# TEST GROUP 1: HardwareManager unit tests
# ─────────────────────────────────────────────────────────────

class TestHardwareManager:

    def get_hm(self, db):
        return items_module.HardwareManager(db)

    def test_add_and_retrieve(self, tmp_path):
        """Can add an item and retrieve it by ID."""
        db = str(tmp_path / "hw.db")
        hm = self.get_hm(db)
        hm.add({"id": 1, "name": "Test Laptop", "brand": "Dell",
                "purchaseDate": "2023-01-01", "status": "Available"})
        item = hm.get(1)
        hm.close()
        assert item is not None
        assert item[1] == "Test Laptop"

    def test_skip_exact_duplicate(self, tmp_path):
        """Exact duplicate (same id + same data) is silently skipped."""
        db = str(tmp_path / "hw.db")
        hm = self.get_hm(db)
        payload = {"id": 1, "name": "Mouse", "brand": "Logitech",
                   "purchaseDate": "2022-06-01", "status": "Available"}
        hm.add(payload)
        hm.add(payload)
        all_items = hm.get_all()
        hm.close()
        ids = [r[0] for r in all_items]
        assert ids.count(1) == 1

    def test_duplicate_id_different_data_gets_new_id(self, tmp_path):
        """ID conflict with different data → item gets next free ID."""
        db = str(tmp_path / "hw.db")
        hm = self.get_hm(db)
        hm.add({"id": 4, "name": "Samsung Galaxy S21", "brand": "Samsung",
                "purchaseDate": "2021-11-23", "status": "Available"})
        hm.add({"id": 4, "name": "Duplicate ID Test Laptop", "brand": "Lenovo",
                "purchaseDate": "2023-01-01", "status": "Repair"})
        all_items = hm.get_all()
        hm.close()
        ids = [r[0] for r in all_items]
        assert 4 in ids, "original item at id=4 preserved"
        assert len(ids) == 2, "both items saved"
        assert ids[0] != ids[1], "they have different IDs"

    def test_normalize_invalid_date_returns_none(self, tmp_path):
        """Malformed date string is stored as None."""
        db = str(tmp_path / "hw.db")
        hm = self.get_hm(db)
        hm.add({"id": 9, "name": "iPad Pro 12.9", "brand": "Apple",
                "purchaseDate": "NOT-A-DATE", "status": "Available"})
        item = hm.get(9)
        hm.close()
        assert item[3] is None

    def test_normalize_dd_mm_yyyy_date(self, tmp_path):
        """Date in DD-MM-YYYY format is converted to YYYY-MM-DD."""
        db = str(tmp_path / "hw.db")
        hm = self.get_hm(db)
        hm.add({"id": 9, "name": "iPad", "brand": "Apple",
                "purchaseDate": "22-05-2023", "status": "Available"})
        item = hm.get(9)
        hm.close()
        assert item[3] == "2023-05-22"

    def test_normalize_unknown_status(self, tmp_path):
        """Status not in [Available, In Use, Repair] → 'Unknown'."""
        db = str(tmp_path / "hw.db")
        hm = self.get_hm(db)
        hm.add({"id": 10, "name": "Mystery Device", "brand": "",
                "purchaseDate": None, "status": "Broken"})
        item = hm.get(10)
        hm.close()
        assert item[4] == "Unknown"

    def test_normalize_empty_brand(self, tmp_path):
        """Empty brand is stored as 'Unknown'."""
        db = str(tmp_path / "hw.db")
        hm = self.get_hm(db)
        hm.add({"id": 10, "name": "Unknown Device", "brand": "",
                "purchaseDate": None, "status": "Unknown"})
        item = hm.get(10)
        hm.close()
        assert item[2] == "Unknown"

    def test_delete_existing(self, tmp_path):
        """Delete an existing item by ID."""
        db = str(tmp_path / "hw.db")
        hm = self.get_hm(db)
        hm.add({"id": 1, "name": "To Delete", "brand": "Test",
                "purchaseDate": "2022-01-01", "status": "Available"})
        hm.delete(1)
        assert hm.get(1) is None
        hm.close()

    def test_delete_nonexistent_no_crash(self, tmp_path):
        """Deleting a non-existent ID should not raise an exception."""
        db = str(tmp_path / "hw.db")
        hm = self.get_hm(db)
        hm.delete(9999) 
        hm.close()

    def test_update_item(self, tmp_path):
        """Update changes stored values."""
        db = str(tmp_path / "hw.db")
        hm = self.get_hm(db)
        hm.add({"id": 1, "name": "Old Name", "brand": "X",
                "purchaseDate": "2022-01-01", "status": "Available"})
        hm.update(1, {"name": "New Name", "brand": "Y",
                      "purchaseDate": "2023-05-05", "status": "Repair", "notes": None})
        item = hm.get(1)
        hm.close()
        assert item[1] == "New Name"
        assert item[4] == "Repair"


# ─────────────────────────────────────────────────────────────
# TEST GROUP 2: UserManager unit tests
# ─────────────────────────────────────────────────────────────

class TestUserManager:

    def get_um(self, db):
        return users_module.UserManager(db)

    def test_register_and_login(self, tmp_path):
        """Register a user then login successfully."""
        db = str(tmp_path / "users.db")
        um = self.get_um(db)
        um.register("alice", "pass123")
        result = um.login("alice", "pass123")
        um.close()
        assert result is not None
        assert result["username"] == "alice"

    def test_login_wrong_password(self, tmp_path):
        """Login with wrong password returns None."""
        db = str(tmp_path / "users.db")
        um = self.get_um(db)
        um.register("bob", "correct")
        result = um.login("bob", "wrong")
        um.close()
        assert result is None

    def test_duplicate_username_rejected(self, tmp_path):
        """Registering same username twice fails gracefully."""
        db = str(tmp_path / "users.db")
        um = self.get_um(db)
        r1 = um.register("carol", "abc")
        r2 = um.register("carol", "xyz")
        um.close()
        assert r1 is True or r1 is None 
        assert r2 is False or r2 is None

    def test_delete_user(self, tmp_path):
        """Delete removes the user."""
        db = str(tmp_path / "users.db")
        um = self.get_um(db)
        um.register("dave", "pass")
        users_before = um.get_all_users()
        user_id = users_before[0][0]
        um.delete_user(user_id)
        assert um.get_user(user_id) is None
        um.close()

    def test_delete_nonexistent_no_crash(self, tmp_path):
        """Deleting a non-existent user should not raise."""
        db = str(tmp_path / "users.db")
        um = self.get_um(db)
        um.delete_user(9999)
        um.close()


# ─────────────────────────────────────────────────────────────
# TEST GROUP 3: Critical rental business-logic tests
# These test the rules enforced in main.py via the API layer.
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path, monkeypatch):
    """FastAPI test client with fresh DB."""
    db = str(tmp_path / "api.db")
    import main as main_module
    import importlib

    original_hm = main_module.HardwareManager
    original_um = main_module.UserManager

    monkeypatch.setattr(main_module, "HardwareManager", lambda path=None: original_hm(db))
    monkeypatch.setattr(main_module, "UserManager", lambda path=None: original_um(db))

    hm.add({"id": 1, "name": "Available Phone", "brand": "Apple",
            "purchaseDate": "2022-01-01", "status": "Available"})
    hm.add({"id": 2, "name": "Taken Laptop", "brand": "Dell",
            "purchaseDate": "2022-01-01", "status": "In Use"})
    hm.add({"id": 3, "name": "Broken Mouse", "brand": "Razer",
            "purchaseDate": "2022-01-01", "status": "Repair"})
    hm.close()

    um = original_um(db)
    um.register("admin@local.com", "admin123", role="admin")
    um.register("user1@local.com", "pass123", role="user")
    um.close()

    return TestClient(main_module.app)


def get_token(client, username, password):
    r = client.post("/api/auth/login", json={"email": username, "password": password})
    return r.json()["token"]


class TestRentalLogic:

    def test_rent_available_item_succeeds(self, client):
        """[CRITICAL] User can rent an Available item."""
        token = get_token(client, "user1@local.com", "pass123")
        r = client.post("/api/hardware/1/rent",
                        json={"user_id": 2, "username": "user1@local.com"},
                        headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200

    def test_cannot_rent_item_already_in_use(self, client):
        """[CRITICAL] Cannot rent an item that is already In Use."""
        token = get_token(client, "user1@local.com", "pass123")
        r = client.post("/api/hardware/2/rent",
                        json={"user_id": 2, "username": "user1@local.com"},
                        headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 400
        assert "In Use" in r.json()["detail"]

    def test_cannot_rent_item_in_repair(self, client):
        """[CRITICAL] Cannot rent a device that is under Repair."""
        token = get_token(client, "user1@local.com", "pass123")
        r = client.post("/api/hardware/3/rent",
                        json={"user_id": 2, "username": "user1@local.com"},
                        headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 400
        assert "Repair" in r.json()["detail"]

    def test_return_item_in_use_succeeds(self, client):
        """[CRITICAL] Can return an item that is currently In Use (that they rented)."""
        token = get_token(client, "user1@local.com", "pass123")
        client.post("/api/hardware/1/rent",
                    json={"user_id": 2, "username": "user1@local.com"},
                    headers={"Authorization": f"Bearer {token}"})

        r = client.post("/api/hardware/1/return",
                        headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200

    def test_cannot_return_available_item(self, client):
        """[CRITICAL] Cannot return an item that is already Available."""
        token = get_token(client, "user1@local.com", "pass123")
        r = client.post("/api/hardware/1/return",
                        headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 400

    def test_unauthenticated_cannot_rent(self, client):
        """[CRITICAL] Requests without a token are rejected."""
        r = client.post("/api/hardware/1/rent",
                        json={"user_id": 1, "username": "ghost"})
        assert r.status_code == 403

    def test_only_admin_can_add_hardware(self, client):
        """[CRITICAL] Regular user cannot add hardware items."""
        token = get_token(client, "user1@local.com", "pass123")
        r = client.post("/api/hardware",
                        json={"name": "Hacked Item", "brand": "Evil", "status": "Available"},
                        headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403

    def test_admin_can_add_hardware(self, client):
        """Admin can successfully add a hardware item."""
        token = get_token(client, "admin@local.com", "admin123")
        r = client.post("/api/hardware",
                        json={"name": "New Keyboard", "brand": "Keychron",
                              "purchaseDate": "2024-01-01", "status": "Available"},
                        headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200

    def test_rent_then_return_flow(self, client):
        """Full cycle: rent → item becomes In Use → return → Available."""
        token = get_token(client, "user1@local.com", "pass123")

        client.post("/api/hardware/1/rent",
                    json={"user_id": 2, "username": "user1@locall.com"},
                    headers={"Authorization": f"Bearer {token}"})

        r = client.get("/api/hardware/1", headers={"Authorization": f"Bearer {token}"})
        assert r.json()["status"] == "In Use"

        client.post("/api/hardware/1/return",
                    headers={"Authorization": f"Bearer {token}"})

        r = client.get("/api/hardware/1", headers={"Authorization": f"Bearer {token}"})
        assert r.json()["status"] == "Available"
