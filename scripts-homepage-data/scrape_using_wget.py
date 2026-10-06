import re
import shutil

from pytimeparse.timeparse import timeparse
import os
from datetime import datetime
from page_exclusions import nytimes, ajc, default_exclusion
from merge_two_dirs import main_merge as merge_dirs
from playwright.sync_api import sync_playwright
import subprocess
from subprocess import Popen, PIPE, run, check_call
import glob
import requests
import re
import typing
from pathlib import Path
import time

here = os.path.dirname(__file__)
epoch_time = datetime(1970, 1, 1)
approach_to_needs_page = {
    'wget': False,
    'single-file-cli': False,
    'playwright': True,
    'combined': True,
}
site_to_method = {
    'nytimes.com': 'wget',
    'inquirer.com': 'playwright',
    'latimes.com': 'single-file-cli',
    'sfchronicle.com': 'single-file-cli',
}
site_to_processor = {
    'nytimes.com': (nytimes, True),
    'ajc.com': (ajc, False),
}

default_reject_list = '*.ttf,*.woff2,*.woff,*.js,*.ico,*.txt,*.gif,*.jpg,*.jpeg,*.png,*.mp3,*.pdf,*.tgz,*.flv,*.avi,*.mpeg,*.iso'
site_to_reject_list = {
    # 'inquirer.com': '*.ttf,*.woff2,*.woff,*.ico,*.txt,*.gif,*.jpg,*.jpeg,*.png,*.mp3,*.pdf,*.tgz,*.flv,*.avi,*.mpeg,*.iso',
    'sfchronicle.com': '*.css,*.js,*.ttf,*.woff2,*.woff,*.ico,*.txt,*.gif,*.jpg,*.jpeg,*.png,*.mp3,*.pdf,*.tgz,*.flv,*.avi,*.mpeg,*.iso',
    'latimes.com': '*.css,*.js,*.ttf,*.woff2,*.woff,*.ico,*.txt,*.gif,*.jpg,*.jpeg,*.png,*.mp3,*.pdf,*.tgz,*.flv,*.avi,*.mpeg,*.iso',
}
USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36'
def get_time_from_waybackpack_url(url_str:str):
    """
    Extracts the date string from a waybackurl and converts it to total_seconds from 1970/1/1
        :type url_str: str
    """
    date_str = url_str.split('/')[4]
    dt = datetime.strptime(date_str, '%Y%m%d%H%M%S')
    return (dt - epoch_time).total_seconds()


def rename_files_for_playwright(file_on_disk):
    fname = 'index.html'
    if not os.path.isdir(file_on_disk):
        temp_fname = os.path.join(os.path.dirname(file_on_disk), fname)
        perm_fname = os.path.join(file_on_disk, fname)
        os.rename(file_on_disk, temp_fname)
        os.mkdir(file_on_disk)
        shutil.move(temp_fname, perm_fname)
        file_on_disk = perm_fname
    else:
        file_on_disk = os.path.join(file_on_disk, fname)
        if not os.path.exists(file_on_disk):
            raise FileNotFoundError(f"{file_on_disk} doesn't exist!")
    return file_on_disk


def use_wget(site, url, verbose=False):
    temp_outdir = os.path.join(here, f'tmp-{site}')
    reject_list = site_to_reject_list.get(site, default_reject_list)
    cmd = f'''wget \
                -U  '{USER_AGENT}'\
                --no-clobber \
                --page-requisites \
                --convert-links \
                --timestamping \
                --reject '{reject_list}' \
                --ignore-tags=img \
                --domains web.archive.org \
                --no-parent {url} \
                -P {temp_outdir}'''
    try:
        print(f'running wget on {url}...')
        print(re.sub('\s+', ' ', cmd))
        if verbose:
            wget_output = check_call(cmd, shell=True)
        else:
            wget_output = check_call(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        return temp_outdir
    except subprocess.CalledProcessError as e:
        pass

def use_combined_approach(site, url, page, output_file, scroll_to_bottom=False):
    use_wget(site, url)  # outputs to os.path.join(here, f'tmp-{site}')
    temp_outfile = rename_files_for_playwright(output_file)
    reformatted_temp_outfile = 'file://' + temp_outfile
    use_playwright_singlefile(reformatted_temp_outfile, page, temp_outfile, scroll_to_bottom)


def use_playwright_singlefile(url, page, output_file, scroll_to_bottom=True):
    def perform_scroll_to_bottom(page):
        scroll_height = page.evaluate("document.body.scrollHeight")
        current_pos = 0
        current_iter = 0
        max_iterations = 200
        amount_to_scroll = 200
        while (current_pos < scroll_height) and (current_iter < max_iterations):
            current_pos += amount_to_scroll
            page.evaluate(f"scroll(0, {current_pos})")
            time.sleep(1)
            scroll_height = page.evaluate("document.body.scrollHeight")
            current_iter += 1
        page.evaluate("scroll(0, 0)")
        time.sleep(1)

    def _read_script_from_file(filename: typing.Union[str, Path]) -> str:
        """Read and return Javascript code from a file. Convenience function."""
        ext_dir = Path(here) / Path("js")
        with open(ext_dir / filename) as f:
            return f.read()

    single_file_pre_load_extensions = [
        "single-file-bootstrap.js",
        "single-file-hooks-frames.js",
        "single-file-frames.js",
    ]
    for f in single_file_pre_load_extensions:
        page.evaluate(_read_script_from_file(f))

    wait_seconds = 5
    print(f'hitting {url} in playwright...')
    page.goto(url, timeout=60000)
    time.sleep(wait_seconds)

    page.evaluate(_read_script_from_file("single-file.js"))

    if scroll_to_bottom:
        perform_scroll_to_bottom(page)

    # get singlefile
    page_content = page.evaluate(
        """
            () => singlefile.getPageData({
                    removeHiddenElements: true,
                    removeUnusedStyles: true,
                    removeUnusedFonts: true,
                    removeImports: true,
                    blockScripts: true,
                    blockAudios: true,
                    blockVideos: true,
                    compressHTML: false,
                    removeAlternativeFonts: true,
                    removeAlternativeMedias: true,
                    removeAlternativeImages: true,
                    groupDuplicateImages: true
            });
        """
    )
    page_html_content = page_content.get("content")
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w') as f:
        f.write(page_html_content)


def get_browser_and_page(p, headless, scraping_approach):
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
    if scraping_approach == 'wget':
        page.route("https://web.archive.org*/*", lambda route: route.abort())
    return browser, page


def use_single_file_cli_docker(url, output_file, verbose=False):
    output_dir = os.path.dirname(output_file)
    if output_dir != '':
        os.makedirs(output_dir, exist_ok=True)

    cmd = f'''
        sudo docker run singlefile {url} --block-images > {output_file}
    '''
    print(f'running single-file-cli on {url}')
    if verbose:
        output = check_call(cmd, shell=True)
    else:
        output = check_call(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)


def use_single_file_cli(url, output_file, browser_path, verbose=False):
    output_dir = os.path.dirname(output_file)
    if output_dir != '':
        os.makedirs(output_dir, exist_ok=True)

    cmd = f'''
        single-file {url} \
            --block-images \
            --dump-content \
            --browser-executable-path={browser_path} \
            --user-agent '{USER_AGENT}' \
             > {output_file}
    '''
    print(f'running {cmd}...')
    if verbose:
        output = check_call(cmd, shell=True)
    else:
        output = check_call(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)



if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--site', type=str, default='nytimes.com')
    parser.add_argument('--from-date', dest='from_date', type=str, default='20230101')
    parser.add_argument('--to-date', dest='to_date', type=str, default='20230102')
    parser.add_argument('--output-dir', dest='output_dir', type=str, default='/dev/shm')
    parser.add_argument('--non-headless-browser', dest='headless', action='store_false')
    parser.add_argument(
        '--approach', dest='approach', default=None, type=str,
        help='Options: ["use-single-file", "combined", "wget", "single-file-cli"]'
    )
    parser.add_argument('--browser-path', dest='browser_path', type=str, default='/usr/bin/chromium-browser')
    parser.add_argument('--wait-seconds', dest='wait_seconds', default=0, type=int)
    parser.add_argument('--verbose', action='store_true', )
    parser.add_argument(
        '--collapse',
        type=str,
        default='30m',
        help='Amount of time in between wayback page snapshots (e.g. 32m, 2h32m, 4:13, 1.2 minutes, 5hr34m56s).',
    )
    args = parser.parse_args()

    'http://web.archive.org/cdx/search/cdx?url=ajc.com&output=json&from=20230101&to=20230102'

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

    wayback_urls = output.decode().split()
    wayback_seconds = list(map(get_time_from_waybackpack_url, wayback_urls))

    collapse_time = timeparse(args.collapse)
    prev_datetime = wayback_seconds[0] - 2 * collapse_time  # default to make sure we get the first endpoint
    processor, exclusion_needs_page = site_to_processor.get(args.site, (default_exclusion, False))
    approach = args.approach
    if approach is None:
        approach = site_to_method[args.site]
    approach_needs_page = approach_to_needs_page[approach]

    p, browser, page = None, None, None
    if approach_needs_page or exclusion_needs_page:
        p = sync_playwright()
        browser, page = get_browser_and_page(p, args.headless, args.approach)

    for url, url_seconds in zip(wayback_urls, wayback_seconds):
        if (url_seconds - prev_datetime) < collapse_time:
            continue

        time.sleep(args.wait_seconds)
        # get website
        file_on_disk = os.path.join(here, f'tmp-{args.site}', url.replace('https://', ''))
        try:
            if args.approach == 'use-single-file':
                use_playwright_singlefile(url, page, file_on_disk)
            elif args.approach == 'combined':
                use_combined_approach(args.site, url, page, file_on_disk)
            elif args.approach == 'single-file-cli':
                use_single_file_cli(url, file_on_disk, args.browser_path)
            else:
                use_wget(args.site, url, args.verbose)
        except Exception as e:
            print(f'failed: {str(e)}')
            if approach_needs_page or exclusion_needs_page:
                browser.close()
                browser, page = get_browser_and_page(p, args.headless, args.approach)
            continue

        if not os.path.exists(file_on_disk):
            continue

        date_str = url.split('/')[-2]
        file_on_disk = rename_files_for_playwright(file_on_disk=file_on_disk)
        raw_html = open(file_on_disk).read()

        # test to see if it meets criteria
        accept = processor.score_webpage(page=page, raw_html=raw_html, file_on_disk=file_on_disk)

        # if true, move these files to the output directory
        if accept:
            print(f'success! found good webpage. saving...')
            src = os.path.join(here, f'tmp-{args.site}', 'web.archive.org', 'web')
            dest = os.path.join(here, args.output_dir, 'web.archive.org', 'web')
            for dirname in list(filter(lambda x: date_str in x, os.listdir(src))):
                src_dirname = os.path.join(src, dirname)
                dest_dirname = os.path.join(dest, dirname)
                shutil.move(src_dirname, dest_dirname)

            prev_datetime = url_seconds
        else:
            print('bad webpage, deleting...')
            to_delete = glob.glob(os.path.join(here, f'tmp-{args.site}', 'web.archive.org', 'web', date_str + '*'))
            for d in to_delete:
                shutil.rmtree(d)









