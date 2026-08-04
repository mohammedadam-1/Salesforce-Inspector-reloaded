import json
import sys
import uuid
from urllib.parse import parse_qs, urlparse

import httpx

BASE = "http://localhost:8000/api/v1"
EMAIL = f"phase7.{uuid.uuid4().hex[:8]}@test.local"
PASSWORD = "Phase7-Test-2026!"

c = httpx.Client(base_url=BASE, timeout=30)

r = c.post("/auth/register", json={"email": EMAIL, "password": PASSWORD, "display_name": "Phase 7 Tester"})
print("register:", r.status_code)
if r.status_code != 201 and r.status_code != 200:
    print(r.text)
    sys.exit(1)
tok = r.json()
print("got access_token:", bool(tok.get("access_token")), "org:", tok.get("organization_id"))
headers = {"Authorization": f"Bearer {tok['access_token']}"}

r = c.post("/salesforce/connect", json={"environment": "production"}, headers=headers)
print("connect:", r.status_code)
if r.status_code != 200:
    print(r.text)
    sys.exit(1)
data = r.json()
print("state:", data["state"])
print("code_verifier:", data["code_verifier"])
print("environment:", data["environment"])

u = urlparse(data["authorization_url"])
q = parse_qs(u.query)
print("authorize base:", f"{u.scheme}://{u.netloc}")
print("client_id:", q.get("client_id", [""])[0])
print("redirect_uri:", q.get("redirect_uri", [""])[0])
print("response_type:", q.get("response_type", [""])[0])
print("code_challenge:", q.get("code_challenge", [""])[0])
print("code_challenge_method:", q.get("code_challenge_method", [""])[0])
print("scope:", q.get("scope", [""])[0])
print("state_in_url:", q.get("state", [""])[0])

with open("/tmp/phase7_oauth.json", "w") as f:
    json.dump({
        "access_token": tok["access_token"],
        "refresh_token": tok.get("refresh_token"),
        "organization_id": str(tok.get("organization_id")),
        "user_id": str(tok.get("user_id")),
        "state": data["state"],
        "code_verifier": data["code_verifier"],
        "authorization_url": data["authorization_url"],
        "email": EMAIL,
    }, f)
print("saved /tmp/phase7_oauth.json")
