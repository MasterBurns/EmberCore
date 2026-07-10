import os, sys, threading, time
import urllib.request

os.environ["TEST_MODE"] = "1"
sys.path.append(os.path.abspath("backend"))

from backend.main import app, BASE_DIR
import uvicorn

print(f"DEBUG: BASE_DIR is {BASE_DIR}")
static_dir = os.path.join(BASE_DIR, "static")
print(f"DEBUG: static_dir is {static_dir}")
print(f"DEBUG: static_dir exists? {os.path.exists(static_dir)}")
if os.path.exists(static_dir):
    print(f"DEBUG: index.html exists? {os.path.exists(os.path.join(static_dir, 'index.html'))}")

def run_server():
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")

threading.Thread(target=run_server, daemon=True).start()
time.sleep(3)

try:
    r = urllib.request.urlopen("http://127.0.0.1:8000/")
    print(f"GET / -> Status: {r.getcode()}")
    if r.getcode() != 200:
        print(f"Response: {r.read().decode('utf-8')}")
except Exception as e:
    print(f"Request failed: {e}")
