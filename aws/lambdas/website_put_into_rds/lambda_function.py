import sys
import os
import logging
import psycopg2
import json
from pprint import pprint

logger = logging.getLogger()
try:
    conn = psycopg2.connect(
        dbname=os.environ.get('DB_NAME'),
        user=os.environ.get('DB_USER'),
        password=os.environ.get('DB_PASSWORD'),
        host=os.environ.get('DB_HOST')
    )
except psycopg2.Error as e:
    logger.error("ERROR: Unable to connect to database")
    logger.error(e)
    sys.exit(1)

logger.info("SUCCESS: Connection to RDS database established")


def lambda_handler(event: dict, context):  # noqa
    # Pobieranie linku z eventu
    link = event.get('url', 'default_url')
    url_type = event.get('type', 'link')

    pprint(event)

    if link == 'default_url':
        logger.error("ERROR: Missing url in event")
        return {
            'statusCode': 500,
            'body': json.dumps('Missing url in body')
        }

    if url_type not in ['link', 'webpage']:
        logger.error(f"ERROR: Invalid url type: {url_type}. Must be 'link', 'webpage'")
        return {
            'statusCode': 500,
            'body': json.dumps("Invalid url type: {url_type}. Must be 'link' or 'webpage'")
        }

    try:
        with conn:
            with conn.cursor() as cur:
                # Wykonanie operacji INSERT INTO
                cur.execute(
                    "INSERT INTO websites(document_type, url) VALUES (%s, %s)",
                    (url_type, link)
                )
                logger.info(f"Successfully inserted {url_type} {link} into document table.")
                return {
                    'statusCode': 200,
                    'body': 'Successfully inserted link into document table.'
                }

    except Exception as exception:
        logger.exception(f"Failed to insert {url_type} {link} into documents table due to {exception}")
        return {
            'statusCode': 500,
            'body': json.dumps(f'Failed to insert {url_type} into documents table due to {exception}')
        }
