"""
pin_graph.py — the LangGraph orchestration layer.

It wraps the LangChain caption step in a STATEFUL GRAPH with a real retry loop:

    pick -> caption -> validate --(invalid & retries left)--> caption  (loop)
                                \--(valid OR out of retries)--> save -> END

Why LangGraph and not a plain function? Because of that loop-back edge.
A linear script can't cleanly say "if the result fails my rules, go back a step
and try again." A graph can. That conditional edge is the whole point.

Run:  python langchain/pin_graph.py
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import TypedDict, Optional, List

# Reuse the working LangChain pieces from generate_pin.py (same folder).
import generate_pin as gp   # pick_image, caption, resolve_link, load_used, save_used, OUTPUTS

from langgraph.graph import StateGraph, START, END

MAX_ATTEMPTS = 3   # how many times we'll let it regenerate a bad caption


# ---------------------------------------------------------------------------
# State — the shared object every node reads from and writes to
# ---------------------------------------------------------------------------
class PinState(TypedDict, total=False):
    image_path: str
    folder: str
    filename: str
    link: str
    metadata: Optional[dict]
    attempts: int
    valid: bool
    errors: List[str]


# ---------------------------------------------------------------------------
# Nodes — each does ONE thing and returns only the keys it changed
# ---------------------------------------------------------------------------
def pick_node(state: PinState) -> dict:
    img, _used = gp.pick_image()
    return {
        "image_path": str(img),
        "folder": img.parent.name,
        "filename": img.stem,
        "link": gp.resolve_link(img),
        "attempts": 0,
        "errors": [],
    }

def caption_node(state: PinState) -> dict:
    img = Path(state["image_path"])
    meta = gp.caption(img, state["folder"], state["filename"])
    return {"metadata": meta.model_dump(), "attempts": state["attempts"] + 1}

def validate_node(state: PinState) -> dict:
    m = state.get("metadata") or {}
    errors: List[str] = []
    title = m.get("title", "")
    desc = m.get("description", "")
    tags = m.get("tags", [])

    if "the mirelands" not in [t.lower() for t in tags]:
        errors.append("missing 'the mirelands' tag")
    if not (1 <= len(title) <= 100):
        errors.append(f"title length {len(title)} not 1-100")
    if not (100 <= len(desc) <= 350):
        errors.append(f"description length {len(desc)} not 100-350")
    if not (8 <= len(tags) <= 12):
        errors.append(f"tag count {len(tags)} not 8-12")
    if not m.get("alt_text"):
        errors.append("missing alt_text")

    valid = not errors
    print(f"[validate] attempt {state['attempts']}: "
          + ("OK" if valid else "FAIL -> " + "; ".join(errors)))
    return {"valid": valid, "errors": errors}

def save_node(state: PinState) -> dict:
    package = {
        "image_path": state["image_path"],
        "folder": state["folder"],
        "link": state["link"],
        "valid": state["valid"],
        "attempts": state["attempts"],
        "validation_errors": state["errors"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metadata": state["metadata"],
    }
    out = gp.OUTPUTS / f"pin_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(package, indent=2, ensure_ascii=False), encoding="utf-8")
    used = gp.load_used(); used.add(state["image_path"]); gp.save_used(used)
    print(f"[save] {out.name}  (valid={state['valid']}, attempts={state['attempts']})")
    return {}


# ---------------------------------------------------------------------------
# The conditional edge — the heart of why this is a GRAPH
# ---------------------------------------------------------------------------
def route_after_validate(state: PinState) -> str:
    if state["valid"]:
        return "save"
    if state["attempts"] < MAX_ATTEMPTS:
        print(f"[retry] caption failed validation -> regenerating "
              f"(attempt {state['attempts']}/{MAX_ATTEMPTS})")
        return "caption"
    print("[retry] out of attempts -> saving best effort (flagged invalid)")
    return "save"


# ---------------------------------------------------------------------------
# Build + run
# ---------------------------------------------------------------------------
def build_graph():
    g = StateGraph(PinState)
    g.add_node("pick", pick_node)
    g.add_node("caption", caption_node)
    g.add_node("validate", validate_node)
    g.add_node("save", save_node)

    g.add_edge(START, "pick")
    g.add_edge("pick", "caption")
    g.add_edge("caption", "validate")
    g.add_conditional_edges("validate", route_after_validate,
                            {"caption": "caption", "save": "save"})
    g.add_edge("save", END)
    return g.compile()


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    app = build_graph()
    final = app.invoke({})

    m = final.get("metadata") or {}
    print(f"\n[done] folder={final.get('folder')} | valid={final.get('valid')} "
          f"| attempts={final.get('attempts')} | link={final.get('link')}")
    if m:
        print(f"  title: {m.get('title')}")
        print(f"  tags : {', '.join(m.get('tags', []))}")


if __name__ == "__main__":
    main()
