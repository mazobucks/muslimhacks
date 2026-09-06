from flask import Flask, g, render_template, request, flash, redirect, url_for, flash, g, abort, jsonify
import os
import sqlite3
import secrets
import json
import datetime
from datetime import datetime, timedelta
import sqlite3
from flask_login import current_user, login_required, login_user, UserMixin, LoginManager, logout_user
import werkzeug
import requests


app = Flask(__name__)
app.secret_key = secrets.token_hex(16) # This is necessary for flash!

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

class Elder:
    def __init__(self, id, full_name):
        self.id = id
        self.full_name = full_name

class Caregiver:
    def __init__(self, id, full_name, elder_id, is_primary, diet=0, medication=0, prayer=0):
        self.id = id
        self.full_name = full_name
        self.elder_id = elder_id
        self.is_primary = is_primary
        self.diet = diet
        self.medication = medication
        self.prayer = prayer

class Medication:
    def __init__(self, id, elder_id, name, dosage, schedule_time, created_by):
        self.id = id
        self.elder_id = elder_id
        self.name = name
        self.dosage = dosage
        self.schedule_time = schedule_time
        self.created_by = created_by

class User(UserMixin):
    def __init__(self, id, name, password, role):
        self.id = name
        self.user_id = id
        self.name = name
        self.password = password
        self.role = role

@login_manager.user_loader
def user_loader(name):
    record = get_db().execute("SELECT id, username, password, role FROM Users WHERE username = ? LIMIT 1", [name]).fetchone()
    if not record:
        return None
    return User(record[0], record[1], record[2], record[3])

path = "cnc.db" 
database_exists = os.path.isfile(path)
db = sqlite3.connect("cnc.db")
if not database_exists: 
    db.execute("""CREATE TABLE IF NOT EXISTS Users (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(255) UNIQUE NOT NULL,
    password VARCHAR(32) NOT NULL,
    role     VARCHAR(10) NOT NULL CHECK(role IN ('elder','caregiver'))
    )""")

    db.execute("""CREATE TABLE IF NOT EXISTS Elders (
        id                    INTEGER PRIMARY KEY,
        full_name             VARCHAR(255),
        language              VARCHAR(50) DEFAULT 'English',
        color_theme           VARCHAR(20) DEFAULT 'default',
        tts_enabled           BOOLEAN DEFAULT 1,
        rakah_counter_enabled BOOLEAN DEFAULT 0,
        created_at            DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (id) REFERENCES Users(id) ON DELETE CASCADE
    )""")

    db.execute("""CREATE TABLE IF NOT EXISTS Caregivers (
        id         INTEGER PRIMARY KEY,
        full_name  VARCHAR(255),
        elder_id   INTEGER,
        is_primary BOOLEAN DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (id) REFERENCES Users(id) ON DELETE CASCADE,
        FOREIGN KEY (elder_id) REFERENCES Elders(id) ON DELETE CASCADE
    )""")

    db.execute("""CREATE TABLE IF NOT EXISTS Responsibilities (
        caregiver_id INTEGER PRIMARY KEY,
        diet         BOOLEAN NOT NULL DEFAULT 1,
        medication   BOOLEAN NOT NULL DEFAULT 1,
        prayer       BOOLEAN NOT NULL DEFAULT 1,
        FOREIGN KEY (caregiver_id) REFERENCES Caregivers(id) ON DELETE CASCADE
    )""")

    db.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_one_primary_per_elder
        ON Caregivers(elder_id)
        WHERE is_primary = 1""")

    db.execute("""CREATE TABLE IF NOT EXISTS Medications (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        elder_id      INTEGER NOT NULL,
        name          VARCHAR(255) NOT NULL,
        dosage        VARCHAR(100),
        photo_path    VARCHAR(255),
        schedule_time VARCHAR(20),
        created_by    INTEGER NOT NULL,
        created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (elder_id) REFERENCES Elders(id) ON DELETE CASCADE,
        FOREIGN KEY (created_by) REFERENCES Users(id)
    )""")

    db.execute("""CREATE TABLE IF NOT EXISTS Reminders (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        elder_id        INTEGER NOT NULL,
        created_by      INTEGER NOT NULL,
        category        VARCHAR(20) NOT NULL DEFAULT 'custom'
                        CHECK(category IN ('prayer','medication','custom')),
        title           VARCHAR(255) NOT NULL,
        description     TEXT,
        frequency       VARCHAR(10) NOT NULL CHECK(frequency IN ('one_time','daily','weekly')),
        scheduled_time  VARCHAR(20),
        day_of_week     VARCHAR(10),
        next_occurrence DATETIME,
        active          BOOLEAN DEFAULT 1,
        FOREIGN KEY (elder_id) REFERENCES Elders(id) ON DELETE CASCADE,
        FOREIGN KEY (created_by) REFERENCES Users(id)
    )""")

    db.execute("""CREATE TABLE IF NOT EXISTS TaskLogs (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        reminder_id INTEGER NOT NULL,
        logged_by   INTEGER,
        status      VARCHAR(10) NOT NULL DEFAULT 'done' CHECK(status IN ('done','missed')),
        logged_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (reminder_id) REFERENCES Reminders(id) ON DELETE CASCADE,
        FOREIGN KEY (logged_by) REFERENCES Users(id) ON DELETE SET NULL
    )""")

    db.execute("""CREATE TABLE IF NOT EXISTS Notifications (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        from_user  INTEGER NOT NULL,
        to_user    INTEGER NOT NULL,
        message    VARCHAR(255) NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (from_user) REFERENCES Users(id),
        FOREIGN KEY (to_user) REFERENCES Users(id)
    )""")

    # --- Elder ---

    # --- Caregiver (primary, tied to the elder above) ---
    db.execute("INSERT INTO Users (username, password, role) VALUES (?, ?, ?)",
            ["yusuf", "9999", "caregiver"])
    caregiver_user_id = db.execute("SELECT id FROM Users WHERE username = ?", ["yusuf"]).fetchone()[0]

    db.execute("INSERT INTO Caregivers (id, full_name, elder_id, is_primary) VALUES (?, ?, ?, ?)",
        [caregiver_user_id, "Yusuf Ahmed", None, 0])   # elder_id = NULL, no elder yet

    db.execute("INSERT INTO Responsibilities (caregiver_id) VALUES (?)",
        [caregiver_user_id])

    db.commit()


# Gets a database connection.
def get_db():
  db = g.get("_database")
  if not db:
    db = sqlite3.connect("cnc.db")
    g._database = db
  return db

@app.route("/login")
def login_form():
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def login():
    try:
        name = request.form["username"]
        password = request.form["password"]
        record = get_db().execute(
            "SELECT id, password, role FROM Users WHERE username = ? LIMIT 1", [name]
        ).fetchone()
        print("Record:", record)

        if not record or password != record[1]:
            flash("Login info invalid!!!")
            return redirect(url_for("login_form"))

        user = User(record[0], name, record[1], record[2])
        login_user(user)

        if user.role == 'caregiver':
            return redirect(url_for("caregiver"))
        else:
            return redirect(url_for('elder'))

    except Exception as e:
        print("Login error:", e)
        flash("Something went wrong logging you in.")
        return redirect(url_for("login_form"))

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))
  
@app.route("/elder")
@login_required
def elder():
    if current_user.role != "elder":
        abort(403)

    db = get_db()
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    medication_rows = db.execute(
            "SELECT id, name, dosage, schedule_time FROM Medications WHERE elder_id = ? ORDER BY schedule_time, name",
            [current_user.user_id]
    ).fetchall()
    medications = []
    for row in medication_rows:
        start_time = parse_schedule_time(row[3])
        end_time = start_time + timedelta(hours=1) if start_time else None
        log = db.execute(
                """SELECT status FROM TaskLogs WHERE reminder_id = (
                         SELECT id FROM Reminders WHERE elder_id = ? AND category = 'medication' AND title = ? LIMIT 1
                     ) AND date(logged_at) = ? ORDER BY logged_at DESC LIMIT 1""",
                [current_user.user_id, row[1], today]
        ).fetchone()
        medications.append({
                "id": row[0], "name": row[1], "dosage": row[2],
                "schedule_time": format_time(start_time),
                "ends_at": format_time(end_time),
                "status": medication_status(now, start_time, log[0] if log else None),
        })

    custom_reminders = db.execute(
            """SELECT id, title, description, frequency, scheduled_time
                 FROM Reminders WHERE elder_id = ? AND category = 'custom' AND active = 1
                 ORDER BY scheduled_time, id""",
            [current_user.user_id]
    ).fetchall()

    prayer = get_prayer_summary()
    prayer_log = get_today_task_log(current_user.user_id, prayer["current"]["name"], "prayer", today)
    prayer["current"]["done"] = bool(prayer_log and prayer_log[0] == "done")

    return render_template("elder.html", prayer=prayer, medications=medications,
                                                 custom_reminders=custom_reminders, now=now)


def parse_schedule_time(value):
    if not value:
        return None
    for pattern in ("%H:%M", "%I:%M %p"):
        try:
            return datetime.strptime(value.strip(), pattern).replace(year=2000, month=1, day=1)
        except ValueError:
            continue
    return None


def format_time(value):
    return value.strftime("%I:%M %p").lstrip("0") if value else "Not scheduled"


def medication_status(now, start_time, log_status):
    if log_status == "done":
        return "done"
    if not start_time:
        return "unscheduled"
    current = now.replace(year=2000, month=1, day=1, second=0, microsecond=0)
    end_time = start_time + timedelta(hours=1)
    if current < start_time:
        return "upcoming"
    if current <= end_time:
        return "now"
    return "missed"


def get_today_task_log(elder_id, title, category, today):
    return get_db().execute(
            """SELECT tl.status FROM TaskLogs tl JOIN Reminders r ON r.id = tl.reminder_id
                 WHERE r.elder_id = ? AND r.title = ? AND r.category = ? AND date(tl.logged_at) = ?
                 ORDER BY tl.logged_at DESC LIMIT 1""",
            [elder_id, title, category, today]
    ).fetchone()


def get_prayer_summary():
    try:
        response = requests.get(
                "https://api.aladhan.com/v1/timings",
                params={"latitude": DEFAULT_LAT, "longitude": DEFAULT_LNG, "method": 2},
                timeout=5,
        )
        timings = response.json()["data"]["timings"]
    except Exception:
        timings = {name: "--:--" for name in FARD_RAKAHS}

    now_text = datetime.now().strftime("%H:%M")
    ordered = list(FARD_RAKAHS)
    current_index = -1
    for index, name in enumerate(ordered):
        if timings.get(name, "99:99") <= now_text:
            current_index = index
    if current_index == -1:
        current_index = len(ordered) - 1
    next_index = (current_index + 1) % len(ordered)
    return {
            "current": {"name": ordered[current_index], "time": timings.get(ordered[current_index], "--:--")},
            "next": {"name": ordered[next_index], "time": timings.get(ordered[next_index], "--:--")},
    }


def get_or_create_task_reminder(elder_id, title, category, created_by):
    db = get_db()
    row = db.execute(
            "SELECT id FROM Reminders WHERE elder_id = ? AND category = ? AND title = ? LIMIT 1",
            [elder_id, category, title]
    ).fetchone()
    if row:
        return row[0]
    cursor = db.execute(
            "INSERT INTO Reminders (elder_id, created_by, category, title, frequency) VALUES (?, ?, ?, ?, 'daily')",
            [elder_id, created_by, category, title]
    )
    db.commit()
    return cursor.lastrowid


@app.route("/elder/medications/<int:medication_id>/done", methods=["POST"])
@login_required
def medication_done(medication_id):
    if current_user.role != "elder":
        abort(403)
    db = get_db()
    medication = db.execute(
            "SELECT name FROM Medications WHERE id = ? AND elder_id = ?",
            [medication_id, current_user.user_id]
    ).fetchone()
    if not medication:
        abort(404)
    reminder_id = get_or_create_task_reminder(current_user.user_id, medication[0], "medication", current_user.user_id)
    db.execute("INSERT INTO TaskLogs (reminder_id, logged_by, status, logged_at) VALUES (?, ?, 'done', ?)",
                         [reminder_id, current_user.user_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
    db.commit()
    return redirect(url_for("elder"))


@app.route("/elder/reminders", methods=["POST"])
@login_required
def add_elder_reminder():
    if current_user.role != "elder":
        abort(403)
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    frequency = request.form.get("frequency", "one_time")
    scheduled_time = request.form.get("scheduled_time", "").strip()
    if not title or frequency not in {"one_time", "daily", "weekly"}:
        flash("A reminder title and valid frequency are required.")
        return redirect(url_for("elder"))
    db = get_db()
    db.execute(
            """INSERT INTO Reminders (elder_id, created_by, category, title, description, frequency, scheduled_time)
                 VALUES (?, ?, 'custom', ?, ?, ?, ?)""",
            [current_user.user_id, current_user.user_id, title, description, frequency, scheduled_time or None]
    )
    db.commit()
    return redirect(url_for("elder"))

FARD_RAKAHS = {
    "Fajr": 2,
    "Dhuhr": 4,
    "Asr": 4,
    "Maghrib": 3,
    "Isha": 4,
}

# Fallback coordinates if the browser doesn't share location (Mecca, as a placeholder)
DEFAULT_LAT = 21.3891
DEFAULT_LNG = 39.8579


@app.route("/prayer-check")
@login_required
def prayer_check():
    return render_template("prayer-check.html")


@app.route("/api/current-prayer")
@login_required
def current_prayer():
    lat = request.args.get("lat", DEFAULT_LAT)
    lng = request.args.get("lng", DEFAULT_LNG)

    try:
        resp = requests.get(
            "https://api.aladhan.com/v1/timings",
            params={"latitude": lat, "longitude": lng, "method": 2},
            timeout=5,
        )
        timings = resp.json()["data"]["timings"]
    except Exception:
        return {"error": "Could not reach prayer time service"}, 502

    now = datetime.now().strftime("%H:%M")
    current_name = None
    current_time = None

    # Find the most recent fard prayer time that has already passed today
    for name in FARD_RAKAHS:
        t = timings.get(name)
        if t and t <= now:
            current_name = name
            current_time = t

    if not current_name:
        # before Fajr - default to yesterday's Isha
        current_name = "Isha"
        current_time = timings.get("Isha")

    return {
        "name": current_name,
        "time": current_time,
        "rakahs": FARD_RAKAHS[current_name],
    }


def get_or_create_prayer_reminder(elder_id, prayer_name):
    db = get_db()
    row = db.execute(
        "SELECT id FROM Reminders WHERE elder_id = ? AND category = 'prayer' AND title = ? LIMIT 1",
        [elder_id, prayer_name],
    ).fetchone()
    if row:
        return row[0]

    cur = db.execute(
        """INSERT INTO Reminders (elder_id, created_by, category, title, frequency)
           VALUES (?, ?, 'prayer', ?, 'daily')""",
        [elder_id, elder_id, prayer_name],
    )
    db.commit()
    return cur.lastrowid


def get_primary_caregiver(elder_id):
    db = get_db()
    row = db.execute(
        "SELECT id FROM Caregivers WHERE elder_id = ? AND is_primary = 1 LIMIT 1",
        [elder_id],
    ).fetchone()
    return row[0] if row else None


@app.route("/api/prayer/end", methods=["POST"])
@login_required
def end_prayer():
    data = request.get_json()
    prayer_name = data.get("prayer_name")
    rakahs_completed = data.get("rakahs_completed", 0)
    rakahs_required = data.get("rakahs_required")

    elder_id = current_user.user_id
    db = get_db()

    reminder_id = get_or_create_prayer_reminder(elder_id, prayer_name)

    status = "done"
    if rakahs_required and rakahs_completed < rakahs_required:
        status = "missed"

    db.execute(
        "INSERT INTO TaskLogs (reminder_id, logged_by, status, logged_at) VALUES (?, ?, ?, ?)",
        [reminder_id, elder_id, status, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
    )

    caregiver_id = get_primary_caregiver(elder_id)
    if caregiver_id:
        message = f"{current_user.name} completed {prayer_name} ({rakahs_completed} rakah)."
        db.execute(
            "INSERT INTO Notifications (from_user, to_user, message) VALUES (?, ?, ?)",
            [elder_id, caregiver_id, message],
        )

    db.commit()
    return {"ok": True}
@app.route("/caregiver")
@login_required
def caregiver():
    if current_user.role != "caregiver":
        abort(403)

    db = get_db()
    elder_id = get_linked_elder_id()

    elder = None
    secondary_caregivers = []
    reminders = []
    if elder_id is not None:
        elderRow = db.execute(
            "SELECT * FROM Elders WHERE id = ?", [elder_id]
        ).fetchone()
        elder = Elder(elderRow[0], elderRow[1])
        secondary_caregivers_rows = db.execute(
            """SELECT c.id, c.full_name, c.elder_id, c.is_primary, r.diet, r.medication, r.prayer
            FROM Caregivers c
            LEFT JOIN Responsibilities r ON r.caregiver_id = c.id
            WHERE c.elder_id = ? AND c.id != ?""",
            [elder_id, current_user.user_id]
        ).fetchall()
        secondary_caregivers = [
            Caregiver(
                row[0],
                row[1],
                row[2],
                row[3],
                row[4] or 0,
                row[5] or 0,
                row[6] or 0,
            )
            for row in secondary_caregivers_rows
        ]
        reminders = db.execute(
            "SELECT * FROM Reminders WHERE elder_id = ? AND active = 1", [elder_id]
        ).fetchall()
        
    caregiver_row = db.execute(
        "SELECT is_primary FROM Caregivers WHERE id = ?", [current_user.user_id]
    ).fetchone()
    is_primary = bool(caregiver_row[0]) if caregiver_row else False

    primary_caregiver = None
    if elder_id is not None and not is_primary:
        primary_row = db.execute(
            "SELECT id, full_name, elder_id, is_primary FROM Caregivers WHERE elder_id = ? AND is_primary = 1",
            [elder_id]
        ).fetchone()
        if primary_row:
            primary_caregiver = Caregiver(primary_row[0], primary_row[1], primary_row[2], primary_row[3])

    notifications = db.execute(
        "SELECT * FROM Notifications WHERE to_user = ? ORDER BY created_at DESC LIMIT 20",
        [current_user.user_id]   # <-- fixing the still-outstanding id/user_id bug while I'm here
    ).fetchall()

    return render_template(
        "caregiver.html",
        elder=elder,
        secondary_caregivers=secondary_caregivers,
        notifications=notifications,
        reminders=reminders,
        is_primary=is_primary,
        primary_caregiver=primary_caregiver
    )

def get_linked_elder_id():
    """Returns the elder_id already linked to this caregiver, or None."""
    row = get_db().execute(
        "SELECT elder_id FROM Caregivers WHERE id = ?", [current_user.user_id]
    ).fetchone()
    return row[0] if row else None 

@app.route("/add_elder", methods=["GET", "POST"])
@login_required
def add_elder():
    if current_user.role != "caregiver":
        abort(403)

    if get_linked_elder_id() is not None:
        flash("You already have an elder linked to your account.")
        return redirect(url_for("caregiver"))

    if request.method == "GET":
        return render_template("add_elder.html")

    full_name = request.form.get("full_name", "").strip()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    language = request.form.get("language", "").strip()

    if not full_name or not username or not password or not language:
        flash("Name, username, password, and language are required.")
        return redirect(url_for("add_elder"))

    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO Users (username, password, role) VALUES (?, ?, 'elder')",
            [username, password]
        )
        elder_user_id = cur.lastrowid

        db.execute(
            "INSERT INTO Elders (id, full_name, language) VALUES (?, ?, ?)",
            [elder_user_id, full_name, language]
        )

        db.execute(
            "UPDATE Caregivers SET elder_id = ?, is_primary = 1 WHERE id = ?",
            [elder_user_id, current_user.user_id]
        )
        db.commit()

    except sqlite3.IntegrityError:
        db.rollback()
        flash("That username is already taken.")
        return redirect(url_for("add_elder"))

    flash(f"{full_name} has been added.")
    return redirect(url_for("caregiver"))


@app.route("/add_secondary_caregiver", methods=["GET", "POST"])
@login_required
def add_secondary_caregiver():
    if current_user.role != "caregiver":
        abort(403)

    caregiver_row = get_db().execute(
        "SELECT is_primary FROM Caregivers WHERE id = ?", [current_user.user_id]
    ).fetchone()
    if not caregiver_row or not caregiver_row[0]:
        abort(403)   # only the primary caregiver can add secondary caregivers

    elder_id = get_linked_elder_id()
    if elder_id is None:
        flash("Add an elder before adding a secondary caregiver.")
        return redirect(url_for("caregiver"))

    if request.method == "GET":
        return render_template("add_secondary.html")

    full_name = request.form.get("full_name", "").strip()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    if not full_name or not username or not password:
        flash("Name, username, and password are required.")
        return redirect(url_for("add_secondary_caregiver"))

    # checkboxes: present in form data only when checked
    diet = 1 if request.form.get("diet") else 0
    medication = 1 if request.form.get("medication") else 0
    prayer = 1 if request.form.get("prayer") else 0

    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO Users (username, password, role) VALUES (?, ?, 'caregiver')",
            [username, password]
        )
        new_caregiver_id = cur.lastrowid

        db.execute(
            "INSERT INTO Caregivers (id, full_name, elder_id, is_primary) VALUES (?, ?, ?, 0)",
            [new_caregiver_id, full_name, elder_id]
        )

        db.execute(
            "INSERT INTO Responsibilities (caregiver_id, diet, medication, prayer) VALUES (?, ?, ?, ?)",
            [new_caregiver_id, diet, medication, prayer]
        )
        db.commit()

    except sqlite3.IntegrityError:
        db.rollback()
        flash("That username is already taken.")
        return redirect(url_for("add_secondary_caregiver"))

    flash(f"{full_name} has been added as a secondary caregiver.")
    return redirect(url_for("caregiver"))

@app.route("/add_meds", methods=["GET", "POST"])
@login_required
def add_meds():
    if current_user.role != "caregiver":
        abort(403)

    elder_id = get_linked_elder_id()
    if elder_id is None:
        flash("Add an elder before adding medications.")
        return redirect(url_for("caregiver"))

    db = get_db()

    elder_row = db.execute(
        "SELECT id, full_name FROM Elders WHERE id = ?", [elder_id]
    ).fetchone()
    elder = Elder(elder_row[0], elder_row[1])

    if request.method == "GET":
        medication_rows = db.execute(
            "SELECT id, elder_id, name, dosage, schedule_time, created_by "
            "FROM Medications WHERE elder_id = ? ORDER BY created_at DESC",
            [elder_id]
        ).fetchall()
        medications = [
            Medication(row[0], row[1], row[2], row[3], row[4], row[5])
            for row in medication_rows
        ]
        return render_template("add_meds.html", elder=elder, medications=medications)

    name = request.form.get("name", "").strip()
    dosage = request.form.get("dosage", "").strip()
    schedule_time = request.form.get("schedule_time", "").strip()

    if not name:
        flash("Medication name is required.")
        return redirect(url_for("add_meds"))

    db.execute(
        "INSERT INTO Medications (elder_id, name, dosage, schedule_time, created_by) VALUES (?, ?, ?, ?, ?)",
        [elder_id, name, dosage, schedule_time, current_user.user_id]
    )
    db.commit()

    flash(f"{name} has been added.")
    return redirect(url_for("add_meds"))


@app.route("/remove_medication/<int:medication_id>", methods=["POST"])
@login_required
def remove_medication(medication_id):
    if current_user.role != "caregiver":
        abort(403)

    elder_id = get_linked_elder_id()
    if elder_id is None:
        abort(403)

    db = get_db()
    # only delete if this medication actually belongs to this caregiver's elder
    db.execute(
        "DELETE FROM Medications WHERE id = ? AND elder_id = ?",
        [medication_id, elder_id]
    )
    db.commit()

    flash("Medication removed.")
    return redirect(url_for("add_meds"))


# Cleans up a database connection.
@app.teardown_appcontext
def cleanup(exception):
  db = g.get("_database")
  if db:
    db.close()
