# database.py
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

load_dotenv()

# Set DATABASE_URL in .env to whichever backend you want. Examples:
#   MySQL:    mysql+pymysql://<user>:<pass>@<host>:<port>/<db>
#   Postgres: postgresql://<user>:<pass>@<host>:<port>/<db>
# Some hosts (older Heroku-style) hand out URLs starting with "postgres://" —
# SQLAlchemy needs "postgresql://", so we normalize that here.
SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://tor_bagger:aBcDeFgH@localhost:3306/tor_bagger",
)
if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(SQLALCHEMY_DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
