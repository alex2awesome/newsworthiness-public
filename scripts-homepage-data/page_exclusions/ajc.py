from bs4 import BeautifulSoup
import re

def specific_prefetch_filtering(cdx_results):
    pass


def score_webpage(page, raw_html, *args, **kwargs):
    """Determine whether we should include the webpage or not.

    Reasons for not including the web-page:
        * the layout is a mobile-only layout.
        * redirects or other blank pages
        * more TK
    """
    # handle redirect
    key_strings = [
        'Redirecting to... https://www.ajc.com/gdpr.html',
        'Our apologies, unfortunately our website is currently unavailable in most European countries due to GDPR rules.',
    ]

    soup = BeautifulSoup(raw_html, features='lxml')
    raw_text = soup.get_text()
    text = re.sub('\s+', ' ', raw_text)
    matches = any(map(lambda x: x in text, key_strings))
    return not matches
