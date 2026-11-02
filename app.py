"""Healthcare Aide - Flask application (upgraded).
Run:  python app.py        (see README.md for full setup)"""
import json
import logging
import re
import secrets
import time
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path

from flask import (Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for)
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

import chat_service
import db as database
from config import Config

BASE = Path(__file__).parent
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+?\d{10,15}$")
GENDERS = ("female", "male", "other", "prefer-not-to-say")
BLOOD_GROUPS = ("A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-")


def _load(name):
    return json.loads((BASE / "data" / name).read_text(encoding="utf-8"))


def create_app(overrides=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if overrides:
        app.config.update(overrides)
    logging.basicConfig(level=logging.INFO)
    if not app.config["SECRET_KEY_FROM_ENV"] and not (overrides or {}).get("TESTING"):
        app.logger.warning("SECRET_KEY is not set in .env - using a temporary random key; sessions reset on restart.")

    SPECIALTIES = _load("specialties.json")
    MEDICINES = _load("medicines.json")
    CONTENT = _load("content.json")
    SPEC_BY_SLUG = {s["slug"]: s for s in SPECIALTIES}
    app.teardown_appcontext(database.close_db)

    # ------------------------------------------------------------------ helpers
    def db():
        return database.get_db()

    def cfg():
        return app.config

    def current_user():
        uid = session.get("user_id")
        if not uid:
            return None
        return db().one("SELECT * FROM patient WHERE id=%s", (uid,))

    def is_admin(user):
        return bool(user) and user["email"].lower() in cfg()["ADMIN_EMAILS"]

    def wants_json():
        return request.path.startswith("/api/")

    def login_required(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if "user_id" not in session:
                if wants_json():
                    return jsonify(success=False, message="Please log in first."), 401
                flash("Please log in to continue.", "info")
                return redirect(url_for("login", next=request.full_path.rstrip("?")))
            return fn(*a, **kw)
        return wrapper

    def safe_next(target):
        return target if target and target.startswith("/") and not target.startswith("//") else url_for("dashboard")

    def clean(value, maxlen=200):
        return re.sub(r"\s+", " ", (value or "").strip())[:maxlen]

    def notify(patient_id, title, body=""):
        db().run("INSERT INTO notifications (patient_id,title,body,is_read,created_at) VALUES (%s,%s,%s,0,%s)",
                 (patient_id, title[:160], body[:400], now_str()))

    def now_str():
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def password_problem(pw):
        if len(pw) < 8:
            return "Password must be at least 8 characters."
        if not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
            return "Password must contain at least one letter and one number."
        if len(pw) > 128:
            return "Password is too long."
        return None

    # simple in-memory throttles (single-process); use Redis/Flask-Limiter when deploying at scale
    attempts = {}

    def throttled(key, limit, window):
        now = time.time()
        recent = [t for t in attempts.get(key, []) if now - t < window]
        attempts[key] = recent
        return len(recent) >= limit

    def record(key):
        attempts.setdefault(key, []).append(time.time())

    def time_slots():
        c = cfg()
        h, m = map(int, c["CLINIC_START"].split(":")); start = h * 60 + m
        h, m = map(int, c["CLINIC_END"].split(":")); end = h * 60 + m
        return [f"{t // 60:02d}:{t % 60:02d}" for t in range(start, end + 1, c["SLOT_MINUTES"])]

    def appt_view(a):
        when = datetime.strptime(f"{a['appointment_date']} {a['appointment_time']}", "%Y-%m-%d %H:%M")
        a["when"] = when
        a["specialty_name"] = SPEC_BY_SLUG.get(a["doctor_specialty"], {}).get("name", a["doctor_specialty"].title())
        a["display_date"] = when.strftime("%a, %d %b %Y")
        a["display_time"] = when.strftime("%I:%M %p")
        if a["status"] == "cancelled":
            a["state"] = "cancelled"
        elif when < datetime.now():
            a["state"] = "completed"
        else:
            a["state"] = "upcoming"
        return a

    def validate_slot(d_str, t_str):
        """Returns (error, date_str, time_str)."""
        try:
            d = datetime.strptime(d_str or "", "%Y-%m-%d").date()
        except ValueError:
            return "Please choose a valid date.", None, None
        if t_str not in time_slots():
            return "Please choose a valid time slot.", None, None
        if d < date.today():
            return "You cannot book an appointment in the past.", None, None
        if d > date.today() + timedelta(days=cfg()["MAX_BOOKING_DAYS_AHEAD"]):
            return f"Appointments can be booked up to {cfg()['MAX_BOOKING_DAYS_AHEAD']} days ahead.", None, None
        if datetime.strptime(f"{d} {t_str}", "%Y-%m-%d %H:%M") <= datetime.now():
            return "That time has already passed. Please pick a later slot.", None, None
        return None, d.isoformat(), t_str

    def slot_conflict(pid, specialty, d, t, exclude_id=0):
        own_same_time = db().one(
            "SELECT id FROM appointments WHERE patient_id=%s AND status='confirmed' AND appointment_date=%s "
            "AND appointment_time=%s AND id<>%s", (pid, d, t, exclude_id))
        if own_same_time:
            return "You already have an appointment at that date and time."
        same_day_spec = db().one(
            "SELECT id FROM appointments WHERE patient_id=%s AND status='confirmed' AND doctor_specialty=%s "
            "AND appointment_date=%s AND id<>%s", (pid, specialty, d, exclude_id))
        if same_day_spec:
            return "You already have an appointment with this specialty on that day."
        taken = db().one(
            "SELECT COUNT(*) AS n FROM appointments WHERE status='confirmed' AND doctor_specialty=%s "
            "AND appointment_date=%s AND appointment_time=%s AND id<>%s", (specialty, d, t, exclude_id))
        if taken and taken["n"] >= cfg()["SLOT_CAPACITY"]:
            return "That time slot is full. Please choose another time."
        return None

    # ------------------------------------------------------------------ request hooks
    @app.context_processor
    def inject():
        user, unread = None, 0
        if "user_id" in session:
            try:
                user = current_user()
                if user is None:
                    session.clear()
                else:
                    unread = db().one("SELECT COUNT(*) AS n FROM notifications WHERE patient_id=%s AND is_read=0",
                                      (user["id"],))["n"]
            except Exception:
                app.logger.exception("context lookup failed")
        c = cfg()
        return dict(
            csrf_token=lambda: session.setdefault("csrf", secrets.token_hex(16)),
            logged_in=bool(user), user=user, user_name=user["first_name"] if user else None,
            unread_count=unread, is_admin=is_admin(user), year=date.today().year,
            emergency_number=c["EMERGENCY_NUMBER"], ambulance_number=c["AMBULANCE_NUMBER"],
            support=dict(email=c["SUPPORT_EMAIL"], phone=c["SUPPORT_PHONE"], address=c["SUPPORT_ADDRESS"], hours=c["SUPPORT_HOURS"]),
        )

    @app.before_request
    def csrf_protect():
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            sent = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
            if not sent or sent != session.get("csrf"):
                if wants_json():
                    return jsonify(success=False, message="Your session expired. Please refresh the page."), 400
                flash("Your session expired. Please try again.", "danger")
                return redirect(request.referrer or url_for("index"))

    @app.after_request
    def security_headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        resp.headers["Permissions-Policy"] = "geolocation=(self), microphone=(self)"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' https://unpkg.com; style-src 'self' 'unsafe-inline' https://unpkg.com; "
            "img-src 'self' data: https://tile.openstreetmap.org https://*.tile.openstreetmap.org https://unpkg.com; "
            "connect-src 'self' https://nominatim.openstreetmap.org https://overpass-api.de https://overpass.kumi.systems; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        if request.path.startswith("/api/") or "user_id" in session:
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.errorhandler(Exception)
    def on_error(exc):
        if isinstance(exc, HTTPException):
            code, msg = exc.code, exc.description
        else:
            app.logger.exception("Unhandled error")
            code, msg = 500, "Something went wrong on our side. Please try again in a moment."
        if wants_json():
            return jsonify(success=False, message=msg), code
        titles = {404: "Page not found", 403: "Not allowed", 405: "Not allowed", 429: "Too many requests"}
        return render_template("error.html", code=code, title=titles.get(code, "Something went wrong"), message=msg), code

    # ------------------------------------------------------------------ public pages
    @app.route("/")
    def index():
        return render_template("index.html", specialties=SPECIALTIES[:6])

    @app.route("/health")
    def health_hub():
        return render_template("health.html", articles=CONTENT["articles"], tip=daily_tip())

    @app.route("/health/<slug>")
    def article(slug):
        a = next((x for x in CONTENT["articles"] if x["slug"] == slug), None)
        if not a:
            abort(404)
        return render_template("article.html", article=a)

    def daily_tip():
        tips = CONTENT["tips"]
        return tips[date.today().toordinal() % len(tips)]

    @app.route("/emergency")
    def emergency():
        extra = []
        for part in cfg()["EXTRA_EMERGENCY_CONTACTS"].split(";"):
            if ":" in part:
                label, number = part.split(":", 1)
                if label.strip() and number.strip():
                    extra.append((label.strip(), number.strip()))
        return render_template("emergency.html", extra=extra)

    @app.route("/specialization")
    def specialization():
        counts = {}
        try:
            for r in db().all("SELECT specialty, COUNT(*) AS n FROM doctors GROUP BY specialty"):
                counts[(r["specialty"] or "").lower()] = r["n"]
        except Exception:
            app.logger.exception("doctor counts failed")
        return render_template("specialization.html", specialties=SPECIALTIES, counts=counts)

    @app.route("/medicine")
    def medicine_info():
        q = clean(request.args.get("q"), 60).lower()
        items = [m for m in MEDICINES if not q or q in m["name"].lower() or q in m["type"].lower() or q in m["uses"].lower()]
        return render_template("medicine.html", medicines=items, q=q, total=len(MEDICINES))

    @app.route("/hospital")
    def hospital_finder():
        return render_template("hospital.html")

    @app.route("/chatbot")
    def chatbot():
        return render_template("chatbot.html")

    @app.route("/contact")
    def contact():
        return render_template("contact.html", faqs=CONTENT["faqs"])

    @app.route("/contact", methods=["POST"])
    def contact_post():
        f = {k: clean(request.form.get(k), 2000 if k == "message" else 160) for k in
             ("firstName", "lastName", "email", "phone", "subject", "message")}
        if not (f["firstName"] and f["email"] and f["subject"] and len(f["message"]) >= 10):
            flash("Please fill in your name, email, subject and a message of at least 10 characters.", "danger")
            return redirect(url_for("contact") + "#contact-form")
        if not EMAIL_RE.match(f["email"]):
            flash("Please enter a valid email address.", "danger")
            return redirect(url_for("contact") + "#contact-form")
        db().run("INSERT INTO contact_messages (first_name,last_name,email,phone,subject,message,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                 (f["firstName"], f["lastName"], f["email"], f["phone"][:20], f["subject"], f["message"], now_str()))
        db().commit()
        flash("Thank you! Your message was sent. We will reply to your email.", "success")
        return redirect(url_for("contact"))

    @app.route("/feedback", methods=["POST"])
    def feedback_post():
        category = clean(request.form.get("category"), 30)
        message = clean(request.form.get("message"), 2000)
        try:
            rating = int(request.form.get("rating") or 0)
        except ValueError:
            rating = 0
        if category not in ("suggestion", "bug", "compliment", "other") or len(message) < 5 or not 0 <= rating <= 5:
            flash("Please choose a category and write at least a few words of feedback.", "danger")
            return redirect(url_for("contact") + "#feedback-form")
        db().run("INSERT INTO feedback (patient_id,category,rating,message,created_at) VALUES (%s,%s,%s,%s,%s)",
                 (session.get("user_id"), category, rating or None, message, now_str()))
        db().commit()
        flash("Thank you for your feedback!", "success")
        return redirect(url_for("contact") + "#feedback-form")

    # ------------------------------------------------------------------ auth
    @app.route("/signup")
    def signup():
        if "user_id" in session:
            return redirect(url_for("dashboard"))
        return render_template("signup.html", form={})

    @app.route("/signup", methods=["POST"])
    def signup_post():
        f = {k: clean(request.form.get(k), 160) for k in ("firstName", "lastName", "email", "phone")}
        pw, pw2 = request.form.get("password", ""), request.form.get("confirmPassword", "")
        f["email"] = f["email"].lower()
        error = None
        if not f["firstName"] or not f["lastName"]:
            error = "Please enter your first and last name."
        elif not EMAIL_RE.match(f["email"]):
            error = "Please enter a valid email address."
        elif f["phone"] and not PHONE_RE.match(f["phone"].replace(" ", "")):
            error = "Phone number should have 10 to 15 digits."
        elif pw != pw2:
            error = "Passwords do not match."
        else:
            error = password_problem(pw)
        if not request.form.get("terms") and not error:
            error = "Please accept the terms to create an account."
        if error:
            flash(error, "danger")
            return render_template("signup.html", form=f), 400
        try:
            if db().one("SELECT id FROM patient WHERE email=%s", (f["email"],)):
                raise ValueError("duplicate")
            db().run("INSERT INTO patient (first_name,last_name,email,phone,password,created_at) VALUES (%s,%s,%s,%s,%s,%s)",
                     (f["firstName"], f["lastName"], f["email"], f["phone"].replace(" ", ""), generate_password_hash(pw), now_str()))
            db().commit()
        except ValueError:
            flash("That email is already registered. Please log in.", "danger")
            return render_template("signup.html", form=f), 409
        except Exception as exc:
            db().rollback()
            if "uplicate" in str(exc) or "UNIQUE" in str(exc):
                flash("That email is already registered. Please log in.", "danger")
                return render_template("signup.html", form=f), 409
            raise
        flash("Account created! Please log in.", "success")
        return redirect(url_for("login"))

    @app.route("/login")
    def login():
        if "user_id" in session:
            return redirect(url_for("dashboard"))
        return render_template("login.html", next=request.args.get("next", ""))

    @app.route("/login", methods=["POST"])
    def login_post():
        email = clean(request.form.get("email"), 190).lower()
        password = request.form.get("password", "")
        nxt = request.form.get("next", "")
        key = f"login:{request.remote_addr}:{email}"
        if throttled(key, 5, 300):
            flash("Too many failed attempts. Please wait 5 minutes and try again.", "danger")
            return render_template("login.html", next=nxt), 429
        user = db().one("SELECT * FROM patient WHERE email=%s", (email,)) if email else None
        if not user or not check_password_hash(user["password"], password):
            record(key)
            flash("Invalid email or password.", "danger")
            return render_template("login.html", next=nxt), 401
        session.clear()  # prevents session fixation
        session.permanent = True
        session["user_id"] = user["id"]
        session["csrf"] = secrets.token_hex(16)
        attempts.pop(key, None)
        flash(f"Welcome back, {user['first_name']}!", "success")
        return redirect(safe_next(nxt))

    @app.route("/logout", methods=["POST"])
    def logout():
        session.clear()
        flash("You have been logged out.", "info")
        return redirect(url_for("login"))

    # ------------------------------------------------------------------ dashboard & profile
    @app.route("/dashboard")
    @login_required
    def dashboard():
        user = current_user()
        rows = [appt_view(a) for a in db().all(
            "SELECT * FROM appointments WHERE patient_id=%s ORDER BY appointment_date, appointment_time", (user["id"],))]
        upcoming = [a for a in rows if a["state"] == "upcoming"][:3]
        past = sorted([a for a in rows if a["state"] != "upcoming"], key=lambda a: a["when"], reverse=True)[:5]
        notes = db().all("SELECT * FROM notifications WHERE patient_id=%s ORDER BY id DESC LIMIT 4", (user["id"],))
        return render_template("dashboard.html", upcoming=upcoming, past=past, notes=notes, tip=daily_tip(),
                               articles=CONTENT["articles"][:3])

    @app.route("/profile")
    @login_required
    def profile():
        return render_template("profile.html", genders=GENDERS, blood_groups=BLOOD_GROUPS)

    @app.route("/profile", methods=["POST"])
    @login_required
    def profile_post():
        f = {k: clean(request.form.get(k), 120) for k in
             ("first_name", "last_name", "phone", "date_of_birth", "gender", "city", "blood_group",
              "emergency_contact_name", "emergency_contact_phone")}
        error = None
        if not f["first_name"] or not f["last_name"]:
            error = "First and last name are required."
        elif f["phone"] and not PHONE_RE.match(f["phone"].replace(" ", "")):
            error = "Phone number should have 10 to 15 digits."
        elif f["emergency_contact_phone"] and not PHONE_RE.match(f["emergency_contact_phone"].replace(" ", "")):
            error = "Emergency contact phone should have 10 to 15 digits."
        elif f["gender"] and f["gender"] not in GENDERS:
            error = "Please choose a valid gender option."
        elif f["blood_group"] and f["blood_group"] not in BLOOD_GROUPS:
            error = "Please choose a valid blood group."
        elif f["date_of_birth"]:
            try:
                dob = datetime.strptime(f["date_of_birth"], "%Y-%m-%d").date()
                if dob > date.today() or dob.year < 1900:
                    error = "Please enter a valid date of birth."
            except ValueError:
                error = "Please enter a valid date of birth."
        if error:
            flash(error, "danger")
            return redirect(url_for("profile"))
        db().run("UPDATE patient SET first_name=%s,last_name=%s,phone=%s,date_of_birth=%s,gender=%s,city=%s,blood_group=%s,"
                 "emergency_contact_name=%s,emergency_contact_phone=%s WHERE id=%s",
                 (f["first_name"], f["last_name"], f["phone"].replace(" ", ""), f["date_of_birth"], f["gender"], f["city"],
                  f["blood_group"], f["emergency_contact_name"], f["emergency_contact_phone"].replace(" ", ""), session["user_id"]))
        db().commit()
        flash("Your profile was updated.", "success")
        return redirect(url_for("profile"))

    @app.route("/profile/password", methods=["POST"])
    @login_required
    def change_password():
        user = current_user()
        cur, new, conf = (request.form.get(k, "") for k in ("current_password", "new_password", "confirm_password"))
        key = f"pw:{user['id']}"
        if throttled(key, 5, 300):
            flash("Too many attempts. Please wait a few minutes.", "danger")
        elif not check_password_hash(user["password"], cur):
            record(key)
            flash("Your current password is incorrect.", "danger")
        elif new != conf:
            flash("New passwords do not match.", "danger")
        elif new == cur:
            flash("Please choose a password different from your current one.", "danger")
        elif password_problem(new):
            flash(password_problem(new), "danger")
        else:
            db().run("UPDATE patient SET password=%s WHERE id=%s", (generate_password_hash(new), user["id"]))
            notify(user["id"], "Password changed", "Your password was changed. If this wasn't you, contact support.")
            db().commit()
            flash("Password changed successfully.", "success")
        return redirect(url_for("profile") + "#security")

    # ------------------------------------------------------------------ appointments
    @app.route("/appointment")
    def appointment():
        if "user_id" not in session:
            flash("Please log in to book an appointment.", "info")
            return redirect(url_for("login", next=request.full_path.rstrip("?")))
        return render_booking()

    def render_booking(form=None, status=200):
        user = current_user()
        pre = request.args.get("specialty", "")
        form = form or dict(patient_name=f"{user['first_name']} {user['last_name']}", patient_email=user["email"],
                            patient_phone=user["phone"] or "", doctor_specialty=pre if pre in SPEC_BY_SLUG else "")
        today = date.today()
        return render_template("appointment.html", form=form, specialties=SPECIALTIES, slots=time_slots(),
                               min_date=today.isoformat(), max_date=(today + timedelta(days=cfg()["MAX_BOOKING_DAYS_AHEAD"])).isoformat()), status

    @app.route("/appointment", methods=["POST"])
    @login_required
    def appointment_post():
        user = current_user()
        f = {k: clean(request.form.get(k), 500 if k == "reason" else 160) for k in
             ("patient_name", "patient_email", "patient_phone", "doctor_specialty", "appointment_date", "appointment_time", "reason")}
        f["patient_phone"] = f["patient_phone"].replace(" ", "")
        error = None
        if not all(f.values()):
            error = "Please fill in all the fields."
        elif not EMAIL_RE.match(f["patient_email"]):
            error = "Please enter a valid email address."
        elif not PHONE_RE.match(f["patient_phone"]):
            error = "Phone number should have 10 to 15 digits."
        elif f["doctor_specialty"] not in SPEC_BY_SLUG:
            error = "Please choose a valid specialty."
        elif len(f["reason"]) < 3:
            error = "Please describe the reason for your visit."
        if not error:
            error, d, t = validate_slot(f["appointment_date"], f["appointment_time"])
        if not error:
            error = slot_conflict(user["id"], f["doctor_specialty"], d, t)
        if error:
            flash(error, "danger")
            return render_booking(f, 400)
        appt_id, _ = db().run(
            "INSERT INTO appointments (patient_id,patient_name,patient_email,patient_phone,doctor_specialty,appointment_date,"
            "appointment_time,reason,status,created_at,updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'confirmed',%s,%s)",
            (user["id"], f["patient_name"], f["patient_email"], f["patient_phone"], f["doctor_specialty"], d, t, f["reason"], now_str(), now_str()))
        name = SPEC_BY_SLUG[f["doctor_specialty"]]["name"]
        notify(user["id"], "Appointment confirmed", f"{name} on {d} at {t}.")
        db().commit()
        flash("Your appointment is confirmed!", "success")
        return redirect(url_for("appointment_confirmation", appt_id=appt_id))

    @app.route("/appointment/<int:appt_id>/confirmation")
    @login_required
    def appointment_confirmation(appt_id):
        a = db().one("SELECT * FROM appointments WHERE id=%s AND patient_id=%s", (appt_id, session["user_id"]))
        if not a:
            abort(404)
        return render_template("appointment_confirmation.html", a=appt_view(a))

    @app.route("/appointments")
    @login_required
    def my_appointments():
        rows = [appt_view(a) for a in db().all(
            "SELECT * FROM appointments WHERE patient_id=%s ORDER BY appointment_date, appointment_time", (session["user_id"],))]
        upcoming = [a for a in rows if a["state"] == "upcoming"]
        history = sorted([a for a in rows if a["state"] != "upcoming"], key=lambda a: a["when"], reverse=True)
        today = date.today()
        return render_template("appointments.html", upcoming=upcoming, history=history, slots=time_slots(),
                               min_date=today.isoformat(), max_date=(today + timedelta(days=cfg()["MAX_BOOKING_DAYS_AHEAD"])).isoformat())

    def own_active_appointment(appt_id):
        a = db().one("SELECT * FROM appointments WHERE id=%s AND patient_id=%s", (appt_id, session["user_id"]))
        if not a:
            abort(404)
        return appt_view(a)

    @app.route("/appointment/<int:appt_id>/cancel", methods=["POST"])
    @login_required
    def cancel_appointment(appt_id):
        a = own_active_appointment(appt_id)
        if a["state"] != "upcoming":
            flash("Only upcoming appointments can be cancelled.", "danger")
        else:
            db().run("UPDATE appointments SET status='cancelled', updated_at=%s WHERE id=%s", (now_str(), appt_id))
            notify(session["user_id"], "Appointment cancelled", f"{a['specialty_name']} on {a['appointment_date']} at {a['appointment_time']}.")
            db().commit()
            flash("Your appointment was cancelled.", "success")
        return redirect(url_for("my_appointments"))

    @app.route("/appointment/<int:appt_id>/reschedule", methods=["POST"])
    @login_required
    def reschedule_appointment(appt_id):
        a = own_active_appointment(appt_id)
        if a["state"] != "upcoming":
            flash("Only upcoming appointments can be rescheduled.", "danger")
            return redirect(url_for("my_appointments"))
        error, d, t = validate_slot(request.form.get("appointment_date"), request.form.get("appointment_time"))
        if not error:
            error = slot_conflict(session["user_id"], a["doctor_specialty"], d, t, exclude_id=appt_id)
        if error:
            flash(error, "danger")
        else:
            db().run("UPDATE appointments SET appointment_date=%s, appointment_time=%s, updated_at=%s WHERE id=%s", (d, t, now_str(), appt_id))
            notify(session["user_id"], "Appointment rescheduled", f"{a['specialty_name']} is now on {d} at {t}.")
            db().commit()
            flash("Your appointment was rescheduled.", "success")
        return redirect(url_for("my_appointments"))

    @app.route("/api/appointments")
    @login_required
    def api_appointments():
        rows = [appt_view(a) for a in db().all(
            "SELECT * FROM appointments WHERE patient_id=%s ORDER BY appointment_date DESC, appointment_time DESC", (session["user_id"],))]
        for a in rows:
            a.pop("when", None)
        return jsonify(success=True, appointments=rows)

    # ------------------------------------------------------------------ notifications
    @app.route("/notifications")
    @login_required
    def notifications():
        rows = db().all("SELECT * FROM notifications WHERE patient_id=%s ORDER BY id DESC LIMIT 50", (session["user_id"],))
        return render_template("notifications.html", notes=rows)

    @app.route("/notifications/read", methods=["POST"])
    @login_required
    def notifications_read():
        db().run("UPDATE notifications SET is_read=1 WHERE patient_id=%s", (session["user_id"],))
        db().commit()
        return redirect(url_for("notifications"))

    # ------------------------------------------------------------------ medicines API
    @app.route("/api/medicines/suggest")
    def api_medicine_suggest():
        q = clean(request.args.get("q"), 40).lower()
        if len(q) < 1:
            return jsonify(success=True, suggestions=[])
        starts = [m["name"] for m in MEDICINES if m["name"].lower().startswith(q)]
        contains = [m["name"] for m in MEDICINES if q in m["name"].lower() and m["name"] not in starts]
        return jsonify(success=True, suggestions=(starts + contains)[:8])

    # ------------------------------------------------------------------ doctors API (original endpoints kept)
    @app.route("/api/specialists")
    def api_get_specialists():
        specialty = clean(request.args.get("specialty"), 60).lower()
        if not specialty:
            return jsonify(success=False, message="Missing specialty parameter"), 400
        rows = db().all("SELECT id, first_name, last_name, email, phone, experience_years, qualifications FROM doctors "
                        "WHERE LOWER(specialty)=%s ORDER BY experience_years DESC", (specialty,))
        return jsonify(success=True, doctors=rows)

    @app.route("/api/doctors", methods=["POST"])
    @login_required
    def api_create_doctor():
        if not is_admin(current_user()):
            return jsonify(success=False, message="Only administrators can add doctors."), 403
        data = request.get_json(silent=True) or {}
        first = clean(data.get("first_name"), 80)
        specialty = clean(data.get("specialty"), 60).lower()
        if not first or specialty not in SPEC_BY_SLUG:
            return jsonify(success=False, message="First name and a valid specialty are required."), 400
        try:
            years = max(0, min(70, int(data.get("experience_years") or 0)))
        except (TypeError, ValueError):
            years = 0
        new_id, _ = db().run(
            "INSERT INTO doctors (first_name,last_name,email,phone,specialty,experience_years,qualifications) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (first, clean(data.get("last_name"), 80), clean(data.get("email"), 190), clean(data.get("phone"), 20), specialty, years,
             clean(data.get("qualifications"), 255)))
        db().commit()
        return jsonify(success=True, id=new_id), 201

    # ------------------------------------------------------------------ chatbot API
    def chat_endpoint():
        data = request.get_json(silent=True) or {}
        message = clean(data.get("message"), 1000)
        lang = data.get("lang") if data.get("lang") in chat_service.LANGS else "en"
        if not message:
            return jsonify(success=False, message="Please type a message."), 400
        key = f"chat:{session.get('user_id') or request.remote_addr}"
        if throttled(key, 20, 60):
            return jsonify(success=False, message="You are sending messages very quickly. Please wait a moment."), 429
        record(key)
        uid = session.get("user_id")
        if uid:
            hist = list(reversed(db().all("SELECT role, content FROM chat_messages WHERE patient_id=%s ORDER BY id DESC LIMIT 8", (uid,))))
        else:
            hist = [h for h in (data.get("history") or []) if isinstance(h, dict)][-8:]
        result = chat_service.respond(message, lang, hist, cfg(), SPECIALTIES)
        for s in result["specialists"]:
            s["url"] = url_for("appointment", specialty=s["slug"])
        if uid:
            db().run("INSERT INTO chat_messages (patient_id,role,content,created_at) VALUES (%s,'user',%s,%s)", (uid, message, now_str()))
            db().run("INSERT INTO chat_messages (patient_id,role,content,created_at) VALUES (%s,'bot',%s,%s)", (uid, result["reply"], now_str()))
            db().commit()
        return jsonify(success=True, **result)

    app.add_url_rule("/api/chat", "api_chat", chat_endpoint, methods=["POST"])
    app.add_url_rule("/api/ai", "api_ai_legacy", chat_endpoint, methods=["POST"])  # old route name still works

    @app.route("/api/chat/history")
    @login_required
    def chat_history():
        rows = list(reversed(db().all("SELECT role, content, created_at FROM chat_messages WHERE patient_id=%s ORDER BY id DESC LIMIT 60", (session["user_id"],))))
        return jsonify(success=True, messages=rows)

    @app.route("/api/chat/history", methods=["DELETE"])
    @login_required
    def chat_history_clear():
        db().run("DELETE FROM chat_messages WHERE patient_id=%s", (session["user_id"],))
        db().commit()
        return jsonify(success=True)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=app.config["DEBUG"])
