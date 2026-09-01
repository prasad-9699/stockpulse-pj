import urllib.request
import json
import time

base_url = 'http://localhost:8000'

print("=== Automated Test for Reorder Engine ===")

# 1. Update stock to trigger loop
print("Triggering agentic loop on Product 1 (Stock -> 1)...")
req = urllib.request.Request(f"{base_url}/products/1/stock", data=json.dumps({"stock_level": 1}).encode("utf-8"), method="PATCH")
req.add_header("Content-Type", "application/json")
urllib.request.urlopen(req)

# Wait for background task to finish
print("Waiting 5 seconds for background agentic loop to process...")
time.sleep(5)

# 2. Fetch reorder suggestions
print("Fetching reorder suggestions...")
req = urllib.request.Request(f"{base_url}/reorder-suggestions")
response = urllib.request.urlopen(req)
data = json.loads(response.read())

if not data:
    print("ERROR: No suggestions found!")
else:
    s = data[0]
    print("\n--- Latest Suggestion Data ---")
    print(json.dumps(s, indent=2))
    
    # Check for new fields
    expected_fields = [
        "demand_velocity", "safety_stock_days", "expected_lead_time_demand", 
        "safety_stock", "target_inventory", "guardrail_applied"
    ]
    missing = [f for f in expected_fields if f not in s]
    
    print("\n--- Test Results ---")
    if missing:
        print(f"❌ ERROR: Missing fields in response: {missing}")
    else:
        print("✅ SUCCESS: All calculation fields are present in the API response!")
        print(f"   Target Inventory calculated as: {s['target_inventory']} units.")
        print(f"   Recommended Reorder calculated as: {s['recommended_quantity']} units.")
