# 🔐 Passwordless Behavioral Authentication System
### Built with Django · Django REST Framework · PostgreSQL

---

## What Is This?

A backend system that authenticates users **without passwords** by analyzing
behavioral signals — how they type, move their mouse, scroll, and more.

Every login attempt is scored against the user's historical behavioral profile.
If the score exceeds the threshold (default: 60/100), access is granted.

---

## Project Structure

```
behavioral_auth/
├── config/
│   ├── settings.py        # Project settings + behavior config thresholds
│   └── urls.py            # Root URL routing
│
├── authcore/              # The core authentication app
│   ├── models.py          # User (no password) + BehaviorLog
│   ├── views.py           # register, login, save_behavior APIs
│   ├── serializers.py     # Request/response validation
│   ├── trust_engine.py    # Rule-based trust score computation
│   ├── urls.py            # App-level URL routes
│   └── admin.py           # Django admin configuration
│
├── frontend_guide.js      # How frontend collects + sends behavior data
├── requirements.txt
└── README.md
```

---

## API Endpoints

| Method | Endpoint                  | Description                        |
|--------|---------------------------|------------------------------------|
| POST   | `/api/auth/register/`     | Create account (no password)       |
| POST   | `/api/auth/login/`        | Authenticate via behavior signals  |
| POST   | `/api/auth/behavior/save/`| Save post-login behavior snapshot  |

---

## Behavioral Signals

| Signal           | Type   | Description                          |
|------------------|--------|--------------------------------------|
| `typing_speed`   | float  | Avg characters per second            |
| `key_hold_time`  | float  | Avg ms a key is held before release  |
| `mouse_velocity` | float  | Avg mouse speed in px/sec            |
| `click_interval` | float  | Avg ms between clicks                |
| `scroll_depth`   | float  | Fraction of page scrolled (0–1)      |
| `network_latency`| float  | Round-trip latency in ms             |
| `device_hash`    | string | SHA-256 of device fingerprint        |
| `location_hash`  | string | SHA-256 of coarse location           |
| `time_of_day`    | int    | Hour of day (0–23, UTC)              |

---

## Trust Score Logic

Each signal contributes to a total score out of 100:

```
typing_speed     → 15 pts   (% deviation from baseline)
key_hold_time    → 15 pts   (% deviation from baseline)
mouse_velocity   → 10 pts   (% deviation from baseline)
click_interval   → 10 pts   (% deviation from baseline)
scroll_depth     → 10 pts   (% deviation from baseline)
network_latency  → 10 pts   (hard cap: 300ms)
device_hash      → 15 pts   (binary: match or no match)
location_hash    → 10 pts   (binary: match or no match)
time_of_day      →  5 pts   (circular hour proximity)
─────────────────────────────
TOTAL            → 100 pts
```

Default login threshold: **60/100**. Configurable in `settings.py`.

---

## Quick Start

```bash
# 1. Clone and install
pip install -r requirements.txt

# 2. Set up PostgreSQL database
createdb behavioral_auth_db

# 3. Apply migrations
python manage.py makemigrations authcore
python manage.py migrate

# 4. Run the server
python manage.py runserver
```

---

## Future ML Integration

The `trust_engine.py` module is intentionally isolated. To upgrade from
rule-based to ML scoring, simply replace the body of `compute_trust_score()`
with a `model.predict()` call — zero changes needed in `views.py`.

```python
# Future upgrade (drop-in replacement):
def compute_trust_score(current_data: dict, baseline: dict) -> int:
    features = vectorize(current_data, baseline)
    return int(ml_model.predict_proba([features])[0][1] * 100)
```

---

## Security Notes

- Passwords are **never accepted, stored, or used**
- Device and location data are **hashed before storage** (SHA-256)
- Only **engineered numeric features** are stored — no raw event logs
- User IDs are **UUID4** (no sequential ID enumeration)
- For production: replace the session token with **JWT** and use HTTPS
