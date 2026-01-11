#!/usr/bin/env python3
"""Test MongoDB VPS Green connection."""
import os
from urllib.parse import quote_plus
from pymongo import MongoClient

def main():
    pwd = os.environ.get('MONGO_APP_PASSWORD')
    if not pwd:
        # Read from .env file
        env_path = os.path.join(os.path.dirname(__file__), '.env')
        with open(env_path) as f:
            for line in f:
                if line.startswith('MONGO_APP_PASSWORD='):
                    pwd = line.split('=', 1)[1].strip()
                    break

    if not pwd:
        print('ERROR: MONGO_APP_PASSWORD not found')
        return

    # directConnection=true bypasses replica set member discovery (needed for external access)
    uri = f'mongodb://jobsearch_app:{quote_plus(pwd)}@72.61.92.76:27018/jobs?authSource=jobs&directConnection=true'
    print(f'Testing connection to VPS MongoDB (port 27018)...')

    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    result = client.admin.command('ping')
    print(f'Ping result: {result}')

    collections = client['jobs'].list_collection_names()
    print(f'Collections: {collections}')

    print('\nMongoDB VPS Green is healthy!')

if __name__ == '__main__':
    main()
