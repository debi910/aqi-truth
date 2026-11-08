"""IBM Granite via a local Ollama server (free, no API key)."""
import json, os, urllib.request
OLLAMA = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL = os.getenv("LLM_MODEL", "granite4-micro")

def generate(prompt, max_tokens=180, system=None):
    body = {"model": MODEL, "prompt": prompt, "stream": False,
            "options": {"temperature": 0, "num_predict": max_tokens}}
    if system: body["system"] = system
    req = urllib.request.Request(f"{OLLAMA}/api/generate", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=300))["response"].strip()
