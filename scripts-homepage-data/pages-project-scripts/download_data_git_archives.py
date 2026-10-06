import requests
import json
import pandas as pd
from tqdm.auto import tqdm
import os
import shutil
from multiprocessing import cpu_count
from multiprocessing.pool import ThreadPool
import concurrent.futures
from google.cloud import storage


admin_token = os.environ["GITHUB_TOKEN"]
headers = {
            "Accept" : "application/vnd.github+json",
            "Authorization": f"Bearer {admin_token}",
            "User-Agent": "alex2awesome"
        }
cache_endpoint = "https://api.github.com/repos/palewire/news-homepages-runner/actions/artifacts?per_page=100&page=%s"
download_api = 'https://api.github.com/repos/palewire/news-homepages-runner/actions/artifacts/%s/zip'
def download_file(artifact_id=None, filetype=None, save_dir=None, headers=headers):
    url = download_api % artifact_id

    # local url
    if filetype is None:
        local_filename = url.split('/')[-1]
    else:
        local_filename = '%s-%s.zip' % (filetype, artifact_id)

    try:
        with requests.get(url, stream=True, headers=headers) as r:
            r.raise_for_status()
            with open(local_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

        if save_dir is not None:
            shutil.copy(local_filename, os.path.join(save_dir, local_filename))
            os.remove(local_filename)
    except Exception as e:
        print('error: %s' % e)


def download_parallel(artifact_ids, filetype, save_dir=None):
    # let's give it some more threads:
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        list(tqdm(
            executor.map(lambda x: download_file(x, save_dir=save_dir, filetype=filetype), artifact_ids),
            total=len(artifact_ids)
        ))

prefixes = [
    'newspaper-pages/full-page-htmls',
]
def list_files(prefix):
    client = storage.Client()
    files = client.list_blobs('usc-data', prefix=prefix)

    files = list(files)
    fnames = list(map(lambda x: x.name.split('/')[-1], files))
    f_ids = list(map(lambda x: x.split('-')[-1].replace('.zip', ''), fnames))
    return f_ids


def upload_to_bucket(blob_name, path_to_file, bucket_name='usc-data'):
    """ Upload data to a bucket"""

    # Explicitly use service account credentials by specifying the private key
    # file.
    #     storage_client = storage.Client.from_service_account_json('creds.json')
    storage_client = storage.Client()

    bucket = storage_client.get_bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(path_to_file)

    # returns a public url
    return blob.public_url


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--run_cache_lookup', action='store_true')
    parser.add_argument('--cache_file')
    parser.add_argument('--save_dir', default='.')
    parser.add_argument('--run_html', action='store_true')
    parser.add_argument('--run_fullscreen', action='store_true')
    parser.add_argument('--check_already_retrieved', action='store_true')

    args = parser.parse_args()

    if args.run_cache_lookup:
        page_num = 1
        all_artifacts = []

        artifact_list = requests.get(cache_endpoint % page_num, headers=headers)
        artifact_list = json.loads(artifact_list.text)

        total_count = artifact_list['total_count']
        all_artifacts.extend(artifact_list['artifacts'])

        num_pages = int(total_count / 100) + 1
        for i in tqdm(range(2, num_pages + 1)):
            artifact_list = requests.get(cache_endpoint % i, headers=headers)
            artifact_list = json.loads(artifact_list.text)
            all_artifacts.extend(artifact_list['artifacts'])

        all_artifacts_df = pd.DataFrame(all_artifacts)
        all_artifacts_df.to_csv(args.cache_file)

    if args.run_html:
        all_artifacts_df = pd.read_csv(args.cache_file)
        html_pages = all_artifacts_df.loc[lambda df: df['name'] == 'html']
        html_ids_to_retrieve = html_pages['id'].astype(int)
        if args.check_already_retrieved:
            html_retrieved = list_files('newspaper-pages/full-page-htmls')
            html_retrieved = pd.Series(html_retrieved).astype(int)
            html_ids_to_retrieve = html_ids_to_retrieve.loc[lambda s: ~s.isin(pd.Series(html_retrieved).astype(int))]

        download_parallel(html_ids_to_retrieve.tolist(), filetype='html', save_dir=args.save_dir)

    if args.run_fullscreen:
        all_artifacts_df = pd.read_csv(args.cache_file)
        full_page_screenshots = all_artifacts_df.loc[lambda df: df['name'] == 'full-page-screenshots']
        download_parallel(full_page_screenshots['id'].tolist(), filetype= 'fullscreen', save_dir = args.save_dir)


