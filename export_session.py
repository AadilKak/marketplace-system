"""
After running save_session.py, run this to get the value to paste into Render.

Usage:
    python export_session.py
"""
import base64, json, sys, os

SESSION_FILE = "fb_session.json"

if not os.path.exists(SESSION_FILE):
    print("ERROR: fb_session.json not found. Run `python save_session.py` first.")
    sys.exit(1)

with open(SESSION_FILE, "rb") as f:
    encoded = base64.b64encode(f.read()).decode()

print("\nCopy this value and set it as FB_SESSION on Render:\n")
print(encoded)
print("\nIn Render dashboard: Environment → Add Environment Variable")
print("  Key:   FB_SESSION")
print("  Value: (paste the above)")
