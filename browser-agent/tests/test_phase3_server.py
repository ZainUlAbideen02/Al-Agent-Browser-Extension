import sys
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from server import app

class TestServerEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_root_endpoint(self):
        """Test GET / returns server status and links."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("service", data)
        self.assertEqual(data["dashboard"], "/dashboard/")

    def test_start_and_status_endpoints(self):
        """Test POST /api/agent/start and GET /api/agent/status/{task_id}."""
        payload = {
            "url": "https://the-internet.herokuapp.com/login",
            "goal": "Test goal launch",
            "max_steps": 2,
            "width": 1280,
            "height": 800,
            "mode": "dom"
        }
        response = self.client.post("/api/agent/start", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("task_id", data)
        self.assertEqual(data["status"], "started")

        task_id = data["task_id"]
        status_resp = self.client.get(f"/api/agent/status/{task_id}")
        self.assertEqual(status_resp.status_code, 200)
        status_data = status_resp.json()
        self.assertEqual(status_data["task_id"], task_id)

    def test_stop_endpoint(self):
        """Test POST /api/agent/stop/{task_id} cancellation."""
        payload = {
            "url": "https://the-internet.herokuapp.com/login",
            "goal": "Test goal cancellation",
            "max_steps": 2
        }
        start_resp = self.client.post("/api/agent/start", json=payload)
        task_id = start_resp.json()["task_id"]

        stop_resp = self.client.post(f"/api/agent/stop/{task_id}")
        self.assertEqual(stop_resp.status_code, 200)
        self.assertEqual(stop_resp.json()["status"], "cancelled")

if __name__ == "__main__":
    unittest.main()
