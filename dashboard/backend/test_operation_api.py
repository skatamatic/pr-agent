import requests
import json

# Test what the operation API returns for an operation with insights
operation_id = "4bdbf2b9-2bbd-42be-96b1-5909ae0ef17d"  # The most recent one with insights
url = f"http://localhost:8000/api/operations/{operation_id}"

try:
    print(f"Testing operation API: {url}")
    response = requests.get(url)
    
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print("✅ API call successful!")
        print(f"Response keys: {list(data.keys())}")
        
        if 'insights' in data:
            print(f"✅ Insights field found: {type(data['insights'])}")
            if data['insights']:
                if isinstance(data['insights'], str):
                    try:
                        parsed_insights = json.loads(data['insights'])
                        print(f"✅ Insights JSON keys: {list(parsed_insights.keys())}")
                    except:
                        print(f"❌ Insights is a string but not valid JSON: {data['insights'][:100]}...")
                elif isinstance(data['insights'], dict):
                    print(f"✅ Insights is dict with keys: {list(data['insights'].keys())}")
                else:
                    print(f"❌ Insights has unexpected type: {type(data['insights'])}")
            else:
                print("❌ Insights field is empty/null")
        else:
            print("❌ No insights field in response")
            
        # Show all fields for debugging
        print("\n=== Full Response Structure ===")
        for key, value in data.items():
            if key == 'insights' and value:
                print(f"{key}: {type(value)} - (insights data)")
            elif isinstance(value, (dict, list)):
                print(f"{key}: {type(value)} (length: {len(value) if hasattr(value, '__len__') else 'N/A'})")
            else:
                value_str = str(value)[:50] + "..." if len(str(value)) > 50 else str(value)
                print(f"{key}: {value_str}")
    else:
        print(f"❌ API call failed: {response.status_code}")
        print(f"Response: {response.text}")
        
except Exception as e:
    print(f"❌ Error: {e}") 