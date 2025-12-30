import requests
import json

# Test the Soul of Anlasana API
USER_ID = "j7DoDdmpelbt3H5BFDNKI2MxxEz2"
BASE_URL = "http://localhost:8000"

def test_soul_api():
    url = f"{BASE_URL}/soul_of_anlasana_2_1/{USER_ID}"
    print(f"Testing API: {url}")
    print("=" * 60)
    
    try:
        response = requests.get(url, timeout=30)
        print(f"Status Code: {response.status_code}")
        print(f"Response Time: {response.elapsed.total_seconds():.2f}s")
        print("=" * 60)
        
        if response.status_code == 200:
            data = response.json()
            print(f"[SUCCESS] API is working!")
            print(f"User ID: {data.get('user_id')}")
            print(f"Number of matches: {len(data.get('matches', []))}")
            
            if data.get('matches'):
                print("\nTop 3 matches:")
                for i, match in enumerate(data['matches'][:3], 1):
                    print(f"  {i}. {match.get('name')} - {match.get('match_percent')}% ({match.get('type')})")
            else:
                print("\n[WARNING] No matches found")
                
        else:
            print(f"[ERROR] API returned error status: {response.status_code}")
            try:
                error_data = response.json()
                print(f"Error details: {json.dumps(error_data, indent=2)}")
            except:
                print(f"Response: {response.text[:500]}")
            
    except requests.exceptions.Timeout:
        print("[ERROR] Request timed out (>30s)")
    except requests.exceptions.ConnectionError:
        print("[ERROR] Cannot connect to server. Is it running on port 8000?")
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__ == "__main__":
    test_soul_api()
