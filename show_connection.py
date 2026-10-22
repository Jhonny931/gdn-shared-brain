"""Run locally on YOUR trusted computer. Prints a credential; never post its output."""
import argparse
import json
import os
from pathlib import Path

p=argparse.ArgumentParser(description="Display MCP endpoint and a scoped access token")
p.add_argument("--scope",choices=("reader","writer"),default="reader")
p.add_argument("--host",default=os.getenv("GDN_BRAIN_PUBLIC_HOST","brain.example.com"))
a=p.parse_args()
keypath=Path(os.getenv("GDN_BRAIN_TOKENS","~/.config/gdn-shared-brain/remote-tokens.json")).expanduser()
tokens=json.loads(keypath.read_text())
print("MCP URL: https://"+a.host+"/mcp")
print("Scope: "+a.scope)
print("Bearer token (keep private): "+tokens[a.scope])
