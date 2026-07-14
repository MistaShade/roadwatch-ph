"""Flask API serving the trained road damage classifier to the web UI."""

from __future__ import annotations

import tempfile
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS

from predict import MODEL_PATH, META_PATH, predict_image

app = Flask(__name__)
CORS(app)


@app.get("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "model_loaded": MODEL_PATH.exists(),
        "metadata_loaded": META_PATH.exists(),
    })


@app.post("/api/classify")
def classify():
    if "image" not in request.files:
        return jsonify({"error": "Missing image file"}), 400

    upload = request.files["image"]
    if not upload.filename:
        return jsonify({"error": "Empty upload"}), 400

    suffix = Path(upload.filename).suffix or ".jpg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        upload.save(tmp.name)
        tmp_path = tmp.name

    try:
        result = predict_image(tmp_path)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return jsonify(result)


if __name__ == "__main__":
    print("RoadWatch PH prediction API on http://localhost:7860")
    print("Endpoints: GET /api/health  POST /api/classify")
    app.run(host="0.0.0.0", port=7860, debug=False)
