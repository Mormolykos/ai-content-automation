"""
generate_pin.py
===============
Picks ONE unused image from the pinterest_queue, captions it with Gemini
(multimodal — it actually *sees* the image), writes a ready-to-post JSON
package, and marks the image as used so it never repeats.

Run:  python langchain/generate_pin.py
"""

import os
import sys
import json
import base64
import random
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent          # automation/
load_dotenv(ROOT / ".env")

QUEUE = Path(r"C:\Users\User\Downloads\pinterest_queue")  # source images
OUTPUTS = ROOT / "outputs"; OUTPUTS.mkdir(parents=True, exist_ok=True)
USED_FILE = ROOT / "used.json"                          # tracks posted images
HUB_URL = "https://tts.bedvibe.studio/the-mirelands/"   # backlink every pin uses
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp"}
MODEL = "gemini-2.5-flash"


# ---------------------------------------------------------------------------
# Output schema — forces Gemini to return clean, validated JSON
# ---------------------------------------------------------------------------
class PinMetadata(BaseModel):
    title: str = Field(..., description="Pinterest pin title, keyword-rich, max ~95 chars. Must include 'The Mirelands'.")
    description: str = Field(..., description="Pin description, 150-300 chars, keyword-rich, ends with a soft call-to-action.")
    tags: list[str] = Field(..., min_length=8, max_length=12, description="8-12 lowercase keyword tags.")
    alt_text: str = Field(..., description="Short accessibility alt-text describing what is visible.")


# ---------------------------------------------------------------------------
# 1) PICK — choose an unused image, rotating across folders for variety
# ---------------------------------------------------------------------------
def load_used() -> set:
    return set(json.loads(USED_FILE.read_text())) if USED_FILE.exists() else set()

def save_used(used: set):
    USED_FILE.write_text(json.dumps(sorted(used), indent=2), encoding="utf-8")

def pick_image():
    used = load_used()
    all_imgs = [p for p in QUEUE.rglob("*")
                if p.is_file() and p.suffix.lower() in IMG_EXT]
    unused = [p for p in all_imgs if str(p) not in used]
    if not all_imgs:
        sys.exit(f"No images found in {QUEUE}")
    if not unused:
        sys.exit("All images already used — generate more, or clear used.json")

    # rotate by folder: pick a random folder, then a random image inside it
    by_folder = {}
    for p in unused:
        by_folder.setdefault(p.parent.name, []).append(p)
    folder = random.choice(list(by_folder.keys()))
    img = random.choice(by_folder[folder])
    print(f"[pick] {len(unused)}/{len(all_imgs)} unused. Chose: {folder}/{img.name}")
    return img, used


def resolve_link(img_path: Path) -> str:
    """Per-folder landing URL: a _link.txt in the folder, else the default hub."""
    link_file = img_path.parent / "_link.txt"
    if link_file.exists():
        url = link_file.read_text(encoding="utf-8").strip()
        if url:
            return url
    return HUB_URL


# ---------------------------------------------------------------------------
# 2) CAPTION — Gemini *sees* the image + folder/filename context
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """\
You are an SEO strategist for a dark-fantasy franchise called "The Mirelands"
(a saga of ebooks, dramatized audiobooks, and a browser game).

Write Pinterest metadata for the image you are shown. Rules:
- ALWAYS include the keyword "The Mirelands" and the folder/place name in the tags.
- If "Known facts" are provided, treat them as authoritative truth and use them accurately.
- Otherwise, describe ONLY what is visible. Do NOT invent character names, place
  lore, or events you cannot see — keep it evocative but honest.
- Keywords should help the brand term "The Mirelands" and the place name rank.
- Tone: atmospheric dark fantasy. No hashtags in tags. Lowercase tags.
"""

def caption(img_path: Path, folder: str, filename: str) -> PinMetadata:
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_core.messages import HumanMessage, SystemMessage

    llm = ChatGoogleGenerativeAI(
        model=MODEL, temperature=0.7,
        google_api_key=os.getenv("GEMINI_API_KEY"),
    ).with_structured_output(PinMetadata)

    b64 = base64.b64encode(img_path.read_bytes()).decode()
    mime = "image/png" if img_path.suffix.lower() == ".png" else "image/jpeg"

    # Optional per-folder lore hint YOU write (your canon) — stops hallucination.
    ctx_file = img_path.parent / "_context.txt"
    known = ctx_file.read_text(encoding="utf-8").strip() if ctx_file.exists() else ""

    text = f"Folder/place: {folder}\nFilename: {filename}\n"
    if known:
        text += f"Known facts (authoritative — use accurately, do not contradict): {known}\n"
    text += "Write Pinterest metadata for this image from The Mirelands."

    human = HumanMessage(content=[
        {"type": "text", "text": text},
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
    ])
    return llm.invoke([SystemMessage(content=SYSTEM_PROMPT), human])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    if not os.getenv("GEMINI_API_KEY"):
        sys.exit("ERROR: GEMINI_API_KEY not set in automation/.env")

    # Optional: pass a specific image path to caption it directly (for testing).
    if len(sys.argv) > 1:
        img = Path(sys.argv[1]); used = load_used()
        print(f"[pick] forced: {img.parent.name}/{img.name}")
    else:
        img, used = pick_image()
    meta = caption(img, img.parent.name, img.stem)

    package = {
        "image_path": str(img),
        "folder": img.parent.name,
        "link": resolve_link(img),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metadata": meta.model_dump(),
    }
    out = OUTPUTS / f"pin_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(package, indent=2, ensure_ascii=False), encoding="utf-8")

    used.add(str(img))
    save_used(used)

    print(f"[saved] {out}")
    print(f"[title] {meta.title}")
    print(f"[tags ] {', '.join(meta.tags)}")


if __name__ == "__main__":
    main()
