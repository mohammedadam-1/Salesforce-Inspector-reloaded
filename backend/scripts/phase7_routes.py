import json
import sys

d = json.load(sys.stdin)
for p in d["paths"]:
    if "salesforce" in p or "sync" in p or "auth" in p:
        print(p)
