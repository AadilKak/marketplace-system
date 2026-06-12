from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import cloudinary
import cloudinary.uploader
from sqlalchemy.orm import Session
import os

# Import our database requirements
from database import init_db, SessionLocal, VehicleListing
from scraper import scrape_listing

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

class ScrapeRequest(BaseModel):
    url: str
    key: str  # Simple secret key to prevent unauthorized triggers

SCRAPE_KEY = os.environ.get("SCRAPE_KEY", "changeme")

async def run_scrape_and_save(url: str):
    """Background task: scrape the listing then save it via the existing pipeline."""
    data = await scrape_listing(url)
    if not data.get("success"):
        print(f"Scrape failed: {data.get('error')}")
        return

    # Reuse the existing save logic by building a CarListing and calling receive_car_listing
    listing = CarListing(**data)
    db = SessionLocal()
    try:
        existing = db.query(VehicleListing).filter(VehicleListing.facebook_source_url == listing.url).first()
        if existing:
            print(f"Already in DB: {listing.title}")
            return

        permanent_images = []
        for fb_url in listing.images:
            try:
                result = cloudinary.uploader.upload(fb_url, folder=f"car_inventory/{listing.title.replace(' ', '_')}")
                permanent_images.append(result.get("secure_url"))
            except Exception as e:
                print(f"Image upload failed: {e}")

        new_vehicle = VehicleListing(
            title=listing.title,
            price=listing.price,
            mileage=listing.mileage,
            transmission=listing.transmission,
            description=listing.description,
            facebook_source_url=listing.url,
            permanent_photos=permanent_images,
            is_sold=data.get("is_sold", False),
        )
        db.add(new_vehicle)
        db.commit()
        print(f"Saved: {listing.title} (ID {new_vehicle.id}), sold={new_vehicle.is_sold}")
    except Exception as e:
        db.rollback()
        print(f"DB error: {e}")
    finally:
        db.close()


async def check_sold_status(vehicle_id: int, url: str):
    """Re-scrape a listing just to check sold status and update DB."""
    from scraper import scrape_listing
    result = await scrape_listing(url)
    if not result.get("success"):
        print(f"Sold check failed for ID {vehicle_id}: {result.get('error')}")
        return
    db = SessionLocal()
    try:
        vehicle = db.query(VehicleListing).filter(VehicleListing.id == vehicle_id).first()
        if vehicle:
            vehicle.is_sold = result.get("is_sold", False)
            db.commit()
            print(f"Updated sold status: ID {vehicle_id} → sold={vehicle.is_sold}")
    finally:
        db.close()


@app.post("/api/sync-sold")
async def sync_sold(background_tasks: BackgroundTasks, key: str = ""):
    """Re-check sold status for all listings. Pass ?key=YOUR_KEY."""
    if key != SCRAPE_KEY:
        raise HTTPException(status_code=401, detail="Invalid key.")
    db = SessionLocal()
    try:
        listings = db.query(VehicleListing).all()
        for v in listings:
            background_tasks.add_task(check_sold_status, v.id, v.facebook_source_url)
        return {"status": "queued", "message": f"Checking sold status for {len(listings)} listings."}
    finally:
        db.close()


@app.post("/api/scrape")
async def trigger_scrape(req: ScrapeRequest, background_tasks: BackgroundTasks):
    """
    Triggered from the dealer's phone shortcut.
    Accepts a Marketplace listing URL + secret key, scrapes it in the background.
    """
    if req.key != SCRAPE_KEY:
        raise HTTPException(status_code=401, detail="Invalid key.")
    if "facebook.com/marketplace/item/" not in req.url:
        raise HTTPException(status_code=400, detail="URL must be a Facebook Marketplace listing.")

    background_tasks.add_task(run_scrape_and_save, req.url)
    return {"status": "queued", "message": "Scraping started in background. Check inventory in ~30 seconds."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)