import os
import base64
import tempfile
import subprocess
import json
from flask import Flask, request, jsonify
from openai import OpenAI

app = Flask(__name__)

# -------- OPENAI --------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

# ================================================
#  DOWNLOAD VIDEO (yt-dlp)
# ================================================
def download_video(url: str) -> str:
    temp_dir = tempfile.mkdtemp()
    out = os.path.join(temp_dir, "video.mp4")

    cmd = ["yt-dlp", "-f", "mp4", "-o", out, url]
    r = subprocess.run(cmd, capture_output=True, text=True)

    if r.returncode != 0:
        raise Exception("Download failed: " + r.stderr)

    return out


# ================================================
#  EXTRACT FRAMES (ffmpeg – υπάρχει στο Railway)
# ================================================
def extract_frames(video_path: str, num_frames: int = 6):
    tmp = tempfile.mkdtemp()
    pattern = os.path.join(tmp, "f_%03d.jpg")

    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", f"fps={num_frames}",   # π.χ. 6 frames από όλο το βίντεο
        pattern,
        "-hide_banner", "-loglevel", "error"
    ]

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise Exception("ffmpeg failed: " + r.stderr)

    files = sorted([os.path.join(tmp, f) for f in os.listdir(tmp)])
    return files


# ================================================
#  SEND TO OPENAI
# ================================================
def analyze_frames(frames, caption=None):
    content = [
        {
            "type": "text",
            "text": """
Analyze ALL these cooking video frames.
Extract a REAL recipe.
Return ONLY pure JSON with:
title, description, ingredients[], steps[], calories, servings, totalMinutes.
"""
        }
    ]

    # embed frames
    for f in frames:
        with open(f, "rb") as fp:
            b64 = base64.b64encode(fp.read()).decode()
            content.append({
                "type": "input_image",
                "image_url": f"data:image/jpeg;base64,{b64}"
            })

    if caption:
        content.append({"type": "text", "text": caption})

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": content}]
    )

    raw = resp.choices[0].message["content"].strip()

    # --- parse JSON ---
    try:
        if raw.startswith("```"):
            raw = raw[raw.index("{"): raw.rindex("}") + 1]
        return json.loads(raw)
    except:
        return {"error": "JSON parse fail", "raw": raw}


# ================================================
#  API ROUTE
# ================================================
@app.post("/extract")
def extract_route():
    body = request.json
    url = body.get("url")
    caption = body.get("caption")

    if not url:
        return jsonify({"error": "Missing url"}), 400

    try:
        print("Downloading video...")
        video = download_video(url)

        print("Extracting frames…")
        frames = extract_frames(video)

        print("Sending to OpenAI…")
        recipe = analyze_frames(frames, caption)

        return jsonify({"success": True, "recipe": recipe})

except Exception as e:
    import traceback
    traceback.print_exc()   # ⭐ ΤΥΠΩΝΕΙ ΤΟ ERROR ΣΤΟ DEPLOY LOGS
    print("🔥 FULL ERROR:", e)
    return jsonify({"error": str(e)}), 500



@app.get("/")
def home():
    return {"status": "ok", "service": "video-recipe-backend"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
