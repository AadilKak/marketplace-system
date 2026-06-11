from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import cloudinary
import cloudinary.uploader
from sqlalchemy.orm import Session

# Import our database requirements
from database import init_db, SessionLocal, VehicleListing

app = FastAPI()

# Automatically build/verify DB tables on script launch
init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure Cloudinary
cloudinary.config( 
    cloud_name = "dxmridiec", 
    api_key = "169548193132435", 
    api_secret = "eg62Gxdcf58PLXNgIhniduuY_bM",
    secure = True
)

class CarListing(BaseModel):
    success: bool
    timestamp: str
    url: str
    title: str
    price: str
    mileage: str
    transmission: str
    description: str
    images: List[str]

# Database Session Dependency management
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
@app.get("/api/listings")
async def get_all_listings(db: Session = Depends(get_db)):
    # Pulls all vehicles, newest arrivals first
    listings = db.query(VehicleListing).order_by(VehicleListing.created_at.desc()).all()
    return listings
@app.post("/api/listings")
async def receive_car_listing(listing: CarListing, db: Session = Depends(get_db)):
    print(f"\n--- Checking Pipeline for: {listing.title} ---")
    
    # OPTIMIZATION STEP: Check database first before running Cloudinary uploads
    existing_listing = db.query(VehicleListing).filter(VehicleListing.facebook_source_url == listing.url).first()
    if existing_listing:
        print(f" -> SKIPPED: URL already saved in database (ID: {existing_listing.id}).")
        return {
            "status": "ignored",
            "message": f"Listing '{listing.title}' already exists in your database system."
        }

    permanent_images = []
    
    # Loop through temporary Facebook URLs and migrate them to Cloudinary
    print(f"Uploading {len(listing.images)} images to Cloudinary permanent storage...")
    for index, fb_url in enumerate(listing.images):
        try:
            upload_result = cloudinary.uploader.upload(
                fb_url,
                folder=f"car_inventory/{listing.title.replace(' ', '_')}"
            )
            permanent_url = upload_result.get("secure_url")
            permanent_images.append(permanent_url)
            print(f" -> Photo {index + 1} uploaded successfully!")
        except Exception as e:
            print(f" -> Failed to upload photo {index + 1}: {e}")

    # Map details to SQLAlchemy DB engine model
    new_vehicle = VehicleListing(
        title=listing.title,
        price=listing.price,
        mileage=listing.mileage,
        transmission=listing.transmission,
        description=listing.description,
        facebook_source_url=listing.url,
        permanent_photos=permanent_images
    )

    try:
        db.add(new_vehicle)
        db.commit()
        db.refresh(new_vehicle)
        print(f"\n--- DATABASE INSERTION SUCCESS: RECORD ID {new_vehicle.id} ---")
    except Exception as db_err:
        db.rollback()
        print(f" -> Error committing transaction to database: {db_err}")
        raise HTTPException(status_code=500, detail="Database write action failed.")
    
    return {
        "status": "success", 
        "database_id": new_vehicle.id,
        "message": f"Successfully committed {listing.title} to database with {len(permanent_images)} cloud assets!"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)