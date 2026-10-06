# Define here the models for your spider middleware
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/spider-middleware.html

from scrapy import signals

# useful for handling different item types with a single interface
from itemadapter import is_item, ItemAdapter
from rotating_proxies.middlewares import RotatingProxyMiddleware
import codecs
from scrapy.exceptions import CloseSpider, NotConfigured
import requests


class RotatingProxyGeoNode(RotatingProxyMiddleware):
    @classmethod
    def from_crawler(cls, crawler):
        # This method is used by Scrapy to create your spiders.
        s = crawler.settings
        proxy_url = s.get('ROTATING_PROXY_LIST_URL', None)
        proxy_list = None
        if proxy_url is not None:
            try:
                r = requests.get(proxy_url)
                urls = r.json()
                proxy_list = list(map(lambda x: x['ip'], urls['data']))
            except:
                print('failed getting proxies through URL...')
        else:
            proxy_path = s.get('ROTATING_PROXY_LIST_PATH', None)
            if proxy_path is not None:
                with codecs.open(proxy_path, 'r', encoding='utf8') as f:
                    proxy_list = [line.strip() for line in f if line.strip()]
            else:
                proxy_list = s.getlist('ROTATING_PROXY_LIST')
        if not proxy_list:
            raise NotConfigured()
        mw = cls(
            proxy_list=proxy_list,
            logstats_interval=s.getfloat('ROTATING_PROXY_LOGSTATS_INTERVAL', 30),
            stop_if_no_proxies=s.getbool('ROTATING_PROXY_CLOSE_SPIDER', False),
            max_proxies_to_try=s.getint('ROTATING_PROXY_PAGE_RETRY_TIMES', 5),
            backoff_base=s.getfloat('ROTATING_PROXY_BACKOFF_BASE', 300),
            backoff_cap=s.getfloat('ROTATING_PROXY_BACKOFF_CAP', 3600),
            crawler=crawler,
        )
        crawler.signals.connect(mw.engine_started, signal=signals.engine_started)
        crawler.signals.connect(mw.engine_stopped, signal=signals.engine_stopped)
        return mw