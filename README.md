# Healthcare Aide — AI Healthcare Chatbot (Upgraded)

Flask + MySQL web app: AI health-information chatbot (English / हिन्दी / मराठी), appointments, medicine information, hospital finder, doctor specialties, profile, dashboard, feedback & FAQ, emergency help.

> **Medical disclaimer:** The chatbot gives general health information only. It does not diagnose or prescribe. Always consult a qualified doctor.

## Features
- **Auth & security:** hashed passwords, CSRF protection on every form/API call, secure session cookies, login throttling, input validation, security headers (CSP etc.), no secrets in code.
- **Dashboard:** welcome, profile summary, upcoming/previous appointments, notifications, daily tip, articles, emergency info.
- **Chatbot:** quick-reply buttons, typing indicator, saved history (logged-in users), clear chat, voice input (browsers with Web Speech API), 3 languages, emergency detection (never sent to AI), specialist suggestion with booking link, graceful fallback when the AI is down.
- **Appointments:** book, view upcoming/history, reschedule, cancel, confirmation page, notifications; blocks past dates, invalid slots, double-bookings and full slots.
- **Medicines:** search with suggestions; uses, side effects, precautions, Rx/OTC tag, disclaimer. **No dosage is shown** (safety).
- **Hospital finder:** OpenStreetMap data (Nominatim + Overpass), city search or "use my location", type/radius/facility filters, Google Maps directions. No fake data, no live availability. Needs internet.
- **Doctors/specialties:** search by specialty *or concern* (e.g. "knee pain"), descriptions, booking links, doctors list from your database (admins can add doctors).
- **Profile:** edit details, change password, history, logout. **Support:** contact form, feedback form, FAQ. **Health:** tips and articles.
- **UI:** responsive, light/dark mode, keyboard & screen-reader friendly (skip link, labels, focus outlines, reduced-motion).

## Setup (VS Code)
Requirements: Python 3.10+, MySQL 8 (or MariaDB 10.4+).

```bash
# 1. open the folder in VS Code, then in the terminal:
python -m venv venv
venv\Scripts\activate          # Windows      (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt

# 2. configure
copy .env.example .env         # macOS/Linux: cp .env.example .env
#   edit .env: SECRET_KEY, DB_PASSWORD, (optional) AI_API_KEY, ADMIN_EMAILS

# 3. create the database + tables (safe to re-run; also upgrades your OLD database)
python init_db.py
#   or manually:  mysql -u root -p < sql/schema.sql

# 4. run
python app.py                  # open http://127.0.0.1:5000
```

### Upgrading your existing database
Keep `DB_NAME=Healthcare_chat_bot` and run `python init_db.py`. It keeps your `patient`, `appointments`, `doctors`, `contact_messages` data, adds the new columns (profile fields, appointment `status`) and creates the new tables (`feedback`, `notifications`, `chat_messages`). Existing passwords keep working.

### AI configuration
Set `AI_API_KEY` in `.env` (OpenAI by default; for any OpenAI-compatible provider also set `AI_BASE_URL` and `AI_MODEL`). The key stays on the server and is never sent to the browser. Without a key the chatbot still answers with built-in safe guidance. The old `OPENAI_API_KEY` variable name is also accepted.

### Admin
Put your email in `ADMIN_EMAILS`, sign up with it, then open **Doctors** to register doctors.

### Emergency & support details
Edit `EMERGENCY_NUMBER`, `AMBULANCE_NUMBER`, `EXTRA_EMERGENCY_CONTACTS`, `SUPPORT_*` in `.env`.

## Tests
```bash
python -m unittest discover -s tests -v
```
Tests run on a temporary SQLite database (same SQL), so no MySQL is needed for them.

## Project layout
```
app.py  config.py  db.py  chat_service.py  init_db.py  requirements.txt  .env.example
sql/schema.sql        data/{specialties,medicines,content}.json
templates/            static/{css,js}/            tests/test_app.py
```

## Technologies
Python, Flask, MySQL (mysql-connector-python), python-dotenv, requests; HTML/CSS/vanilla JavaScript; Leaflet + OpenStreetMap; Web Speech API.

## Known limitations
- MySQL path was written to be portable but only tested via SQLite in the automated tests; test it on your machine after setup.
- Hospital finder needs internet; OSM data can be incomplete (phone/hours often missing).
- Only the chatbot is translated (EN/HI/MR); the rest of the site is in English. Hindi/Marathi text should be reviewed by a native speaker.
- Medicine list (89 entries) comes from your original project and is not a verified drug database; verify before real-world use. Dosage was intentionally removed.
- Appointments are with a specialty/time slot, not a specific doctor; no email/SMS reminders (in-app notifications only).
- Rate limiting is in-memory (single process). Use HTTPS, `SESSION_COOKIE_SECURE=true` and a production server (gunicorn/waitress) when deploying.
- Social login buttons from the old UI were removed (they were non-functional placeholders).
