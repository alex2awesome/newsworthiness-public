from pathlib import Path

import scrapy
import newspaper
import pandas as pd

CDX_TEMPLATE = 'https://web.archive.org/cdx/search/cdx?url={url}&output=json&fl=timestamp,original,statuscode,digest'
ARCHIVE_TEMPLATE = "https://web.archive.org/web/{timestamp}{flag}/{url}"


class BasicArticleParserSpider(scrapy.Spider):
    name = "basic_article"
    def start_requests(self):
        input_filename = getattr(self, 'input_filename', None)
        n_articles = getattr(self, 'num_articles', None)
        if input_filename:
            article_df = pd.read_csv(input_filename)
            article_df = article_df[:n_articles]
            for _, row in article_df.iterrows():
                url, homepage_key = row['href'], row['key']
                yield scrapy.Request(
                    CDX_TEMPLATE.format(url=url),
                    callback=self.parse_cdx,
                    cb_kwargs={'homepage_key': homepage_key, 'orig_article_url': url}
                )

    def parse_cdx(self, response, homepage_key, orig_article_url):
        cdx_response = response.json()
        if len(cdx_response) < 2:
            return

        cdx_df = pd.DataFrame(cdx_response[1:], columns=cdx_response[0])
        article_timestamp = (
            cdx_df.assign(time_diff=lambda df: (df['timestamp'].astype(int) - int(homepage_key)).abs())
                  .loc[lambda df: df['time_diff'].idxmin()]['timestamp']
        )
        url_to_fetch = ARCHIVE_TEMPLATE.format(timestamp=article_timestamp, flag='', url=orig_article_url)
        yield scrapy.Request(url_to_fetch, cb_kwargs={
            'article_wb_ts': int(article_timestamp),
            'hp_key': homepage_key,
            'orig_article_url': orig_article_url,
            'all_article_wb_ts': cdx_df['timestamp'].astype(int).tolist()
        }, callback=self.parse_wayback_article)

    def parse_wayback_article(self, response, article_wb_ts, hp_key, orig_article_url, all_article_wb_ts):
        html = response.body.decode()
        one_article = newspaper.Article('')
        one_article.set_html(html)
        one_article.parse()
        return {
            'article_url': orig_article_url,
            'homepage_key': hp_key,
            'article_html': one_article.html,
            'article_text': one_article.text,
            'article_publish_date': str(one_article.publish_date),
            'article_authors': one_article.authors,
            'article_top_image': one_article.top_image,
            'article_video': one_article.movies,
            'article_wayback_timestamp': article_wb_ts,
            'all_article_wayback_timestamps': all_article_wb_ts,

        }




