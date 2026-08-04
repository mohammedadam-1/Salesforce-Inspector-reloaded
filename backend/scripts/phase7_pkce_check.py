import base64
import hashlib
import json

data = json.load(open("/tmp/phase7_oauth.json"))
digest = hashlib.sha256(data["code_verifier"].encode()).digest()
challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
print("expected challenge:", challenge)
print("url challenge:    ", data["authorization_url"].split("code_challenge=")[1].split("&")[0])
print("PKCE S256 match:  ", challenge == data["authorization_url"].split("code_challenge=")[1].split("&")[0])
