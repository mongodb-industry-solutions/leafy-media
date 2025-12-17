#
# Cron Jobs for Leafy Media
# Converted from shell-based cron to APScheduler for Kanopy deployment
#
# Copyright (c) 2024, 2025 MongoDB Inc.
# Author: Benjamin Lorenz <benjamin.lorenz@mongodb.com>
#

import os
import re
import json
import uuid
import datetime
import logging
import subprocess
import requests
import feedparser
import cloudscraper
import httpx
import time
import random
import pymongo

from time import sleep
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from dateutil import parser as date_parser
from pymongo.errors import DuplicateKeyError
from openai import OpenAI, AzureOpenAI
from pydub import AudioSegment
from faker import Faker

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration - use environment variables
# ---------------------------------------------------------------------------

def get_mongo_client():
    """Get MongoDB client using environment variable."""
    return pymongo.MongoClient(os.environ.get('MONGODB_LEAFY_MEDIA', ''))

def get_db():
    """Get the database instance."""
    return get_mongo_client()["1_media_demo"]

def get_content_dir():
    """Get the content directory path."""
    return os.environ.get('CONTENT_DIR', '/app/content')

def get_tmp_dir():
    """Get the temporary directory for image processing."""
    tmp_dir = '/tmp/images.leafy.media'
    os.makedirs(tmp_dir, exist_ok=True)
    return tmp_dir

# ---------------------------------------------------------------------------
# News Collection Jobs
# ---------------------------------------------------------------------------

def job_news_collect():
    """
    Collect articles from Guardian API.
    Originally: cronjobs/update_content.sh -> scripts/news_collect.py
    """
    logger.info("Starting job_news_collect")

    db = get_db()
    collection = db["news_incoming"]

    api_key = os.environ.get('NEWS_API_KEY', '')
    search_url = os.environ.get('NEWS_API_URL', '')

    if not api_key or not search_url:
        logger.error("NEWS_API_KEY or NEWS_API_URL not configured")
        return

    params = {
        'api-key': api_key,
        'type': 'article',
        'section': 'world',
        'show-blocks': 'all'
    }

    try:
        response = requests.get(search_url, params=params)
        data = response.json()

        if response.status_code == 200:
            collection.delete_many({})  # erase incoming
            for article in data['response']['results'][:5]:
                imageURL = None
                bodyHTML = ""
                rawText = ""
                article_id = article['id']
                webURL = article['webUrl']
                title = article['webTitle']
                publishedDate = article['webPublicationDate']
                elements = article['blocks']['main']['elements']

                for element in elements:
                    if element['type'] == 'image':
                        assets = element['assets']
                        for asset in assets:
                            if asset['typeData']['width'] == 1000:
                                imageURL = asset['file']
                                break

                bodyChunks = article['blocks']['body']
                for chunk in bodyChunks:
                    bodyHTML = chunk['bodyHtml']
                    rawText = chunk['bodyTextSummary']
                    break

                if imageURL:
                    raw_article = {
                        'uuid': str(uuid.uuid5(uuid.NAMESPACE_DNS, article_id)),
                        'weburl': webURL,
                        'title': title,
                        'published': publishedDate,
                        'imageurl': imageURL,
                        'html': bodyHTML,
                        'text': rawText
                    }
                    try:
                        collection.insert_one(raw_article)
                        logger.debug(f"Inserted article: {title}")
                    except DuplicateKeyError:
                        logger.debug(f"Duplicate article: {title}")
        else:
            logger.error(f"API Error: {response.status_code} - {data}")
    except Exception as e:
        logger.error(f"job_news_collect failed: {e}")


def job_news_collect_section(sector_id: str):
    """
    Collect articles from CNBC RSS feed for a specific section.
    Originally: cronjobs/update_section.sh -> scripts/news_collect_2.py
    """
    logger.info(f"Starting job_news_collect_section for sector {sector_id}")

    db = get_db()
    collection = db["news_incoming"]

    base_url = 'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01'
    url = base_url + '&id=' + sector_id

    feed = feedparser.parse(url)
    collection.delete_many({})  # erase incoming

    scraper = cloudscraper.create_scraper()

    def get_full_text(article_url):
        try:
            response = scraper.get(article_url)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                group_divs = soup.find_all('div', class_='group')
                full_text = ''
                for div in group_divs:
                    p_tags = div.find_all('p')
                    for p in p_tags:
                        full_text += p.get_text().strip() + ' '
                return full_text.strip()
            else:
                logger.warning(f"Failed to fetch: {article_url}: HTTP {response.status_code}")
                return ""
        except Exception as e:
            logger.error(f"Failed to fetch full article: {e}")
            return ""

    for entry in feed.entries[:5]:
        title = entry.title if 'title' in entry else ''
        article_url = entry.link if 'link' in entry else ''

        date = entry.published if 'published' in entry else ''
        if date:
            try:
                date = date_parser.parse(date).strftime('%Y-%m-%dT%H:%M:%SZ')
            except Exception:
                date = None

        full_text = get_full_text(article_url) if article_url else ''

        if len(full_text) < 500:
            continue

        raw_article = {
            'uuid': str(uuid.uuid5(uuid.NAMESPACE_DNS, entry.id)),
            'weburl': article_url,
            'title': title,
            'published': date,
            'text': full_text
        }
        try:
            collection.insert_one(raw_article)
            logger.debug(f"Inserted section article: {title}")
        except DuplicateKeyError:
            logger.debug(f"Duplicate section article: {title}")
        except Exception as e:
            logger.error(f"Error inserting article: {e}")


# Section ID mapping
SECTION_FEED_IDS = {
    'travel': '10000101',
    'autos': '10000101',
    'business': '10001147',
    'earnings': '15839135',
    'europe': '19794221',
    'finance': '10000664',
    'intnews': '100727362',
    'tech': '19854910',
    'usnews': '15837362',
}

def job_update_section(section_name: str):
    """Wrapper to update a specific news section."""
    feed_id = SECTION_FEED_IDS.get(section_name)
    if feed_id:
        job_news_collect_section(feed_id)
        job_process_content_pipeline()
    else:
        logger.error(f"Unknown section: {section_name}")


# ---------------------------------------------------------------------------
# Content Processing Pipeline
# ---------------------------------------------------------------------------

def job_create_images():
    """
    Generate images for new articles using Azure OpenAI DALL-E.
    Originally: scripts/create_images.py
    """
    logger.info("Starting job_create_images")

    db = get_db()
    incoming = db["news_incoming"]
    news = db["news"]
    tmp_dir = get_tmp_dir()

    try:
        ai = AzureOpenAI(
            api_version="2024-02-01",
            api_key=os.environ.get("AZURE_OPENAI_API_KEY", ""),
            azure_endpoint=os.environ.get('AZURE_OPENAI_ENDPOINT', '')
        )
    except Exception as e:
        logger.error(f"Failed to initialize Azure OpenAI: {e}")
        return

    uuids_to_delete = []

    try:
        for doc in incoming.find():
            if news.find_one({'uuid': doc['uuid']}):
                continue

            prompt = """Never show people, organizations, or copyrighted
            elements. If the following contains text that is not allowed by
            your safety system then please create a compliant image that
            comes close: """ + doc['title'] + " " + doc['text'][:350]

            try:
                response = ai.images.generate(
                    model="dall-e-3",
                    prompt=prompt,
                    size="1792x1024",
                    quality="standard",
                    n=1
                )
                img_data = requests.get(response.data[0].url).content
                png_path = os.path.join(tmp_dir, doc['uuid'] + '.png')
                with open(png_path, 'wb') as handler:
                    handler.write(img_data)
                logger.debug(f"Created image for: {doc['title']}")
            except Exception as e:
                logger.warning(f"Image generation failed for {doc['uuid']}: {e}")
                uuids_to_delete.append(doc['uuid'])
                continue

            sleep(10)  # Rate limiting

        for uuid_to_del in uuids_to_delete:
            incoming.delete_one({'uuid': uuid_to_del})

    except Exception as e:
        logger.error(f"job_create_images failed: {e}")


def job_convert_images():
    """
    Convert PNG images to WebP and move to content directory.
    Originally: shell commands in update_content.sh
    """
    logger.info("Starting job_convert_images")

    tmp_dir = get_tmp_dir()
    content_dir = get_content_dir()
    images_dir = os.path.join(content_dir, 'images')
    os.makedirs(images_dir, exist_ok=True)

    try:
        for filename in os.listdir(tmp_dir):
            if filename.endswith('.png'):
                png_path = os.path.join(tmp_dir, filename)
                webp_filename = filename.replace('.png', '.webp')
                webp_path = os.path.join(tmp_dir, webp_filename)
                final_path = os.path.join(images_dir, webp_filename)

                # Convert using ImageMagick (magick command)
                try:
                    subprocess.run(['magick', png_path, webp_path], check=True)
                    # Move to content directory
                    os.rename(webp_path, final_path)
                    # Clean up PNG
                    os.remove(png_path)
                    logger.debug(f"Converted and moved: {webp_filename}")
                except subprocess.CalledProcessError as e:
                    logger.error(f"ImageMagick conversion failed: {e}")
                except FileNotFoundError:
                    # If magick not found, try using Pillow as fallback
                    try:
                        from PIL import Image
                        img = Image.open(png_path)
                        img.save(final_path, 'WEBP')
                        os.remove(png_path)
                        logger.debug(f"Converted with Pillow: {webp_filename}")
                    except Exception as e:
                        logger.error(f"Image conversion failed: {e}")
    except Exception as e:
        logger.error(f"job_convert_images failed: {e}")


def job_process_incoming():
    """
    Process incoming articles - rewrite with GPT-4o and move to news collection.
    Originally: scripts/process_incoming.py
    """
    logger.info("Starting job_process_incoming")

    db = get_db()
    incoming = db["news_incoming"]
    news = db["news"]

    ai = OpenAI()

    def gen(text):
        prompt = f"""
        Write three paragraphs in your own words based on the following text:
        {text}
        """
        try:
            response = ai.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2000,
                n=1,
                temperature=0.7
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"GPT-4o generation failed: {e}")
            return None

    try:
        for doc in incoming.find():
            if news.find_one({'uuid': doc['uuid']}):
                continue

            new_text = gen(doc['text'])
            if not new_text:
                continue

            doc['text'] = new_text
            del doc['_id']

            try:
                news.insert_one(doc)
                logger.debug(f"Processed article: {doc['title']}")
            except DuplicateKeyError:
                pass

            sleep(0.5)
    except Exception as e:
        logger.error(f"job_process_incoming failed: {e}")


def job_vectorize():
    """
    Add vector embeddings to news documents.
    Originally: scripts/vectorize.py
    """
    logger.info("Starting job_vectorize")

    db = get_db()
    collection = db["news"]

    openai_client = OpenAI()

    def generate_embedding(text: str):
        response = openai_client.embeddings.create(
            model="text-embedding-ada-002",
            input=text
        )
        return response.data[0].embedding

    try:
        for doc in collection.find({"embedding": {"$exists": False}}):
            try:
                embedding = generate_embedding(doc['text'])
                collection.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"embedding": embedding}}
                )
                logger.debug(f"Vectorized: {doc.get('title', 'unknown')}")
            except Exception as e:
                logger.warning(f"Embedding failed for {doc['_id']}: {e}")
                collection.delete_one({"_id": doc["_id"]})
    except Exception as e:
        logger.error(f"job_vectorize failed: {e}")


def job_add_sentiment():
    """
    Add sentiment analysis to news documents.
    Originally: scripts/add_sentiment.py
    """
    logger.info("Starting job_add_sentiment")

    db = get_db()
    collection = db["news"]

    ai = OpenAI()

    def sentiment(text):
        prompt = f"""
        I want you to detect the sentiment of an article, which can be one
        of '+' (positive), 'o' (neutral), or '-' (negative). Please
        return as a single char without quotes that can be processed
        programmatically. The article starts now:
        {text}
        """
        try:
            response = ai.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=10,
                n=1,
                temperature=0.7
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Sentiment analysis failed: {e}")
            return None

    try:
        for doc in collection.find({"sentiment": {"$exists": False}}):
            try:
                sent = sentiment(doc['text'])
                if sent:
                    collection.update_one(
                        {"_id": doc["_id"]},
                        {"$set": {"sentiment": sent}}
                    )
                    logger.debug(f"Added sentiment for: {doc.get('title', 'unknown')}")
            except Exception as e:
                logger.warning(f"Sentiment failed for {doc['_id']}: {e}")
    except Exception as e:
        logger.error(f"job_add_sentiment failed: {e}")


def job_add_sections():
    """
    Add section categorization to news documents using xAI Grok.
    Originally: scripts/add_sections.py
    """
    logger.info("Starting job_add_sections")

    db = get_db()
    collection = db["news"]

    xai_key = os.environ.get("XAI_API_KEY", "")
    if not xai_key:
        logger.warning("XAI_API_KEY not set, skipping section detection")
        return

    ai = OpenAI(
        api_key=xai_key,
        base_url="https://api.x.ai/v1",
    )

    def detect_sections(text):
        prompt = f"""
        I want you to detect the sections of a news article. Each article
        belongs to at least one, and at most 3 sections. You decide!

        You can choose from these sections to build the list:
        Automotive, Business, Careers & Work, Culture, Education,
        Entertainment, Environment, Finance, Health, Lifestyle,
        Politics, Real Estate, Science & Tech, Sports, Travel

        Please use ONLY items from the list above. NO OTHER items!
        The list may not contain more than ONE of the following sections:
        Finance, Business, Science & Tech

        Please return as a Python list without ``` or ```python that
        can be processed programmatically. The article starts now:
        {text}
        """
        try:
            response = ai.chat.completions.create(
                model="grok-3",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=100,
                n=1,
                temperature=0.7
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Section detection failed: {e}")
            return None

    try:
        for doc in collection.find({"sections": {"$exists": False}}):
            try:
                sections_str = detect_sections(doc['text'])
                if sections_str:
                    sections = eval(sections_str)
                    collection.update_one(
                        {"_id": doc["_id"]},
                        {"$set": {"sections": sections}}
                    )
                    logger.debug(f"Added sections for: {doc.get('title', 'unknown')}")
            except Exception as e:
                logger.warning(f"Section detection failed for {doc['_id']}: {e}")
    except Exception as e:
        logger.error(f"job_add_sections failed: {e}")


def job_process_content_pipeline():
    """
    Full content processing pipeline.
    Originally: cronjobs/update_content.sh (after news_collect.py)
    """
    logger.info("Starting full content processing pipeline")
    job_create_images()
    job_convert_images()
    job_process_incoming()
    job_vectorize()
    job_add_sentiment()
    job_add_sections()
    logger.info("Content processing pipeline complete")


def job_update_content():
    """
    Main content update job - collect news and process.
    Originally: cronjobs/update_content.sh
    Schedule: 14:09 UTC Mon-Fri
    """
    logger.info("Starting job_update_content")
    job_news_collect()
    job_process_content_pipeline()
    logger.info("job_update_content complete")


# ---------------------------------------------------------------------------
# Daily Summary Jobs
# ---------------------------------------------------------------------------

def job_daily_summary():
    """
    Generate daily news summary.
    Originally: scripts/daily.py
    Schedule: 14:21, 23:21 UTC Mon-Fri
    """
    logger.info("Starting job_daily_summary")

    db = get_db()
    news_collection = db["news"]
    daily_collection = db["daily"]

    ai = OpenAI()

    def get_mongodb_date_filter(natural_language_date):
        today = datetime.datetime.now(datetime.UTC)
        prompt = f"""
        Convert the following time expression into a MongoDB-compatible filter format.
        Example:
        - "last week" → {{ "$gte": "<YYYY-MM-DD>", "$lt": "<YYYY-MM-DD>" }}
        - "yesterday" → {{ "$gte": "<YYYY-MM-DD>", "$lt": "<YYYY-MM-DD>" }}
        Time expression: "{natural_language_date}"
        Never create date expressions that point to the future.
        Return **only** a valid JSON object, without explanations.
        Today is "{today}"
        """
        response = ai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        raw_text = response.choices[0].message.content.strip()
        try:
            json_text = raw_text.strip("`")
            return json.loads(json_text)
        except json.JSONDecodeError:
            return None

    def get_context():
        pipeline = [
            {"$match": {"published": get_mongodb_date_filter("today")}},
            {"$project": {"uuid": 1, "title": 1, "text": {"$substrCP": ["$text", 0, 1500]}}}
        ]
        return list(news_collection.aggregate(pipeline))

    context = get_context()

    prompt = f"""
    You are a news reporting web service.
    Generate a dossier of news from the text fields in the JSON list.
    Do not use bullet points. Combine them intelligently as floating text.
    Highlight entities central to stories (people, products, companies).
    Include links as https://leafy.media/post?uuid=<uuid> using the title.
    At the beginning, add headlines summary: Headline 1 | Headline 2 | ...
    "{context}"
    """

    try:
        response = ai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )

        now = datetime.datetime.now(datetime.UTC)
        formatted_date = now.strftime("%d %B %Y")
        summary = response.choices[0].message.content.strip()

        daily_collection.update_one(
            {"day": formatted_date},
            {"$set": {"summary": summary}},
            upsert=True
        )
        logger.info(f"Daily summary created for {formatted_date}")
    except Exception as e:
        logger.error(f"job_daily_summary failed: {e}")


def job_daily_entities():
    """
    Extract entities from daily news.
    Originally: scripts/daily-entities.py
    """
    logger.info("Starting job_daily_entities")

    db = get_db()
    news_collection = db["news"]
    daily_collection = db["daily"]

    ai = OpenAI()

    def get_mongodb_date_filter(natural_language_date):
        today = datetime.datetime.now(datetime.UTC)
        prompt = f"""
        Convert the following time expression into a MongoDB-compatible filter format.
        Time expression: "{natural_language_date}"
        Return **only** a valid JSON object.
        Today is "{today}"
        """
        response = ai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        raw_text = response.choices[0].message.content.strip()
        try:
            return json.loads(raw_text.strip("`"))
        except json.JSONDecodeError:
            return None

    def get_context():
        pipeline = [
            {"$match": {"published": get_mongodb_date_filter("today")}},
            {"$project": {"uuid": 1, "title": 1, "text": {"$substrCP": ["$text", 0, 1500]}}}
        ]
        return list(news_collection.aggregate(pipeline))

    context = get_context()

    prompt = f"""
    You are an entity extraction service.
    Generate a python list of 15 entities from the text fields.
    Include names, locations, companies, concepts, initiatives, events.
    Return a machine-readable Python list. No ```python prefix.
    "{context}"
    """

    try:
        response = ai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )

        now = datetime.datetime.now(datetime.UTC)
        formatted_date = now.strftime("%d %B %Y")

        entities_string = response.choices[0].message.content.strip()
        entities_string = re.sub(r"(?<=\w)'(?=\w)", "\\\\'", entities_string)
        entities = eval(entities_string)
        entities = list(filter(lambda e: len(e) < 30, entities))[:20]

        daily_collection.update_one(
            {"day": formatted_date},
            {"$set": {"entities": entities}},
            upsert=True
        )
        logger.info(f"Daily entities extracted for {formatted_date}")
    except Exception as e:
        logger.error(f"job_daily_entities failed: {e}")


def job_update_daily():
    """
    Full daily update job.
    Originally: cronjobs/update_daily.sh
    Schedule: 14:21, 23:21 UTC Mon-Fri
    """
    logger.info("Starting job_update_daily")
    job_daily_summary()
    job_daily_entities()
    logger.info("job_update_daily complete")


# ---------------------------------------------------------------------------
# Podcast Job
# ---------------------------------------------------------------------------

def job_create_podcast():
    """
    Convert daily news summary into a podcast.
    Originally: scripts/podcast.py
    Schedule: 14:29, 23:29 UTC Mon-Fri
    """
    logger.info("Starting job_create_podcast")

    content_dir = get_content_dir()
    audio_dir = os.path.join(content_dir, 'audio')
    os.makedirs(audio_dir, exist_ok=True)
    podcast_tmp_file = '/tmp/podcast_tmp.mp3'

    token = os.environ.get('AUTOCONTENT_API_KEY', '')
    if not token:
        logger.warning("AUTOCONTENT_API_KEY not set, skipping podcast creation")
        return

    create_url = 'https://api.autocontentapi.com/Content/Create'
    status_base_url = 'https://api.autocontentapi.com/content/status/'
    poll_interval = 10
    today = datetime.datetime.now(datetime.UTC)

    # Get the daily feed content
    base_url = os.environ.get('MAIN_BASE_URL', 'https://leafy.media')
    try:
        response = requests.get(f"{base_url}/feed")
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        paragraphs = [p.get_text() for p in soup.body.find_all("p", recursive=False)]
        news_content = "\n\n".join(paragraphs)
    except Exception as e:
        logger.error(f"Failed to fetch feed: {e}")
        return

    spoken_today = today.strftime("%B %-d")
    request_data = {
        "resources": [{"content": news_content, "type": "text"}],
        "text": f"""
        Create a summary of the news for the day. Merge topics
        of similar category. Mention the date "{spoken_today}".
        No social grunting, no "uh", "aha", "wow". No intro comments.
        """,
        "outputType": "audio"
    }

    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        'accept': 'text/plain'
    }

    try:
        # Create content request
        response = requests.post(create_url, json=request_data, headers=headers)
        response.raise_for_status()
        request_id = response.json().get('request_id')

        if not request_id:
            logger.error("No request_id returned from podcast API")
            return

        logger.info(f"Podcast request initiated: {request_id}")

        # Poll for completion
        headers['accept'] = 'application/json'
        max_attempts = 30

        for _ in range(max_attempts):
            status_response = requests.get(
                f'{status_base_url}{request_id}',
                headers=headers
            )
            status_response.raise_for_status()
            data = status_response.json()

            if data.get('error_message'):
                logger.error(f"Podcast API error: {data['error_message']}")
                return

            if data.get('status') == 100:
                audio_url = data.get('audio_url')
                logger.info(f"Podcast ready: {audio_url}")

                # Download and process audio
                podcast_data = requests.get(audio_url).content
                with open(podcast_tmp_file, 'wb') as handler:
                    handler.write(podcast_data)

                audio = AudioSegment.from_file(podcast_tmp_file, format="mp3")
                audio = audio.set_frame_rate(44100)
                filename = f"{audio_dir}/podcast-{today:%d.%m.%Y}.mp3"
                audio.export(filename, format="mp3", bitrate="192k")

                logger.info(f"Podcast saved: {filename}")
                return

            logger.debug(f"Podcast status: {data.get('status')}, waiting...")
            time.sleep(poll_interval)

        logger.warning("Podcast creation timed out")

    except Exception as e:
        logger.error(f"job_create_podcast failed: {e}")


# ---------------------------------------------------------------------------
# Cache Warming Job
# ---------------------------------------------------------------------------

def job_keep_cache_warm():
    """
    Keep filesystem, network, and MongoDB caches warm.
    Originally: scripts/keepwarm.py
    Schedule: Every 7 minutes
    """
    logger.info("Starting job_keep_cache_warm")

    base_url = os.environ.get('MAIN_BASE_URL', 'https://leafy.media')
    headers = {"User-Agent": "Mozilla/5.0 (CacheWarmer)"}
    timeout = httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=10.0)
    faker = Faker()

    def get_articles(client, url):
        res = client.get(url)
        soup = BeautifulSoup(res.text, "html.parser")
        return soup.select("a.tm-post-link")

    def click_articles(client, links):
        for a in links[:2]:
            href = a.get("href")
            if not href:
                continue
            full_url = urljoin(base_url, href)
            try:
                client.get(full_url)
            except Exception:
                pass
            time.sleep(0.5)

    try:
        with httpx.Client(
            headers=headers,
            timeout=timeout,
            follow_redirects=True
        ) as client:
            # Initial request
            client.get(base_url)

            # Visit homepage articles
            homepage_links = get_articles(client, base_url)
            click_articles(client, homepage_links)

            # Random searches
            for _ in range(3):
                term = faker.catch_phrase()
                if 3 <= len(term) <= 30:
                    search_url = f"{base_url}/?query={term.replace(' ', '+')}"
                    try:
                        client.get(search_url)
                    except Exception:
                        pass
                    time.sleep(0.2)

        logger.info("Cache warming complete")
    except Exception as e:
        logger.error(f"job_keep_cache_warm failed: {e}")


# ---------------------------------------------------------------------------
# API Content Processing Job
# ---------------------------------------------------------------------------

def job_process_incoming_api():
    """
    Process articles submitted via API.
    Originally: cronjobs/process_incoming_api.sh
    Schedule: Every ~20 minutes (37, 58 past the hour)
    """
    logger.info("Starting job_process_incoming_api")

    db = get_db()
    incoming = db["news_incoming"]

    # Delete non-API articles (those with imageurl - from news_collect)
    incoming.delete_many({"imageurl": {"$exists": True}})

    # Process remaining (API-submitted) articles
    job_create_images()
    job_convert_images()
    job_process_incoming()
    job_vectorize()
    job_add_sentiment()
    job_add_sections()

    # Clean up API articles from incoming
    incoming.delete_many({})

    logger.info("job_process_incoming_api complete")
