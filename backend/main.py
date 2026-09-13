import os
import shutil
import tempfile
from datetime import datetime
from math import radians, cos, sin, asin, sqrt

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import bcrypt
import psycopg2.extras

from database import get_connection
from yolo_detect import detect_issue

app = FastAPI(title="Civic Issue Reporting API")

# Allow the frontend (opened as a local file / different port) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# ---------- PHOTO STORAGE (Cloudinary if configured, otherwise local disk) ----------

CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY = os.environ.get("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET")

USE_CLOUDINARY = bool(CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET)

if USE_CLOUDINARY:
    import cloudinary
    import cloudinary.uploader

    cloudinary.config(
        cloud_name=CLOUDINARY_CLOUD_NAME,
        api_key=CLOUDINARY_API_KEY,
        api_secret=CLOUDINARY_API_SECRET,
        secure=True,
    )


def store_photo_from_path(local_path: str) -> str:
    """Upload a local file to Cloudinary (if configured) and return its URL,
    or move it into the local uploads folder and return its filename."""
    if USE_CLOUDINARY:
        result = cloudinary.uploader.upload(local_path, folder="civic-app")
        return result["secure_url"]
    else:
        filename = os.path.basename(local_path)
        dest = os.path.join(UPLOAD_DIR, filename)
        if local_path != dest:
            shutil.move(local_path, dest)
        return filename


def store_photo_from_upload(upload: UploadFile, prefix: str = "") -> str:
    """Upload a FastAPI UploadFile directly to Cloudinary (if configured) and
    return its URL, or save it to the local uploads folder and return its filename."""
    filename = f"{prefix}{datetime.utcnow().timestamp()}_{upload.filename}"
    if USE_CLOUDINARY:
        result = cloudinary.uploader.upload(upload.file, folder="civic-app")
        return result["secure_url"]
    else:
        filepath = os.path.join(UPLOAD_DIR, filename)
        with open(filepath, "wb") as f:
            shutil.copyfileobj(upload.file, f)
        return filename


# Categories considered higher-risk by default, regardless of description
HIGH_RISK_CATEGORIES = {"open_manhole", "fallen_tree", "water_leak", "manhole"}
LOW_RISK_CATEGORIES = {"garbage", "streetlight"}

# Words in the citizen's description that bump priority up
URGENT_KEYWORDS = [
    "urgent", "dangerous", "emergency", "danger", "accident",
    "blocking", "blocked road", "electrocut", "collapse", "injur",
]


def calculate_priority(category: str, description: str) -> str:
    """Simple rule-based priority: category baseline, then bumped by keywords."""
    category = (category or "").lower()
    description = (description or "").lower()

    if any(word in description for word in URGENT_KEYWORDS):
        return "high"

    if category in HIGH_RISK_CATEGORIES:
        return "high"
    if category in LOW_RISK_CATEGORIES:
        return "low"
    return "medium"


def distance_meters(lat1, lon1, lat2, lon2):
    """Great-circle distance between two lat/long points, in meters."""
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371000 * 2 * asin(sqrt(a))


@app.get("/")
def root():
    return {"status": "Civic Issue API is running"}


# ---------- AUTH ----------

@app.post("/register")
def register(name: str = Form(...), email: str = Form(...), password: str = Form(...)):
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (%s, %s, %s)",
            (name, email, hashed),
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=f"Could not register: {e}")
    finally:
        cur.close()
        conn.close()
    return {"message": "Registered successfully"}


@app.post("/login")
def login(email: str = Form(...), password: str = Form(...)):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cur.fetchone()
    cur.close()
    conn.close()

    if not user or not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return {
        "message": "Login successful",
        "user_id": user["id"],
        "name": user["name"],
        "is_admin": user["is_admin"],
    }


# ---------- COMPLAINTS ----------

@app.post("/complaints")
def submit_complaint(
    user_id: int = Form(...),
    description: str = Form(""),
    latitude: float = Form(...),
    longitude: float = Form(...),
    photo: UploadFile = File(...),
):
    # 1. Save the uploaded photo to a temp file first (YOLO needs a local path to read)
    suffix = os.path.splitext(photo.filename or "")[1] or ".jpg"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=UPLOAD_DIR) as tmp:
        shutil.copyfileobj(photo.file, tmp)
        tmp_path = tmp.name

    # 2. Run AI detection on it
    result = detect_issue(tmp_path)
    category = result["category"]
    confidence = result.get("confidence", 0.0)

    # 3. Store the photo permanently (Cloudinary URL, or local filename) and clean up the temp file
    image_reference = store_photo_from_path(tmp_path)
    if os.path.exists(tmp_path):
        os.remove(tmp_path)

    # 4. Match category to a department
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT id FROM departments WHERE category = %s", (category,))
    dept = cur.fetchone()
    department_id = dept["id"] if dept else None

    # 5. Calculate priority
    priority = calculate_priority(category, description)

    # 6. Check for likely duplicates: same category, still open, nearby, recent
    cur.execute(
        """SELECT id, latitude, longitude FROM complaints
           WHERE category = %s AND status IN ('pending', 'in_progress')
           AND created_at > NOW() - INTERVAL '7 days'""",
        (category,),
    )
    possible_duplicate_of = None
    for row in cur.fetchall():
        dist = distance_meters(latitude, longitude, row["latitude"], row["longitude"])
        if dist <= 50:
            possible_duplicate_of = row["id"]
            break

    # 7. Save complaint to database
    cur.execute(
        """INSERT INTO complaints
           (user_id, department_id, category, description, image_path, latitude, longitude,
            possible_duplicate_of, priority, confidence)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           RETURNING id""",
        (user_id, department_id, category, description, image_reference, latitude, longitude,
         possible_duplicate_of, priority, confidence),
    )
    complaint_id = cur.fetchone()["id"]
    conn.commit()
    cur.close()
    conn.close()

    return {
        "message": "Complaint submitted",
        "complaint_id": complaint_id,
        "detected_category": category,
        "ai_mode": result.get("mode"),
        "possible_duplicate_of": possible_duplicate_of,
        "confidence": confidence,
        "priority": priority,
    }


@app.get("/complaints")
def list_complaints(status: str = None, category: str = None):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    query = """SELECT c.id, c.user_id, c.description, c.category, c.status, c.latitude, c.longitude,
                      c.image_path, c.resolved_image_path, c.created_at, c.possible_duplicate_of,
                      c.priority, c.confidence, c.citizen_verified,
                      u.name AS reported_by, d.name AS department
               FROM complaints c
               JOIN users u ON c.user_id = u.id
               LEFT JOIN departments d ON c.department_id = d.id
               WHERE 1=1"""
    params = []

    if status:
        query += " AND c.status = %s"
        params.append(status)
    if category:
        query += " AND c.category = %s"
        params.append(category)

    query += " ORDER BY c.created_at DESC"

    cur.execute(query, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


@app.put("/complaints/{complaint_id}/status")
def update_status(complaint_id: int, status: str = Form(...)):
    if status not in ("pending", "in_progress", "resolved"):
        raise HTTPException(status_code=400, detail="Invalid status")
    conn = get_connection()
    cur = conn.cursor()
    # Reset citizen verification whenever a report is (re)marked resolved,
    # so the citizen gets asked again for this latest resolution.
    if status == "resolved":
        cur.execute("UPDATE complaints SET status = %s, citizen_verified = NULL WHERE id = %s", (status, complaint_id))
    else:
        cur.execute("UPDATE complaints SET status = %s WHERE id = %s", (status, complaint_id))
    conn.commit()
    cur.close()
    conn.close()
    return {"message": "Status updated"}


@app.put("/complaints/{complaint_id}/category")
def update_category(complaint_id: int, category: str = Form(...)):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT id FROM departments WHERE category = %s", (category,))
    dept = cur.fetchone()
    department_id = dept["id"] if dept else None

    cur.execute(
        "UPDATE complaints SET category = %s, department_id = %s WHERE id = %s",
        (category, department_id, complaint_id),
    )
    conn.commit()
    cur.close()
    conn.close()
    return {"message": "Category updated"}


@app.put("/complaints/{complaint_id}/verify")
def verify_resolution(complaint_id: int, verified: str = Form(...)):
    """Citizen confirms whether a resolved report was actually fixed.
    verified: 'true' -> stays resolved, citizen_verified = TRUE
    verified: 'false' -> reopened (status back to pending), citizen_verified = FALSE
    """
    is_verified = verified.lower() == "true"
    conn = get_connection()
    cur = conn.cursor()
    if is_verified:
        cur.execute(
            "UPDATE complaints SET citizen_verified = TRUE WHERE id = %s",
            (complaint_id,),
        )
    else:
        cur.execute(
            "UPDATE complaints SET citizen_verified = FALSE, status = 'pending' WHERE id = %s",
            (complaint_id,),
        )
    conn.commit()
    cur.close()
    conn.close()
    return {"message": "Verification recorded", "verified": is_verified}


@app.put("/complaints/{complaint_id}/resolve-photo")
def upload_resolve_photo(complaint_id: int, photo: UploadFile = File(...)):
    """Admin uploads an 'after' photo showing the issue was fixed."""
    image_reference = store_photo_from_upload(photo, prefix="resolved_")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE complaints SET resolved_image_path = %s WHERE id = %s",
        (image_reference, complaint_id),
    )
    conn.commit()
    cur.close()
    conn.close()
    return {"message": "Resolution photo uploaded", "resolved_image_path": image_reference}