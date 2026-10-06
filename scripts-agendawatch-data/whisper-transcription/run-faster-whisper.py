from faster_whisper import WhisperModel
import requests
import os 
import re
import argparse
import pandas as pd 
from urllib.parse import urlparse
import requests
import os 
import glob
import jsonlines
from tqdm.auto import tqdm
import subprocess
from util import parse_index_and_get_video_link, request_with_repeat


# run:
# python run-faster-whisper.py <input> <output_dir> --model-size <model_size> --repeat-cutoff <repeat_cutoff> --split-audio-into-seconds <split_audio_into_seconds> --no-check-audio-file-parts
# 
# ex:
#    CUDA_VISIBLE_DEVICES=2 python run-faster-whisper.py data/2019-san-francisco-to-fetch.csv data/large-v2-output-2019/ --split-audio-into-seconds 1800 --no-check-audio-file-parts
#    CUDA_VISIBLE_DEVICES=2 python run-faster-whisper.py \
#                                   data/2019-san-francisco-to-fetch.csv \
#                                   data/large-v2-output-2019/ \
#                                   --split-audio-into-seconds 1800 \
#                                   --no-check-audio-file-parts
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('input', help='Input file')
    parser.add_argument('output_dir', help='Output directory')
    parser.add_argument('--model-size', default='large-v2', help='Model file')
    parser.add_argument('--repeat-cutoff', default=30)
    parser.add_argument('--split-audio-into-seconds', default=3600)
    parser.add_argument('--no-check-audio-file-parts', action='store_true')
    parser.add_argument('--start-idx', default=None, type=int)
    parser.add_argument('--end-idx', default=None, type=int)
    parser.add_argument('--num-tries', default=3, type=int, help='Number of tries to run the model before giving up.')
    args = parser.parse_args()

    input_df = pd.read_csv(args.input)
    print(f'Total number of files in df: {len(input_df)}')
    if ('doc_type' in input_df.columns) and ('committee' in input_df.columns):
        input_df = input_df.loc[lambda df: df['doc_type'] == 'Video'].loc[lambda df: df['committee'] == 'Board of Supervisors']
    if (args.start_idx is not None) and (args.end_idx is not None):
        input_df = input_df.iloc[args.start_idx : args.end_idx]
    elif args.start_idx is not None:
        input_df = input_df.iloc[args.start_idx:]
    
    print(f'Total number of files in df after filtering: {len(input_df)}')

    # Run on GPU with FP16
    model = WhisperModel(args.model_size, device="cuda", compute_type="float16")

    for landing_page_url in tqdm(input_df['url'], total=len(input_df)):
        audio_url_1, index_df_1 = parse_index_and_get_video_link(landing_page_url, index_method=1) # gets the bottom-half index.
        audio_url_2, index_df_2 = parse_index_and_get_video_link(landing_page_url, index_method=2) # gets the right side-bar index.
        audio_url = audio_url_1 or audio_url_2 # prefer the bottom-half index, but if it doesn't exist, use the right side-bar index.
        if audio_url == None:
            continue

        clip_id = re.search(r'clip/(\d+)', landing_page_url)[1]

        if not os.path.exists(args.output_dir):
            os.makedirs(args.output_dir)

        index_outfile_1 = f'{args.output_dir}/index-clip-{clip_id}-1.csv'
        index_outfile_2 = f'{args.output_dir}/index-clip-{clip_id}-2.csv'
        mp3_audio_file = f'{args.output_dir}/audio-clip-{clip_id}.mp3'
        mp3_audio_file_parts = f'{args.output_dir}/audio-clip-{clip_id}__part-%03d.mp3'

        # if the audio file exists, and we're not checking the parts, skip
        if args.no_check_audio_file_parts:
            if os.path.exists(mp3_audio_file):
                continue

        for index_outfile, index_df in [(index_outfile_1, index_df_1), (index_outfile_2, index_df_2)]:
            if not os.path.exists(index_outfile):
                with open(index_outfile, 'w') as f:
                    if index_df is not None:
                        index_df.to_csv(f)
                    else:
                        f.write(f'No index found on {landing_page_url}.')

        if not os.path.exists(mp3_audio_file):
            audio_resp = request_with_repeat(audio_url)
            if audio_resp is None:
                continue
            
            with open(mp3_audio_file, 'wb') as f:
                f.write(audio_resp.content)

            # split audio into parts
            subprocess.check_call(f'ffmpeg -i {mp3_audio_file} -f segment -segment_time {args.split_audio_into_seconds} -c copy {mp3_audio_file_parts}', shell=True)

        mp3_audio_files = glob.glob(f'{args.output_dir}/audio-clip-{clip_id}__part-*.mp3')
        for mp3_file in mp3_audio_files:
            txt_file_output = mp3_file.replace('.mp3', '.txt')
            if os.path.exists(txt_file_output):
                continue

            for i in range(args.num_tries):
                print(f'running {mp3_file}... ({i+1}/{args.num_tries})')
                try:
                    # increase num beams and patience to prevent degeneration
                    segments, info = model.transcribe(
                        mp3_file, 
                        beam_size=(3 + i), 
                        patience=(1.0 + 2 * float(i)/10),
                    ) 
                except ValueError as e:
                    print(f'WARNING: {e}, trying again... ({i+1}/{args.num_tries})')
                    continue

                all_segments = []
                for segment in segments:
                    all_segments.append({
                        'start': segment.start,
                        'end': segment.end,
                        'text': segment.text
                    })

                # Get the text of the last `repeat_cutoff` segments.
                repeat_cutoff = all_segments[-args.repeat_cutoff:]
                repeat_cutoff = list(map(lambda x: x['text'], repeat_cutoff))
                # Check if the last `repeat_cutoff` transcribed segments are all the same.
                # If so, then we're probably in a degenerate state, and we should try again.
                if len(set(repeat_cutoff)) > 1:
                    break
                else:
                    print(f'WARNING: repeat cutoff failed: {os.linesep.join(repeat_cutoff)}, trying again... ({i+1}/{args.num_tries})')

            with open(txt_file_output, 'w') as f:
                jsonlines.Writer(f).write_all(all_segments)
        
        # remove mp3 files
        for mp3_file in mp3_audio_files:
            os.remove(mp3_file)