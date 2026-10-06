import pandas as pd 
import whisperx
import gc 
import argparse
from whisperx import DiarizationPipeline
from pyannote.audio.pipelines.speaker_diarization import SpeakerDiarization
from typing import Optional, Union
import json 
import xopen 
import torch
import subprocess
import glob
import os, re 
from tqdm.auto import tqdm

transcription_batch_size = 16 # reduce if low on GPU mem
embedding_batch_size = 32 # reduce if low on GPU mem
segmentation_batch_size = 64 # reduce if low on GPU mem
compute_type = "float16" # change to "int8" if low on GPU mem (may reduce accuracy)

class MyDiarizationPipeline(DiarizationPipeline):
    def __init__(
        self,
        model_name=None,
        use_auth_token=None,
        device: Optional[Union[str, torch.device]] = "cpu",
    ):
        if isinstance(device, str):
            device = torch.device(device)
        top_level_params = {
            'clustering': 'AgglomerativeClustering', 
            'embedding': 'speechbrain/spkrec-ecapa-voxceleb',
            'embedding_batch_size': embedding_batch_size,
            'embedding_exclude_overlap': True,
            # 'segmentation': 'pyannote/segmentation@2022.07',
            'segmentation': 'pyannote/segmentation-3.0',
            'segmentation_batch_size': segmentation_batch_size,
            'use_auth_token': use_auth_token,
            "segmentation_step": 0.3,
        }
        low_level_params = {
            'clustering': 
                {'method': 'centroid', 'min_cluster_size': 10, 'threshold': 0.7153814381597874},
            'segmentation': 
                {'min_duration_off': 0.5817029604921046, 'threshold': 0.4442333667381752}
        }
        self.model = SpeakerDiarization(**top_level_params)
        self.model.instantiate(low_level_params)
        self.model = self.model.to(device)


def read_in_keys(args):
    all_key_files = glob.glob(pathname=os.path.join(args.input_dir, '*.csv'))
    if args.years is None:
        all_key_files = list(filter(lambda x: re.search('\d{4}', x) is not None, all_key_files))
        args.years = list(map(lambda x: int(re.search(r'\d{4}', x)[0]), all_key_files))
    else:
        all_key_files = list(filter(lambda x: int(re.search(r'\d{4}', x)[0]) in args.years, all_key_files))

    # get all the key files
    all_keys = pd.concat(list(map(pd.read_csv, all_key_files)))
    all_keys = (
        all_keys
            .assign(year=lambda df: pd.to_datetime(df['date']).dt.year)
            .assign(clip=lambda df: df['url'].str.extract('clip/(\d+)', expand=False))
            .loc[lambda df: df['year'].isin(args.years)]
            .loc[lambda df: df['doc_type'] == 'Video']
    )
    if args.committee_filter is not None:
        all_keys = all_keys.loc[lambda df: df['committee'].isin([args.committee_filter])]

    print(f'Total keys in years [{", ".join(list(map(str, args.years)))}]: {len(all_keys)}')

    # filter to already fetched
    already_fetched_clip_ids = get_already_fetched(args)
    all_keys_to_fetch = all_keys.loc[lambda df: ~df['clip'].isin(already_fetched_clip_ids)]

    print(f'Total keys to fetch: {len(all_keys_to_fetch)}')
    return all_keys_to_fetch

def convert_to_wav(mp3_file, wav_file, verbose):
    cmd = [
        'ffmpeg', '-i', mp3_file, 
        '-acodec', 'pcm_s16le',
        '-ac', '1', # audio channels
        '-ab', '1024', # audio bitrate 
        '-ar', '22050', # audio frequency
        wav_file
    ]
    if verbose:
        subprocess.run(cmd)
    else:
        subprocess.run(cmd, stdout=open(os.devnull, 'wb') )

def get_already_fetched(args):
    already_fetched = glob.glob(os.path.join(args.output_dir, '*/*.full.json.gz'))
    return list(map(lambda x: re.search('clip-(\d+)', os.path.basename(x))[1], already_fetched))


# run 
# python run-whisper-x.py --input-dir whisper-transcription/data/ --committee-filter "Board of Supervisors" --start-idx 0 --end-idx 1000
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-dir', type=str)
    parser.add_argument('--output-dir', type=str, default=None)
    parser.add_argument('--start-idx', type=int)
    parser.add_argument('--end-idx', type=int)
    parser.add_argument('--years', nargs='+', type=int, default=None, help='Years to filter the data to, if any.')
    parser.add_argument('--committee-filter', type=str, default=None,  help='Committee to filter the data to, if any.')
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if args.output_dir is None:
        args.output_dir = args.input_dir

    # read in keys and all MP3 files on disk
    all_keys_to_fetch = read_in_keys(args)
    mp3_files = glob.glob(os.path.join(args.input_dir, '*/*.mp3'))
    mp3_files = list(filter(lambda x: '__part' not in x, mp3_files))
    mp3_files = list(filter(lambda x: re.search('clip-(\d+)', x)[1] in all_keys_to_fetch['clip'].values, mp3_files))
    mp3_files = sorted(mp3_files)[args.start_idx:args.end_idx]

    YOUR_HF_TOKEN = os.environ["HF_TOKEN"]
    diarize_model = MyDiarizationPipeline(use_auth_token=YOUR_HF_TOKEN, device=device)
    whisper_model = whisperx.load_model("large-v2", device, compute_type=compute_type)
    alignment_model, metadata = whisperx.load_align_model(language_code="en", device=device)

    for mp3_file in tqdm(mp3_files):
        # check if it got completed by another process...
        clip_id = re.search('clip-(\d+)', mp3_file)[1]
        already_fetched_clip_ids = get_already_fetched(args)
        if clip_id in already_fetched_clip_ids:
            continue

        # files 
        wav_file = mp3_file.replace('.mp3', '.wav')
        output_file = os.path.join(
            args.output_dir,
            mp3_file.split(os.sep)[-2].replace('-mp3s', ''), 
            os.path.basename(mp3_file).replace('.mp3', '.full.json')
        )

        num_tries = 0
        while num_tries < 3:
            try: 
                if not os.path.exists(wav_file):
                    convert_to_wav(mp3_file, wav_file, args.verbose)

                # 1. Transcribe with original whisper (batched)
                audio = whisperx.load_audio(wav_file)
                result = whisper_model.transcribe(audio, batch_size=transcription_batch_size)

                # 2. Align whisper output
                result = whisperx.align(result["segments"], alignment_model, metadata, audio, device, return_char_alignments=False)

                # 3. Assign speaker labels
                diarize_segments = diarize_model(wav_file)
                result = whisperx.assign_word_speakers(diarize_segments, result)
                with xopen.xopen(output_file, "w") as f:
                    f.write(json.dumps(result))
                os.remove(wav_file)
                break 

            except Exception as e:
                print(f'Error on {mp3_file}: {e}')
                num_tries += 1

        
