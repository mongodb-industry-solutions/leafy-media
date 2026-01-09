#
# Download images to local directory
#
# Copyright (c) 2024, 2025 MongoDB Inc.
# Author: Benjamin Lorenz <benjamin.lorenz@mongodb.com>

from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from time import sleep
import keyparams, os, requests

client = MongoClient(keyparams.MONGO_URI)
dbName = keyparams.MONGO_DB_NAME
collectionName = "business_news"
collection = client[dbName][collectionName]
print(f"Using database: {dbName}")


content_dir = os.environ.get('CONTENT_DIR', '/app/content')
target_dir = os.environ.get('IMAGES_TMP_DIR', f'{content_dir}/images')
os.makedirs(target_dir, exist_ok=True)


i = 0
try:
    for doc in collection.find():
        i += 1
        if i % 50 == 0:
            print("\n" + str(i))
        img_data = requests.get(doc['thread']['main_image']).content
        with open(target_dir + '/' + doc['uuid'] + '.jpg', 'wb') as handler:
            handler.write(img_data)
        print(".", end="", flush=True)
        sleep(0.5)
except Exception as e:
    print(e)
    exit(1)

print("\nDone")
