import os

openai_api_key = os.environ.get('OPENAI_API_KEY', '')

# MongoDB URI
MONGO_URI = os.environ.get('MONGODB_IST_MEDIA', '')
MONGO_DB_NAME  = os.environ.get('MONGODB_DB_NAME', '')  # Set via MONGODB_DB_NAME env var
NEWS_API_URL   = os.environ.get('NEWS_API_URL', '')
NEWS_API_KEY   = os.environ.get('NEWS_API_KEY', '')

# for clonedb.py script only
MONGO_URI_NEW  = os.environ.get('MONGODB_IST_MEDIA_NEW', '')
