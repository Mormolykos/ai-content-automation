"""
api.py — a thin FastAPI wrapper around the LangGraph pipeline.

Why this exists:
  n8n runs inside Docker; this pipeline + its venv run on the HOST. A container
  can't reach into the host and run host Python. So we expose the pipeline as a
  tiny HTTP service. n8n (in Docker) triggers it at:
      POST http://host.docker.internal:8090/run
  and the host service runs the graph and returns the generated pin package.

Run:  python langchain/api.py
"""

import sys
from pathlib import Path

# this folder holds pin_graph + generate_pin
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pin_graph
from fastapi import FastAPI
import uvicorn

app = FastAPI(title="BedVibe Pin Automation", version="1.0")
_graph = pin_graph.build_graph()   # compile the LangGraph once at startup (no API call here)


@app.get("/health")
def health():
    return {"status": "ok", "service": "bedvibe-pin-automation"}


@app.post("/run")
def run():
    """Run the pipeline once: pick -> caption -> validate (retry) -> save."""
    final = _graph.invoke({})
    return {
        "ok": True,
        "folder": final.get("folder"),
        "valid": final.get("valid"),
        "attempts": final.get("attempts"),
        "link": final.get("link"),
        "image_path": final.get("image_path"),
        "metadata": final.get("metadata"),
    }


if __name__ == "__main__":
    print("BedVibe Pin Automation API -> http://0.0.0.0:8090  (docs at /docs)")
    uvicorn.run(app, host="0.0.0.0", port=8090)
