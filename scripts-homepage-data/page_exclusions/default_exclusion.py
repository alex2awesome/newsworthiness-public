from bs4 import BeautifulSoup
import re
import os
import tempfile

def specific_prefetch_filtering(cdx_results):
    pass


def score_webpage(page=None, raw_html=None, file_on_disk=None, *args, **kwargs):
    """Determine whether we should include the webpage or not.

    Reasons for not including the web-page:
        * the layout is a mobile-only layout.
        * redirects or other blank pages
        * more TK
    """
    # handle redirect
    key_strings = [
        'You have sent too many requests in a given amount of time',
    ]
    if file_on_disk is None:
        with tempfile.TemporaryFile(mode='w') as f:
            f.write(raw_html)
            f_size = f.tell()
    else:
        f_size = os.path.getsize(file_on_disk)

    if f_size < 100:
        return False

    if len(raw_html) < 100:
        return False

    soup = BeautifulSoup(raw_html, features='lxml')
    raw_text = soup.get_text()
    text = re.sub('\s+', ' ', raw_text)
    matches = any(map(lambda x: x in text, key_strings))
    return not matches
