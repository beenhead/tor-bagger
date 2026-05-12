from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
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
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/tors")
def get_all_tors(db: Session = Depends(get_db)):
    tors = db.query(models.Tor).all()
    return {"tors": tors}

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
    closest_distances = {}

    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                for tor in all_tors:
                    if tor.id not in already_bagged_ids:
                        distance = calculate_distance_meters(point.latitude, point.longitude, tor.lat, tor.lon)
                        if tor.id not in closest_distances:
                            closest_distances[tor.id] = distance
                        else:
                            closest_distances[tor.id] = min(closest_distances[tor.id], distance)

    bagged_this_trip = []
    near_misses = []

    for tor_id, min_dist in closest_distances.items():
        tor = next(t for t in all_tors if t.id == tor_id)
        if min_dist <= bagging_radius:
            new_log = models.Logbook(user_id=current_user.id, tor_id=tor.id, distance_meters=min_dist)
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