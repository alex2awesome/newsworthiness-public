import newspaper
from newspaper.article import ArticleException
from tqdm.auto import tqdm
from subprocess import Popen, PIPE, run, check_call
import re
import pandas as pd
import jsonlines
import time
from playwright._impl._api_types import TimeoutError
from playwright.sync_api import sync_playwright

USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36'

def hit_wayback_pack_for_list(url):
    cmd = f"waybackpack {url} --list --user-agent waybackpack-spangher@usc.edu"
    print(cmd)
    output, err = Popen(cmd.split(), stdin=PIPE, stdout=PIPE, stderr=PIPE).communicate()
    article_links = output.decode().split()
    return article_links


def get_article_native(url):
    one_article = newspaper.Article(url)
    one_article.download()
    one_article.parse()
    return one_article

def get_browser_and_page(p, not_headless=False):
    headless = not not_headless
    browser = p.chromium.launch(
        channel="chrome",
        headless=headless,
    )
    context = browser.new_context(
        screen={'width': 860, 'height': 2040},
        user_agent=USER_AGENT
    )
    page = context.new_page()
    page.route("**/*", lambda route: route.abort() if route.request.resource_type == "image" else route.continue_())
    page.route("https://web.archive.org*/*", lambda route: route.abort())
    RESOURCE_EXCLUSIONS = ['image', 'stylesheet', 'media', 'font', 'other']
    for r in RESOURCE_EXCLUSIONS:
        page.route(
            "**/*",
            lambda route: route.abort() if route.request.resource_type == r else route.continue_()
        )
    return browser, page


def get_article_playwright(url, page):
    print(f'hitting {url} in playwright...')
    page.goto(url, timeout=60_000, wait_until='domcontentloaded')
    html = page.content()
    article = newspaper.Article('')
    article.set_html(html)
    article.parse()
    return article


def format_output_dict(one_article, wayback_url, article_url, hp_key, wayback_links):
    return {
        'article_wayback_url': wayback_url,
        'article_url': article_url,
        'homepage_key': hp_key,
        'article_html': one_article.html,
        'article_text': one_article.text,
        'article_publish_date': str(one_article.publish_date),
        'article_authors': one_article.authors,
        'article_top_image': one_article.top_image,
        'article_video': one_article.movies,
        'all_article_wayback_urls': wayback_links
    }


if __name__ == "__main__":
    from argparse import ArgumentParser
    parser = ArgumentParser()

    parser.add_argument(
        '--input-article-file', dest='input_file',
        help="CSV with the following columns: ['href', 'key']. href is links on the homepage from the site's domain."
    )
    parser.add_argument(
        '--output-file', dest='output_file',
        help="Output jsonlines file to stream the articles to."
    )
    parser.add_argument(
        '--approach', dest='approach', default="newspaper", type=str,
        help='Options: ["newspaper", "playwright", "combined"]'
    )
    parser.add_argument('--not-headless', dest='not_headless', action='store_true')
    parser.add_argument('--wait-time', dest='wait_time', default=.5, type=float, help='Num seconds to wait.')
    args = parser.parse_args()

    input_article_links_df = pd.read_csv(args.input_file)
    output_json_writer = jsonlines.Writer(open(args.output_file, 'w'))

    # todo: figure out way to not create context-manager when not using the playwright appraoch
    with sync_playwright() as p:
        browser, page = get_browser_and_page(p, args.not_headless)

        for _, a in tqdm(input_article_links_df.iterrows(), total=len(input_article_links_df)):
            article_links = hit_wayback_pack_for_list(a['href'])

            if len(article_links) > 0:
                k = a['key']
                link_df = (pd.Series(article_links)
                           .to_frame('link')
                           .assign(link_key=lambda df: df['link'].apply(lambda x: re.search('web.archive.org/web/(\d+)', x)[1]))
                           .assign(time_diff=lambda df: (df['link_key'].astype(int) - int(k)).abs())
                           )

                l = link_df.loc[lambda df: df['time_diff'].idxmin()]['link']
                if args.approach == 'newspaper':
                    try:
                        one_article = get_article_native(l)
                    except ArticleException as e:
                        print(f'failed on {str(e)}')
                        continue

                elif args.approach == 'playwright':
                    one_article = get_article_playwright(l, page)

                elif args.approach == 'combined':
                    try:
                        one_article = get_article_native(l)
                    except ArticleException as e1:
                        try:
                            one_article = get_article_playwright(l, page)
                        except TimeoutError as e2:
                            print(f'failed on {str(e1)} and {str(e2)}...')

                else:
                    raise ValueError(f'approach={args.approach} not recognized...')

                output_dict = format_output_dict(
                    one_article=one_article,
                    wayback_url=l,
                    article_url=a['href'],
                    hp_key=a['key'],
                    wayback_links=article_links
                )

                output_json_writer.write(output_dict)

                time.sleep(args.wait_time)