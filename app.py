"""MediBook - Hospital Appointment Booking System (Flask + SQLite)."""
import os
import re
import secrets
import sqlite3
from datetime import date, datetime, time, timedelta
from functools import wraps

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from markupsafe import Markup
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config["DATABASE"] = os.path.join(BASE_DIR, "hospital.db")

SLOT_MINUTES = 30        # length of one appointment slot
MAX_ADVANCE_DAYS = 30    # how far ahead a patient may book
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

DOCTOR_SELECT = """
    SELECT d.*, u.name, u.email, dep.name AS department
    FROM doctors d
    JOIN users u ON u.id = d.user_id
    JOIN departments dep ON dep.id = d.department_id
"""


# --------------------------------------------------------------------------
# Database helpers
# --------------------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create tables and insert demo data on first run."""
    db = get_db()
    with open(os.path.join(BASE_DIR, "schema.sql"), encoding="utf-8") as f:
        db.executescript(f.read())
    seed(db)


def seed(db):
    if db.execute("SELECT 1 FROM users WHERE role = 'admin'").fetchone():
        return
    db.execute(
        "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'admin')",
        ("Administrator", "admin@hospital.com", generate_password_hash("admin123")),
    )
    for dept in ["General Medicine", "Cardiology", "Pediatrics",
                 "Orthopedics", "Dermatology"]:
        db.execute("INSERT OR IGNORE INTO departments (name) VALUES (?)", (dept,))
    samples = [
        ("Dr. Arun Kumar", "arun@hospital.com", "General Medicine", "MBBS, MD", 300),
        ("Dr. Meena Lakshmi", "meena@hospital.com", "Cardiology", "MBBS, DM (Cardiology)", 600),
        ("Dr. Karthik Raja", "karthik@hospital.com", "Pediatrics", "MBBS, DCH", 400),
    ]
    for name, email, dept, qualification, fee in samples:
        cur = db.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'doctor')",
            (name, email, generate_password_hash("doctor123")),
        )
        dept_id = db.execute("SELECT id FROM departments WHERE name = ?", (dept,)).fetchone()["id"]
        db.execute(
            "INSERT INTO doctors (user_id, department_id, qualification, fee) VALUES (?, ?, ?, ?)",
            (cur.lastrowid, dept_id, qualification, fee),
        )
    db.commit()


# --------------------------------------------------------------------------
# Security helpers: CSRF protection and role-based access
# --------------------------------------------------------------------------
def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


app.jinja_env.globals["csrf_field"] = lambda: Markup(
    '<input type="hidden" name="_csrf" value="%s">' % csrf_token()
)


@app.before_request
def csrf_protect():
    if request.method == "POST":
        token = session.get("_csrf")
        if not token or token != request.form.get("_csrf"):
            abort(400, "Invalid or missing form token. Please go back and try again.")


def login_required(role=None):
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in to continue.", "warning")
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                abort(403, "You do not have permission to open this page.")
            return view(*args, **kwargs)
        return wrapper
    return decorator


# --------------------------------------------------------------------------
# Domain helpers
# --------------------------------------------------------------------------
@app.template_filter("days_text")
def days_text(value):
    return ", ".join(DAY_NAMES[int(i)] for i in value.split(",") if i != "")


def doctor_days(doctor):
    return {int(i) for i in doctor["days"].split(",") if i != ""}


def get_doctor(db, doctor_id):
    return db.execute(DOCTOR_SELECT + " WHERE d.id = ?", (doctor_id,)).fetchone()


def current_doctor(db):
    return db.execute(DOCTOR_SELECT + " WHERE d.user_id = ?", (session["user_id"],)).fetchone()


def parse_date(value):
    try:
        return datetime.strptime(value or "", "%Y-%m-%d").date()
    except ValueError:
        return None


def available_slots(db, doctor, day):
    """Free HH:MM slots for a doctor on a given date."""
    if day.weekday() not in doctor_days(doctor):
        return []
    booked = {
        r["appt_time"] for r in db.execute(
            "SELECT appt_time FROM appointments "
            "WHERE doctor_id = ? AND appt_date = ? AND status <> 'Cancelled'",
            (doctor["id"], day.isoformat()))
    }
    now = datetime.now()
    slots = []
    t = datetime.combine(day, time(doctor["start_hour"]))
    end = datetime.combine(day, time(doctor["end_hour"]))
    while t < end:
        label = t.strftime("%H:%M")
        in_past = day == now.date() and t <= now
        if label not in booked and not in_past:
            slots.append(label)
        t += timedelta(minutes=SLOT_MINUTES)
    return slots


# --------------------------------------------------------------------------
# Public pages and authentication
# --------------------------------------------------------------------------
@app.route("/")
def index():
    db = get_db()
    dept = request.args.get("dept", type=int)
    sql = DOCTOR_SELECT + " WHERE d.active = 1"
    params = []
    if dept:
        sql += " AND d.department_id = ?"
        params.append(dept)
    doctors = db.execute(sql + " ORDER BY dep.name, u.name", params).fetchall()
    departments = db.execute("SELECT * FROM departments ORDER BY name").fetchall()
    return render_template("index.html", doctors=doctors,
                           departments=departments, selected=dept)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        errors = []
        if len(name) < 2:
            errors.append("Please enter your full name.")
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            errors.append("Please enter a valid email address.")
        if phone and not re.fullmatch(r"[0-9+\- ]{7,15}", phone):
            errors.append("Phone number may contain only digits, +, - and spaces (7-15 characters).")
        if len(password) < 6:
            errors.append("Password must be at least 6 characters.")
        if password != request.form.get("confirm", ""):
            errors.append("Passwords do not match.")
        if not errors:
            try:
                db = get_db()
                db.execute(
                    "INSERT INTO users (name, email, password_hash, role, phone) "
                    "VALUES (?, ?, ?, 'patient', ?)",
                    (name, email, generate_password_hash(password), phone))
                db.commit()
                flash("Registration successful. Please log in.", "success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                errors.append("This email is already registered.")
        for e in errors:
            flash(e, "danger")
        return render_template("register.html", form=request.form)
    return render_template("register.html", form={})


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Incorrect email or password.", "danger")
        else:
            if user["role"] == "doctor":
                doc = db.execute("SELECT active FROM doctors WHERE user_id = ?",
                                 (user["id"],)).fetchone()
                if doc is None or not doc["active"]:
                    flash("This doctor account has been deactivated.", "danger")
                    return render_template("login.html")
            session.clear()
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]
            flash("Welcome, %s!" % user["name"], "success")
            return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required()
def dashboard():
    target = {"patient": "patient_home", "doctor": "doctor_home", "admin": "admin_home"}
    return redirect(url_for(target[session["role"]]))


# --------------------------------------------------------------------------
# Patient
# --------------------------------------------------------------------------
@app.route("/patient")
@login_required("patient")
def patient_home():
    appts = get_db().execute(
        """SELECT a.*, u.name AS doctor_name, dep.name AS department, d.fee
           FROM appointments a
           JOIN doctors d ON d.id = a.doctor_id
           JOIN users u ON u.id = d.user_id
           JOIN departments dep ON dep.id = d.department_id
           WHERE a.patient_id = ?
           ORDER BY a.appt_date DESC, a.appt_time DESC""",
        (session["user_id"],)).fetchall()
    return render_template("patient_dashboard.html", appts=appts,
                           today=date.today().isoformat())


@app.route("/book/<int:doctor_id>", methods=["GET", "POST"])
@login_required("patient")
def book(doctor_id):
    db = get_db()
    doctor = get_doctor(db, doctor_id)
    if doctor is None or not doctor["active"]:
        abort(404, "Doctor not found.")
    today = date.today()
    last_day = today + timedelta(days=MAX_ADVANCE_DAYS)

    raw = request.form.get("date") if request.method == "POST" else request.args.get("date")
    day = parse_date(raw) if raw else today
    error = None
    if day is None or not (today <= day <= last_day):
        error = "Please choose a date between %s and %s." % (today, last_day)
        day = today

    if request.method == "POST" and error is None:
        slot = request.form.get("slot", "")
        reason = request.form.get("reason", "").strip()[:300]
        if slot not in available_slots(db, doctor, day):
            error = "That time slot is not available. Please pick another."
        else:
            try:
                db.execute(
                    "INSERT INTO appointments (patient_id, doctor_id, appt_date, appt_time, reason) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (session["user_id"], doctor_id, day.isoformat(), slot, reason))
                db.commit()
            except sqlite3.IntegrityError:
                error = "Sorry, someone just booked that slot. Please pick another."
            else:
                flash("Appointment booked with %s on %s at %s."
                      % (doctor["name"], day.strftime("%d %b %Y"), slot), "success")
                return redirect(url_for("patient_home"))
    if error:
        flash(error, "danger")
    return render_template("book.html", doctor=doctor, day=day, today=today,
                           last_day=last_day, slots=available_slots(db, doctor, day))


@app.route("/appointment/<int:appt_id>/cancel", methods=["POST"])
@login_required()
def cancel_appointment(appt_id):
    db = get_db()
    appt = db.execute(
        "SELECT a.*, d.user_id AS doctor_user FROM appointments a "
        "JOIN doctors d ON d.id = a.doctor_id WHERE a.id = ?", (appt_id,)).fetchone()
    if appt is None:
        abort(404, "Appointment not found.")
    uid, role = session["user_id"], session["role"]
    allowed = (role == "admin"
               or (role == "patient" and appt["patient_id"] == uid)
               or (role == "doctor" and appt["doctor_user"] == uid))
    if not allowed:
        abort(403, "You cannot cancel this appointment.")
    if appt["status"] != "Booked":
        flash("Only booked appointments can be cancelled.", "warning")
    else:
        db.execute("UPDATE appointments SET status = 'Cancelled' WHERE id = ?", (appt_id,))
        db.commit()
        flash("Appointment cancelled.", "info")
    return redirect(url_for("dashboard"))


# --------------------------------------------------------------------------
# Doctor
# --------------------------------------------------------------------------
@app.route("/doctor")
@login_required("doctor")
def doctor_home():
    db = get_db()
    doctor = current_doctor(db)
    rows = db.execute(
        """SELECT a.*, p.name AS patient_name, p.phone AS patient_phone
           FROM appointments a JOIN users p ON p.id = a.patient_id
           WHERE a.doctor_id = ?
           ORDER BY a.appt_date, a.appt_time""", (doctor["id"],)).fetchall()
    today = date.today().isoformat()
    upcoming = [a for a in rows if a["status"] == "Booked"]
    history = [a for a in reversed(rows) if a["status"] != "Booked"]
    return render_template("doctor_dashboard.html", doctor=doctor,
                           upcoming=upcoming, history=history, today=today)


@app.route("/doctor/appointment/<int:appt_id>/complete", methods=["POST"])
@login_required("doctor")
def complete_appointment(appt_id):
    db = get_db()
    doctor = current_doctor(db)
    appt = db.execute("SELECT * FROM appointments WHERE id = ? AND doctor_id = ?",
                      (appt_id, doctor["id"])).fetchone()
    if appt is None:
        abort(404, "Appointment not found.")
    if appt["status"] != "Booked":
        flash("This appointment is not in 'Booked' state.", "warning")
    elif appt["appt_date"] > date.today().isoformat():
        flash("You can complete an appointment only on or after its date.", "warning")
    else:
        notes = request.form.get("prescription", "").strip()[:1000]
        db.execute("UPDATE appointments SET status = 'Completed', prescription = ? WHERE id = ?",
                   (notes, appt_id))
        db.commit()
        flash("Appointment marked as completed.", "success")
    return redirect(url_for("doctor_home"))


@app.route("/doctor/schedule", methods=["GET", "POST"])
@login_required("doctor")
def doctor_schedule():
    db = get_db()
    doctor = current_doctor(db)
    if request.method == "POST":
        days = sorted({int(d) for d in request.form.getlist("days") if d in "0123456"})
        start = request.form.get("start_hour", type=int)
        end = request.form.get("end_hour", type=int)
        if not days:
            flash("Select at least one working day.", "danger")
        elif start is None or end is None or not (0 <= start < end <= 23):
            flash("Working hours must satisfy: start is earlier than end (0-23).", "danger")
        else:
            db.execute("UPDATE doctors SET days = ?, start_hour = ?, end_hour = ? WHERE id = ?",
                       (",".join(map(str, days)), start, end, doctor["id"]))
            db.commit()
            flash("Schedule updated.", "success")
            return redirect(url_for("doctor_schedule"))
    return render_template("doctor_schedule.html", doctor=doctor,
                           working=doctor_days(doctor), day_names=DAY_NAMES)


# --------------------------------------------------------------------------
# Admin
# --------------------------------------------------------------------------
@app.route("/admin")
@login_required("admin")
def admin_home():
    db = get_db()
    one = lambda sql, *p: db.execute(sql, p).fetchone()[0]
    stats = {
        "patients": one("SELECT COUNT(*) FROM users WHERE role = 'patient'"),
        "doctors": one("SELECT COUNT(*) FROM doctors WHERE active = 1"),
        "today": one("SELECT COUNT(*) FROM appointments WHERE appt_date = ? AND status <> 'Cancelled'",
                     date.today().isoformat()),
        "booked": one("SELECT COUNT(*) FROM appointments WHERE status = 'Booked'"),
        "completed": one("SELECT COUNT(*) FROM appointments WHERE status = 'Completed'"),
        "cancelled": one("SELECT COUNT(*) FROM appointments WHERE status = 'Cancelled'"),
    }
    status = request.args.get("status", "")
    sql = """SELECT a.*, p.name AS patient_name, u.name AS doctor_name
             FROM appointments a
             JOIN users p ON p.id = a.patient_id
             JOIN doctors d ON d.id = a.doctor_id
             JOIN users u ON u.id = d.user_id"""
    params = []
    if status in ("Booked", "Completed", "Cancelled"):
        sql += " WHERE a.status = ?"
        params.append(status)
    appts = db.execute(sql + " ORDER BY a.appt_date DESC, a.appt_time DESC LIMIT 100",
                       params).fetchall()
    return render_template("admin_dashboard.html", stats=stats, appts=appts, status=status)


@app.route("/admin/doctors")
@login_required("admin")
def admin_doctors():
    db = get_db()
    doctors = db.execute(DOCTOR_SELECT + " ORDER BY d.active DESC, u.name").fetchall()
    departments = db.execute("SELECT * FROM departments ORDER BY name").fetchall()
    return render_template("admin_doctors.html", doctors=doctors,
                           departments=departments, form={})


@app.route("/admin/doctors/add", methods=["POST"])
@login_required("admin")
def admin_add_doctor():
    db = get_db()
    f = request.form
    name = f.get("name", "").strip()
    email = f.get("email", "").strip().lower()
    password = f.get("password", "")
    qualification = f.get("qualification", "").strip()
    dept_id = f.get("department_id", type=int)
    fee = f.get("fee", type=int)
    errors = []
    if len(name) < 2:
        errors.append("Doctor name is required.")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        errors.append("Enter a valid email address.")
    if len(password) < 6:
        errors.append("Password must be at least 6 characters.")
    if fee is None or not (0 <= fee <= 10000):
        errors.append("Consultation fee must be between 0 and 10000.")
    if not db.execute("SELECT 1 FROM departments WHERE id = ?", (dept_id,)).fetchone():
        errors.append("Please choose a department.")
    if not errors:
        try:
            cur = db.execute(
                "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'doctor')",
                (name, email, generate_password_hash(password)))
            db.execute(
                "INSERT INTO doctors (user_id, department_id, qualification, fee) VALUES (?, ?, ?, ?)",
                (cur.lastrowid, dept_id, qualification, fee))
            db.commit()
            flash("Doctor %s added." % name, "success")
            return redirect(url_for("admin_doctors"))
        except sqlite3.IntegrityError:
            db.rollback()
            errors.append("A user with this email already exists.")
    for e in errors:
        flash(e, "danger")
    doctors = db.execute(DOCTOR_SELECT + " ORDER BY d.active DESC, u.name").fetchall()
    departments = db.execute("SELECT * FROM departments ORDER BY name").fetchall()
    return render_template("admin_doctors.html", doctors=doctors,
                           departments=departments, form=f)


@app.route("/admin/doctors/<int:doctor_id>/toggle", methods=["POST"])
@login_required("admin")
def admin_toggle_doctor(doctor_id):
    db = get_db()
    doctor = get_doctor(db, doctor_id)
    if doctor is None:
        abort(404, "Doctor not found.")
    db.execute("UPDATE doctors SET active = ? WHERE id = ?", (0 if doctor["active"] else 1, doctor_id))
    db.commit()
    flash("%s is now %s." % (doctor["name"], "inactive" if doctor["active"] else "active"), "info")
    return redirect(url_for("admin_doctors"))


@app.route("/admin/departments/add", methods=["POST"])
@login_required("admin")
def admin_add_department():
    name = request.form.get("name", "").strip()
    if len(name) < 2:
        flash("Department name is required.", "danger")
    else:
        try:
            db = get_db()
            db.execute("INSERT INTO departments (name) VALUES (?)", (name,))
            db.commit()
            flash("Department added.", "success")
        except sqlite3.IntegrityError:
            flash("That department already exists.", "warning")
    return redirect(url_for("admin_doctors"))


# --------------------------------------------------------------------------
# Error pages
# --------------------------------------------------------------------------
def handle_error(e):
    return render_template("error.html", code=e.code, message=e.description), e.code


for _code in (400, 403, 404):
    app.register_error_handler(_code, handle_error)


if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(debug=True)  # set debug=False when deploying
