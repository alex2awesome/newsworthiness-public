from pyannote.audio import Pipeline
from pyannote.audio.pipelines.speaker_diarization import SpeakerDiarization
import os 
import glob
import subprocess
import torch 
from tqdm.auto import tqdm
import re 
import pandas as pd 

import time 
class TimerHook():
    def __init__(self):
        self.start = time.time()

    def __call__(self, step_name=None, step_artifact=None, file=None, *args, **kwargs):
        step_name = '' if step_name is None else step_name
        file = '' if file is None else file
        print(f'{file},  {step_name}: {str(time.time() - self.start)}')


def get_already_fetched(args):
    already_fetched = glob.glob(os.path.join(args.output_dir, '*/*.rttm'))
    return list(map(lambda x: re.search('clip-(\d+)', os.path.basename(x))[1], already_fetched))


def instantiate_pipeline():
    device = torch.device("cuda") if torch.cuda.is_available() else "cpu"
    use_presets = False
    if use_presets:
        pipeline = (
            Pipeline
                .from_pretrained("pyannote/speaker-diarization", use_auth_token=os.environ["HF_TOKEN"])
        )
    else:
        top_level_params = {
            'clustering': 'AgglomerativeClustering', 
            'embedding': 'speechbrain/spkrec-ecapa-voxceleb',
            'embedding_batch_size': 128,
            'embedding_exclude_overlap': True,
            'segmentation': 'pyannote/segmentation@2022.07',
            'segmentation_batch_size': 128,
            'use_auth_token': os.environ["HF_TOKEN"],
            "segmentation_step": 0.5,
        }
        pipeline = SpeakerDiarization(**top_level_params)
        low_level_params = {
            'clustering': 
                {'method': 'centroid', 'min_cluster_size': 10, 'threshold': 0.7153814381597874},
            'segmentation': 
                {'min_duration_off': 0.5817029604921046, 'threshold': 0.4442333667381752}
        }
        pipeline.instantiate(low_level_params)
    ## 
    pipeline = pipeline.to(device)
    return pipeline



# run 
# python run-pyannote.py --input-dir <recordings_dir> --output-dir <output_dir> --committee-filter "Board of Supervisors" --start-idx 0 --end-idx 1000
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

    all_key_files = glob.glob(pathname=os.path.join(args.input_dir, '*.csv'))
    if args.years is None:
        all_key_files = list(filter(lambda x: re.search('\d{4}', x) is not None, all_key_files))
        args.years = list(map(lambda x: int(re.search(r'\d{4}', x)[0]), all_key_files))
    else:
        all_key_files = list(filter(lambda x: int(re.search(r'\d{4}', x)[0]) in args.years, all_key_files))

    if args.output_dir is None:
        args.output_dir = args.input_dir

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

    # initialize pipeline
    pipeline = instantiate_pipeline()

    # read in all MP3 files on disk
    mp3_files = glob.glob(os.path.join(args.input_dir, '*/*.mp3'))
    mp3_files = list(filter(lambda x: '__part' not in x, mp3_files))
    mp3_files = list(filter(lambda x: re.search('clip-(\d+)', x)[1] in all_keys_to_fetch['clip'].values, mp3_files))
    mp3_files = sorted(mp3_files)[args.start_idx:args.end_idx]

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
            os.path.basename(mp3_file).replace('.mp3', '.rttm')
        )

        num_tries = 0
        while num_tries < 3:
            try: 
                # convert .mp3 to .wav using python subprocess
                if not os.path.exists(wav_file):
                    cmd = [
                        'ffmpeg', '-i', mp3_file, 
                        '-acodec', 'pcm_s16le',
                        '-ac', '1', # audio channels
                        '-ab', '1024', # audio bitrate 
                        '-ar', '22050', # audio frequency
                        wav_file
                    ]
                    if args.verbose:
                        subprocess.run(cmd)
                    else:
                        subprocess.run(cmd, stdout=open(os.devnull, 'wb') )
                
                # diarize
                if args.verbose:
                    diarization = pipeline(wav_file, hook=TimerHook())
                else:
                    diarization = pipeline(wav_file)
                break
            except Exception as e:
                print(f'Error on {mp3_file}: {e}')
                num_tries += 1
                continue
        
        with open(output_file, "w") as rttm:
            diarization.write_rttm(rttm)

        os.remove(wav_file)


def read_rttm(rttm_file):
    """ 
    Takes a filename and Pandas DataFrame a list of dicts with the following keys:
        * Type -- segment type; should always by SPEAKER
        * File ID -- file name; basename of the recording minus extension (e.g., rec1_a)
        * Channel ID -- channel (1-indexed) that turn is on; should always be 1
        * Turn Onset -- onset of turn in seconds from beginning of recording
        * Turn Duration -- duration of turn in seconds
        * Orthography Field -- should always by < NA >
        * Speaker Type -- should always be < NA >
        * Speaker Name -- name of speaker of turn; should be unique within scope of each file
        * Confidence Score -- system confidence (probability) that information is correct; should always be < NA >
        * Signal Lookahead Time -- should always be < NA >
    """
    import pandas as pd 
    with open(rttm_file, 'r') as f:
        lines = f.readlines()
    lines = list(map(lambda x: x.strip().split(), lines))
    df = pd.DataFrame(
        lines, columns=[
            'Type',  'File ID', 'Channel ID', 'Turn Onset',
            'Turn Duration', 'Orthography Field',
            'Speaker Type', 'Speaker Name',
            'Confidence Score', 
            'Signal Lookahead'
        ])
    return df



CUDA_VISIBLE_DEVICES=0 python run-pyannote.py --input-dir data --start-idx 0 --end-idx 200