"""Check schema details for level-2 docs."""
from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()
client = MongoClient(os.getenv("MONGODB_URI"))
coll = client["jobs"]["level-2"]

# Get a doc with job_description and check job_criteria
doc = coll.find_one({"job_description": {"$exists": True}})
if doc:
    print("=== Fields ===")
    for k, v in doc.items():
        if k in ("job_description", "embeddings_large", "embeddings_small"):
            print(f"  {k}: (length={len(str(v))})")
        elif k == "job_criteria":
            print(f"  job_criteria: {v}")
        elif k == "extracted_jd":
            print(f"  extracted_jd keys: {list(v.keys()) if v else 'None'}")
        else:
            val = str(v)[:100]
            print(f"  {k}: {val}")

# Count docs with job_description vs description
jd = coll.count_documents({"job_description": {"$exists": True}})
desc = coll.count_documents({"description": {"$exists": True}})
print(f"\njob_description: {jd}, description: {desc}")

# Check extracted_jd.technical_skills sample
doc2 = coll.find_one({"extracted_jd.technical_skills": {"$exists": True}})
if doc2:
    ejd = doc2["extracted_jd"]
    print(f"\n=== Sample extracted_jd ===")
    print(f"  title: {doc2.get('title')}")
    print(f"  technical_skills: {ejd.get('technical_skills')}")
    print(f"  seniority_level: {ejd.get('seniority_level')}")
    print(f"  role_category: {ejd.get('role_category')}")
    print(f"  top_keywords: {ejd.get('top_keywords')}")
