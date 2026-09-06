from flask import Flask, g, render_template, request, flash, redirect, url_for, flash, g, abort, jsonify
import os
import sqlite3
import secrets
import json
import datetime
from datetime import datetime
import sqlite3
from flask_login import current_user, login_required, login_user, UserMixin, LoginManager, logout_user
import werkzeug


app = Flask(__name__)
app.secret_key = secrets.token_hex(16) # This is necessary for flash!

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

class Elder:
    def __init__(self, id, full_name):
        self.id = id
        self.full_name = full_name

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
            return redirect(url_for('elderhome'))

    except Exception as e:
        print("Login error:", e)
        flash("Something went wrong logging you in.")
        return redirect(url_for("login_form"))

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))
  
@app.route("/")
@login_required
def home():
  return render_template("home.html")

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
        secondary_caregivers = db.execute(
            """SELECT c.full_name, r.diet, r.medication, r.prayer
               FROM Caregivers c
               LEFT JOIN Responsibilities r ON r.caregiver_id = c.id
               WHERE c.elder_id = ? AND c.id != ?""",
            [elder_id, current_user.user_id]
        ).fetchall()
        reminders = db.execute(
            "SELECT * FROM Reminders WHERE elder_id = ? AND active = 1", [elder_id]
        ).fetchall()

    notifications = db.execute(
        "SELECT * FROM Notifications WHERE to_user = ? ORDER BY created_at DESC LIMIT 20",
        [current_user.id]
    ).fetchall()

    return render_template(
        "caregiver.html",
        elder=elder,
        secondary_caregivers=secondary_caregivers,
        notifications=notifications,
        reminders=reminders
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


# Cleans up a database connection.
@app.teardown_appcontext
def cleanup(exception):
  db = g.get("_database")
  if db:
    db.close()
