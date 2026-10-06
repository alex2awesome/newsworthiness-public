import random
import requests
import itertools
import glob
import jsonlines, json
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from tqdm.auto import tqdm
from concurrent.futures import as_completed

import time
from requests_futures.sessions import FuturesSession

CONTAINER_URLS = [
    'https://requests-ocr-parser-v2-ukvxfz3sya-uw.a.run.app',
    'https://requests-ocr-parser-v2-2-ukvxfz3sya-ue.a.run.app',
    'https://requests-ocr-parser-v2-3-ukvxfz3sya-uc.a.run.app',
    'https://requests-ocr-parser-v2-4-ukvxfz3sya-wl.a.run.app',
    'https://requests-ocr-parser-v2-5-ukvxfz3sya-wm.a.run.app',
    'https://requests-ocr-parser-v2-6-ukvxfz3sya-wn.a.run.app',
    'https://requests-ocr-parser-v2-7-ukvxfz3sya-uk.a.run.app',
    'https://requests-ocr-parser-v2-8-ukvxfz3sya-vp.a.run.app',
    'https://requests-ocr-parser-v2-9-ukvxfz3sya-ew.a.run.app',
    'https://requests-ocr-parser-v2-10-ukvxfz3sya-nw.a.run.app',
    'https://requests-ocr-parser-v2-11-ukvxfz3sya-uc.a.run.app',
    'https://requests-ocr-parser-v3-ukvxfz3sya-uc.a.run.app',
    'https://requests-ocr-parser-v3-1-ukvxfz3sya-oc.a.run.app',
]


def get_one_pdf(row, api_url):
    _, file_to_get = row
    time.sleep(10)

    def _helper(file_to_get):
        return requests.post(
            api_url,
            headers={'Content-Type': 'application/json'},
            data=json.dumps(file_to_get.to_dict())
        )

    num_tries = 1
    for _ in range(num_tries):
        try:
            resp = _helper(file_to_get)
            return handle_response(resp, api_url)

        except Exception as e:
            print(e)
            print(file_to_get.to_dict())
            print(api_url)

def handle_response(resp, api_url):
    if resp.status_code == 200:
        if resp.text == '':
            print('File is not PDF or HTML.')
            print(file_to_get.to_dict())
            return

        return resp.json()
    else:
        print(resp.status_code)
        print(resp.text)
        print(file_to_get.to_dict())
        print(api_url)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--input-dir-pattern', type=str, default='output-*/*')
    parser.add_argument('--output-file', type=str, default='/dev/shm/retrieved-city-council-documents.jsonl')
    parser.add_argument('--verbose', action='store_true', )
    parser.add_argument('--num-concurrent-workers', dest='workers', default=len(CONTAINER_URLS), type=int)
    parser.add_argument('--existing-file', default=None, type=str)
    parser.add_argument(
        '--url-selection-style',
        dest='url_cycle',
        default='round-robin',
        help='values= ["random", "round-robin"].'
    )
    args = parser.parse_args()
    print('args:')
    print(vars(args))
    print()

    input_files = glob.glob(args.input_dir_pattern)
    all_dfs = []
    for csv_file in input_files:
        one_df = pd.read_csv(csv_file, index_col=0)
        all_dfs.append(one_df)
    files_to_get = pd.concat(all_dfs)
    files_to_get = files_to_get.loc[lambda df: df['doc_format'] == 'pdf']

    if args.existing_file is not None:
        existing_urls = []
        for line in jsonlines.open(args.existing_file):
            existing_urls.append(line['url'])
        files_to_get = files_to_get.loc[lambda df: ~df['url'].isin(existing_urls)]

    n_files = len(files_to_get)
    files_to_get = files_to_get.sample(len(files_to_get))
    # get round-robin style cycling
    if args.url_cycle == 'random':
        api_urls = list(map(lambda x: random.choice(CONTAINER_URLS), range(n_files)))
    else:
        c = itertools.cycle(CONTAINER_URLS)
        api_urls = list(map(lambda x: next(c), range(n_files)))

    # launch
    rows = list(files_to_get.iterrows())
    with open(args.output_file, 'a') as f:
        w = jsonlines.Writer(f)

        with FuturesSession(max_workers=args.workers) as session:
            futures = []
            for row, api_url in zip(rows, api_urls):
                _, file_to_get = row
                f = session.post(
                    api_url,
                    headers={'Content-Type': 'application/json'},
                    data=json.dumps(file_to_get.to_dict())
                )
                futures.append(f)

            for output in tqdm(as_completed(futures), total=n_files):
                if output is not None:
                    resp = output.result()
                    resp_json = handle_response(resp, resp.request.url)
                    if resp_json is not None:
                        w.write(resp_json)


        # with ProcessPoolExecutor(max_workers=args.workers) as executor:
        #     for output in tqdm(executor.map(get_one_pdf, rows, api_urls), total=n_files):
        #         if output is not None:
        #             w.write(output)
