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
from util import get_packet, parse_index_and_get_video_link


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('input', help='Input file')
    parser.add_argument('output_dir', help='Output directory')
    parser.add_argument('--model', default='ggml-medium.en.bin', help='Model file')
    args = parser.parse_args()

    input_df = pd.read_csv(args.input)
    input_df = input_df.loc[lambda df: df['doc_type'] == 'Video']

    for landing_page_url in tqdm(input_df['url'], total=len(input_df)):
        audio_url, index_df = parse_index_and_get_video_link(landing_page_url)
        clip_id = re.search(r'clip/(\d+)', landing_page_url)[1]
        
        index_outfile = f'{args.output_dir}/index-clip-{clip_id}.csv'
        if os.path.exists(index_outfile):
            continue

        with open(index_outfile, 'w') as f:
            index_df.to_csv(f)
        audio_resp = requests.get(audio_url).content
        
        # files
        mp3_audio_file = args.output_dir + f'/audio-clip-{clip_id}.mp3'
        wav_audio_file = mp3_audio_file.replace('.mp3', '.wav')
        txt_output_file = mp3_audio_file.replace('.mp3', '.txt')
        with open(mp3_audio_file, 'wb') as f:
            f.write(audio_resp)

        # run whisper.cpp on audio file
        subprocess.check_call(f'ffmpeg -i {mp3_audio_file} -ac 1 -ar 16000 {wav_audio_file}', shell=True)
        subprocess.check_call(f'whisper.cpp/main -m whisper.cpp/models/{args.model} -pp -f {wav_audio_file} | tee {txt_output_file}', shell=True)