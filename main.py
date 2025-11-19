import os
import base64
import tempfile
import subprocess
from flask import Flask, request, jsonify
from moviepy.editor import VideoFileClip
from openai import OpenAI

app = Flask(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=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)


# ---------------------------------------------
# Helper: download video via yt-dlp
# ---------------------------------------------
def download_video(url):
    temp_dir = tempfile.mkdtemp()
    output_path = os.path.join(temp_dir, "video.mp4")

    cmd = [
        "yt-dlp",
        "-f", "mp4",
        "-o", output_path,
        url
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise Exception(f"Download failed: {result.stderr}")

    return output_path


# ---------------------------------------------
# Helper: convert video → frames
# ---------------------------------------------
def extract_keyframes(video_path, max_frames=8):
    clip = VideoFileClip(video_path)
    duration = clip.duration

    frames = []
    step = duration / max_frames

    for i in range(max_frames):
        t = i * step
        frame = clip.get_frame(t)
        temp_img = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        from PIL import Image
        im = Image.fromarray(frame)
        im.save(temp_img.name, "JPEG")
        frames.append(temp_img.name)

    clip.close()
    return frames


# ---------------------------------------------
# Helper: send frames + optional caption to OpenAI
# ---------------------------------------------
def analyze_frames(frames, caption=None):
    content = [
        {
            "type": "text",
            "text": """
Analyze the cooking video frames.
Extract a complete RECIPE in JSON ONLY with:
title, description, ingredients[], steps[], calories, servings, totalMinutes.
"""
        }
    ]

    # Add frames
    for f in frames:
        with open(f, "rb") as fp:
            b64 = base64.b64encode(fp.read()).decode()
            content.append({
                "type": "input_image",
                "image_url": f"data:image/jpeg;base64,{b64}"
            })

    if caption:
        content.append({"type": "text", "text": f"Additional context:\n{caption}"})


    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "user", "content": content}
        ]
    )

    raw = resp.choices[0].message["content"].strip()

    # Try to extract JSON
    import json
    try:
        if raw.startswith("```"):
            raw = raw[raw.index("{") : raw.rindex("}") + 1]
        return json.loads(raw)
    except:
        return {"error": "Could not parse JSON", "raw": raw}


# ---------------------------------------------
# API ROUTE: /extract
# ---------------------------------------------
@app.post("/extract")
def extract_route():
    data = request.json
    url = data.get("url")
    caption = data.get("caption")

    if not url:
        return jsonify({"error": "Missing URL"}), 400

    try:
        # STEP 1 — Download
        video_path = download_video(url)

        # STEP 2 — Extract frames
        frames = extract_keyframes(video_path)

        # STEP 3 — Send to OpenAI
        recipe = analyze_frames(frames, caption)

        return jsonify({"success": True, "recipe": recipe})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/")
def home():
    return {"status": "ok", "message": "video recipe backend running"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
