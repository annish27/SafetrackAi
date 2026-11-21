import sys
sys.path.insert(0, 'c:/Users/Annish/OneDrive/Desktop/final-capstone/reference-accident-detection/backend')
from dotenv import load_dotenv
load_dotenv('c:/Users/Annish/OneDrive/Desktop/final-capstone/reference-accident-detection/backend/.env')
import firebase_admin
from firebase_admin import credentials, firestore

cred = credentials.Certificate('c:/Users/Annish/OneDrive/Desktop/final-capstone/reference-accident-detection/backend/firebase-key.json')
firebase_admin.initialize_app(cred)
db = firestore.client()
print('Firestore connected OK')

docs = list(db.collection('accidents').limit(5).stream())
print(f'accidents collection: {len(docs)} docs')
for d in docs:
    data = d.to_dict()
    print(f'  - {d.id}: accidentDetected={data.get("accidentDetected")}, severity={data.get("severity")}')

users = list(db.collection('users').limit(5).stream())
print(f'users collection: {len(users)} docs')
for u in users:
    data = u.to_dict()
    print(f'  - {u.id}: role={data.get("role")}, email={data.get("email")}')
