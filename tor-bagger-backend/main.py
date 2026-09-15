from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, status, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func
import math
import gpxpy
import bcrypt
import jwt
import os
import secrets
import hashlib
import hmac
import base64
import json
import gzip
import requests as http_requests
from dotenv import load_dotenv
from datetime import datetime, timedelta

import models
from database import engine, get_db

# Load variables from the .env file before anything reads the environment.
load_dotenv()

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Tor Bagger API", description="JWT-powered backend")

# In production the web frontend is served same-origin behind nginx (/api/...),
# so no CORS entry is needed for it. CORS_ORIGINS exists for anything that does
# call the API cross-origin — a separately hosted frontend, or "*" in dev.
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]

if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# --- RATE LIMITING ---
# The signup form is public, so /register, /token and the password-reset
# endpoints are all reachable by anyone who finds the site. These limits are
# per client IP, held in memory — fine for a single uvicorn worker, which is
# what the Dockerfile runs. Add more workers and each gets its own counters.
REGISTER_RATE_LIMIT = os.getenv("REGISTER_RATE_LIMIT", "5/hour")
LOGIN_RATE_LIMIT = os.getenv("LOGIN_RATE_LIMIT", "10/minute")
PASSWORD_RESET_RATE_LIMIT = os.getenv("PASSWORD_RESET_RATE_LIMIT", "5/hour")


def get_client_ip(request: Request) -> str:
    """The real visitor's IP, not nginx's.

    Requests arrive via Cloudflare Tunnel -> nginx -> here, so request.client
    is always the nginx container and would put every visitor in one shared
    bucket. Cloudflare sets CF-Connecting-IP and always overwrites it, so it is
    the one to trust; X-Forwarded-For is the fallback, with the original client
    leftmost. Neither is spoofable here because the origin has no inbound ports
    and is only reachable through the tunnel.
    """
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip.strip()
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=get_client_ip)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- JWT CONFIGURATION ---
# This will now safely grab the key from your .env file!
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7

# --- EMAIL / RESET CONFIG ---
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RESEND_FROM = os.getenv("RESEND_FROM", "Tor Bagger <onboarding@resend.dev>")
WEB_BASE_URL = os.getenv("WEB_BASE_URL", "http://localhost:5500")
PASSWORD_RESET_TTL_HOURS = 1

# This tells FastAPI where the login endpoint is for Swagger UI
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# --- PASSWORD HASHING ---
def get_password_hash(password: str) -> str:
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(pwd_bytes, salt)
    return hashed_password.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    password_byte_enc = plain_password.encode('utf-8')
    hashed_password_byte_enc = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_byte_enc, hashed_password_byte_enc)

# --- JWT HELPER FUNCTIONS ---
def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """This function runs before secured endpoints to verify the token and fetch the user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
        
    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None:
        raise credentials_exception
    return user

# --- SCHEMAS & MATH ---
class UserCreate(BaseModel):
    username: str
    email: str
    password: str = Field(..., max_length=72)

class BagRequest(BaseModel):
    user_lat: float
    user_lon: float

class Token(BaseModel):
    access_token: str
    token_type: str
    is_admin: bool

class TorSuggestionCreate(BaseModel):
    suggested_name: str = Field(..., max_length=100)
    suggested_lat: float
    suggested_lon: float
    suggested_elevation: int
    suggested_description: str | None = None
    tor_id: int | None = None  # None for a NEW tor, ID for an EDIT

@app.post("/tors/suggest")
def suggest_tor(suggestion: TorSuggestionCreate, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    new_suggestion = models.TorSuggestion(
        user_id=current_user.id,
        tor_id=suggestion.tor_id,
        suggested_name=suggestion.suggested_name,
        suggested_lat=suggestion.suggested_lat,
        suggested_lon=suggestion.suggested_lon,
        suggested_elevation=suggestion.suggested_elevation,
        suggested_description=suggestion.suggested_description,
        status="pending"
    )
    db.add(new_suggestion)
    db.commit()
    return {"message": "Suggestion submitted for review!"}

def calculate_distance_meters(lat1, lon1, lat2, lon2):
    R = 6371000 
    phi_1 = math.radians(lat1)
    phi_2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi_1) * math.cos(phi_2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# --- ENDPOINTS ---
@app.get("/")
def read_root():
    return {"status": "Tor Bagger API is secured!"}

@app.post("/register")
@limiter.limit(REGISTER_RATE_LIMIT)
def register_user(request: Request, user: UserCreate, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    if db.query(models.User).filter(models.User.username == user.username).first():
        raise HTTPException(status_code=400, detail="Username already taken")

    hashed_pwd = get_password_hash(user.password)
    db_user = models.User(username=user.username, email=user.email, hashed_password=hashed_pwd)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return {"message": "User created successfully!", "user_id": db_user.id, "username": db_user.username}

@app.post("/token", response_model=Token)
@limiter.limit(LOGIN_RATE_LIMIT)
def login_for_access_token(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """This is the login endpoint!"""
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user.username}, expires_delta=access_token_expires)
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "is_admin": user.is_admin 
    }

@app.get("/tors")
def get_all_tors(db: Session = Depends(get_db)):
    # This query fetches all Tors and calculates their average rating from the reviews table
    tors = db.query(
        models.Tor,
        func.avg(models.TorReview.rating).label('avg_rating'),
        func.count(models.TorReview.id).label('review_count')
    ).outerjoin(models.TorReview).group_by(models.Tor.id).all()

    results = []
    for tor, avg_rating, review_count in tors:
        tor_data = {
            "id": tor.id,
            "name": tor.name,
            "lat": tor.lat,
            "lon": tor.lon,
            "elevation_m": tor.elevation_m,
            "description": tor.description,
            "avg_rating": round(avg_rating, 1) if avg_rating else 0,
            "review_count": review_count
        }
        results.append(tor_data)
    
    return {"tors": results}

# NOTICE: We added current_user: models.User = Depends(get_current_user) to lock this down!
@app.post("/tors/{tor_id}/bag")
def bag_a_tor(tor_id: int, request: BagRequest, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    bagging_radius = 150.0 

    tor = db.query(models.Tor).filter(models.Tor.id == tor_id).first()
    if not tor:
        raise HTTPException(status_code=404, detail="Tor not found")

    existing_log = db.query(models.Logbook).filter_by(user_id=current_user.id, tor_id=tor_id).first()
    if existing_log:
         return {"message": f"You already bagged {tor.name} on {existing_log.bagged_at.date()}!"}

    distance = calculate_distance_meters(request.user_lat, request.user_lon, tor.lat, tor.lon)
    
    if distance <= bagging_radius:
        new_log = models.Logbook(user_id=current_user.id, tor_id=tor.id, distance_meters=distance)
        db.add(new_log)
        db.commit()
        return {"message": f"Success! {current_user.username} just bagged {tor.name}!", "distance_meters": round(distance, 1)}
    else:
        raise HTTPException(status_code=400, detail=f"Too far away! {round(distance, 1)}m from {tor.name}.")

# NOTICE: Also locked down with Depends(get_current_user)
@app.post("/upload-gpx")
async def upload_gpx(file: UploadFile = File(...), current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    contents = await file.read()
    # Strava's bulk export ships some tracks gzipped (.gpx.gz). Sniff the gzip
    # magic bytes rather than trusting the filename, so either form works.
    if contents[:2] == b"\x1f\x8b":
        try:
            contents = gzip.decompress(contents)
        except OSError:
            raise HTTPException(status_code=400, detail="Could not decompress that .gz file.")
    try:
        gpx = gpxpy.parse(contents)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid GPX file.")

    all_tors = db.query(models.Tor).all()
    already_bagged_logs = db.query(models.Logbook).filter_by(user_id=current_user.id).all()
    already_bagged_ids = [log.tor_id for log in already_bagged_logs]

    bagging_radius = 150.0
    near_miss_radius = 500.0
    # tor_id -> {"distance": float, "time": datetime|None} for the closest GPX point
    closest = {}

    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                for tor in all_tors:
                    if tor.id in already_bagged_ids:
                        continue
                    distance = calculate_distance_meters(point.latitude, point.longitude, tor.lat, tor.lon)
                    prev = closest.get(tor.id)
                    if prev is None or distance < prev["distance"]:
                        closest[tor.id] = {"distance": distance, "time": point.time}

    bagged_this_trip = []
    near_misses = []

    for tor_id, approach in closest.items():
        tor = next(t for t in all_tors if t.id == tor_id)
        min_dist = approach["distance"]
        point_time = approach["time"]
        # gpxpy returns tz-aware UTC datetimes; the model stores naive UTC.
        if point_time is not None and point_time.tzinfo is not None:
            point_time = point_time.replace(tzinfo=None)

        if min_dist <= bagging_radius:
            new_log = models.Logbook(
                user_id=current_user.id,
                tor_id=tor.id,
                distance_meters=min_dist,
                bagged_at=point_time or datetime.utcnow(),
            )
            db.add(new_log)
            bagged_this_trip.append(tor.name)
        elif min_dist <= near_miss_radius:
            near_misses.append(f"{tor.name} (Closest approach: {round(min_dist)}m)")

    if bagged_this_trip:
        db.commit()

    return {
        "message": f"GPX file processed for {current_user.username} successfully!",
        "tors_bagged_on_this_walk": bagged_this_trip,
        "total_bagged_count": len(bagged_this_trip),
        "near_misses": near_misses,
        "total_near_miss_count": len(near_misses)
    }

@app.get("/my-bagged-tors")
def get_my_bagged_tors(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Returns a list of Tor IDs that the logged-in user has bagged."""
    logs = db.query(models.Logbook).filter_by(user_id=current_user.id).all()
            
    # We include the name so the frontend doesn't have to look it up
    stats_data = []
    for log in logs:
        stats_data.append({
            "tor_id": log.tor_id,
            "tor_name": log.tor.name,
            "bagged_at": log.bagged_at.isoformat() if log.bagged_at else None
        })

    return {
        "count": len(logs),
        "logs": stats_data
    }


@app.get("/leaderboard")
def get_leaderboard(db: Session = Depends(get_db)):
    """Calculates the top 10 users with the most bagged Tors."""
    leaderboard = db.query(
        models.User.username,
        func.count(models.Logbook.id).label('total_bagged')
    ).join(models.Logbook).group_by(models.User.id).order_by(func.count(models.Logbook.id).desc()).limit(10).all()

    # Format the response into a nice list of dictionaries
    return [{"rank": i + 1, "username": row[0], "total_bagged": row[1]} for i, row in enumerate(leaderboard)]

class ReviewCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5) # Ensure 1-5 stars
    comment: str = Field(..., max_length=500)

@app.post("/tors/{tor_id}/reviews")
def add_review(tor_id: int, review: ReviewCreate, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Optional: Check if they have actually bagged the tor before letting them review it!
    has_bagged = db.query(models.Logbook).filter_by(user_id=current_user.id, tor_id=tor_id).first()
    if not has_bagged:
        raise HTTPException(status_code=403, detail="You must bag this Tor before you can review it!")

    new_review = models.TorReview(
        tor_id=tor_id,
        user_id=current_user.id,
        rating=review.rating,
        comment=review.comment
    )
    db.add(new_review)
    db.commit()
    return {"message": "Review added!"}

@app.get("/tors/{tor_id}/reviews")
def get_reviews(tor_id: int, db: Session = Depends(get_db)):
    return db.query(models.TorReview).filter_by(tor_id=tor_id).all()

@app.get("/admin/suggestions")
def get_suggestions(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return db.query(models.TorSuggestion).filter_by(status="pending").all()

@app.post("/admin/reject/{s_id}")
def reject_suggestion(s_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    suggestion = db.query(models.TorSuggestion).filter_by(id=s_id).first()
    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    suggestion.status = "rejected"
    db.commit()
    return {"message": "Suggestion rejected."}

@app.post("/admin/approve/{s_id}")
def approve_tor(s_id: int, updated_data: TorSuggestionCreate, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    suggestion = db.query(models.TorSuggestion).filter_by(id=s_id).first()
    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    
    if updated_data.tor_id:
        # It's an EDIT: Update the master Tor table with your final tweaked lat/lon
        master_tor = db.query(models.Tor).filter_by(id=updated_data.tor_id).first()
        master_tor.name = updated_data.suggested_name
        master_tor.lat = updated_data.suggested_lat
        master_tor.lon = updated_data.suggested_lon
        master_tor.elevation_m = updated_data.suggested_elevation
        master_tor.description = updated_data.suggested_description
    else:
        # It's a NEW Tor: Insert it
        new_tor = models.Tor(
            name=updated_data.suggested_name,
            lat=updated_data.suggested_lat,
            lon=updated_data.suggested_lon,
            elevation_m=updated_data.suggested_elevation,
            description=updated_data.suggested_description
        )
        db.add(new_tor)

    suggestion.status = "approved"
    db.commit()
    return {"message": "Master database updated!"}


# --- PASSWORD RESET ---
class PasswordResetRequest(BaseModel):
    email: str

class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(..., max_length=72)

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def _send_password_reset_email(to_email: str, token: str):
    link = f"{WEB_BASE_URL}/?reset_token={token}"
    if not RESEND_API_KEY:
        # Dev fallback so resets work without email infrastructure.
        print(f"[DEV] Password reset link for {to_email}: {link}")
        return
    resp = http_requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
        json={
            "from": RESEND_FROM,
            "to": [to_email],
            "subject": "Tor Bagger — Reset your password",
            "html": (
                f"<p>Someone (hopefully you) requested a password reset for your Tor Bagger account.</p>"
                f'<p><a href="{link}">Click here to choose a new password</a></p>'
                f"<p>The link expires in {PASSWORD_RESET_TTL_HOURS} hour(s). If you didn't request this, you can ignore this email.</p>"
            ),
        },
        timeout=10,
    )
    resp.raise_for_status()

@app.post("/password-reset/request")
@limiter.limit(PASSWORD_RESET_RATE_LIMIT)
def request_password_reset(request: Request, req: PasswordResetRequest, db: Session = Depends(get_db)):
    # Always return the same response — don't reveal whether the email is registered.
    user = db.query(models.User).filter(models.User.email == req.email).first()
    if user:
        # Invalidate any unused reset tokens for this user.
        db.query(models.PasswordResetToken).filter(
            models.PasswordResetToken.user_id == user.id,
            models.PasswordResetToken.used_at.is_(None),
        ).update({"used_at": datetime.utcnow()})

        token = secrets.token_urlsafe(32)
        db.add(models.PasswordResetToken(
            user_id=user.id,
            token_hash=_hash_token(token),
            expires_at=datetime.utcnow() + timedelta(hours=PASSWORD_RESET_TTL_HOURS),
        ))
        db.commit()
        try:
            _send_password_reset_email(user.email, token)
        except Exception as e:
            # Don't 500 — keep the response enumeration-resistant.
            print(f"[ERROR] Failed to send password reset email to {user.email}: {e}")
    return {"message": "If an account exists for that email, a reset link has been sent."}

@app.post("/password-reset/confirm")
@limiter.limit(PASSWORD_RESET_RATE_LIMIT)
def confirm_password_reset(request: Request, req: PasswordResetConfirm, db: Session = Depends(get_db)):
    row = db.query(models.PasswordResetToken).filter_by(token_hash=_hash_token(req.token)).first()
    if not row or row.used_at is not None or row.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired reset link.")
    user = db.query(models.User).filter_by(id=row.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid reset link.")
    user.hashed_password = get_password_hash(req.new_password)
    row.used_at = datetime.utcnow()
    db.commit()
    return {"message": "Password updated. You can now log in."}


# --- SIGNED EXPORT / IMPORT ---
def _canonical_json(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()

def _sign_payload(payload: dict) -> str:
    sig = hmac.new(SECRET_KEY.encode(), _canonical_json(payload), hashlib.sha256).digest()
    return base64.b64encode(sig).decode()

def _verify_signature(payload: dict, signature: str) -> bool:
    return hmac.compare_digest(_sign_payload(payload), signature)

@app.get("/my-bagged-tors/export")
def export_my_bagged_tors(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    logs = db.query(models.Logbook).filter_by(user_id=current_user.id).all()
    payload = {
        "version": 1,
        "user_id": current_user.id,
        "username": current_user.username,
        "exported_at": datetime.utcnow().isoformat(),
        "logs": [
            {
                "tor_id": log.tor_id,
                "tor_name": log.tor.name,
                "bagged_at": log.bagged_at.isoformat() if log.bagged_at else None,
                "distance_meters": log.distance_meters,
            }
            for log in logs
        ],
    }
    blob = {"payload": payload, "signature": _sign_payload(payload)}
    body = json.dumps(blob, indent=2)
    filename = f"tor-bagger-{current_user.username}.torbag"
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@app.post("/my-bagged-tors/import")
async def import_my_bagged_tors(file: UploadFile = File(...), current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    contents = await file.read()
    try:
        blob = json.loads(contents)
        payload = blob["payload"]
        signature = blob["signature"]
    except (json.JSONDecodeError, KeyError, TypeError):
        raise HTTPException(status_code=400, detail="Not a valid Tor Bagger export file.")
    if not _verify_signature(payload, signature):
        raise HTTPException(status_code=400, detail="Signature verification failed. The file has been modified or wasn't issued by this server.")
    if payload.get("user_id") != current_user.id:
        raise HTTPException(status_code=400, detail="This export belongs to a different account.")

    def _key(tor_id, bagged_at):
        return (tor_id, bagged_at.replace(microsecond=0) if bagged_at else None)

    existing = db.query(models.Logbook).filter_by(user_id=current_user.id).all()
    existing_keys = {_key(log.tor_id, log.bagged_at) for log in existing}

    imported = 0
    skipped = 0
    for entry in payload.get("logs", []):
        tor_id = entry.get("tor_id")
        bagged_at_iso = entry.get("bagged_at")
        try:
            bagged_at = datetime.fromisoformat(bagged_at_iso.rstrip("Z")) if bagged_at_iso else None
        except (ValueError, AttributeError):
            skipped += 1
            continue
        if bagged_at and bagged_at.tzinfo is not None:
            bagged_at = bagged_at.replace(tzinfo=None)
        if _key(tor_id, bagged_at) in existing_keys:
            skipped += 1
            continue
        if not db.query(models.Tor).filter_by(id=tor_id).first():
            skipped += 1
            continue
        db.add(models.Logbook(
            user_id=current_user.id,
            tor_id=tor_id,
            bagged_at=bagged_at,
            distance_meters=entry.get("distance_meters"),
        ))
        imported += 1
    db.commit()
    return {"imported": imported, "skipped": skipped, "total_in_file": len(payload.get("logs", []))}
