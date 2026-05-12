# ⛰️ Tor Bagger

**Tor Bagger** is a peak-bagging application dedicated to the glorious, granite-topped hills of Dartmoor National Park. 

This project allows hikers to track their progress across the moor. It features a secure backend API that calculates the Haversine distance between user GPS coordinates and Dartmoor's Tors. Users can log their visits live via API or upload historical `.gpx` tracks to retroactively bag peaks and log "near misses."

## ✨ Features

*   **Interactive Web Map:** A Leaflet.js powered frontend visualizing all Dartmoor Tors. Pins are color-coded (currently supporting un-bagged state, with user-specific states coming soon).
*   **GPX Route Processing:** Upload a `.gpx` file from Strava, Garmin, or OS Maps. The engine scans the route and automatically bags any Tors you passed within 150 meters of.
*   **Near Miss Detection:** Agonizingly close? The app detects if you walked within 500 meters of a Tor but missed the summit, logging it as a "Near Miss."
*   **Secure Authentication:** Full user registration and login system protected by bcrypt password hashing and JWT (JSON Web Tokens).
*   **Relational Database:** Powered by MySQL and SQLAlchemy for robust, multi-user data storage.

## 🛠️ Tech Stack

**Backend:**
*   Python 3.x
*   FastAPI (Web framework & API)
*   SQLAlchemy (ORM)
*   MySQL (Database)
*   PyJWT & bcrypt (Security & Auth)
*   gpxpy (GPX file parsing)

**Frontend:**
*   HTML5 / CSS3 / Vanilla JavaScript
*   Leaflet.js (Mapping library)

---

## 🚀 Getting Started

Follow these instructions to get a copy of the project up and running on your local machine for development and testing.

### Prerequisites

*   **Python 3.8+** installed on your machine.
*   **MySQL Server** installed and running locally.
*   A tool to manage virtual environments (built-in `venv` works perfectly).

### 1. Database Setup

Log into your local MySQL server and create a blank database for the project:

```sql
CREATE DATABASE tor_bagger CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
