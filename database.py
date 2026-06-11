import os
from sqlalchemy import create_engine, Column, Integer, String, Text, JSON, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

# Falls back to local SQLite for your laptop, switches to Render Postgres automatically live
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./local_inventory.db")

# Render postgres workaround fix for older connection formats
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# SQLite requires specific arguments that PostgreSQL doesn't need
engine_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
engine = create_engine(DATABASE_URL, connect_args=engine_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class VehicleListing(Base):
    __tablename__ = "listings"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    price = Column(String)
    mileage = Column(String)
    transmission = Column(String)
    description = Column(Text)
    facebook_source_url = Column(Text, unique=True) # Ensures strict uniqueness
    permanent_photos = Column(JSON)  # Stores your array of Cloudinary links
    created_at = Column(DateTime, default=datetime.utcnow)

def init_db():
    Base.metadata.create_all(bind=engine)