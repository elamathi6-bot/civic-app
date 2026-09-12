import os
import shutil
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
    # 1. Save the uploaded photo
    filename = f"{datetime.utcnow().timestamp()}_{photo.filename}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        shutil.copyfileobj(photo.file, f)

    # 2. Run AI detection on it
    result = detect_issue(filepath)
    category = result["category"]

    # 3. Match category to a department
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT id FROM departments WHERE category = %s", (category,))
    dept = cur.fetchone()
    department_id = dept["id"] if dept else None

    # 4. Check for likely duplicates: same category, still open, nearby, recent
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

    # 5. Save complaint to database
    cur.execute(
        """INSERT INTO complaints
           (user_id, department_id, category, description, image_path, latitude, longitude, possible_duplicate_of)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
           RETURNING id""",
        (user_id, department_id, category, description, filename, latitude, longitude, possible_duplicate_of),
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
    }


@app.get("/complaints")
def list_complaints(status: str = None, category: str = None):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    query = """SELECT c.id, c.user_id, c.description, c.category, c.status, c.latitude, c.longitude,
                      c.image_path, c.created_at, c.possible_duplicate_of, u.name AS reported_by, d.name AS department
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
