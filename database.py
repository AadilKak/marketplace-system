import os
from sqlalchemy import create_engine, Column, Integer, String, Text, JSON, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

# 1. Grab the raw environment variable string
RAW_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./local_inventory.db")

# 2. Strict Cleaning Layer (strips hidden quotes, spaces, or wrapper junk)
DATABASE_URL = RAW_DATABASE_URL.strip().replace('"', '').replace("'", "")

# 3. Dynamic Protocol Standardization
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# 4. Apply connection arguments based on database engine type
engine_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}

# 5. Initialize Engine
engine = create_engine(DATABASE_URL, connect_args=engine_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ... (Keep your VehicleListing class and init_db function exactly the same below this line)

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