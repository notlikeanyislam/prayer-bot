# test_mongo.py
import os
from pymongo import MongoClient
uri = os.environ.get("MONGO_URI")
if not uri:
    print("Set MONGO_URI first")
    raise SystemExit(1)
client = MongoClient(uri, serverSelectionTimeoutMS=5000)
try:
    info = client.admin.command("ping")
    print("Connected to Mongo:", info)
except Exception as e:
    print("Connection error:", e)
