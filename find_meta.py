import requests
import json
import urllib.parse

def find_working_meta(contest_id):
    base_url = "https://sdataprod.ncaa.com/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Referer': 'https://www.ncaa.com/',
    }
    
    # Common hashes and metas
    tests = [
        ("4a7fa26398db33de3ff51402a90eb5f25acef001cca28d239fe5361315d1419a", "NCAA_GetGamecenterBoxscoreBasketballById_web"),
        ("7287cda610a9326931931080cb3a604828febe6fe3c9016a7e4a36db99efdb7c", "GetContests_web"), # This one needs different variables
    ]
    
    # For boxscore, let's try to see if we can find a different hash
    # I'll try to find a game that WORKS and see its hash if I had one.
    # But I can't even get one to work here.
    
    for hash_val, meta_val in tests:
        print(f"Testing {meta_val}...")
        extensions = {"persistedQuery": {"version": 1, "sha256Hash": hash_val}}
        if "Contests" in meta_val:
            variables = {"sportCode": "WBB", "division": 1, "seasonYear": 2025, "contestId": str(contest_id)}
        else:
            variables = {"contestId": str(contest_id), "staticTestEnv": None}
            
        url = f"{base_url}?meta={meta_val}&extensions={urllib.parse.quote(json.dumps(extensions))}&variables={urllib.parse.quote(json.dumps(variables))}"
        
        try:
            r = requests.get(url, headers=headers)
            data = r.json()
            if "errors" in data:
                print(f"  Error: {data['errors'][0].get('message')}")
            else:
                print(f"  SUCCESS for {meta_val}!")
                # print(json.dumps(data, indent=2)[:200])
        except Exception as e:
            print(f"  Exception: {e}")

if __name__ == "__main__":
    find_working_meta("6355212")
