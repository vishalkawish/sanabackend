import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def check_chart_data():
    print("Checking chart data in database...")
    print("=" * 70)
    
    # Get total users
    total_res = supabase.table("users").select("id", count="exact").execute()
    total_count = total_res.count if hasattr(total_res, 'count') else len(total_res.data)
    print(f"Total users in database: {total_count}")
    
    # Get users with chart data
    chart_res = supabase.table("users").select("id, chart").not_.is_("chart", "null").execute()
    users_with_charts = len(chart_res.data) if chart_res.data else 0
    print(f"Users with chart data: {users_with_charts}")
    
    # Sample a few users to check chart data structure
    sample_res = supabase.table("users").select("id, name, chart, gender").limit(5).execute()
    print(f"\nSample of 5 users:")
    print("-" * 70)
    
    for i, user in enumerate(sample_res.data, 1):
        chart = user.get('chart')
        has_chart = chart is not None and chart != ''
        chart_preview = str(chart)[:50] if chart else "None"
        print(f"{i}. {user.get('name', 'N/A')[:20]:20} | Gender: {user.get('gender', 'N/A'):10} | Has Chart: {has_chart} | Preview: {chart_preview}")
    
    # Check specific user from the test
    print("\n" + "=" * 70)
    print("Checking target user: j7DoDdmpelbt3H5BFDNKI2MxxEz2")
    print("-" * 70)
    target_res = supabase.table("users").select("*").eq("id", "j7DoDdmpelbt3H5BFDNKI2MxxEz2").execute()
    if target_res.data:
        user = target_res.data[0]
        print(f"Name: {user.get('name')}")
        print(f"Gender: {user.get('gender')}")
        print(f"Has chart: {user.get('chart') is not None}")
        print(f"Has psych_vector: {user.get('psych_vector') is not None}")
        if user.get('chart'):
            print(f"Chart preview: {str(user.get('chart'))[:100]}")
    else:
        print("User not found!")
    
    # Check opposite gender users with charts
    print("\n" + "=" * 70)
    print("Checking Female users with chart data (opposite gender)...")
    print("-" * 70)
    female_res = supabase.table("users").select("id, name, chart, age").eq("gender", "Female").not_.is_("chart", "null").limit(5).execute()
    print(f"Found {len(female_res.data)} female users with charts (showing first 5):")
    for i, user in enumerate(female_res.data, 1):
        print(f"{i}. {user.get('name', 'N/A'):20} | Age: {user.get('age', 'N/A'):3} | Has chart: {user.get('chart') is not None}")

if __name__ == "__main__":
    check_chart_data()
