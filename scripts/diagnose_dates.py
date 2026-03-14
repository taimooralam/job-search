"""Diagnose date fields in level-2 collection."""
from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()
client = MongoClient(os.getenv("MONGODB_URI"))
coll = client["jobs"]["level-2"]

# Sample 20 random docs
sample = list(coll.aggregate([{"$sample": {"size": 20}}]))
print("=== SAMPLE OF 20 DOCS: date fields ===")
for doc in sample:
    ca = doc.get("createdAt")
    pd = doc.get("postedDate")
    title = (doc.get("title") or "")[:50]
    print(f"  type={type(ca).__name__} val={ca}  title={title}")

# Type distribution for createdAt
print("\n=== createdAt type distribution ===")
for r in coll.aggregate([{"$group": {"_id": {"$type": "$createdAt"}, "count": {"$sum": 1}}}]):
    print(f"  {r['_id']}: {r['count']}")

# Check all top-level fields on a doc
sample_full = coll.find_one({})
print(f"\n=== ALL fields on first doc ===")
print(sorted(sample_full.keys()))

# Count with/without createdAt
has_date = coll.count_documents({"createdAt": {"$exists": True}})
no_date = coll.count_documents({"createdAt": {"$exists": False}})
print(f"\nHas createdAt: {has_date}, Missing: {no_date}, Total: {has_date + no_date}")

# Check _id ObjectId timestamp as proxy (ObjectIds encode creation time)
from bson import ObjectId
first = coll.find_one(sort=[("_id", 1)])
last = coll.find_one(sort=[("_id", -1)])
print(f"\nFirst _id timestamp: {first['_id'].generation_time}")
print(f"Last _id timestamp: {last['_id'].generation_time}")

# Monthly distribution by _id generation time
print("\n=== Monthly distribution by _id creation time ===")
for r in coll.aggregate([
    {"$project": {
        "month": {"$dateToString": {"format": "%Y-%m", "date": {"$toDate": "$_id"}}}
    }},
    {"$group": {"_id": "$month", "count": {"$sum": 1}}},
    {"$sort": {"_id": 1}},
]):
    print(f"  {r['_id']}: {r['count']}")
