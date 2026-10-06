import os
import sys
sys.path.insert(0, '../../scripts-homepage-data/')
import get_bounding_boxes_from_html as bb
from tqdm.auto import tqdm
import glob
import pandas as pd
import jsonlines
from tqdm.auto import tqdm
from urllib.parse import urlencode, urlparse, urlunparse, parse_qs, urljoin
import spacy
from unidecode import unidecode
import re
import gzip
import asyncio
import urllib


def clean_url(url):
    if isinstance(url, float):
        return
    return urljoin(url, urlparse(url).path)

spacy_model = spacy.load('en_core_web_lg')
spacy_model.add_pipe('sentencizer')

regex_replacers = [
    (r'"\s*([^"]*?)\s*"', r' "\1" '),
    ('\s+', ' '),
    #
    ('\.""', '." "'),
    ('\?""', '?" "'),
    ('\!""', '!" "'),
    #
    ('\."(?=[\w])', '." '),
    ('\?"(?=[\w])', '?" '),
    ('\!"(?=[\w])', '!" '),
    #
    ('\.(?=[\w])', '. '),
    ('\?(?=[\w])', '? '),
    ('\!(?=[\w])', '! '),
    ('\:(?=[\w])', ': '),
]

def process_text(text):
    text = unidecode(text)
    for p, r in regex_replacers:
        text = re.sub(p, r, text)
    return text.strip()


def unquote_and_clean_url(x):
    if pd.isnull(x):
        return
    url = urllib.parse.unquote(x, encoding='utf-8')
    url = unidecode(url)
    url = url.replace(' ', '')
    if ')' in url:
        path = url.split(')')[-1]
    else:
        path = urllib.parse.urlparse(url).path
    return path.lower()



if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--parse-html', action='store_true',
                        help='Whether to parse homepage-html. If not, must use cache.')
    parser.add_argument('--input-dir-pattern', type=str, default=None)
    parser.add_argument(
        '--filter-bbs-to-articles',
        action='store_true',
        dest='filter_articles',
        help="Whether to calculate the bounding boxes of the biggest possible div excluding articles. "
             "Helps get better boxes around articles, but can fail for side-bars/etc. Not recommended."
    )
    parser.add_argument('--bb-output-cache', type=str)
    parser.add_argument('--clip-width', action='store_true',
                        help='whether to clip the width of the webpage to a width-line that captures 5% of all boxes. '
                             'Helps prevent one weird box from giving us a huge max-width.')
    parser.add_argument('--fetched-article-files', nargs='+')
    parser.add_argument('--training-data-output-file', type=str)
    args = parser.parse_args()

    #
    #
    # 1.
    # Read in and process homepage files.
    ###########################################
    if args.parse_html:
        print('parsing HTML files....')
        homepage_files = glob.glob(args.input_dir_pattern)
        homepage_files = sorted(homepage_files, key=lambda x: re.search(r'\d{14}', x)[0])
        bounding_boxes, _ = asyncio.run(bb.get_bounding_boxes_for_files(
            homepage_files, filter_to_articles=args.filter_articles
        ))
        os.makedirs(args.bb_output_cache, exist_ok=True)
        for bb_df in bounding_boxes:
            if bb_df is not None and len(bb_df) > 0:
                homepage_key = bb_df.iloc[0]['key']
                bb_df.to_csv(os.path.join(args.bb_output_cache, f'homepage-{homepage_key}.csv'))
    else:
        bounding_boxes = []
        for csv_fn in tqdm(glob.glob(os.path.join(args.bb_output_cache, '*'))):
            one_df = pd.read_csv(csv_fn)
            bounding_boxes.append(one_df)

    print('clipping bounding boxes...')
    clipped_bounding_boxes = []
    for bb_df in tqdm(bounding_boxes):
        if bb_df is not None and len(bb_df) > 0:
            if args.clip_width:
                bb_df['page_width'] = bb.get_clipped_height_or_width(bb_df)
            bb_df['page_height'] = bb_df.pipe(lambda df: df['y'] + df['height']).max()
            clipped_bounding_boxes.append(bb_df)

    all_bb_dfs = pd.concat(clipped_bounding_boxes)
    all_bb_dfs['key'] = all_bb_dfs['key'].astype(int)

    #
    #
    # 2. READ IN and process
    # article files
    #####################################
    print('reading in files...')
    article_data = []
    for f in args.fetched_article_files:
        if f.endswith('.gz'):
            f = gzip.open(f, 'rb')
        else:
            f = open(f, 'r')
        with jsonlines.Reader(f) as j:
            article_data += list(j)
    article_data_df = pd.DataFrame(article_data)

    #
    #
    # 3. MERGE article files with processed homepage dfs
    #########################

    all_bb_dfs['clean_href'] = all_bb_dfs['href'].apply(unquote_and_clean_url)
    article_data_df['clean_article_url'] = article_data_df['article_url'].apply(unquote_and_clean_url)

    article_data_df_w_hp_info = (
        article_data_df
             .merge(all_bb_dfs, left_on=['clean_article_url'],  right_on=['clean_href'])
             .drop_duplicates(['clean_article_url', 'key'])
             .assign(perc_height=lambda df: df['y'] / df['page_height'])
             .assign(perc_width=lambda df: (df['x'] / df['page_width']).apply(lambda x: min(x, 1)))
    )

    training_data = (
        article_data_df_w_hp_info
        .assign(area=lambda df: df['width'] * df['height'])
        .drop('homepage_key', axis=1)
        .rename(columns={'key': 'homepage_key'})
        [['clean_article_url', 'homepage_key', 'article_text', 'perc_height', 'perc_width', 'area', 'width', 'height', 'x', 'y']]
    )

    print(f'training data size: {str(training_data.shape)}')

    tqdm.pandas()
    deduped_processed_text = training_data['article_text'].drop_duplicates().progress_apply(process_text)
    all_sentences = []
    for doc in tqdm(spacy_model.pipe(
            deduped_processed_text.tolist(),
            disable=["ner", "tok2vec", "tagger", "parser", "attribute_ruler", "lemmatizer"]
    ), total=len(deduped_processed_text)):
        sents = list(doc.sents)
        sents = list(map(str, sents))
        all_sentences.append(sents)
    text_to_sents = training_data['article_text'].drop_duplicates().to_frame().assign(sentences=all_sentences)

    training_data = (training_data
                     .merge(text_to_sents, left_on='article_text', right_on='article_text', how='left')
                     )

    training_data.to_json(args.training_data_output_file, orient='records', lines=True)


# python process-homepage-data.py --parse-html --input-dir-pattern "/Users/spangher/Projects/usc-research/newsworthiness/data/sfchron-ten-years/web.archive.org/web/*/sfchronicle.com/index.html" --bb-output-cache ../../data/sfchron-bb-csvs/ --fetched-article-files ../../data/sfchron-fetched-articles.jsonl ../../data/sfchron-cc-fetched-articles.jsonl.gz ../../data/sfchron-cc-fetched-articles-2.jsonl.gz --training-data-output-file ../data/sfchron-homepage-placement-no-article-filter.jsonl