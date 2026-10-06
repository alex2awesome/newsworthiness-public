from simcse import SimCSE
import torch
from tqdm.auto import tqdm 
import pandas as pd 
import numpy as np 

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('input', help='Input file, which is a CSV file with columns: `doc_id`, `sentences`.')
    parser.add_argument('output', help='Output file')
    parser.add_argument('--model', default='princeton-nlp/unsup-simcse-roberta-large', help='Model file')
    parser.add_argument('--process-sentences', action='store_true')
    parser.add_argument('--text-col', default='sentences', help='Column name for text')
    parser.add_argument('--lr-cutoff', type=float, default=None, help='Cutoff for first-pass-probability estimate.')
    parser.add_argument('--round', type=int, default=None, help='Number of decimal places to round to.')
    args = parser.parse_args()

    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    model = SimCSE(args.model, device=device)
    
    input_df = (
        pd.read_csv(args.input)
        .loc[lambda df: df[args.text_col].notnull()]
    )
    if args.lr_cutoff is not None:
        input_df = input_df.loc[lambda df: df['lr_prob'] > args.lr_cutoff]
    

    output_embs = model.encode(input_df[args.text_col].tolist(), batch_size=32).numpy()
    output_embs = pd.DataFrame(output_embs, index=input_df.index)
    if args.round is not None:
        output_embs = output_embs.round(args.round)
        
    output_embs.to_csv(args.output)