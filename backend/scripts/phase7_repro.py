import json

import httpx

data = json.load(open("/tmp/phase7_oauth.json"))
url = data["authorization_url"]
print("URL:", url)
print()
r = httpx.get(url, follow_redirects=False, timeout=30)
print("status:", r.status_code)
print("location:", r.headers.get("location"))
print("content-type:", r.headers.get("content-type"))
body = r.text[:300]
print("body head:", body)
