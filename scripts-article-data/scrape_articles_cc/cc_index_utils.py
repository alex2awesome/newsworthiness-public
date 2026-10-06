import gzip
import requests
import pandas as pd
from tqdm.auto import tqdm
from bs4 import BeautifulSoup


def get_common_crawl_indices_table():
    # Let's fetch the Common Crawl FAQ using the CC index
    cc_url = 'https://index.commoncrawl.org/'
    common_crawl_indices_page = requests.get(cc_url).text

    soup = BeautifulSoup(common_crawl_indices_page, features="lxml")
    table = soup.find('table')
    if table is None:
        return False

    all_rows = []
    header = list(map(lambda x: x.get_text(), table.find_all('th')))
    rows = table.find_all('tr')[1:]

    for tr in rows:
        td = tr.find_all('td')
        to_append = {k: d for k, d in zip(header, td)}
        to_append_with_links = {}
        for c_head, c in to_append.items():
            if c.find('a'):
                to_append_with_links[f'{c_head} Link'] = c.find('a').attrs.get('href')
            to_append_with_links[c_head] = c.get_text()

        all_rows.append(to_append_with_links)

    common_crawl_table = pd.DataFrame(all_rows)
    return common_crawl_table


def get_common_crawl_indices_option():

    from playwright.sync_api import sync_playwright
    import time
    playwright = sync_playwright().start()
    cc_url = 'https://index.commoncrawl.org/'
    browser = playwright.chromium.launch()
    page = browser.new_page()
    page.goto(cc_url)
    time.sleep(5)
    common_crawl_indices_page = page.content()

    soup = BeautifulSoup(common_crawl_indices_page, features="lxml")
    select_block = soup.find('select', attrs={'id': 'ccIndices'})
    if select_block is None:
        return False

    all_rows = []
    options = select_block.find_all('option')
    for option in options:
        to_append = option.attrs['value']
        if not to_append.endswith('-index'):
            to_append = f'{to_append}-index'
        all_rows.append(to_append)

    return all_rows


def get_all_lines_from_local_server(domain, crawls=None):
    if crawls is None:
        crawls = get_common_crawl_indices_table()
        if crawls != False:
            crawls = crawls['API endpoint']
        else:
            crawls = get_common_crawl_indices_option()

    url_base = 'http://localhost:8080'
    all_lines = []


    for index in tqdm(crawls):
        i = 0
        index = index.replace('/', '')
        while True:
            resp = requests.get(f'{url_base}/{index}?url={domain}/*&page={i}')
            #
            if resp.status_code == 200:
                lines = resp.text.split('\n')
                all_lines += lines
                i += 1
            else:
                break

    return all_lines


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--domain', type=str)
    parser.add_argument('--output-file', dest='output_file', type=str)
    args = parser.parse_args()

    all_lines = get_all_lines_from_local_server(args.domain)

    if not args.output_file.endswith('.gz'):
        args.output_file = args.output_file + '.gz'

    with gzip.open(args.output_file, 'wb') as f:
        for line in all_lines:
            f.write(line.encode())
            f.write(b'\n')






