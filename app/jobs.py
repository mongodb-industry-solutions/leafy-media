#
# Copyright (c) 2025 MongoDB Inc.
# Author: Benjamin Lorenz <benjamin.lorenz@mongodb.com>
#

from openai import OpenAI
from datetime import datetime
from .agentic.main import (
    ai_agent_compute_user_summary,
    ai_agent_compute_user_aquisition_promo )
import logging, ast, subprocess, os

# Feed IDs for news sections
FEED_IDS = {
    'autos': '10000101',
    'business': '10001147',
    'earnings': '15839135',
    'europe': '19794221',
    'finance': '10000664',
    'intnews': '100727362',
    'tech': '19854910',
    'travel': '10000739',
    'usnews': '15837362',
}

# TODO: In scheduler run, also
#         - change from state 'pending' to 'failed' after 4 hours,
#             if not 'success' in the meantime
#         - delete failed promotions after 2 days, to keep demo view clear

logger = logging.getLogger(__name__)

def agentic_master_planner(app):
    """Master planner scheduled task. Runs inside the Flask app context."""
    from . import mongo

    with app.app_context():
        cursor = mongo.db.users.find(
            {
                "$or" : [
                    { "summary" : { "$exists" : False }},
                    { "$expr" : { "$gt" : [ "$last_active", "$summary.ts" ]}}
                ]
            },
            { "username" : 1, "fullname" : 1 }
        )

        for user in cursor:
            username = user["username"]
            fullname = user["fullname"]

            # re-generate user summary for users with recent activity
            logger.info(f"(Re-)generating user summary for {username}")
            try:
                if not (summary_text := ai_agent_compute_user_summary(username)):
                    summary_text = "No insights available (yet)."
                mongo.db.users.update_one(
                    { "_id" : user["_id"] },
                    { "$set" : {
                        "summary" : {
                            "text" : summary_text,
                            "ts" : datetime.utcnow()
                        }
                    }}
                )
            except Exception as e:
                logger.error(f"While re-generating user summary: {e}")

            # for anonymous users with recent activity, check
            # - if there's already a promotion for them in place,
            # - if not, ask the ai agent to generate one, only if
            #   this is a suitable prospect. The agent will decide.
            if fullname != 'Anonymous User':
                return # acquisition promo only applies to anonymous users
            if not mongo.db.planner.find_one({ "username" : username }):
                if (result := ai_agent_compute_user_aquisition_promo(username)):
                    add_promotion, promo_type, promo_text, why = ast.literal_eval(result)
                    logger.info(f"User acquisition agent: {username}, {promo_type}, { promo_text}, {why}")
                    if add_promotion:
                        mongo.db.planner.update_one(
                            { "username" : username },
                            { "$set" : {
                                "promo" : {
                                    "text" : promo_text,
                                    "ts" : datetime.utcnow()
                                },
                                "type" : promo_type,
                                "why" : why
                            }},
                            upsert=True
                        )


def run_script(script_name, *args):
    """Run a script from the scripts directory."""
    scripts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts')
    script_path = os.path.join(scripts_dir, script_name)
    cmd = ['python', script_path] + list(args)
    logger.info(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.stdout:
            logger.info(f"[{script_name}] {result.stdout}")
        if result.stderr:
            logger.warning(f"[{script_name}] {result.stderr}")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        logger.error(f"[{script_name}] Timeout after 600s")
        return False
    except Exception as e:
        logger.error(f"[{script_name}] Error: {e}")
        return False


def update_section(section):
    """Update a news section: collect, generate images, process, vectorize."""
    feed_id = FEED_IDS.get(section)
    if not feed_id:
        logger.error(f"Unknown section: {section}")
        return

    logger.info(f"=== Updating section: {section} (feed: {feed_id}) ===")
    run_script('news_collect_2.py', feed_id)
    run_script('create_images.py')
    run_script('process_incoming.py')
    run_script('vectorize.py')
    run_script('add_sentiment.py')
    run_script('add_sections.py')
    logger.info(f"=== Section {section} update complete ===")


def update_daily_summary():
    """Generate daily summary."""
    logger.info("=== Generating daily summary ===")
    run_script('daily.py')
    run_script('daily-entities.py')
    logger.info("=== Daily summary complete ===")


def create_podcast():
    """Generate podcast from daily summary."""
    logger.info("=== Creating podcast ===")
    run_script('podcast.py')
    logger.info("=== Podcast complete ===")


def update_content():
    """Update content: collect news, generate images, process pipeline."""
    logger.info("=== Updating content (news_collect) ===")
    run_script('news_collect.py')
    run_script('create_images.py')
    run_script('process_incoming.py')
    run_script('vectorize.py')
    run_script('add_sentiment.py')
    run_script('add_sections.py')
    logger.info("=== Content update complete ===")


def send_daily_mail():
    """Send daily email newsletter."""
    logger.info("=== Sending daily mail ===")
    run_script('daily-mail.py')
    logger.info("=== Daily mail sent ===")


def process_incoming_api():
    """Process incoming API content: delete non-api, process pipeline, delete api."""
    logger.info("=== Processing incoming API content ===")
    run_script('delete_non_api.py')
    run_script('create_images.py')
    run_script('process_incoming.py')
    run_script('vectorize.py')
    run_script('add_sentiment.py')
    run_script('add_sections.py')
    run_script('delete_api.py')
    logger.info("=== Incoming API processing complete ===")


def keep_cache_warm():
    """Keep cache warm by running keepwarm script."""
    logger.info("=== Keeping cache warm ===")
    run_script('keepwarm.py')
    logger.info("=== Cache warm complete ===")
