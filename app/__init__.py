#
# Copyright (c) 2024, 2025 MongoDB Inc.
# Author: Benjamin Lorenz <benjamin.lorenz@mongodb.com>
#

from flask import Flask
from flask_pymongo import PyMongo
from flask.json.provider import JSONProvider, DefaultJSONProvider
from apscheduler.schedulers.background import BackgroundScheduler
from bson import ObjectId
from config import config
import logging


mongo = PyMongo()
mongo_preview = PyMongo()

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler(timezone="UTC")

def json_default(obj):
    if isinstance(obj, ObjectId):
        return str(obj)
    raise TypeError

class CustomJSONProvider(DefaultJSONProvider):
    def default(self, o):
        if isinstance(o, ObjectId):
            return str(o)
        return super(CustomJSONProvider, self).default(o)

def create_app(config_name):
    app = Flask(__name__)
    app.json = CustomJSONProvider(app)
    app.secret_key = 'LEAFY_MEDIA_SECRET_KEY'
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)

    mongo.init_app(app)
    mongo_preview.init_app(app, uri=app.config["MONGO_URI_PREVIEW"])

    logging.basicConfig(
        filename = '/tmp/leafy.media.log',
        level = app.config["LOG_LEVEL"],
        format = '%(asctime)s.%(msecs)03d %(levelname)s %(module)s - %(funcName)s: %(message)s',
        datefmt = '%Y-%m-%d %H:%M:%S'
    )
    logging.getLogger('apscheduler').setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    from .main import main as main_blueprint
    app.register_blueprint(main_blueprint)

    from .api import api as api_blueprint
    app.register_blueprint(api_blueprint, url_prefix='/api')

    from .agentic import ai as ai_blueprint
    app.register_blueprint(ai_blueprint, url_prefix='/ai')

    # scheduler initialization
    from .jobs import agentic_master_planner
    from .cronjobs import (
        job_update_content,
        job_update_section,
        job_update_daily,
        job_create_podcast,
        job_keep_cache_warm,
        job_process_incoming_api,
    )

    if not scheduler.running:
        scheduler.start()

    # Existing agentic job - runs every 30 seconds
    scheduler.add_job(
        func=agentic_master_planner,
        args=[app],
        trigger='interval',
        seconds=30,
        id='agentic_master_planner',
        max_instances=1,
        replace_existing=True
    )

    # -------------------------------------------------------------------------
    # Content Update Jobs (converted from crontab)
    # -------------------------------------------------------------------------

    # Main content update: 14:09 UTC Mon-Fri
    scheduler.add_job(
        func=job_update_content,
        trigger='cron',
        hour=14, minute=9,
        day_of_week='mon-fri',
        id='job_update_content',
        max_instances=1,
        replace_existing=True
    )

    # Section updates - various schedules
    # Travel: 07:09 UTC Mon-Fri
    scheduler.add_job(
        func=job_update_section,
        args=['travel'],
        trigger='cron',
        hour=7, minute=9,
        day_of_week='mon-fri',
        id='job_update_section_travel',
        max_instances=1,
        replace_existing=True
    )

    # Autos: 08:09, 15:09 UTC Mon-Fri
    scheduler.add_job(
        func=job_update_section,
        args=['autos'],
        trigger='cron',
        hour='8,15', minute=9,
        day_of_week='mon-fri',
        id='job_update_section_autos',
        max_instances=1,
        replace_existing=True
    )

    # Europe: 09:09, 16:09 UTC Mon-Sat
    scheduler.add_job(
        func=job_update_section,
        args=['europe'],
        trigger='cron',
        hour='9,16', minute=9,
        day_of_week='mon-sat',
        id='job_update_section_europe',
        max_instances=1,
        replace_existing=True
    )

    # Tech: 10:09, 17:09 UTC Mon-Sat
    scheduler.add_job(
        func=job_update_section,
        args=['tech'],
        trigger='cron',
        hour='10,17', minute=9,
        day_of_week='mon-sat',
        id='job_update_section_tech',
        max_instances=1,
        replace_existing=True
    )

    # Business: 11:09, 18:09 UTC Mon-Sat
    scheduler.add_job(
        func=job_update_section,
        args=['business'],
        trigger='cron',
        hour='11,18', minute=9,
        day_of_week='mon-sat',
        id='job_update_section_business',
        max_instances=1,
        replace_existing=True
    )

    # International News: 12:09, 19:09 UTC Mon-Fri
    scheduler.add_job(
        func=job_update_section,
        args=['intnews'],
        trigger='cron',
        hour='12,19', minute=9,
        day_of_week='mon-fri',
        id='job_update_section_intnews',
        max_instances=1,
        replace_existing=True
    )

    # US News: 20:09 UTC Mon-Fri
    scheduler.add_job(
        func=job_update_section,
        args=['usnews'],
        trigger='cron',
        hour=20, minute=9,
        day_of_week='mon-fri',
        id='job_update_section_usnews',
        max_instances=1,
        replace_existing=True
    )

    # Finance: 13:09, 21:09 UTC Mon-Fri
    scheduler.add_job(
        func=job_update_section,
        args=['finance'],
        trigger='cron',
        hour='13,21', minute=9,
        day_of_week='mon-fri',
        id='job_update_section_finance',
        max_instances=1,
        replace_existing=True
    )

    # Earnings: 23:09 UTC Mon-Fri
    scheduler.add_job(
        func=job_update_section,
        args=['earnings'],
        trigger='cron',
        hour=23, minute=9,
        day_of_week='mon-fri',
        id='job_update_section_earnings',
        max_instances=1,
        replace_existing=True
    )

    # -------------------------------------------------------------------------
    # Daily Summary Jobs
    # -------------------------------------------------------------------------

    # Daily summary: 14:21, 23:21 UTC Mon-Fri
    scheduler.add_job(
        func=job_update_daily,
        trigger='cron',
        hour='14,23', minute=21,
        day_of_week='mon-fri',
        id='job_update_daily',
        max_instances=1,
        replace_existing=True
    )

    # Podcast creation: 14:29, 23:29 UTC Mon-Fri
    scheduler.add_job(
        func=job_create_podcast,
        trigger='cron',
        hour='14,23', minute=29,
        day_of_week='mon-fri',
        id='job_create_podcast',
        max_instances=1,
        replace_existing=True
    )

    # -------------------------------------------------------------------------
    # Recurring Maintenance Jobs
    # -------------------------------------------------------------------------

    # Process incoming API articles: 37, 58 minutes past each hour
    scheduler.add_job(
        func=job_process_incoming_api,
        trigger='cron',
        minute='37,58',
        id='job_process_incoming_api',
        max_instances=1,
        replace_existing=True
    )

    # Keep cache warm: every 7 minutes
    scheduler.add_job(
        func=job_keep_cache_warm,
        trigger='interval',
        minutes=7,
        id='job_keep_cache_warm',
        max_instances=1,
        replace_existing=True
    )

    logger.info("All cron jobs registered with APScheduler")

    return app
