import os
from supabase import create_client
from dotenv import load_dotenv
import json

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def fetch_top_psych_matches(vector: list, limit: int = 100):
    """Mimics the exact function from soul_of_anlasana_2_1.py"""
    try:
        res = supabase.rpc("match_users", {
            "query_vector": vector,
            "match_limit": limit
        }).execute()
        return res.data or []
    except Exception as e:
        print(f"vector search failed: {e}")
        res = supabase.table("users").select("*").limit(limit).execute()
        return res.data or []

def test_exact_flow():
    """Test the EXACT flow as in the endpoint"""
    user_id = "j7DoDdmpelbt3H5BFDNKI2MxxEz2"
    print(f"Testing exact flow for user: {user_id}")
    print("=" * 70)
    
    # Step 1: Fetch user
    res = supabase.table("users").select("*").eq("id", user_id).execute()
    if not res.data:
        print("User not found!")
        return
    
    user = res.data[0]
    target_vector = user.get("psych_vector")
    
    print(f"User: {user.get('name')}")
    print(f"Has vector: {target_vector is not None}")
    
    # Step 2: Get matches via RPC (EXACTLY as in the code)
    print("\nStep 2: Calling RPC...")
    match_results = fetch_top_psych_matches(target_vector, 100)
    print(f"RPC returned {len(match_results)} results")
    print(f"First result keys: {list(match_results[0].keys()) if match_results else 'None'}")
    print(f"First result has 'chart': {'chart' in match_results[0] if match_results else 'N/A'}")
    
    # Step 3: Extract IDs and re-fetch (EXACTLY as in code)
    print("\nStep 3: Extracting IDs and re-fetching...")
    if match_results:
        user_ids = [m.get("id") for m in match_results if m.get("id")]
        print(f"Extracted {len(user_ids)} user IDs")
        
        if user_ids:
            res = supabase.table("users").select("*").in_("id", user_ids).execute()
            candidates = res.data or []
            print(f"Re-fetched {len(candidates)} full records")
            
            # Check first 3
            print("\nChecking first 3 candidates:")
            for i, candidate in enumerate(candidates[:3]):
                chart_data = candidate.get("chart")
                print(f"{i+1}. ID: {candidate.get('id')[:10]}...")
                print(f"   has_chart_field: {chart_data is not None}")
                print(f"   chart_type: {type(chart_data)}")
                print(f"   Keys: {list(candidate.keys())}")
                
        else:
            print("No user IDs extracted!")
    else:
        print("No match results!")

if __name__ == "__main__":
    test_exact_flow()
