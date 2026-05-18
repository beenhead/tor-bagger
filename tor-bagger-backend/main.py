from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func
import math
import gpxpy
import bcrypt
import jwt
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta

import models
from database import engine, get_db



models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Tor Bagger API", description="MySQL & JWT Powered Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, this would be your actual website URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load variables from the .env file
load_dotenv()

# --- JWT CONFIGURATION ---
# This will now safely grab the key from your .env file!
SECRET_KEY = os.getenv("SECRET_KEY") 
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7

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
def register_user(user: UserCreate, db: Session = Depends(get_db)):
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
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
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

