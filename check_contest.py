import requests
import json
import urllib.parse

def check_contests_data(contest_id):
    base_url = "https://sdataprod.ncaa.com/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    
    hash_val = "7287cda610a9326931931080cb3a604828febe6fe3c9016a7e4a36db99efdb7c"
    variables = {"sportCode": "WBB", "division": 1, "seasonYear": 2025, "contestId": str(contest_id)}
    extensions = {"persistedQuery": {"version": 1, "sha256Hash": hash_val}}
    
    url = f"{base_url}?meta=GetContests_web&extensions={urllib.parse.quote(json.dumps(extensions))}&variables={urllib.parse.quote(json.dumps(variables))}"
    
    r = requests.get(url, headers=headers)
    print(json.dumps(r.json(), indent=2))

if __name__ == "__main__":
    check_contests_data("6355212")
