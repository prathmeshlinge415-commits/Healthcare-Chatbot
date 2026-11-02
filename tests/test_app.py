"""Automated tests. Run:  python -m unittest discover -s tests -v
They run against a throw-away SQLite database (the app's SQL is portable), so no MySQL server is needed."""
import os
import sys
import tempfile
import unittest
from datetime import date, timedelta
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db as database  # noqa: E402
from app import create_app  # noqa: E402

TOKEN = "test-token"


def future(days=3):
    d = date.today() + timedelta(days=days)
    return d.isoformat()


class Base(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db"); os.close(fd)
        self.app = create_app({"TESTING": True, "SECRET_KEY": "x", "SECRET_KEY_FROM_ENV": True, "DB_BACKEND": "sqlite",
                               "SQLITE_PATH": self.path, "AI_API_KEY": "", "ADMIN_EMAILS": ["admin@example.com"], "SLOT_CAPACITY": 2})
        database.init_schema(self.app.config)
        self.c = self.app.test_client()
        with self.c.session_transaction() as s:
            s["csrf"] = TOKEN

    def tearDown(self):
        os.unlink(self.path)

    def post(self, url, data=None, client=None, **kw):
        data = dict(data or {}); data["csrf_token"] = TOKEN
        return (client or self.c).post(url, data=data, **kw)

    def signup(self, email="asha@example.com", pw="Passw0rd1", client=None):
        return self.post("/signup", dict(firstName="Asha", lastName="Patil", email=email, phone="9876543210",
                                         password=pw, confirmPassword=pw, terms="on"), client=client)

    def login(self, email="asha@example.com", pw="Passw0rd1", client=None):
        c = client or self.c
        r = self.post("/login", dict(email=email, password=pw), client=c)
        with c.session_transaction() as s:  # login rotates the CSRF token (by design); re-pin it for tests
            s["csrf"] = TOKEN
        return r

    def logged_in(self):
        self.signup(); r = self.login(); self.assertEqual(r.status_code, 302); return self.c

    def book(self, **over):
        d = dict(patient_name="Asha Patil", patient_email="asha@example.com", patient_phone="9876543210",
                 doctor_specialty="cardiologist", appointment_date=future(), appointment_time="10:00", reason="Checkup")
        d.update(over); return self.post("/appointment", d)


class TestPages(Base):
    def test_public_pages_load(self):
        for url in ["/", "/login", "/signup", "/chatbot", "/specialization", "/medicine", "/hospital", "/contact",
                    "/emergency", "/health", "/health/hydration"]:
            self.assertEqual(self.c.get(url).status_code, 200, url)

    def test_404_and_protected_redirect(self):
        self.assertEqual(self.c.get("/nope").status_code, 404)
        for url in ["/dashboard", "/profile", "/appointments", "/appointment", "/notifications"]:
            r = self.c.get(url); self.assertEqual(r.status_code, 302, url); self.assertIn("/login", r.headers["Location"])

    def test_old_routes_names_kept(self):
        self.assertEqual(self.c.get("/hospital").status_code, 200)
        self.assertEqual(self.c.get("/api/specialists?specialty=cardiologist").get_json()["doctors"], [])

    def test_security_headers_and_csrf(self):
        r = self.c.get("/"); self.assertEqual(r.headers["X-Frame-Options"], "DENY")
        bad = self.c.post("/contact", data={"firstName": "a"}); self.assertEqual(bad.status_code, 302)
        j = self.c.post("/api/chat", json={"message": "hi"}); self.assertEqual(j.status_code, 400)


class TestAuth(Base):
    def test_signup_validation(self):
        r = self.post("/signup", dict(firstName="A", lastName="B", email="bad", password="Passw0rd1", confirmPassword="Passw0rd1", terms="on"))
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.signup(pw="short1").status_code, 400)
        self.assertEqual(self.signup(pw="onlyletters").status_code, 400)
        r = self.post("/signup", dict(firstName="A", lastName="B", email="a@b.co", password="Passw0rd1", confirmPassword="Different1", terms="on"))
        self.assertEqual(r.status_code, 400)

    def test_signup_login_logout_and_hashing(self):
        self.assertEqual(self.signup().status_code, 302)
        with self.app.app_context():
            row = database.get_db().one("SELECT password FROM patient WHERE email=%s", ("asha@example.com",))
            self.assertTrue(row["password"].startswith(("scrypt:", "pbkdf2:")))
            self.assertNotIn("Passw0rd1", row["password"])
        self.assertEqual(self.signup().status_code, 409)  # duplicate email
        self.assertEqual(self.login(pw="Wrongpass1").status_code, 401)
        r = self.login(); self.assertEqual(r.status_code, 302)
        self.assertIn(b"Hello, Asha", self.c.get("/dashboard").data)
        self.post("/logout"); self.assertEqual(self.c.get("/dashboard").status_code, 302)

    def test_login_throttle_and_open_redirect(self):
        self.signup()
        for _ in range(5): self.login(pw="Wrongpass1")
        self.assertEqual(self.login().status_code, 429)
        c2 = self.app.test_client()
        with c2.session_transaction() as s: s["csrf"] = TOKEN
        self.signup("b@example.com", client=c2)
        r = self.post("/login", dict(email="b@example.com", password="Passw0rd1", next="//evil.com"), client=c2)
        self.assertNotIn("evil.com", r.headers["Location"])


class TestAppointments(Base):
    def test_book_view_confirmation_notification(self):
        self.logged_in(); r = self.book(); self.assertEqual(r.status_code, 302)
        self.assertIn("/confirmation", r.headers["Location"])
        self.assertIn(b"Appointment confirmed", self.c.get(r.headers["Location"]).data)
        self.assertIn(b"Cardiologist", self.c.get("/appointments").data)
        self.assertIn(b"Appointment confirmed", self.c.get("/notifications").data)
        self.assertEqual(len(self.c.get("/api/appointments").get_json()["appointments"]), 1)

    def test_invalid_input_rejected(self):
        self.logged_in()
        past = (date.today() - timedelta(days=1)).isoformat()
        for over in [dict(appointment_date=past), dict(appointment_date="garbage"), dict(appointment_time="03:17"),
                     dict(doctor_specialty="wizard"), dict(patient_phone="12"), dict(reason=""),
                     dict(appointment_date=(date.today() + timedelta(days=500)).isoformat())]:
            self.assertEqual(self.book(**over).status_code, 400, over)

    def test_duplicates_and_capacity(self):
        self.logged_in(); self.assertEqual(self.book().status_code, 302)
        self.assertEqual(self.book().status_code, 400)  # same slot
        self.assertEqual(self.book(appointment_time="11:00").status_code, 400)  # same specialty same day
        self.assertEqual(self.book(doctor_specialty="dentist").status_code, 400)  # same time other specialty
        self.assertEqual(self.book(doctor_specialty="dentist", appointment_time="11:00").status_code, 302)
        for i in range(2):  # capacity 2 for cardiologist 14:00 on another day
            c = self.app.test_client()
            with c.session_transaction() as s: s["csrf"] = TOKEN
            self.signup(f"u{i}@x.com", client=c); self.login(f"u{i}@x.com", client=c)
            r = self.post("/appointment", dict(patient_name="U", patient_email=f"u{i}@x.com", patient_phone="9876543210", doctor_specialty="cardiologist",
                                               appointment_date=future(5), appointment_time="14:00", reason="Checkup"), client=c)
            self.assertEqual(r.status_code, 302 if i < 2 else 400)
        c = self.app.test_client()
        with c.session_transaction() as s: s["csrf"] = TOKEN
        self.signup("u9@x.com", client=c); self.login("u9@x.com", client=c)
        r = self.post("/appointment", dict(patient_name="U", patient_email="u9@x.com", patient_phone="9876543210", doctor_specialty="cardiologist",
                                           appointment_date=future(5), appointment_time="14:00", reason="Checkup"), client=c)
        self.assertEqual(r.status_code, 400); self.assertIn(b"slot is full", r.data)

    def test_reschedule_cancel_and_ownership(self):
        self.logged_in(); self.book()
        with self.app.app_context(): aid = database.get_db().one("SELECT id FROM appointments")["id"]
        r = self.post(f"/appointment/{aid}/reschedule", dict(appointment_date=future(6), appointment_time="15:30"))
        self.assertEqual(r.status_code, 302)
        with self.app.app_context():
            a = database.get_db().one("SELECT * FROM appointments WHERE id=%s", (aid,))
            self.assertEqual((a["appointment_date"], a["appointment_time"]), (future(6), "15:30"))
        self.post(f"/appointment/{aid}/reschedule", dict(appointment_date="2000-01-01", appointment_time="10:00"))
        with self.app.app_context(): self.assertEqual(database.get_db().one("SELECT appointment_date FROM appointments")["appointment_date"], future(6))
        other = self.app.test_client()
        with other.session_transaction() as s: s["csrf"] = TOKEN
        self.signup("o@x.com", client=other); self.login("o@x.com", client=other)
        self.assertEqual(self.post(f"/appointment/{aid}/cancel", client=other).status_code, 404)
        self.post(f"/appointment/{aid}/cancel")
        with self.app.app_context(): self.assertEqual(database.get_db().one("SELECT status FROM appointments")["status"], "cancelled")
        self.assertIn(b"Cancelled", self.c.get("/appointments").data)
        self.assertEqual(self.book().status_code, 302)  # cancelled slot can be booked again


class TestChat(Base):
    def chat(self, msg, lang="en"):
        return self.c.post("/api/chat", json={"message": msg, "lang": lang}, headers={"X-CSRF-Token": TOKEN}).get_json()

    def test_emergency_all_languages(self):
        for msg, lang in [("I have chest pain", "en"), ("मुझे सीने में दर्द है", "hi"), ("मला श्वास घेता येत नाही", "mr")]:
            d = self.chat(msg, lang); self.assertTrue(d["emergency"], msg); self.assertIn("112", d["reply"]); self.assertEqual(d["source"], "safety")

    def test_greeting_symptom_specialist_without_ai(self):
        self.assertEqual(self.chat("hello")["source"], "rules")
        d = self.chat("I have fever"); self.assertIn("Fever", d["reply"]); self.assertIn("not a diagnosis", d["reply"])
        d = self.chat("my knee hurts when I climb stairs"); self.assertEqual(d["specialists"][0]["slug"], "orthopedic")
        self.assertIn("appointment?specialty=orthopedic", d["specialists"][0]["url"])
        self.assertEqual(self.chat("बुखार है", "hi")["specialists"][0]["slug"], "general")
        self.assertIn("डॉक्टर", self.chat("मला ताप आहे", "mr")["reply"])
        self.assertEqual(self.c.post("/api/chat", json={"message": ""}, headers={"X-CSRF-Token": TOKEN}).status_code, 400)

    def test_ai_success_and_failure_fallback(self):
        self.app.config["AI_API_KEY"] = "fake"
        ok = mock.Mock(); ok.raise_for_status.return_value = None; ok.json.return_value = {"choices": [{"message": {"content": "Drink water and rest."}}]}
        with mock.patch("chat_service.requests.post", return_value=ok) as p:
            d = self.chat("I feel tired lately"); self.assertEqual(d["source"], "ai"); self.assertIn("Drink water", d["reply"])
            self.assertIn("Bearer fake", p.call_args.kwargs["headers"]["Authorization"])
            self.assertIn("NEVER diagnose", p.call_args.kwargs["json"]["messages"][0]["content"])
        with mock.patch("chat_service.requests.post", side_effect=Exception("boom")):
            d = self.chat("I have a headache"); self.assertEqual(d["source"], "fallback"); self.assertIn("not available", d["reply"])
        with mock.patch("chat_service.requests.post") as p:  # emergencies never go to the AI
            self.chat("severe bleeding"); p.assert_not_called()

    def test_history_saved_and_cleared_for_users(self):
        self.logged_in(); self.chat("hello")
        h = self.c.get("/api/chat/history").get_json()["messages"]; self.assertEqual([m["role"] for m in h], ["user", "bot"])
        self.assertTrue(self.c.delete("/api/chat/history", headers={"X-CSRF-Token": TOKEN}).get_json()["success"])
        self.assertEqual(self.c.get("/api/chat/history").get_json()["messages"], [])
        self.assertEqual(self.app.test_client().get("/api/chat/history").status_code, 401)


class TestOther(Base):
    def test_medicines(self):
        d = self.c.get("/api/medicines/suggest?q=para").get_json()["suggestions"]; self.assertTrue(any("Paracetamol" in x for x in d))
        html = self.c.get("/medicine?q=ibuprofen").data
        self.assertIn(b"Ibuprofen", html); self.assertNotIn(b"mg every", html); self.assertIn(b"Medical disclaimer", html)
        self.assertIn(b"No medicines found", self.c.get("/medicine?q=zzzzqq").data.replace(b"hidden", b"")) 

    def test_profile_and_password(self):
        self.logged_in()
        r = self.post("/profile", dict(first_name="Asha", last_name="P", phone="9876543210", date_of_birth="1990-05-01", gender="female", city="Satara", blood_group="O+"))
        self.assertEqual(r.status_code, 302); self.assertIn(b"Satara", self.c.get("/profile").data)
        self.post("/profile", dict(first_name="Asha", last_name="P", date_of_birth="2999-01-01"))
        self.assertIn(b"1990-05-01", self.c.get("/profile").data)
        self.post("/profile/password", dict(current_password="bad", new_password="NewPassw0rd", confirm_password="NewPassw0rd"))
        self.post("/profile/password", dict(current_password="Passw0rd1", new_password="NewPassw0rd", confirm_password="NewPassw0rd"))
        c2 = self.app.test_client()
        with c2.session_transaction() as s: s["csrf"] = TOKEN
        self.assertEqual(self.login(pw="Passw0rd1", client=c2).status_code, 401)
        self.assertEqual(self.login(pw="NewPassw0rd", client=c2).status_code, 302)

    def test_contact_feedback_and_doctor_admin(self):
        self.assertEqual(self.post("/contact", dict(firstName="A", lastName="B", email="a@b.co", subject="Other", message="Hello there team")).status_code, 302)
        self.assertEqual(self.post("/feedback", dict(category="suggestion", rating="5", message="Great site!")).status_code, 302)
        with self.app.app_context():
            self.assertEqual(database.get_db().one("SELECT COUNT(*) AS n FROM contact_messages")["n"], 1)
            self.assertEqual(database.get_db().one("SELECT COUNT(*) AS n FROM feedback")["n"], 1)
        self.logged_in()
        r = self.c.post("/api/doctors", json={"first_name": "Ravi", "specialty": "dentist"}, headers={"X-CSRF-Token": TOKEN}); self.assertEqual(r.status_code, 403)
        admin = self.app.test_client()
        with admin.session_transaction() as s: s["csrf"] = TOKEN
        self.signup("admin@example.com", client=admin); self.login("admin@example.com", client=admin)
        r = admin.post("/api/doctors", json={"first_name": "Ravi", "specialty": "dentist", "experience_years": 5}, headers={"X-CSRF-Token": TOKEN}); self.assertEqual(r.status_code, 201)
        self.assertEqual(self.c.get("/api/specialists?specialty=dentist").get_json()["doctors"][0]["first_name"], "Ravi")


if __name__ == "__main__":
    unittest.main()
