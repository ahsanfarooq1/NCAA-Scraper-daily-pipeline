import requests
from bs4 import BeautifulSoup

url = "https://njcaastats.prestosports.com/sports/wbkb/2024-25/div1/schedule"
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

print(f"Fetching {url}")
res = requests.get(url, headers=headers)
print(f"Status: {res.status_code}")

soup = BeautifulSoup(res.text, 'html.parser')
links = soup.find_all('a', href=True)
print(f"Found {len(links)} links")

boxscore_links = [l['href'] for l in links if 'boxscores' in l['href']]
print(f"Found {len(boxscore_links)} boxscore links")
for l in boxscore_links[:10]:
    print(f" - {l}")
