import sys
import urllib.request
import json
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_URL = "http://localhost:8000"

def test_dashboard_flow():
    print("1. Checking Server Root...")
    req = urllib.request.urlopen(f"{BASE_URL}/")
    data = json.loads(req.read().decode())
    print("   Root Service Response:", data)
    assert data["service"] is not None

    print("\n2. Checking GET /api/tasks...")
    req = urllib.request.urlopen(f"{BASE_URL}/api/tasks")
    tasks = json.loads(req.read().decode())
    print(f"   Current Saved Tasks Count: {len(tasks)}")

    print("\n3. Testing POST /api/tasks (Adding Preset)...")
    preset_data = json.dumps({
        "name": "dashboard_demo_task",
        "goal": "Log in with username tomsmith and password SuperSecretPassword!",
        "url": "https://the-internet.herokuapp.com/login",
        "mode": "visual"
    }).encode("utf-8")
    
    post_req = urllib.request.Request(
        f"{BASE_URL}/api/tasks",
        data=preset_data,
        headers={"Content-Type": "application/json"}
    )
    res = json.loads(urllib.request.urlopen(post_req).read().decode())
    print("   Created Preset Response:", res)

    print("\n4. Verifying GET /api/tasks after addition...")
    tasks_updated = json.loads(urllib.request.urlopen(f"{BASE_URL}/api/tasks").read().decode())
    print("   Saved Tasks:", tasks_updated)
    assert any(t["name"] == "dashboard_demo_task" for t in tasks_updated)

    print("\n5. Testing GET /api/history...")
    req = urllib.request.urlopen(f"{BASE_URL}/api/history")
    history = json.loads(req.read().decode())
    print(f"   History Runs Count: {len(history)}")

    print("\n[OK] All Web Dashboard REST API endpoints verified successfully!")

if __name__ == "__main__":
    test_dashboard_flow()
