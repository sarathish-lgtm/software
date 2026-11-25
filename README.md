# MediBook - Hospital Appointment Booking System

A web-based Hospital Appointment Booking System built as a **Software Engineering mini project**.
Patients can find doctors and book time slots online; doctors manage their schedule and
appointments; the admin manages doctors, departments and monitors all bookings.

**Tech stack:** Python 3 - Flask - SQLite - HTML/CSS (Jinja2 templates)

---

## 1. How to run

You need Python 3.9 or newer.

```bash
# 1. (optional but recommended) create a virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux / macOS

# 2. install the only dependency
pip install -r requirements.txt

# 3. start the app (creates hospital.db with demo data on first run)
python app.py
```

Open **http://127.0.0.1:5000** in your browser.

## 2. Demo accounts

| Role    | Email                  | Password   |
|---------|------------------------|------------|
| Admin   | admin@hospital.com     | admin123   |
| Doctor  | arun@hospital.com      | doctor123  |
| Doctor  | meena@hospital.com     | doctor123  |
| Doctor  | karthik@hospital.com   | doctor123  |
| Patient | register a new account from the *Register* page | |

To reset all data, stop the app and delete `hospital.db`.

## 3. Features

**Patient**
- Register / login (passwords stored as salted hashes)
- Browse doctors, filter by department
- Pick a date (up to 30 days ahead) and see only the **free 30-minute slots**
- Book, view and cancel appointments; read the doctor's notes after the visit

**Doctor**
- Dashboard with upcoming appointments and history
- Mark an appointment completed and write prescription / notes
- Set own working days and working hours (slots are generated from this)

**Admin**
- Statistics (patients, doctors, today's / booked / completed / cancelled)
- View all appointments, filter by status, cancel any booking
- Add doctors, activate / deactivate doctors, add departments

**Engineering points worth mentioning in your viva**
- Role-based access control (patient / doctor / admin)
- **Double booking is prevented twice**: in code (slot check) and in the database
  (partial UNIQUE index on doctor + date + time for non-cancelled appointments)
- CSRF tokens on every POST form
- Input validation on all forms; parameterised SQL queries (no SQL injection)
- Past dates / past time slots and non-working days cannot be booked
- 29 automated tests

## 4. Run the tests

```bash
python -m unittest discover -s tests -v
```

## 5. Project structure

```
hospital_appointment/
|-- app.py                  Flask application (routes, business logic)
|-- schema.sql              Database tables
|-- requirements.txt
|-- static/style.css
|-- templates/              Jinja2 HTML pages
|-- tests/test_app.py       Automated tests
|-- docs/PROJECT_REPORT.md  SRS, use cases, ER diagram, test cases, plan
```

## 6. Ideas to extend it (future scope)

- Email / SMS reminders for appointments
- Online payment of consultation fee
- Doctor leave management and rescheduling
- PDF prescription download
- Deploy on a cloud platform with MySQL / PostgreSQL

> Before deploying anywhere public: set the `SECRET_KEY` environment variable
> and change `debug=True` to `debug=False` at the bottom of `app.py`.
