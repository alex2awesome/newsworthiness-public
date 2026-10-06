
import argparse
import os
from helpers import *
import librosa
import torch
import soundfile
from nemo.collections.asr.models import ClusteringDiarizer
import os 
import glob
import subprocess
from tqdm.auto import tqdm
import re 
import shutil
import logging
from typing import Any, List, Optional, Union
from nemo.collections.asr.parts.utils.speaker_utils import (
    audio_rttm_map,
    get_embs_and_timestamps,
    perform_clustering,
)
import pandas as pd 
from nemo.collections.asr.metrics.der import score_labels


def get_already_fetched(args):
    already_fetched = glob.glob(os.path.join(args.output_dir, '*/*.rttm'))
    return list(map(lambda x: re.search('clip-(\d+)', os.path.basename(x))[1], already_fetched))


class MyClusteringDiarizer(ClusteringDiarizer):
    """Same as the base class, but optionally performs the clustering on CPU."""

    def diarize(self, paths2audio_files: List[str] = None, batch_size: int = 0, run_clustering_on_cpu: bool = False):
        """
        Diarize files provided thorugh paths2audio_files or manifest file
        
        Input:
        * paths2audio_files (List[str]): list of paths to file containing audio file
        * batch_size (int): batch_size considered for extraction of speaker embeddings and VAD computation
        * run_clustering_on_cpu (bool): if True, run clustering on CPU
        """

        self._out_dir = self._diarizer_params.out_dir

        self._speaker_dir = os.path.join(self._diarizer_params.out_dir, 'speaker_outputs')

        if os.path.exists(self._speaker_dir):
            logging.warning("Deleting previous clustering diarizer outputs.")
            shutil.rmtree(self._speaker_dir, ignore_errors=True)
        os.makedirs(self._speaker_dir)

        if not os.path.exists(self._out_dir):
            os.mkdir(self._out_dir)

        self._vad_dir = os.path.join(self._out_dir, 'vad_outputs')
        self._vad_out_file = os.path.join(self._vad_dir, "vad_out.json")

        if batch_size:
            self._cfg.batch_size = batch_size

        if paths2audio_files:
            if type(paths2audio_files) is list:
                self._diarizer_params.manifest_filepath = os.path.join(self._out_dir, 'paths2audio_filepath.json')
                self.path2audio_files_to_manifest(paths2audio_files, self._diarizer_params.manifest_filepath)
            else:
                raise ValueError("paths2audio_files must be of type list of paths to file containing audio file")

        self.AUDIO_RTTM_MAP = audio_rttm_map(self._diarizer_params.manifest_filepath)

        out_rttm_dir = os.path.join(self._out_dir, 'pred_rttms')
        os.makedirs(out_rttm_dir, exist_ok=True)

        # Speech Activity Detection
        self._perform_speech_activity_detection()

        # Segmentation
        scales = self.multiscale_args_dict['scale_dict'].items()
        for scale_idx, (window, shift) in scales:

            # Segmentation for the current scale (scale_idx)
            self._run_segmentation(window, shift, scale_tag=f'_scale{scale_idx}')

            # Embedding Extraction for the current scale (scale_idx)
            self._extract_embeddings(self.subsegments_manifest_path, scale_idx, len(scales))

            self.multiscale_embeddings_and_timestamps[scale_idx] = [self.embeddings, self.time_stamps]

        embs_and_timestamps = get_embs_and_timestamps(
            self.multiscale_embeddings_and_timestamps, self.multiscale_args_dict
        )

        # Clustering
        all_reference, all_hypothesis = perform_clustering(
            embs_and_timestamps=embs_and_timestamps,
            AUDIO_RTTM_MAP=self.AUDIO_RTTM_MAP,
            out_rttm_dir=out_rttm_dir,
            clustering_params=self._cluster_params,
            device=self._speaker_model.device if not run_clustering_on_cpu else torch.device('cpu'),
            verbose=self.verbose,
        )
        logging.info("Outputs are saved in {} directory".format(os.path.abspath(self._diarizer_params.out_dir)))

        # Scoring
        return score_labels(
            self.AUDIO_RTTM_MAP,
            all_reference,
            all_hypothesis,
            collar=self._diarizer_params.collar,
            ignore_overlap=self._diarizer_params.ignore_overlap,
            verbose=self.verbose,
        )



# run 
# python run-on-many-files.py --input-dir ../whisper-transcription/data --output-dir diarized-clips --committee-filter "Board of Supervisors" --start-idx 0 --end-idx 100
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-dir', type=str)
    parser.add_argument('--output-dir', type=str, default=None)
    parser.add_argument('--start-idx', type=int)
    parser.add_argument('--end-idx', type=int)
    parser.add_argument('--years', nargs='+', type=int, default=None, help='Years to filter the data to, if any.')
    parser.add_argument('--committee-filter', type=str, default=None,  help='Committee to filter the data to, if any.')
    parser.add_argument('--max-split-size-mb', type=int, default=None, help='Max split size in MB.')
    args = parser.parse_args()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if args.max_split_size_mb is not None:
        os.environ["PYTORCH_CUDA_ALLOC_CONF"] = f"max_split_size_mb:{args.max_split_size_mb}"


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
            .loc[lambda df: df['committee'].isin([args.committee_filter])]
            .loc[lambda df: df['doc_type'] == 'Video']
    )

    print(f'Total keys in years [{", ".join(list(map(str, args.years)))}]: {len(all_keys)}')

    # filter to already fetched
    already_fetched_clip_ids = get_already_fetched(args)
    all_keys_to_fetch = all_keys.loc[lambda df: ~df['clip'].isin(already_fetched_clip_ids)]

    print(f'Total keys to fetch: {len(all_keys_to_fetch)}')

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

        # convert audio to mono for NeMo combatibility
        signal, sample_rate = librosa.load(mp3_file, sr=None)
        ROOT = os.getcwd()
        temp_path = os.path.join(args.output_dir, clip_id)
        os.makedirs(temp_path, exist_ok=True)
        soundfile.write(os.path.join(temp_path, "mono_file.wav"), signal, sample_rate, "PCM_24")

        # Initialize NeMo MSDD diarization model
        model = MyClusteringDiarizer(cfg=create_config(temp_path)).to(device)
        model.diarize(run_clustering_on_cpu=True)
        del model 





