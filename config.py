#
# Copyright (c) 2024, 2025 MongoDB Inc.
# Author: Benjamin Lorenz <benjamin.lorenz@mongodb.com>
#

import os, logging
basedir = os.path.abspath(os.path.dirname(__file__))


class Config:

    # MongoDB Atlas - use .get() to avoid crash if env var missing
    MONGO_URI = os.environ.get('MONGODB_LEAFY_MEDIA', '')
    MONGO_URI_PREVIEW = os.environ.get('MONGODB_LEAFY_MEDIA_PREVIEW', '')

    # Content directory for media files (images, audio, video)
    CONTENT_DIR = os.environ.get('CONTENT_DIR', '/app/content')

    # currently supported LLMs
    AVAILABLE_LLMS = { 'OpenAI GPT-3.5' : 'gpt-3.5-turbo',
                       'OpenAI GPT-4'   : 'gpt-4-turbo',
                       'OpenAI GPT-4o'  : 'gpt-4o' }
    # log level
    LOG_LEVEL = logging.WARNING

    @staticmethod
    def init_app(app):
        pass


class DevelopmentConfig(Config):

    MAIN_BASE_URL = os.environ.get('MAIN_BASE_URL', 'http://localhost:9090')
    API_BASE_URL = os.environ.get('API_BASE_URL', 'http://localhost:9090/api')
    AGENTIC_BASE_URL = os.environ.get('AGENTIC_BASE_URL', 'http://localhost:9090/agentic')

    # log level
    LOG_LEVEL = logging.INFO

    # turn Flask into debug mode
    DEBUG = True


class ProductionConfig(Config):

    # URLs configurable via environment variables for Kanopy deployment
    MAIN_BASE_URL = os.environ.get('MAIN_BASE_URL', 'https://leafy.media')
    API_BASE_URL = os.environ.get('API_BASE_URL', 'https://leafy.media/api')
    AGENTIC_BASE_URL = os.environ.get('AGENTIC_BASE_URL', 'https://leafy.media/agentic')

    # cookie security
    SESSION_COOKIE_SECURE    = True
    REMEMBER_COOKIE_SECURE   = True
    REMEMBER_COOKIE_HTTPONLY = True

    @classmethod
    def init_app(cls, app):
        Config.init_app(app)


config = {
    'development' : DevelopmentConfig,
    'production'  : ProductionConfig
}
