#
# Copyright (c) 2024, 2025 MongoDB Inc.
# Author: Benjamin Lorenz <benjamin.lorenz@mongodb.com>
#

from flask import Flask, request, g
from flask_pymongo import PyMongo
from flask.json.provider import JSONProvider, DefaultJSONProvider
from apscheduler.schedulers.background import BackgroundScheduler
from bson import ObjectId
from config import config
import logging
import os
import sys
import time
import traceback


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
    app = Flask(__name__, static_url_path='')
    app.json = CustomJSONProvider(app)
    app.secret_key = 'LEAFY_MEDIA_SECRET_KEY'
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)

    # Configure logging to output to both file and console (for kubectl logs)
    log_format = '%(asctime)s.%(msecs)03d %(levelname)s %(module)s - %(funcName)s: %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'

    # Console handler (shows in kubectl logs)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(log_format, date_format))

    # File handler
    file_handler = logging.FileHandler('/tmp/leafy.media.log')
    file_handler.setLevel(app.config["LOG_LEVEL"])
    file_handler.setFormatter(logging.Formatter(log_format, date_format))

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    logging.getLogger('apscheduler').setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger('werkzeug').setLevel(logging.WARNING)

    # Initialize MongoDB connections
    print("[INIT] Initializing MongoDB connections...", flush=True)
    try:
        mongo.init_app(app)
        print("[INIT] Primary MongoDB initialized", flush=True)
    except Exception as e:
        print(f"[ERROR] Failed to initialize primary MongoDB: {e}", flush=True)
        print(f"[ERROR] Traceback: {traceback.format_exc()}", flush=True)

    try:
        mongo_preview.init_app(app, uri=app.config["MONGO_URI_PREVIEW"])
        print("[INIT] Preview MongoDB initialized", flush=True)
    except Exception as e:
        print(f"[ERROR] Failed to initialize preview MongoDB: {e}", flush=True)
        print(f"[ERROR] Traceback: {traceback.format_exc()}", flush=True)

    # Test MongoDB connection
    with app.app_context():
        try:
            # Attempt to ping the database
            mongo.cx.admin.command('ping')
            print("[INIT] MongoDB connection test: SUCCESS", flush=True)
        except Exception as e:
            print(f"[ERROR] MongoDB connection test FAILED: {e}", flush=True)
            print(f"[ERROR] This likely means the database is unreachable (IP allowlist or network issue)", flush=True)

    from .main import main as main_blueprint
    app.register_blueprint(main_blueprint)

    from .api import api as api_blueprint
    app.register_blueprint(api_blueprint, url_prefix='/api')

    from .agentic import ai as ai_blueprint
    app.register_blueprint(ai_blueprint, url_prefix='/ai')

    # Scheduler initialization
    from .jobs import (
        agentic_master_planner,
        update_section,
        update_daily_summary,
        create_podcast,
        update_content,
        send_daily_mail,
        process_incoming_api,
        keep_cache_warm
    )

    if not scheduler.running:
        scheduler.start()

    # Agentic planner - every 30 seconds
    scheduler.add_job(
        func=agentic_master_planner,
        args=[app],
        trigger='interval',
        seconds=30,
        id='agentic_master_planner',
        max_instances=1,
        replace_existing=True
    )

    # Content update jobs - determine if enabled based on environment
    # staging: disabled by default, production: enabled by default
    flask_env = os.getenv('FLASK_ENV', '')
    enable_jobs_override = os.getenv('ENABLE_CONTENT_JOBS', '')

    if enable_jobs_override:
        jobs_enabled = enable_jobs_override.lower() == 'true'
    else:
        jobs_enabled = flask_env == 'production'

    if jobs_enabled:
        print(f"[SCHEDULER] Content jobs ENABLED (FLASK_ENV={flask_env})", flush=True)

        # Section updates (weekdays, staggered throughout the day - UTC times)
        scheduler.add_job(func=update_section, args=['travel'], trigger='cron', hour=7, minute=9, day_of_week='mon-fri', id='update_travel', max_instances=1, replace_existing=True)
        scheduler.add_job(func=update_section, args=['autos'], trigger='cron', hour='8,15', minute=9, day_of_week='mon-fri', id='update_autos', max_instances=1, replace_existing=True)
        scheduler.add_job(func=update_section, args=['europe'], trigger='cron', hour='9,16', minute=9, day_of_week='mon-sat', id='update_europe', max_instances=1, replace_existing=True)
        scheduler.add_job(func=update_section, args=['tech'], trigger='cron', hour='10,17', minute=9, day_of_week='mon-sat', id='update_tech', max_instances=1, replace_existing=True)
        scheduler.add_job(func=update_section, args=['business'], trigger='cron', hour='11,18', minute=9, day_of_week='mon-sat', id='update_business', max_instances=1, replace_existing=True)
        scheduler.add_job(func=update_section, args=['intnews'], trigger='cron', hour='12,19', minute=9, day_of_week='mon-fri', id='update_intnews', max_instances=1, replace_existing=True)
        scheduler.add_job(func=update_section, args=['usnews'], trigger='cron', hour=20, minute=9, day_of_week='mon-fri', id='update_usnews', max_instances=1, replace_existing=True)
        scheduler.add_job(func=update_section, args=['finance'], trigger='cron', hour='13,21', minute=9, day_of_week='mon-fri', id='update_finance', max_instances=1, replace_existing=True)
        scheduler.add_job(func=update_section, args=['earnings'], trigger='cron', hour=23, minute=9, day_of_week='mon-fri', id='update_earnings', max_instances=1, replace_existing=True)

        # Daily summary (weekdays 14:21 & 23:21 UTC)
        scheduler.add_job(func=update_daily_summary, trigger='cron', hour='14,23', minute=21, day_of_week='mon-fri', id='daily_summary', max_instances=1, replace_existing=True)

        # Podcast (weekdays 14:29 & 23:29 UTC)
        scheduler.add_job(func=create_podcast, trigger='cron', hour='14,23', minute=29, day_of_week='mon-fri', id='create_podcast', max_instances=1, replace_existing=True)

        # Update content - news_collect (weekdays 14:09 UTC)
        scheduler.add_job(func=update_content, trigger='cron', hour=14, minute=9, day_of_week='mon-fri', id='update_content', max_instances=1, replace_existing=True)

        # Send daily email (weekdays 23:25 UTC)
        scheduler.add_job(func=send_daily_mail, trigger='cron', hour=23, minute=25, day_of_week='mon-fri', id='send_daily_mail', max_instances=1, replace_existing=True)

        # Process incoming API content (every hour at :37 and :58)
        scheduler.add_job(func=process_incoming_api, trigger='cron', minute='37,58', id='process_incoming_api', max_instances=1, replace_existing=True)

        # Keep cache warm (every 7 minutes)
        scheduler.add_job(func=keep_cache_warm, trigger='interval', minutes=7, id='keep_cache_warm', max_instances=1, replace_existing=True)
    else:
        print(f"[SCHEDULER] Content jobs DISABLED (FLASK_ENV={flask_env}, set ENABLE_CONTENT_JOBS=true to override)", flush=True)

    # Request logging middleware
    @app.before_request
    def before_request_logging():
        """Log request start and store timing info."""
        # Skip logging for health checks to reduce noise
        if request.path == '/health':
            return
        g.request_start_time = time.time()
        print(f"[REQUEST] {request.method} {request.path} started", flush=True)

    @app.after_request
    def after_request_logging(response):
        """Log request completion with timing and status."""
        # Skip logging for health checks to reduce noise
        if request.path == '/health':
            return response

        duration = 0
        if hasattr(g, 'request_start_time'):
            duration = (time.time() - g.request_start_time) * 1000  # ms

        status_emoji = "✓" if response.status_code < 400 else "✗"
        print(f"[REQUEST] {status_emoji} {request.method} {request.path} -> {response.status_code} ({duration:.0f}ms)", flush=True)

        # Log slow requests
        if duration > 5000:
            print(f"[SLOW REQUEST] {request.method} {request.path} took {duration:.0f}ms", flush=True)

        return response

    print("[INIT] App initialization complete", flush=True)

    return app
