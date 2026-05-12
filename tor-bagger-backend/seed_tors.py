# seed_tors.py
import json
from database import SessionLocal
from models import Tor

def seed_database():
    # 1. Open a connection to the database
    db = SessionLocal()
    
    try:
        # 2. Load the data from the JSON file
        with open("tors.json", "r") as file:
            tors_data = json.load(file)
            
        print(f"Found {len(tors_data)} tors in JSON file. Starting import...")
        
        added_count = 0
        
        # 3. Loop through each Tor and add it to the database
        for item in tors_data:
            # Check if it already exists so we don't create duplicates if we run this twice
            existing_tor = db.query(Tor).filter(Tor.name == item["name"]).first()
            
            if not existing_tor:
                new_tor = Tor(
                    id=item["id"],
                    name=item["name"],
                    lat=item["lat"],
                    lon=item["lon"],
                    elevation_m=item["elevation_m"]
                )
                db.add(new_tor)
                added_count += 1
            else:
                print(f"Skipping {item['name']} - already exists in database.")
                
        # 4. Save (commit) the changes to MySQL
        db.commit()
        print(f"Successfully added {added_count} new Tors to the database!")
        
    except Exception as e:
        print(f"An error occurred: {e}")
        db.rollback() # Cancel the transaction if something breaks
    finally:
        db.close() # Always close the connection

if __name__ == "__main__":
    seed_database()