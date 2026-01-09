import os

openai_api_key = os.environ.get('OPENAI_API_KEY', '')

# Use different MongoDB URI based on environment
FLASK_ENV = os.environ.get('FLASK_ENV', '')
if FLASK_ENV == 'staging':
    MONGO_URI = os.environ.get('MONGODB_IST_MEDIA', '')
else:
    MONGO_URI = os.environ.get('MONGODB_LEAFY_MEDIA', '')
MONGO_DB_NAME  = os.environ.get('MONGODB_DB_NAME', 'test-media')  # Use test-media by default for cronjobs
NEWS_API_URL   = os.environ.get('NEWS_API_URL', '')
NEWS_API_KEY   = os.environ.get('NEWS_API_KEY', '')

# for clonedb.py script only
MONGO_URI_NEW  = os.environ.get('MONGODB_LEAFY_MEDIA_NEW', '')
