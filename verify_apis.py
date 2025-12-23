import os
import asyncio
from dotenv import load_dotenv

# Load env before importing soul_of_anlasana to avoid Supabase initialization error
load_dotenv()

from soul_of_anlasana_2_1 import soul_of_anlasana, get_sana_advice

async def main():
    uid = '0G7LxwwU2MXl4ycaVvhnZbqkyRF3'
    tid = '0IR8hN4mtpX4CaBTOIMil5O1A693'
    
    print(f"--- Testing soul_of_anlasana for {uid} ---")
    try:
        res1 = await soul_of_anlasana(uid)
        matches = res1.get('matches', [])
        print(f"Found {len(matches)} matches")
        if matches:
            print(f"Top match: {matches[0]['name']} ({matches[0]['match_percent']}%)")
            print(f"Match response keys: {matches[0].keys()}")
    except Exception as e:
        print(f"Error in soul_of_anlasana: {e}")

    print(f"\n--- Testing get_sana_advice between {uid} and {tid} ---")
    try:
        res2 = await get_sana_advice(uid, tid)
        print(f"Advice: {res2.get('advice')}")
        print(f"AI Rating: {res2.get('ai_rating')}")
    except Exception as e:
        print(f"Error in get_sana_advice: {e}")

if __name__ == '__main__':
    asyncio.run(main())
