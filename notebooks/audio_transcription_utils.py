import seaborn as sns
import matplotlib.pyplot as plt
import numpy as np
import jsonlines
import re 
import pandas as pd
import glob
from itertools import groupby
import re 
from itertools import groupby
import jsonlines
import os 
from tqdm.auto import tqdm


def find_header(row):
    is_header = True
    text = row['text'] if pd.notnull(row['text']) else ''
    text = text.split('[')[0].strip()
    is_header = is_header and (re.search('[A-Z]{2}', text) is not None)
    is_header = is_header and (text.upper() == text)
    is_header = is_header and pd.isnull(row['proposal_number'])
    return is_header


def header_to_category(header):
    if pd.isnull(header):
        header = ''  
    # split on '[' and take first part (eg. CONSENT AGENDA[Consent Boiler|B1] => CONSENT AGENDA)
    header = header.split('[')[0]
    # remove trailing 'S' from header
    if (header.endswith('S')) and (not header.endswith('SS')):
        header = header[:-1]
    # remove numbers that are happen at the beginning of `header`
    header = re.sub('^[0-9]+', '', header)
    for category in ['SPECIAL ORDER', 'REMARKS', 'ELECTION', 'ROLL CALL', 'PUBLIC COMMENT', 'PROPOSED ORDINANCE', 'PROPOSED RESOLUTION', 'COMMITTEE REPORT', ]:    
        if category in header:
            return category    
    return header.strip()


def infer_and_fill_in_missing_time_values(index_csvs, transcribed_texts_df, acceptable_transcriptions=None):
    """ 
    Fill in missing time values in the `index_csvs` with a single segment of transcribed text.

    Parameters
    ----------
    * index_csvs : (pd.DataFrame)
        A dataframe of the index-csvs to process. Must have a `clip_id` column.
    * transcribed_texts_df : (pd.DataFrame)
        A dataframe of the transcribed texts. Must have a `clip_id` column.
    * acceptable_transcriptions : (pd.DataFrame)
        A dataframe of the acceptable transcriptions. Must have a `clip_id` column.
    """ 
    # prepare the dataframes for easier processing,
    index_csvs = index_csvs.reset_index().set_index('clip_id')
    transcribed_texts_df = transcribed_texts_df.reset_index().set_index('clip_id')
    if acceptable_transcriptions is not None:
        acceptable_transcriptions = acceptable_transcriptions.reset_index().set_index('clip_id')

    filled_in_csvs = []
    for clip_id in tqdm(index_csvs.index.drop_duplicates()):
        if not (clip_id in transcribed_texts_df.index):
            continue
        if acceptable_transcriptions is not None:
            if not (clip_id in acceptable_transcriptions.index):
                continue

        # get index csv, transcribed text and max time for this clip
        one_csv_df = index_csvs.loc[clip_id].loc[lambda df: df['text'].notnull()].reset_index()
        one_transcribed_text_df = transcribed_texts_df.loc[clip_id].reset_index()
        if acceptable_transcriptions is not None:
            max_time = acceptable_transcriptions.loc[clip_id, 'transcribed_end_time']
        else:
            max_time = one_transcribed_text_df['end'].max()
        
        # fill in the time column with the maximum time for this clip if the last time is null
        if pd.isnull( one_csv_df.iloc[-1]['time']):
            one_csv_df.iloc[-1, one_csv_df.columns.get_loc('time')] = max_time

        # get the indices of the null time values
        idxs = one_csv_df.loc[lambda df: df['time'].isnull()].index
        for null_idx in idxs:
            # get the start and end time for this agenda item based on surrounding agenda items. 
            # (might give more time to the first item if there are multiple in a row that are null...)
            start_time = one_csv_df['time'].fillna(method='ffill').loc[null_idx - 1] if null_idx > 0 else 0
            end_time = one_csv_df['time'].fillna(method='bfill').loc[null_idx + 1] if (null_idx < len(one_csv_df) - 1) else max_time
            start_time, end_time = (start_time, end_time) if start_time < end_time else (end_time, start_time)

            # get the lines of transcription text for this agenda item
            candidate_transcription_sents = (
                one_transcribed_text_df
                    # `start_time` is the time-marker for the previous agenda item.
                    .pipe(lambda df: df.loc[lambda df: df['start'] > start_time] if len(df) > 1 else df)
                    # `end_time` is the time-marker for the next agenda item.
                    .pipe(lambda df: df.loc[lambda df: df['end'] < end_time] if len(df) > 1 else df)
            )

            # if there are no lines of transcription text for this agenda item, just peg the end-time as the max-time.
            if len(candidate_transcription_sents) == 0:
                max_likelihood_time = end_time
            else:
                max_likelihood_time = (
                    # get the max likelihood transcription
                    candidate_transcription_sents
                    # get the time-marker for the max likelihood
                    .loc[lambda df: df['proba'].idxmax()]
                    ['start']
                )

            # fill in the null time with the max likelihood time
            one_csv_df.loc[null_idx, 'time'] = max_likelihood_time
        
        # sort by time and drop duplicates
        one_csv_df = one_csv_df.sort_values('time').drop_duplicates('text')
        one_csv_df['end_time'] = one_csv_df['time'].tolist()[1:] + [max_time]
        filled_in_csvs.append(one_csv_df)

    return pd.concat(filled_in_csvs)