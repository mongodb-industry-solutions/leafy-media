#!/usr/bin/env python3.11
#
# Copyright (c) 2024, 2025 MongoDB Inc.
# Author: Benjamin Lorenz <benjamin.lorenz@mongodb.com>
#

# Load environment variables FIRST, before any other imports
import os
from dotenv import load_dotenv
load_dotenv()

# Startup diagnostics - check which env vars are set (without showing values)
print("=" * 60, flush=True)
print("STARTUP DIAGNOSTICS", flush=True)
print("=" * 60, flush=True)

env_vars_to_check = [
    'FLASK_CONFIG',
    'MONGODB_IST_MEDIA',
    'MONGODB_IST_MEDIA_PREVIEW',
    'OPENAI_API_KEY',
    'VOYAGE_API_KEY',
    'XAI_API_KEY',
    'AZURE_OPENAI_API_KEY',
    'LEAFY_MEDIA_AUTH_USERNAME',
    'LEAFY_MEDIA_AUTH_PASSWORD',
]

for var in env_vars_to_check:
    value = os.getenv(var)
    if value:
        # Show first 4 chars only for security
        masked = value[:4] + '***' if len(value) > 4 else '***'
        print(f"  {var}: SET ({masked})", flush=True)
    else:
        print(f"  {var}: NOT SET", flush=True)

print("=" * 60, flush=True)

from app import create_app, mongo

flask_config = os.getenv('FLASK_CONFIG') or 'production'
print(f'Using Flask config: {flask_config}', flush=True)
app = create_app(flask_config)
print("App created successfully", flush=True)


if __name__ == '__main__':
    manager.run()
