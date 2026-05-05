import requests
import sys

def check_health(url, name):
    try:
        resp = requests.get(url, timeout=5)
        if resp.ok:
            print(f"✅ {name} is UP ({url})")
            return True
        else:
            print(f"❌ {name} returned error {resp.status_code} ({url})")
            return False
    except Exception as e:
        print(f"❌ {name} is DOWN: {str(e)} ({url})")
        return False

ui_ok = check_health("http://localhost:3000", "Frontend (UI)")
api_ok = check_health("http://localhost:8000/health", "Backend (API)")

if ui_ok and api_ok:
    print("\n🚀 System is fully operational.")
    sys.exit(0)
else:
    print("\n⚠️ System is NOT fully operational.")
    sys.exit(1)
