#!/usr/bin/env python3.11
#
# Copyright (c) 2024, 2025 MongoDB Inc.
# Author: Benjamin Lorenz <benjamin.lorenz@mongodb.com>
#

# Load environment variables FIRST, before any other imports
import os
from dotenv import load_dotenv
load_dotenv()

from app import create_app, mongo

flask_config = os.getenv('FLASK_CONFIG') or 'production'
print('Using Flask config: ' + flask_config)
app = create_app(flask_config)


if __name__ == '__main__':
    manager.run()
