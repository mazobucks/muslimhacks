from flask import Flask, g, render_template, request, flash, redirect, url_for, flash, g
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
        elder_id   INTEGER NOT NULL,
        is_primary BOOLEAN NOT NULL DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (id) REFERENCES Users(id) ON DELETE CASCADE,
        FOREIGN KEY (elder_id) REFERENCES Elders(id) ON DELETE CASCADE
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
    db.execute("INSERT INTO Users (username, password, role) VALUES (?, ?, ?)",
            ["fatima", "5678", "elder"])
    elder_user_id = db.execute("SELECT id FROM Users WHERE username = ?", ["fatima"]).fetchone()[0]

    db.execute("INSERT INTO Elders (id, full_name) VALUES (?, ?)",
            [elder_user_id, "Fatima Ahmed"])

    # --- Caregiver (primary, tied to the elder above) ---
    db.execute("INSERT INTO Users (username, password, role) VALUES (?, ?, ?)",
            ["yusuf", "9999", "caregiver"])
    caregiver_user_id = db.execute("SELECT id FROM Users WHERE username = ?", ["yusuf"]).fetchone()[0]

    db.execute("INSERT INTO Caregivers (id, full_name, elder_id, is_primary) VALUES (?, ?, ?, ?)",
            [caregiver_user_id, "Yusuf Ahmed", elder_user_id, 1])

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
  return render_template("caregiver.html")


# Cleans up a database connection.
@app.teardown_appcontext
def cleanup(exception):
  db = g.get("_database")
  if db:
    db.close()
