import functions_framework
import requests
import newspaper
import json
import random
from urllib.parse import urlparse, urljoin
from io import BytesIO
import gzip
import time


USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.77 Safari/537.36',
    'Mozilla/5.0 (X11; Ubuntu; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2919.83 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_8_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/54.0.2866.71 Safari/537.36',
    'Mozilla/5.0 (X11; Ubuntu; Linux i686 on x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/53.0.2820.59 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/52.0.2762.73 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_8_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/49.0.2656.18 Safari/537.36',
]

CC_PREFIX = 'https://data.commoncrawl.org/'


def clean_url(to_get_url):
    return urljoin(to_get_url, urlparse(to_get_url).path)


def req_cc(filename, offset, offset_end):
    return requests.get(
        CC_PREFIX + filename,
        headers={
            'Range': 'bytes={}-{}'.format(offset, offset_end),
            'User-Agent': random.choice(USER_AGENTS)
        }
    )

@functions_framework.http
def query_common_crawl(request):
    page_data = request.json

    offset, length = int(page_data['offset']), int(page_data['length'])
    offset_end = offset + length - 1
    resp = req_cc(page_data['filename'], offset, offset_end)

    # retry if 503...
    num_attempts = 0
    while (resp.status_code == 503) and (num_attempts < 5):
        print('503 status code, requerying...')
        time.sleep(1)
        resp = req_cc(page_data['filename'], offset, offset_end)
        num_attempts += 1

    if resp.status_code > 399:
        return {
            'article_url': page_data['article_url'],
            'status_code': resp.status_code,
            'text': resp.text
        }

    try:
        raw_data = BytesIO(resp.content)
        f = gzip.GzipFile(fileobj=raw_data)
        data = f.read()
        warc, header, html = data.decode().strip().split('\r\n\r\n', 2)
    except:
        return {
            'article_url': page_data['article_url'],
            'status_code': 'failed reading file from common crawl blob...',
        }

    try:
        one_article = newspaper.Article('')
        one_article.set_html(html)
        one_article.parse()
        return json.dumps({
            'article_url': page_data['article_url'],
            'article_html': one_article.html,
            'article_text': one_article.text,
            'article_publish_date': str(one_article.publish_date),
            'article_authors': one_article.authors,
            'article_top_image': one_article.top_image,
            'article_video': one_article.movies,
            'article_scrape_timestamp': page_data['scrape_timestamp'],
            'source': 'common_crawl',
        })
    except:
        return json.dumps({
            'article_url': page_data['article_url'],
            'article_html': html,
            'article_scrape_timestamp': page_data['scrape_timestamp'],
            'source': 'common_crawl',
        })



# to deploy:
'''
for region in europe-west1 europe-west2 europe-west3 southamerica-east1 us-west1 us-west2 us-west3 us-west4 us-east4 us-east5 northamerica-northeast1 northamerica-northeast2
do
    gcloud functions deploy common-crawl-scrape-v2 \
        --gen2 \
        --runtime=python311 \
        --source . \
        --entry-point=query_common_crawl \
        --trigger-http \
        --region $region \
        --allow-unauthenticated \
        --memory=1Gi
done 
'''