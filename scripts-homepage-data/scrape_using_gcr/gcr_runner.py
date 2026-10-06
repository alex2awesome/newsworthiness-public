from subprocess import Popen, PIPE
from datetime import datetime
from pytimeparse.timeparse import timeparse
import os, sys
sys.path.insert(0, '../page_exclusions')
import nytimes, ajc, default_exclusion
import numpy as np
from tqdm.auto import tqdm
from itertools import groupby
import itertools
import random
import re
import multiprocessing
multiprocessing.set_start_method('spawn', True)
import glob
import requests
from concurrent.futures import ThreadPoolExecutor

here = os.path.dirname(__file__)
epoch_time = datetime(1970, 1, 1)
site_to_processor = {
    'nytimes.com': (nytimes, True),
    'ajc.com': (ajc, False),
}

SF_GCR_SERVICE_URLS = [
    'https://singlefile-webapp-ukvxfz3sya-uc.a.run.app',
    'https://singlefile-webapp-2-ukvxfz3sya-uw.a.run.app',
    'https://singlefile-webapp-3-ukvxfz3sya-ue.a.run.app',
]

PLAYWRIGHT_GCR_SERVICE_URLS = [
    'https://singlefile-webapp-playwright-4-ukvxfz3sya-uw.a.run.app',
    'https://singlefile-webapp-playwright-5-ukvxfz3sya-ue.a.run.app',
    'https://singlefile-webapp-playwright-6-ukvxfz3sya-uc.a.run.app',
]

def get_wayback_nums_from_list(files):
    file_nums = list(map(lambda x: re.search('\d{14}', x), files))
    file_nums = list(filter(lambda x: x is not None, file_nums))
    return list(set(map(lambda x: x[0], file_nums)))


def build_existing_filelist(args):
    existing_file_list = []
    for source in [args.output_dir] + (args.existing_files or []):
        if source.endswith('.zip'):
            from zipfile import ZipFile
            myzip = ZipFile(source)
            files = list(map(lambda x: x.filename, myzip.filelist))
        elif source.endswith('.txt'):
            files = open(source).read().strip().split('\n')
        else:
            files = glob.glob(os.path.join(source, 'web.archive.org', 'web', '*'))
        existing_file_list += get_wayback_nums_from_list(files)
    return existing_file_list


def check_if_we_have(x, file_ids):
    file_key = re.search('\d{14}', x)[0]
    return file_key in file_ids


def get_time_from_waybackpack_url(url_str:str):
    """
    Extracts the date string from a waybackurl and converts it to total_seconds from 1970/1/1
        :type url_str: str
    """
    date_str = url_str.split('/')[4]
    return datetime.strptime(date_str, '%Y%m%d%H%M%S')


def get_time_since_epoch(dt):
    return int((dt - epoch_time).total_seconds())


def get_time_from_wb_url_seconds(url_str: str):
    dt = get_time_from_waybackpack_url(url_str)
    return get_time_since_epoch(dt)


def scrape_for_one_chunk(url_chunk, processor, api_url):
    """
    Given a list of urls, scrape the first one possible using the GCR service. We only have the batch in case the first fails.

    Parameters
    ----------
    url_chunk : list of urls, of which we wish to scrape 1.
    """
    for url in url_chunk:
        # get result
        output = requests.post(
            api_url, headers={'Content-Type': 'application/x-www-form-urlencoded'}, data={'url': url}
        )
        if output.status_code == 200:
            # test to see if it meets criteria
            accept = processor[0].score_webpage(raw_html=output.text)

            # if true, move these files to the output directory
            if accept:
                return url, output.text

    return None, None

def get_wayback_urls(args):
    output, err = Popen([
        "waybackpack",
        args.site,
        "--from-date",
        args.from_date,
        "--to-date",
        args.to_date,
        "--list",
        '--user-agent',
        'waybackpack-spangher@usc.edu'
    ], stdin=PIPE, stdout=PIPE, stderr=PIPE).communicate()
    return output.decode().strip().split()


# run:
# python gcr_runner.py --site nytimes.com --from-date 20230101 --to-date 20230102 --output-dir /dev/shm --verbose --num-concurrent-workers 3 --approach playwright --existing-files /dev/shm/nytimes.com.zip
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--site', type=str, default='nytimes.com')
    parser.add_argument('--from-date', dest='from_date', type=str, default='20230101')
    parser.add_argument('--to-date', dest='to_date', type=str, default='20230102')
    parser.add_argument('--output-dir', dest='output_dir', type=str, default='/dev/shm')
    parser.add_argument('--verbose', action='store_true', )
    parser.add_argument('--num-concurrent-workers', dest='workers', default=1, type=int)
    parser.add_argument('--approach', default='single-file', type=str, help='values= ["single-file", "playwright"].')
    parser.add_argument('--existing-files', dest='existing_files', nargs='*')
    parser.add_argument(
        '--url-selection-style',
        dest='url_cycle',
        default='round-robin',
        help='values= ["random", "round-robin"].'
    )
    parser.add_argument(
        '--collapse',
        type=str,
        default='30m',
        help='Amount of time in between wayback page snapshots (e.g. 32m, 2h32m, 4:13, 1.2 minutes, 5hr34m56s).',
    )
    args = parser.parse_args()

    # bucket wayback_urls
    wayback_urls = get_wayback_urls(args)
    wayback_seconds = list(map(get_time_from_wb_url_seconds, wayback_urls))
    collapse_time = timeparse(args.collapse)
    buckets = list(range(wayback_seconds[0], wayback_seconds[-1], collapse_time))
    time_bins = list(map(lambda x: np.digitize(x, buckets, right=True), wayback_seconds))
    processor = site_to_processor.get(args.site, default_exclusion)

    # collapse
    existing_file_ids = set(build_existing_filelist(args))
    collapsed_groups = []
    for g, g_iter in groupby(zip(time_bins, wayback_urls), key=lambda x: x[0]):
        url_group = list(map(lambda x: x[1], g_iter))
        # filter out files we might already have
        file_exists_on_disk = map(lambda x: check_if_we_have(x, existing_file_ids), url_group)
        if any(file_exists_on_disk):
            continue
        collapsed_groups.append(url_group)

    # get api urls to run service with. 
    URLs = SF_GCR_SERVICE_URLS if args.approach == 'single-file' else PLAYWRIGHT_GCR_SERVICE_URLS
    n_groups = len(collapsed_groups)
    if args.url_cycle == 'random':
        api_urls = list(map(lambda x: random.choice(URLs), range(n_groups)))
    else:
        c = itertools.cycle(URLs)
        api_urls = list(map(lambda x: next(c), range(n_groups)))

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for url, raw_html in tqdm(
                executor.map(scrape_for_one_chunk, collapsed_groups, [processor] * n_groups, api_urls),
                total=n_groups
        ):
            if (url is not None) and (raw_html is not None):
                file_on_disk = os.path.join(here, args.output_dir, url.replace('https://', ''), 'index.html')
                dirname = os.path.dirname(file_on_disk)
                os.makedirs(dirname, exist_ok=True)
                with open(file_on_disk, 'w') as f:
                    f.write(raw_html)










######################################


def move_files():
    ## move files
    ##
    import os
    import glob
    import shutil

    path_1 = 'sfchron-ten-years/web.archive.org/web/*/*/*'
    path_2 = '/dev/shm/'
    source_dir = glob.glob(path_1)
    target_dir = glob.glob(path_2)
    for file in source_dir:
        file_size = os.path.getsize(file)
        total, used, free = shutil.disk_usage(path_2)
        if file_size < free:
            target_dirname = os.path.join(path_2, os.path.dirname(file))
            os.makedirs(target_dirname, exist_ok=True)
            shutil.move(file, target_dirname)
        else:
            print('no more space!!')
            break

