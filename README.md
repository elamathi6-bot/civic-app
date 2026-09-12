# Civic Issue Reporting App — Starter Project (PostgreSQL version)

This works with the Python you already have installed (3.14). No need to
install a different Python version.

## What's inside
- `database/schema.sql` — creates your PostgreSQL tables
- `backend/main.py` — the FastAPI server
- `backend/yolo_detect.py` — AI detection (starts in placeholder mode, upgrade later)
- `frontend/index.html` — citizen "report an issue" page
- `frontend/admin.html` — admin dashboard

## Step 1 — Create the database
Open **pgAdmin**, connect to your local PostgreSQL server (it will ask for
the password you set when installing PostgreSQL). Right-click "Databases"
> Create > Database, name it `civic_app`, save.

## Step 2 — Create the tables
With `civic_app` selected in pgAdmin, open the **Query Tool**, open
`database/schema.sql` (or paste its contents in), and run it (the play
button / F5). This creates the tables.

## Step 3 — Set your DB password
Open `backend/database.py` and replace `CHANGE_ME` with your real
PostgreSQL password (the one you used to log into pgAdmin).

## Step 4 — Install the core Python packages
Open a terminal **inside the `backend` folder** and run:

```
pip install -r requirements.txt
```

This installs only FastAPI, the PostgreSQL driver, etc — no numpy, no AI
packages — so it installs cleanly on Python 3.14 with no build errors.

## Step 5 — Run the server

```
uvicorn main:app --reload
```

You should see `Uvicorn running on http://127.0.0.1:8000`. Leave this
terminal open.

## Step 6 — Try it
1. Open `frontend/index.html` directly in your browser (double-click it).
2. First register a user by visiting http://127.0.0.1:8000/docs in your
   browser — this opens FastAPI's built-in test page. Use the `/register`
   endpoint to create yourself a user, note the ID.
3. Go back to `index.html`, enter that user ID, choose a photo, click
   "Get My Location", then "Submit Report".
4. Open `frontend/admin.html` to see the complaint appear with a status
   dropdown.

At this stage the AI category is a placeholder ("pothole" every time) —
that's expected. Everything else is real and working: photo upload, GPS,
database storage, and the admin view.

## Step 7 — Add real AI detection (do this later, once the app above works)
1. Install the AI packages **separately**, only when you're ready:
   ```
   pip install -r requirements-ai.txt
   ```
2. Train a YOLO model on pothole/garbage images (ask me for the training
   guide when you're ready for this step).
3. Save the trained weights as `backend/best.pt` — the app will
   automatically start using real AI detection instead of the placeholder.

## If something breaks
Copy the exact error message and send it — don't just describe it.
