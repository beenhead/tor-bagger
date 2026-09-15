# ⛰️ Tor Bagger

**Tor Bagger** is a peak-bagging application dedicated to the glorious, granite-topped hills of Dartmoor National Park.

This project allows hikers to track their progress across the moor. It features a secure backend API that calculates the Haversine distance between user GPS coordinates and Dartmoor's Tors. Users can log their visits live via API or upload historical `.gpx` tracks to retroactively bag peaks and log "near misses."

## ✨ Features

*   **Interactive Web Map:** A Leaflet.js powered frontend visualizing all Dartmoor Tors. Pins are color-coded by user-specific bagged / un-bagged state.
*   **GPX Route Processing:** Upload a `.gpx` file from Strava, Garmin, or OS Maps. The engine scans the route, automatically bags any Tors you passed within 150 meters of, and dates each bag from the GPX point's own timestamp.
*   **Near Miss Detection:** Agonizingly close? The app detects if you walked within 500 meters of a Tor but missed the summit, logging it as a "Near Miss."
*   **Mobile App (lean v1):** Flutter app for iOS and Android — login, live map, GPS-based live bagging.
*   **Secure Authentication:** Full user registration and login system protected by bcrypt password hashing and JWT (JSON Web Tokens).
*   **Relational Database:** MySQL + SQLAlchemy for robust, multi-user data storage.
*   **Source Scraper:** Pulls master tor data (name, coordinates, elevation, description) from `dartmoorwalker.co.uk`. Populates an admin approval queue for new entries and backfills missing data on existing ones in-place. Re-runnable / idempotent.

## 🛠️ Tech Stack

**Backend:**
*   Python 3.x
*   FastAPI (web framework & API)
*   SQLAlchemy (ORM)
*   MySQL or PostgreSQL (database — pick whichever; selected via `DATABASE_URL`)
*   PyJWT & bcrypt (security & auth)
*   gpxpy (GPX file parsing)
*   BeautifulSoup4 & requests (scraper)

**Web Frontend:**
*   HTML5 / CSS3 / Vanilla JavaScript
*   Leaflet.js (mapping)

**Mobile App:**
*   Flutter / Dart
*   `flutter_map` (Leaflet-equivalent, OSM tiles)
*   `geolocator` (GPS)
*   `flutter_secure_storage` (Keychain / EncryptedSharedPreferences for JWT)

## 📁 Repo Layout

```
tor-bagger-backend/   FastAPI app, SQLAlchemy models, scraper, .env, virtualenv
tor-bagger-web/       Static index.html — open directly in a browser
tor-bagger-mobile/    Flutter project targeting iOS and Android
```

## 🐳 Running with Docker (quickest route)

`docker-compose.yml` brings up three containers: Postgres, the FastAPI backend,
and an nginx container serving the static web frontend. No local Python, MySQL,
or Postgres install needed.

You still need `tor-bagger-backend/.env` for `SECRET_KEY` (and optionally
`RESEND_API_KEY`). `DATABASE_URL` is set by Compose and points at the `db`
container, so whatever is in `.env` for local runs is ignored inside Docker.

```bash
docker compose up --build        # or: docker-compose up --build
```

*   Web frontend → http://localhost:5500
*   API + Swagger docs → http://localhost:8000/docs
*   Postgres → `localhost:5432` (user/pass/db all `tor_bagger`)

Tables are created automatically on first boot. Seed the master tor data once
the stack is up:

```bash
docker compose exec backend python scraper.py
```

The backend mounts `tor-bagger-backend/` into the container and runs uvicorn
with `--reload`, so Python edits take effect immediately. Edits to
`tor-bagger-web/index.html` are baked into the image — rerun
`docker compose up --build web` to pick them up.

Database contents live in the `db_data` volume and survive `docker compose
down`. To wipe and start fresh:

```bash
docker compose down -v
```

The frontend calls the API at `http://127.0.0.1:8000` from the browser (i.e.
from your host), which is why the backend port is published rather than kept
internal to the Compose network.

## 🚀 Getting Started

### Prerequisites

*   **Python 3.8+**
*   **MySQL Server** *or* **PostgreSQL Server** running locally (pick one)
*   **Flutter SDK** (only if you want to run the mobile app)
*   **Xcode** (iOS) and/or **Android Studio with an AVD** (Android) for the mobile app

### 1. Database

Pick MySQL or Postgres — the schema is portable, SQLAlchemy handles both. Create a blank database:

```sql
-- MySQL
CREATE DATABASE tor_bagger CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Postgres
CREATE DATABASE tor_bagger;
```

Then set `DATABASE_URL` in `tor-bagger-backend/.env` (see the next section). If left unset, the app falls back to a local MySQL connection string baked into `database.py`.

### 2. Backend

```bash
cd tor-bagger-backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in `tor-bagger-backend/` containing:

```
SECRET_KEY=replace-me-with-a-long-random-string

# Database — pick one. If omitted, falls back to local MySQL.
# MySQL:    DATABASE_URL=mysql+pymysql://tor_bagger:aBcDeFgH@localhost:3306/tor_bagger
# Postgres: DATABASE_URL=postgresql://tor_bagger:aBcDeFgH@localhost:5432/tor_bagger
DATABASE_URL=

# Password reset emails (optional in dev — without RESEND_API_KEY, the reset
# link is just printed to the uvicorn console instead of emailed).
RESEND_API_KEY=
RESEND_FROM=Tor Bagger <onboarding@resend.dev>
WEB_BASE_URL=http://localhost:5500
```

`SECRET_KEY` signs JWTs *and* the signed logbook exports — keep it stable so existing exports remain importable. `WEB_BASE_URL` is where password-reset links point; serve the web frontend with `python -m http.server 5500` from `tor-bagger-web/` so the link in the email actually opens something. To enable real email sending in production, sign up at [resend.com](https://resend.com) and paste the API key.

Register at least one user via the `/register` endpoint and flip `is_admin = true` in MySQL for the user the scraper should attribute its harvested suggestions to. Then seed the master tor data:

```bash
python scraper.py
```

This walks the source site (~300 tors), backfills missing elevations and descriptions on existing master rows directly, and queues any genuinely new tors into the suggestion table for admin approval via the web UI.

Run the API:

```bash
uvicorn main:app --reload --host 0.0.0.0
```

`--host 0.0.0.0` is so iOS simulators, Android emulators, and real phones on your LAN can reach it (otherwise it binds only to `127.0.0.1`).

### 3. Web Frontend

Open `tor-bagger-web/index.html` directly in your browser. It expects the API at `http://127.0.0.1:8000`.

### 4. Mobile App

```bash
cd tor-bagger-mobile
flutter pub get
```

Boot a simulator/emulator (Xcode for iOS, Android Studio's **Virtual Device Manager** for Android), then:

```bash
# iOS Simulator — 127.0.0.1 reaches the host directly
flutter run -d ios

# Android emulator — the host is reached via 10.0.2.2
flutter run -d emulator --dart-define=API_BASE_URL=http://10.0.2.2:8000

# Real phone on your LAN — use your Mac's IP (find via: ifconfig | grep "inet 192")
flutter run --dart-define=API_BASE_URL=http://192.168.1.X:8000
```

The mobile app currently uses the `/token`, `/tors`, `/my-bagged-tors`, and `/tors/{id}/bag` endpoints. GPX upload, leaderboard, and reviews are web-only for now.
