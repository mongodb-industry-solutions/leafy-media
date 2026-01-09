#
# Store vector embeddings in MongoDB
#
# Copyright (c) 2025 MongoDB Inc.
# Author: Benjamin Lorenz

import os
import json
from pymongo import MongoClient

client = MongoClient(os.environ.get('MONGODB_LEAFY_MEDIA', ''))
dbName = os.environ.get('MONGODB_DB_NAME', 'test-media')
collectionName = "print"
collection = client[dbName][collectionName]
print(f"Using database: {dbName}")

# Traverse the current directory recursively
json_files = []
for root, dirs, files in os.walk('.'):
    for file in files:
        if file.endswith('.json'):
            filepath = os.path.join(root, file)
            json_files.append(filepath)

# Insert each JSON file into MongoDB
inserted_count = 0
for filepath in json_files:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            result = collection.insert_one(data)
            inserted_count += 1
            print(f"Inserted {filepath} with ID: {result.inserted_id}")
    except Exception as e:
        print(f"Error inserting {filepath}: {e}")

print(f"Total files inserted: {inserted_count}")

client.close()
