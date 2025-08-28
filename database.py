from pymongo import MongoClient
from config import MONGO_URI, DB_NAME
from typing import Optional
import time

if not MONGO_URI:
    raise RuntimeError("MONGO_URI is not set in environment")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

admins_col = db["admins"]
groups_col = db["groups"]
state_col = db["state"]

# Admins
def add_admin_db(user_id: int):
    admins_col.update_one({"user_id": user_id}, {"$set": {"user_id": user_id}}, upsert=True)

def remove_admin_db(user_id: int):
    admins_col.delete_one({"user_id": user_id})

def get_admins():
    return [d["user_id"] for d in admins_col.find({}, {"user_id": 1})]

def is_admin_db(user_id: int) -> bool:
    return admins_col.find_one({"user_id": user_id}) is not None

# Groups (chat + optional thread/topic id)
def add_group_db(chat_id: int, thread_id: Optional[int] = None):
    groups_col.update_one({"chat_id": chat_id}, {"$set": {"chat_id": chat_id, "thread_id": thread_id}}, upsert=True)

def get_groups_db():
    out = {}
    for doc in groups_col.find({}):
        out[str(doc["chat_id"])] = {
            "chat_id": doc["chat_id"],
            "thread_id": doc.get("thread_id")
        }
    return out

def remove_group_db(chat_id: int):
    groups_col.delete_one({"chat_id": chat_id})

# State: closed flag + last_action timestamp (unix)
def update_state_db(chat_id: int, closed: bool):
    state_col.update_one({"chat_id": chat_id}, {"$set": {"chat_id": chat_id, "closed": bool(closed), "last_action": int(time.time())}}, upsert=True)

def get_state_db(chat_id: int):
    doc = state_col.find_one({"chat_id": chat_id})
    if not doc:
        return {"closed": False, "last_action": 0}
    return {"closed": bool(doc.get("closed", False)), "last_action": int(doc.get("last_action", 0))}
