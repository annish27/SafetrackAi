"""
Updates Firestore security rules — allow all authenticated users read/write.
"""
import sys, json, urllib.request, urllib.error

sys.path.insert(0, 'c:/Users/Annish/OneDrive/Desktop/final-capstone/reference-accident-detection/backend')
from dotenv import load_dotenv
load_dotenv('c:/Users/Annish/OneDrive/Desktop/final-capstone/reference-accident-detection/backend/.env')

import google.auth.transport.requests
import google.oauth2.service_account

SA_PATH    = 'c:/Users/Annish/OneDrive/Desktop/final-capstone/reference-accident-detection/backend/firebase-key.json'
PROJECT_ID = 'accident-80ec3'

with open(SA_PATH) as f:
    sa_info = json.load(f)

creds = google.oauth2.service_account.Credentials.from_service_account_info(
    sa_info,
    scopes=['https://www.googleapis.com/auth/cloud-platform'],
)
creds.refresh(google.auth.transport.requests.Request())
token = creds.token
print(f"Access token obtained.")

# Simple rules: any authenticated user can read/write everything
# This is safe for a demo/capstone — all users are known
RULES = '''rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /{document=**} {
      allow read, write: if request.auth != null;
    }
  }
}
'''

# Step 1: Create ruleset
url = f'https://firebaserules.googleapis.com/v1/projects/{PROJECT_ID}/rulesets'
payload = json.dumps({'source': {'files': [{'name': 'firestore.rules', 'content': RULES}]}}).encode()
req = urllib.request.Request(url, data=payload,
    headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}, method='POST')
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        result = json.loads(r.read())
        ruleset_name = result['name']
        print(f"Ruleset created: {ruleset_name}")
except urllib.error.HTTPError as e:
    print(f"Error creating ruleset: {e.code} {e.read().decode()}")
    sys.exit(1)

# Step 2: Release (activate) the ruleset
rel_url = f'https://firebaserules.googleapis.com/v1/projects/{PROJECT_ID}/releases/cloud.firestore'
rel_payload = json.dumps({'release': {
    'name': f'projects/{PROJECT_ID}/releases/cloud.firestore',
    'rulesetName': ruleset_name,
}}).encode()
rel_req = urllib.request.Request(rel_url, data=rel_payload,
    headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}, method='PATCH')
try:
    with urllib.request.urlopen(rel_req, timeout=15) as r:
        print(f"Rules deployed successfully!")
        print("All authenticated users can now read/write Firestore.")
except urllib.error.HTTPError as e:
    print(f"Error releasing ruleset: {e.code} {e.read().decode()}")
