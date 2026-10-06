import re
import argparse
import pandas as pd 
import sys
from urllib.parse import urlparse
import requests
import os 
from bs4 import BeautifulSoup
from tqdm.auto import tqdm
import subprocess
import time


def get_packet(x):
    output = {}
    output['class_name'] = x.attrs['class'][1]
    output['text'] = x.get_text()
    a = x.find('a')
    if a:
        output['time'] = re.search('\d+', a.attrs.get('onclick'))[0]
    return output


def request_with_repeat(url, num_tries=3):
    try:
        for _ in range(num_tries):
            resp = requests.get(url)
            if resp.status_code != 200:
                time.sleep(5)
                continue
            else:
                continue

        if resp.status_code != 200:
            return None
        else:
            return resp 
    except:
        return None


def parse_index_and_get_video_link(landing_page_url, index_method=1):
    """
        Hits the `granicus` page. Returns the audio url and a table of the meeting index.

        Parameters
        ----------
        * landing_page_url : str
            The url of the granicus page.
        * index_method : int
            The index to parse. 
                If 1, use the bottom-half index, which only contains hyperlinked lines. 
                If 2, use the right side-bar index, which contains an index hierarchy.
    """

    # This block might fail if the page returned is `.pdf` or not a 200 response.
    try:
        resp = request_with_repeat(landing_page_url)
        if resp == None:
            return None, None
        html = resp.text
        soup = BeautifulSoup(html, 'lxml')
        index = soup.find('section', {'id': 'index'})
    except:
        return None, None 
    
    if index_method == 1:
        # index method 1 
        index_parts = index.find_all('div') if index is not None else []
        all_index_parts = []
        for p in index_parts:
            time = p.attrs['time']
            text = p.get_text().strip()
            all_index_parts.append({'time': time, 'text': text})
        all_index_parts_df = pd.DataFrame(all_index_parts)

    else:
        # Other index:
        data_url = soup.find(attrs={'class': 'documents-default-document'})
        if data_url is None:
            print(f'No data url found. Url: {data_url}')
            return None, None
        data_url = data_url.attrs['data-url']
        url_parts = urlparse(landing_page_url)
        index_url = url_parts.scheme + '://' + url_parts.netloc + data_url
        index_resp = request_with_repeat(index_url)
        if index_resp == None:
            return None, None
        index_soup = BeautifulSoup(index_resp.text, 'lxml')
        agenda_items = index_soup.find_all('div', attrs={'class': 'agenda'})
        if agenda_items == []:
            return None, None
        agenda_list = list(map(get_packet, agenda_items))
        all_index_parts_df = pd.DataFrame(agenda_list)
    
    download_links = soup.find('div', {'id': 'download-options'})
    download_links = download_links.find_all('a') if download_links is not None else []
    audio_link = list(filter(lambda x: 'audio' in x.get_text().strip().lower(), download_links))
    audio_link = audio_link[0] if len(audio_link) > 0 else None
    audio_download_link = audio_link.get('href') if audio_link is not None else None
    return audio_download_link, all_index_parts_df






## install cudnn
# sudo rpm -i cudnn-local-repo-rhel7-8.9.1.23-1.0-1.x86_64.rpm
# sudo yum install libcudnn8-8.9.1.23-1.cuda12.1
# sudo yum install libcudnn8-devel-8.9.1.23-1.cuda12.1
# sudo yum install libcudnn8-samples-8.9.1.23-1.cuda12.1