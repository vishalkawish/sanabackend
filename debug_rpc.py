import os
from supabase import create_client
from dotenv import load_dotenv
import json

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def test_rpc_response():
    """Test what the match_users RPC actually returns"""
    print("Testing match_users RPC response...")
    print("=" * 70)
    
    # Get the target user first
    target_user = supabase.table("users").select("*").eq("id", "j7DoDdmpelbt3H5BFDNKI2MxxEz2").execute()
    if not target_user.data:
        print("Target user not found!")
        return
    
    psych_vector = target_user.data[0].get("psych_vector")
    print(f"Target user psych_vector: {psych_vector is not None}")
    print(f"Vector length: {len(psych_vector) if psych_vector else 0}")
    
    # Call the RPC like the code does
    print("\n" + "=" * 70)
    print("Calling match_users RPC...")
    try:
        res = supabase.rpc("match_users", {
            "query_vector": psych_vector,
            "match_limit": 10  # Just 10 for testing
        }).execute()
        
        print(f"RPC returned {len(res.data)} results")
        
        # Show first 3 results structure
        print("\nFirst 3 RPC results structure:")
        for i, match in enumerate(res.data[:3], 1):
            print(f"\n{i}. Match keys: {list(match.keys())}")
            print(f"   Full data: {json.dumps(match, indent=2)[:200]}")
        
        # Try to fetch full data like the endpoint does
        print("\n" + "=" * 70)
        print("Testing data fetch after RPC...")
        
        user_ids = [m.get("id") for m in res.data if m.get("id")]
        print(f"Extracted {len(user_ids)} user IDs from RPC results")
        
        if user_ids:
            print(f"Sample IDs: {user_ids[:3]}")
            
            # Fetch full data
            full_data = supabase.table("users").select("*").in_("id", user_ids[:3]).execute()
            print(f"\nFetched {len(full_data.data)} full user records")
            
            for i, user in enumerate(full_data.data, 1):
                has_chart = user.get('chart') is not None
                has_gender = user.get('gender') is not None
                print(f"\n{i}. User: {user.get('name')}")
                print(f"   ID: {user.get('id')}")
                print(f"   Gender: {user.get('gender')}")
                print(f"   Has chart: {has_chart}")
                if has_chart:
                    chart_preview = str(user.get('chart'))[:100]
                    print(f"   Chart preview: {chart_preview}")
                else:
                    print(f"   Chart value: {user.get('chart')}")
                    
    except Exception as e:
        print(f"RPC Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_rpc_response()
