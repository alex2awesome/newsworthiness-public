import functions_framework
import requests
import newspaper
import json
import random
from urllib.parse import urlencode, urlparse, urlunparse, parse_qs, urljoin

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.77 Safari/537.36',
    'Mozilla/5.0 (X11; Ubuntu; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2919.83 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_8_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/54.0.2866.71 Safari/537.36',
    'Mozilla/5.0 (X11; Ubuntu; Linux i686 on x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/53.0.2820.59 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/52.0.2762.73 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_8_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/49.0.2656.18 Safari/537.36',
]
CDX_TEMPLATE = 'https://web.archive.org/cdx/search/cdx?url={url}&output=json&fl=timestamp,original,statuscode,digest'
ARCHIVE_TEMPLATE = "https://web.archive.org/web/{timestamp}{flag}/{url}"


def clean_url(to_get_url):
    return urljoin(to_get_url, urlparse(to_get_url).path)


@functions_framework.http
def scrape_wayback(request):
   data = request.json
   orig_article_url = clean_url(data['article_url'])
   homepage_key = int(data['homepage_key'])

   cdx_url = CDX_TEMPLATE.format(url=orig_article_url)
   cdx_response = requests.get(cdx_url).json()

   if len(cdx_response) < 2:
      return "No items in Wayback Machine"

   cols = cdx_response[0]
   timestamp_col = cols.index('timestamp')
   status_col = cols.index('statuscode')

   rows = cdx_response[1:]
   rows = list(filter(lambda x: x[status_col] != '-', rows))
   timestamps = list(map(lambda r: r[timestamp_col], rows))
   timestamps = sorted(timestamps, key=lambda t: abs(int(t) - homepage_key) )
   article_timestamp = timestamps[0]

   # fetch URL
   url_to_fetch = ARCHIVE_TEMPLATE.format(timestamp=article_timestamp, flag='', url=orig_article_url)
   html = requests.get(
       url_to_fetch, headers={'User-Agent': random.choice(USER_AGENTS)}
   ).text
   one_article = newspaper.Article('')
   one_article.set_html(html)
   one_article.parse()

   output_dict = {
            'article_url': orig_article_url,
            'homepage_key': homepage_key,
            'article_html': one_article.html,
            'article_text': one_article.text,
            'article_publish_date': str(one_article.publish_date),
            'article_authors': one_article.authors,
            'article_top_image': one_article.top_image,
            'article_video': one_article.movies,
            'article_wayback_timestamp': article_timestamp,
            'all_article_wayback_timestamps': timestamps,
        }

   return json.dumps(output_dict)






