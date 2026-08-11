"""API tests for direct, account-scoped memory controls."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from apps.backend.config import get_settings
from src.linger.services.memory import AccountContext, MemoryPolicyService

get_settings.cache_clear()
with patch.dict(
    os.environ,
    {
        "LINGER_MODEL": "google:gemini-2.5-flash",
        "GOOGLE_API_KEY": "placeholder",
    },
):
    from apps.backend import main


class MemoryApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.service = MemoryPolicyService(
            Path(self.temporary_directory.name) / "memories"
        )
        main.app.dependency_overrides[main.get_memory_service] = lambda: self.service
        main.app.dependency_overrides[main.get_memory_context] = lambda: AccountContext(
            "api-test-account"
        )
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        self.client.close()
        main.app.dependency_overrides.clear()
        self.temporary_directory.cleanup()

    def test_complete_direct_control_flow(self) -> None:
        initial = self.client.get("/api/memories")
        self.assertEqual(200, initial.status_code)
        self.assertEqual(
            {"capture_enabled": False, "memories": []},
            initial.json(),
        )

        preference = self.client.put(
            "/api/memory-capture-preference",
            json={"enabled": True},
        )
        self.assertEqual(200, preference.status_code)
        self.assertEqual({"enabled": True}, preference.json())

        save = self.client.post(
            "/api/memories",
            json={
                "text": "The blue door made the scene feel hopeful.",
                "operation_id": str(uuid4()),
            },
        )
        self.assertEqual(201, save.status_code)
        saved = save.json()["memory"]
        self.assertTrue(save.json()["created"])
        self.assertEqual("explicit", saved["capture_type"])
        self.assertNotIn("account_id", saved)
        self.assertNotIn("account_key", saved)

        correction = self.client.put(
            f"/api/memories/{saved['memory_id']}",
            json={
                "text": "The blue door made the scene feel quietly hopeful.",
                "operation_id": str(uuid4()),
            },
        )
        self.assertEqual(201, correction.status_code)
        corrected = correction.json()["memory"]
        self.assertEqual("correction", corrected["capture_type"])
        self.assertNotEqual(saved["memory_id"], corrected["memory_id"])

        current = self.client.get("/api/memories").json()
        self.assertTrue(current["capture_enabled"])
        self.assertEqual([corrected], current["memories"])

        deleted = self.client.delete(f"/api/memories/{corrected['memory_id']}")
        self.assertEqual(204, deleted.status_code)
        self.assertEqual([], self.client.get("/api/memories").json()["memories"])

    def test_save_is_idempotent_and_conflicting_retry_fails(self) -> None:
        operation_id = str(uuid4())
        payload = {"text": "Keep this once.", "operation_id": operation_id}

        first = self.client.post("/api/memories", json=payload)
        retry = self.client.post("/api/memories", json=payload)
        conflict = self.client.post(
            "/api/memories",
            json={"text": "Different words.", "operation_id": operation_id},
        )

        self.assertTrue(first.json()["created"])
        self.assertFalse(retry.json()["created"])
        self.assertEqual(first.json()["memory"], retry.json()["memory"])
        self.assertEqual(409, conflict.status_code)
        self.assertEqual(1, len(self.client.get("/api/memories").json()["memories"]))

    def test_account_scope_is_rejected(self) -> None:
        response = self.client.post(
            "/api/memories",
            json={
                "text": "Try to change account scope.",
                "operation_id": str(uuid4()),
                "account_id": "someone-else",
            },
        )

        self.assertEqual(422, response.status_code)
        self.assertEqual([], self.service.list_active(AccountContext("api-test-account")))

    def test_missing_memory_is_not_disclosed(self) -> None:
        correction = self.client.put(
            "/api/memories/not-owned",
            json={"text": "No access", "operation_id": str(uuid4())},
        )
        deletion = self.client.delete("/api/memories/not-owned")

        self.assertEqual(404, correction.status_code)
        self.assertEqual("Memory not found.", correction.json()["detail"])
        self.assertEqual(404, deletion.status_code)


if __name__ == "__main__":
    unittest.main()
