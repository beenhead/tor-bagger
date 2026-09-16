# ⛰️ Tor Bagger

**Tor Bagger** is a peak-bagging application dedicated to the glorious, granite-topped hills of Dartmoor National Park.

This project allows hikers to track their progress across the moor. It features a secure backend API that calculates the Haversine distance between user GPS coordinates and Dartmoor's Tors. Users can log their visits live via API or upload historical `.gpx` tracks to retroactively bag peaks and log "near misses."

## ✨ Features

*   **Interactive Web Map:** A Leaflet.js powered frontend visualizing all Dartmoor Tors. Pins are color-coded by user-specific bagged / un-bagged state.
*   **GPX Route Processing:** Upload a `.gpx` file from Strava, Garmin, or OS Maps. The engine scans the route, automatically bags any Tors you passed within 150 meters of, and dates each bag from the GPX point's own timestamp. `gpx-help.html`, linked from the upload box, walks users through exporting one from Strava.
*   **Strava Bulk Import:** Feed in the whole-history `.zip` Strava emails you. The archive is opened *in the browser* — its activity list is read to find the walks, hikes and runs, and only those tracks are uploaded, one at a time, with a progress bar. Rides, photos and videos are never sent anywhere.
*   **Route Planner:** Pick a set of Tors and plot a walking route between them. Works out the shortest visiting order, follows real paths via [BRouter](https://brouter.de), and reports distance, ascent and a Naismith time estimate. Routes save to your account and export as GPX for your watch — which then comes back in as a recorded track to bag what you walked.
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
tor-bagger-web/       Static frontend — index.html plus gpx-help.html, served by nginx
tor-bagger-mobile/    Flutter project targeting iOS and Android
```

## 🐳 Running with Docker

`docker-compose.yml` brings up three containers: Postgres, the FastAPI backend,
and nginx serving the static frontend *and* proxying `/api/` through to the
backend. Because the API is same-origin, the frontend uses relative URLs and
nothing needs to know the public hostname.

The compose file is production-shaped by default: only the web port is
published, the database and backend are reachable only on the internal network,
and secrets come from a `.env` file.

### Configure

```bash
cp .env.example .env
```

Fill in at minimum `SECRET_KEY`, `POSTGRES_PASSWORD`, and `WEB_BASE_URL`
(generate secrets with `openssl rand -hex 32`). Compose refuses to start with
a clear error if any of the three is missing.

`SECRET_KEY` signs JWTs *and* logbook exports — keep it stable once set, or
previously generated exports stop validating.

### Production

```bash
docker compose up -d --build
```

The web container publishes on `127.0.0.1:80` by default, i.e. loopback only.
Nothing is exposed to the internet directly — see *Ingress and TLS* below.

Seed the master tor data once the stack is up — note this needs an admin user
to exist first, see below:

```bash
docker compose exec backend python scraper.py
```

### Creating users

Signup is open: the login panel has a **New here? Create an account** link, and
a successful signup logs you straight in. Anyone who reaches the site can
register, so inviting friends is just sending them the URL.

Accounts can still be created through the API directly:

```bash
curl -X POST https://torbagger.beanhead.co.uk/api/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"you","email":"you@example.com","password":"..."}'
```

Passwords are capped at 72 characters (a bcrypt limit). To grant admin rights,
needed for the scraper and the suggestion-approval UI:

```bash
docker compose exec db psql -U tor_bagger -d tor_bagger \
  -c "UPDATE users SET is_admin = true WHERE username = 'you';"
```

### Local development

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

The dev overlay adds uvicorn `--reload` with the backend source bind-mounted,
publishes Postgres on 5432 and the backend on 8000, and sets `CORS_ORIGINS=*`
so the mobile app can call the API directly. The overlay is deliberately *not*
named `docker-compose.override.yml`, so it can never load by accident on a
server.

Set `WEB_PORT=5500` in `.env` for local use; the site is then on
`http://localhost:5500`.

Frontend edits are baked into the web image — rerun with `--build` to pick them
up. Database contents live in the `db_data` volume and survive
`docker compose down`; `docker compose down -v` wipes them.

### Rate limits

Because registration is public, the endpoints anyone can hit unauthenticated
are throttled per client IP. Defaults, overridable in `.env`:

| Variable | Default | Applies to |
| --- | --- | --- |
| `REGISTER_RATE_LIMIT` | `5/hour` | `POST /register` |
| `LOGIN_RATE_LIMIT` | `10/minute` | `POST /token` |
| `PASSWORD_RESET_RATE_LIMIT` | `5/hour` | both `/password-reset/*` endpoints |

A throttled request gets `429` and `{"error": "Rate limit exceeded: ..."}`; the
web UI surfaces that as a "too many attempts" message.

The client IP comes from `CF-Connecting-IP`, which Cloudflare always overwrites,
falling back to the leftmost `X-Forwarded-For` entry and then to the socket
address. Without that, every visitor would share one bucket keyed on the nginx
container's IP. Counters live in the backend process's memory, which is correct
for the single uvicorn worker the Dockerfile runs — they reset when the
container restarts, and adding workers would give each its own set.

### Ingress and TLS

The production deployment sits behind a **Cloudflare Tunnel**, which terminates
TLS at Cloudflare's edge and connects *outbound* from the server to reach the
site at `http://localhost:80`. That means:

*   No inbound ports are open on the host, and none need to be.
*   The origin speaks plain HTTP on loopback. That is fine — the hop is on the
    server itself, and the public connection is HTTPS.
*   Do **not** add a TLS terminator (Caddy, nginx with certbot) on the origin.
    It would take port 80 from the tunnel, and ACME challenges cannot reach a
    host with no inbound ports anyway.

The tunnel's route is configured in the Cloudflare dashboard under
*Networks → Tunnels*, pointing `torbagger.beanhead.co.uk` at
`http://localhost:80`. `WEB_PORT` must match whatever that route says.

If you ever move off the tunnel and expose the host directly, that is when a
TLS terminator becomes necessary — set `WEB_BIND=0.0.0.0` and put one in front.

### Notes

*   `CORS_ORIGINS` should stay empty in production. The frontend is same-origin,
    so it needs no entry; native mobile apps do not enforce CORS.
*   The Strava bulk import unpacks the archive in the browser rather than
    uploading it. That is not just a nicety: Cloudflare caps request bodies at
    100 MB on the free plan, and these archives run to several hundred MB, so an
    upload would be rejected at the edge no matter what `client_max_body_size`
    says. Unpacking client-side also means the photo and video half of the
    archive — usually most of its bulk — never leaves the user's machine. Only
    the individual walking tracks are POSTed to `/upload-gpx`, each a few MB at
    most, comfortably inside nginx's 25 MB limit.
*   `/upload-gpx` sniffs gzip magic bytes, so a `.gpx.gz` can be uploaded
    directly without being unpacked first.
*   The route planner calls BRouter from the browser. It needs no API key and
    sends `Access-Control-Allow-Origin: *`, so there is nothing to proxy and no
    secret to keep — but it is a community-run service with no SLA. If it is
    unreachable the planner falls back to direct lines and says so, rather than
    losing the plan. Self-hosting BRouter is the upgrade path if it proves
    flaky.
*   **Path routing cannot cross open moor**, and that shapes the planner. A
    router only knows mapped ways, so between two Tors with no path between them
    it goes the long way round — Fur Tor to Great Links Tor comes back as 21km
    against a 4.7km straight line. Much of northern Dartmoor is open access land
    that walkers cross on a bearing, so the planner offers a direct-line mode and
    warns automatically when a path route exceeds `DETOUR_WARN_RATIO` times the
    crow-flies distance. Neither mode is right for the whole moor; the point is
    to make the difference visible.
*   Routes store only the ordered tor ids, not the plotted line. The geometry is
    thousands of coordinates and is cheap to re-request when a route is reopened.

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

Then set `DATABASE_URL` in `tor-bagger-backend/.env` (see the next section). If left unset, the app builds a Postgres URL from the `POSTGRES_*` variables instead — that is the path the Docker stack uses, and it percent-encodes the password for you.

> If you do set `DATABASE_URL` by hand and the password contains `@`, `:`, `/` or `#`, percent-encode it (`@` becomes `%40`). An unencoded `@` makes the rest of the password parse as the hostname, and the backend fails to start.

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

# Database — pick one. Percent-encode special characters in the password
# (@ -> %40, : -> %3A, / -> %2F), or leave DATABASE_URL empty and set the
# POSTGRES_* vars below instead, which handles the encoding for you.
# MySQL:    DATABASE_URL=mysql+pymysql://tor_bagger:aBcDeFgH@localhost:3306/tor_bagger
# Postgres: DATABASE_URL=postgresql://tor_bagger:aBcDeFgH@localhost:5432/tor_bagger
DATABASE_URL=

# Used only when DATABASE_URL is empty:
POSTGRES_USER=tor_bagger
POSTGRES_PASSWORD=
POSTGRES_DB=tor_bagger
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# Password reset emails (optional in dev — without RESEND_API_KEY, the reset
# link is just printed to the uvicorn console instead of emailed).
RESEND_API_KEY=
RESEND_FROM=Tor Bagger <onboarding@resend.dev>
WEB_BASE_URL=http://localhost:5500

# Comma-separated origins allowed to call the API cross-origin. Empty means
# none, which is correct when the frontend is proxied same-origin.
CORS_ORIGINS=*

# Per-IP rate limits on the public endpoints. Optional — these are the defaults.
REGISTER_RATE_LIMIT=5/hour
LOGIN_RATE_LIMIT=10/minute
PASSWORD_RESET_RATE_LIMIT=5/hour
```

`SECRET_KEY` signs JWTs *and* the signed logbook exports — keep it stable so existing exports remain importable. `WEB_BASE_URL` is where password-reset links point; serve the web frontend with `python -m http.server 5500` from `tor-bagger-web/` so the link in the email actually opens something. To enable real email sending in production, sign up at [resend.com](https://resend.com) and paste the API key.

Register at least one user via the `/register` endpoint and set `is_admin = true` on the user the scraper should attribute its harvested suggestions to. Then seed the master tor data:

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

The frontend calls the API at relative `/api/...` URLs, which assumes something
is proxying `/api/` to the backend. The Docker stack's nginx does this, so the
simplest route is `docker compose` (above).

Opening `index.html` straight from disk no longer works — `file://` has nothing
to proxy through. If you want to run the frontend without Docker, put any local
proxy in front that maps `/api/` to `http://127.0.0.1:8000/`.

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
