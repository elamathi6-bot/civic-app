"""
AI issue detection.

Until you've trained a real YOLO model (see TRAINING_GUIDE.md), this file
uses a simple placeholder so the REST of your app (upload, save, admin
dashboard) can be built and tested right now.

Once you train a model, drop your weights file in this folder as
'best.pt' and this file will automatically switch to using it.
"""

import os

MODEL_PATH = os.path.join(os.path.dirname(__file__), "best.pt")
_model = None


def _load_model():
    """Lazily load YOLO only if a trained model file exists.
    This means you do NOT need ultralytics installed to run the rest
    of the app — it only gets imported when you actually have a model."""
    global _model
    if _model is not None:
        return _model
    if not os.path.exists(MODEL_PATH):
        return None
    try:
        from ultralytics import YOLO
        _model = YOLO(MODEL_PATH)
        return _model
    except ImportError:
        print("ultralytics not installed — run: pip install ultralytics")
        return None


def detect_issue(image_path: str) -> dict:
    """
    Returns: {"category": str, "confidence": float}
    """
    model = _load_model()

    if model is None:
        # PLACEHOLDER MODE — no trained model yet.
        # Lets you test the full app flow before AI is ready.
        return {"category": "pothole", "confidence": 0.0, "mode": "placeholder"}

    results = model(image_path)
    if len(results[0].boxes) == 0:
        return {"category": "needs_review", "confidence": 0.0, "mode": "yolo"}

    box = results[0].boxes[0]
    class_id = int(box.cls[0])
    confidence = float(box.conf[0])
    category = model.names[class_id]

    return {"category": category, "confidence": confidence, "mode": "yolo"}
