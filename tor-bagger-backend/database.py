# database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# UPDATE THIS STRING with your actual MySQL username, password, and host
# Format: mysql+pymysql://<username>:<password>@<host>:<port>/<database_name>
SQLALCHEMY_DATABASE_URL = "mysql+pymysql://tor_bagger:aBcDeFgH@localhost:3306/tor_bagger"

# Create the SQLAlchemy engine
engine = create_engine(SQLALCHEMY_DATABASE_URL)

# Create a session factory (this is what opens the connection when a user makes an API request)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for our models to inherit from
Base = declarative_base()

# Dependency to get a database session for our API endpoints
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()