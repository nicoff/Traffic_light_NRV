import os, requests
from dotenv import load_dotenv

load_dotenv()
CLIENT_ID     = os.getenv("IPNT_CLIENT_ID")     # set in environment
CLIENT_SECRET = os.getenv("IPNT_CLIENT_SECRET") # set in environment


# 1) Get token
token_url = "https://identity.netztransparenz.de/users/connect/token"
data = {
    "grant_type": "client_credentials",
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
}
headers = {"Content-Type": "application/x-www-form-urlencoded"}

resp = requests.post(token_url, data=data, headers=headers)
resp.raise_for_status()
token = resp.json()["access_token"]
print("Got token:", token[:40], "...")

# 2) Use token to call API
api_url = "https://ds.netztransparenz.de/api/v1/data/TrafficLight/2025-06-17T06:30:00/2025-06-17T12:00:00"

headers = {"Authorization": f"Bearer {token}"}
r = requests.get(api_url, headers=headers)
r.raise_for_status()
print(r.json())
