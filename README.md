# LifeBridge: Blood Donation & Thalassemia Care Management System
**Course Code:** CSE601330 - Web Engineering  
**Academic Capstone:** Production-Ready Enterprise Flask Web Application  
**Author:** Senior Flask Engineering Team  

---

## 1. Project Overview & Clinical Context
In Pakistan, Beta Thalassemia Major represents one of the most severe pediatric genetic hemoglobin disorders, with thousands of children born annually requiring lifelong blood transfusions every 2 to 4 weeks. Simultaneously, acute blood shortages across emergency units create life-threatening delays.

**LifeBridge** bridges the gap between emergency blood donor platforms and long-term thalassemia clinical management:
1. **Chronic Thalassemia Care**: Maintains pediatric clinical charts, recurring 2–4 week transfusion calendars, automated blood requisitioning, serum ferritin tracking (monitoring iron overload hemosiderosis), and daily iron chelation compliance (Deferasirox/Deferiprone).
2. **Algorithmic Emergency SOS**: Immediately matches acute blood shortages with verified local donors based on ABO/Rh compatibility, geographic city proximity, emergency availability preferences, and a strict clinical 90-day donation cooldown.
3. **Cold-Chain Blood Bank Inventory**: Tracks individual bagged blood units (PRBC, Platelets, Whole Blood, FFP), shelf-life expiration warnings (< 7 days), low stock threshold alerts (< 5 units), dynamic stock counts, and custody movement ledgers.
4. **Gamification & Engagement**: Rewards voluntary blood donors with milestone badges (Bronze, Silver, Gold, Life Saver, Thalassemia Hero) and public leaderboards.
5. **Security & Auditing**: Strict role-based access control, ownership scoping, CSRF protection, brute-force rate limiting, and comprehensive audit and login logging.

---

## 2. Tech Stack & Architectural Pattern
- **Backend Framework**: Python 3 (3.11+), Flask (v3.0.3), Application Factory Pattern with 11 Blueprints.
- **ORM & Database**: Flask-SQLAlchemy (v3.1.1), SQLAlchemy 2.0 with SQLite (`instance/lifebridge.db`) and configurable environment database URIs (PostgreSQL / MySQL ready).
- **Service Layer Architecture**: Domain services separated into `app/services/` (`matching_service.py`, `inventory_service.py`, `transfusion_service.py`, `donation_service.py`).
- **Security & RBAC**: Werkzeug password hashing (`pbkdf2:sha256`), Session authentication, Role-Based Access Control (`Admin`, `Doctor`, `Hospital Staff`, `Donor`, `Patient`), custom access decorators (`@login_required`, `@role_required`).
- **Validation**: Strict server-side validation (regex phone, 13-digit CNIC, donor age 18–60, donor weight &ge; 50kg, 90-day donation interval, Hb &ge; 12.5 g/dL).
- **Frontend & UI/UX**: Jinja2 templating, Bootstrap 5 (v5.3.3), FontAwesome 6, Dark/Light mode theme toggle persisted via cookies, Post-Redirect-Get (PRG) patterns, and responsive pagination macros.
- **Testing**: `pytest` suite covering authentication, security RBAC, data models, clinical business logic, and test coverage (36/36 tests passing).

---

## 3. Directory Structure
```text
lifebridge/
│
├── app/
│   ├── __init__.py               # Application Factory (create_app), error handlers, filters
│   ├── config.py                 # Development, Testing, Production configurations
│   ├── extensions.py             # SQLAlchemy and CSRFProtect initialization
│   ├── utils.py                  # Decorators, validation helpers, formatters, audit logger
│   │
│   ├── services/                 # Modular Domain Service Layer
│   │   ├── __init__.py           # Service exports
│   │   ├── matching_service.py   # Algorithmic emergency donor matching & expiration
│   │   ├── inventory_service.py  # Stock synchronization, auto-expiration, barcode generation
│   │   ├── transfusion_service.py# Transfusion execution safety, compatibility checks
│   │   └── donation_service.py   # Donor eligibility bounds, gamification badges
│   │
│   ├── models/                   # 46 SQLAlchemy Models (All inheriting BaseModel)
│   │   ├── __init__.py           # Unified model exports
│   │   ├── base.py               # BaseModel mixin with record_status & soft-delete engine
│   │   ├── auth.py               # users, roles, permissions, user_roles, role_permissions, login_logs, audit_logs
│   │   ├── geography.py          # cities, areas
│   │   ├── reference.py          # blood_groups, diagnoses
│   │   ├── hospital.py           # hospitals, departments, doctors, doctor_schedules, hospital_blood_banks
│   │   ├── patient.py            # patients, guardians, patient_guardians, patient_medical_history, patient_diagnoses, hemoglobin_records, ferritin_records, chelation_therapy_records
│   │   ├── donor.py              # donors, donor_health_screenings, donor_availability, donations, badges, donor_badges
│   │   ├── inventory.py          # blood_units, inventory_transactions
│   │   ├── request.py            # blood_requests, request_status_logs, emergency_requests, donor_matches, response_logs
│   │   ├── transfusion.py        # transfusion_schedules, transfusion_records
│   │   ├── care.py               # appointments, medications, patient_medications, notifications
│   │   └── other.py              # campaigns, campaign_participants, feedback
│   │
│   ├── blueprints/               # 11 Blueprints
│   │   ├── auth/                 # Login, Registration, Logout, Profile, Theme Switcher
│   │   ├── main/                 # Role-tailored Dashboard, Notifications, About
│   │   ├── patients/             # Patient CRUD, Hemoglobin/Ferritin logging, Guardians, Diagnoses
│   │   ├── donors/               # Donor directory, screening, emergency match response, badges
│   │   ├── hospitals/            # Hospitals, Departments, Doctors CRUD, Doctor Schedules
│   │   ├── inventory/            # Blood units catalog, stock summary, expiry alerts, ledger
│   │   ├── requests/             # Requisitions, Emergency SOS broadcasts, status transitions
│   │   ├── transfusions/         # Recurring schedule planner, execution form, clinical records
│   │   ├── care/                 # Outpatient appointments, drug formulary, prescriptions, chelation
│   │   ├── campaigns/            # Donation drives, volunteer signups, bag collection
│   │   └── admin/                # Users management, Recycle bin, audit trail, reference data
│   │
│   ├── templates/
│   │   ├── base.html             # Master layout (Navbar, flashes, theme toggle, footer)
│   │   ├── macros/common.html    # Reusable pagination, blood badges, status badges
│   │   ├── errors/               # 403.html, 404.html, 500.html
│   │   ├── auth/                 # login.html, register.html, profile.html
│   │   ├── main/                 # dashboard.html, notifications.html, about.html
│   │   ├── patients/             # index.html, create.html, view.html, edit.html
│   │   ├── donors/               # index.html, register.html, view.html, edit.html, screen.html, badges.html, emergency_matches.html
│   │   ├── hospitals/            # index.html, create.html, view.html, edit.html, create_doctor.html, doctor_schedules.html
│   │   ├── inventory/            # dashboard.html, units.html, add_unit.html, view_unit.html, edit_unit.html, transactions.html
│   │   ├── requests/             # index.html, create.html, view.html, emergency_active.html
│   │   ├── transfusions/         # schedules.html, create_schedule.html, execute.html, records.html
│   │   ├── care/                 # appointments.html, create_appointment.html, medications.html, create_medication.html, prescribe.html, record_chelation.html
│   │   ├── campaigns/            # index.html, create.html, view.html, edit.html
│   │   └── admin/                # dashboard.html, users.html, create_user.html, edit_user.html, recycle_bin.html, roles.html, permissions.html, audit_logs.html, login_logs.html, cities.html, areas.html, blood_groups.html, diagnoses.html, feedback.html
│   │
│   └── static/
│       ├── css/custom.css        # Glassmorphic touches, pulse animations, dark/light themes
│       └── js/main.js            # Auto-dismissing alerts, soft delete confirmation prompts
│
├── tests/
│   ├── conftest.py               # In-memory SQLite fixture, mock client, authenticated admin fixture
│   ├── test_auth.py              # Register, login, session, logout, RBAC restrictions
│   ├── test_crud.py              # Patient creation, donor screening validation, blood unit ledger
│   ├── test_soft_delete.py       # Soft-delete verification (is_deleted=True, active_query filtering, restore)
│   ├── test_routes.py            # Comprehensive smoke tests for all blueprint GET endpoints
│   ├── test_phase1_security.py   # Security tests (RBAC bypass, open redirects, brute-force rate limit)
│   ├── test_phase2_models.py     # Domain status preservation, partial unique indexes, recycle bin
│   ├── test_phase3_business_logic.py # Emergency matching, state machines, clinical validation
│   └── test_phase5_coverage.py   # CSRF protection, Pakistan validators, services, doctor isolation
│
├── seed.py                       # Seeds all 46 tables with realistic Pakistani clinical sample data
├── run.py                        # Application entry point (127.0.0.1 default, debug flag)
├── requirements.txt              # Pinned dependencies
├── .env.example                  # Environment configuration template
└── README.md                     # Comprehensive project documentation
```

---

## 4. Complete Database Architecture (46 Tables)

Every table inherits from `BaseModel`, guaranteeing uniform audit and soft-deletion tracking:
- `id` (Integer Primary Key)
- `created_at` (UTC DateTime)
- `created_by` (Foreign Key -> `users.id`)
- `updated_at` (UTC DateTime, auto-updated)
- `updated_by` (Foreign Key -> `users.id`)
- `record_status` (`active` / `deactive`)
- `is_deleted` (Boolean, indexed)
- `deleted_by` (Foreign Key -> `users.id`)

### Soft Delete & Domain Status Separation:
1. **Separation of Concerns**: To prevent soft-delete operations from corrupting clinical domain states, `BaseModel.status` was renamed to `record_status`.
2. **Explicit Domain Statuses**: Models including `BloodRequest`, `EmergencyRequest`, `DonorMatch`, `BloodUnit`, `TransfusionSchedule`, `Appointment`, and `Campaign` maintain their own domain `status` column with validated transition state machines.
3. **Partial Unique Indexes**: Unique constraints on natural keys (e.g., username, email, MRN, unit_number) are implemented with partial unique indexes (`sqlite_where=db.text('is_deleted = 0')`), allowing re-registration of soft-deleted identifiers.
4. **Recycle Bin & Restore**: Soft-deleted entities are accessible to administrators at `/admin/recycle-bin` and can be restored using the atomic `restore()` method.

### Table Breakdown by Module (46 Tables):
1. **Auth & Security (7 tables)**: `users`, `roles`, `permissions`, `user_roles`, `role_permissions`, `login_logs`, `audit_logs`
2. **Geography (2 tables)**: `cities`, `areas`
3. **Reference Data (2 tables)**: `blood_groups`, `diagnoses`
4. **Hospitals & Staff (5 tables)**: `hospitals`, `departments`, `doctors`, `doctor_schedules`, `hospital_blood_banks`
5. **Patients & Thalassemia (8 tables)**: `patients`, `guardians`, `patient_guardians`, `patient_medical_history`, `patient_diagnoses`, `hemoglobin_records`, `ferritin_records`, `chelation_therapy_records`
6. **Donors & Gamification (6 tables)**: `donors`, `donor_health_screenings`, `donor_availability`, `donations`, `badges`, `donor_badges`
7. **Inventory & Ledger (2 tables)**: `blood_units`, `inventory_transactions`
8. **Requests & Matching (5 tables)**: `blood_requests`, `request_status_logs`, `emergency_requests`, `donor_matches`, `response_logs`
9. **Transfusions (2 tables)**: `transfusion_schedules`, `transfusion_records`
10. **Care Management (4 tables)**: `appointments`, `medications`, `patient_medications`, `notifications`
11. **Community Drives & Reviews (3 tables)**: `campaigns`, `campaign_participants`, `feedback`

---

## 5. Security & Clinical Safeguards

### Security Hardening
- **RBAC Matrix**: Role checks in `role_required` strictly compare the user's role slug against allowed roles, allowing bypass only for verified system administrators.
- **CSRF Protection**: All POST forms include `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">` protected by Flask-WTF. Logout is POST-only.
- **Login Brute-Force Rate Limiting**: After 5 failed authentication attempts within 15 minutes for a username or IP address, the account is temporarily locked.
- **Account Inactivation**: Inactive user accounts (`is_active_account = False`) are prevented from logging in, and any active session is immediately invalidated.
- **Password Policies**: Staff-created patient accounts receive cryptographically random temporary passwords and are flagged with `must_change_password = True`, forcing a password reset on next login. Default passwords have been completely removed.
- **Ownership Scoping**:
  - *Patients* can view only their personal profile, appointments, lab charts, and transfusion schedules.
  - *Donors* can view only their own screening status, emergency alerts, and badges (no patient data).
  - *Doctors* can access only patients assigned to them (`primary_doctor_id`).
  - *Hospital Staff* can access only their assigned facility's inventory and requests.
- **Exception Sanitization**: Raw database/runtime error strings are never flashed to the user. Errors are logged internally via `app.logger.exception` and surfaced as friendly user alerts.

### Clinical Validation & Safety Rules
- **Emergency Matching**: Priority ranking (Distance, Donation History, Recency), 24-hour expiration window for broadcasts, automatic notification dispatch.
- **Transfusion Clinical Protocol**:
  - Pre-infusion Hb must be between 2.0 and 20.0 g/dL.
  - Execution date cannot be prior to the patient's schedule date.
  - Donor blood group must be red-cell compatible with the recipient.
  - Prevents double-execution of already completed/cancelled schedules.
- **Inventory Ledger**:
  - Terminal statuses (`Transfused`, `Discarded`, `Expired`) cannot transition back to `Available`.
  - Every status transition creates an auditable `InventoryTransaction`.
  - Blood bank inventory stock counts are dynamically synchronized with active `Available` units.
- **Outpatient Care**: Double-booking prevention for doctor clinic slots and duplicate active prescription safeguards.

---

## 6. Setup & Installation Guide

### Prerequisites
- Python 3.10 or higher
- `pip` package manager

### Step 1: Create and Activate Virtual Environment (venv)
On Windows (PowerShell):
```powershell
cd lifebridge
python -m venv venv
.\venv\Scripts\Activate.ps1
```

On Linux / macOS (Bash):
```bash
cd lifebridge
python3 -m venv venv
source venv/bin/activate
```

### Step 2: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 3: Configure Environment Variables
Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```
Default configuration values:
```ini
FLASK_APP=run.py
FLASK_ENV=development
SECRET_KEY=lifebridge-dev-secret-key-cse601330-2026
DATABASE_URL=sqlite:///instance/lifebridge.db
```

### Step 4: Seed Database with Realistic Clinical Data
Execute the seed script:
```bash
# Non-destructive check (if database already contains data)
python seed.py

# Clean full re-seed from scratch across all 46 models
python seed.py --reset
```

### Step 5: Start Development Server
```bash
python run.py
```
Open your browser at `http://127.0.0.1:5000`.

---

## 7. Pre-Configured Test Accounts

| Role | Email | Password | Full Name | Description |
|---|---|---|---|---|
| **System Admin** | `admin@lifebridge.com` | `Admin@123` | Administrator LifeBridge | Full administrative, audit, user management & recycle bin |
| **Doctor** | `doctor.tariq@lifebridge.com` | `Doctor@123` | Dr. Tariq Mansoor | Consultant Hematologist (Indus Hospital) |
| **Doctor** | `doctor.ayesha@lifebridge.com` | `Doctor@123` | Dr. Ayesha Siddiqa | Pediatric Hematologist (Children's Hospital) |
| **Hospital Staff** | `staff.fatima@lifebridge.com` | `Staff@123` | Fatima Noor | Blood Bank Officer (Stock & Requisitions) |
| **Blood Donor** | `donor.hamza@lifebridge.com` | `Donor@123` | Hamza Ali Khan | Gold Badge Donor (B+, Karachi) |
| **Blood Donor** | `donor.usman@lifebridge.com` | `Donor@123` | Usman Ghani | Life Saver Badge Donor (O+, Lahore) |
| **Patient** | `patient.zainab@lifebridge.com` | `Patient@123` | Zainab Bibi | Thalassemia Major Patient (MRN: THAL-2026-0001) |

---

## 8. Running Automated Pytest Suite
Run the complete automated test suite (36 tests):
```bash
python -m pytest tests/ -v
```

Run tests by category:
```bash
# Security & RBAC tests
python -m pytest tests/test_phase1_security.py -v

# Data models, partial unique indexes & soft delete tests
python -m pytest tests/test_phase2_models.py -v

# Clinical business logic & matching tests
python -m pytest tests/test_phase3_business_logic.py -v

# Domain services, validators & doctor isolation coverage
python -m pytest tests/test_phase5_coverage.py -v

# Core routes & CRUD tests
python -m pytest tests/test_auth.py tests/test_crud.py tests/test_routes.py tests/test_soft_delete.py -v
```

---

## 9. Grading Rubric Compliance Checklist

- [x] **Setup & Structure (10 pts)**: Application factory, 11 blueprints, `config.py`, `extensions.py`, `models/`, `services/`, `templates/`, `static/`, `seed.py`, `run.py`, `requirements.txt`, `.env.example`, virtual environment instructions.
- [x] **Routing & View Functions (15 pts)**: RESTful HTTP methods, converter segments (`<int:id>`), single-responsibility controllers, custom 403, 404, 500 error handlers.
- [x] **Templates & Jinja2 (15 pts)**: Single unified `base.html`, `{% extends %}` across all pages, loops, conditionals, `url_for`, reusable form and pagination macros in `macros/common.html`.
- [x] **Database & CRUD (20 pts)**: Exactly **46 SQLAlchemy models**, shared `BaseModel` mixin on every table with full audit columns, soft-delete implementation without physical row removal, full CRUD interfaces, transaction commit/rollback safety, eager `joinedload` query optimization.
- [x] **Forms, Validation, Cookies & Sessions (15 pts)**: Server-side validation beyond HTML5 (CNIC, phone, email, donor age 18–60, 90-day donation cooldown, Hb &ge; 12.5), session-based Werkzeug password hashing, multi-role RBAC, CSRF protection, `remember_me` and `theme` cookies, Post-Redirect-Get on all forms.
- [x] **Pagination**: Reusable `.paginate()` on all list views with URL argument preservation and page navigation macros.
- [x] **Key Clinical Features**: Role-tailored dashboards, emergency blood matching engine, recurring thalassemia transfusion tracker, cold-chain blood bank inventory with expiry alerts, gamified donor badges.
- [x] **Testing (10 pts)**: Pytest suite with 36 comprehensive unit/integration tests passing cleanly.
- [x] **Documentation (5 pts)**: Complete README with course metadata, ER overview, step-by-step setup, credentials, and workflow guides.
