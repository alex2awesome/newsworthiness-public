import get_bounding_boxes_from_html as bb
import os, glob
import subprocess as proc
import re
import jsonlines
from tqdm.auto import tqdm


def run_subprocess(cmd, ret_output=True, verbose=False):
    if ret_output:
        output, err = proc.Popen(cmd.split(), stdin=proc.PIPE, stdout=proc.PIPE, stderr=proc.PIPE).communicate()
        return output.decode().split()

    try:
        if verbose:
            proc.check_call(cmd.split())
        else:
            proc.check_call(cmd.split(), stdout=proc.DEVNULL, stderr=proc.STDOUT)
    except Exception as e:
        print(f'Error: {e}')


if __name__ == '__main__':
    from argparse import ArgumentParser
    parser = ArgumentParser()
    parser.add_argument('--site', type=str, )
    parser.add_argument('--source', type=str, default='gcp')
    parser.add_argument('--batch-size', dest='batch_size', type=str, default=None)
    parser.add_argument('--output-dir', dest='output_dir', type=str, default='.')
    parser.add_argument('--verbose', action='store_true')

    args = parser.parse_args()

    if args.source == 'gcp':
        cmd = 'gsutil ls gs://usc-data/newspaper-pages/full-page-htmls'
        remote_items_to_get = run_subprocess(cmd, ret_output=True)
        print(remote_items_to_get)
        local_items_to_process = []
        for remote_item in tqdm(remote_items_to_get):
            item_zip_file = os.path.join(args.output_dir, os.path.basename(remote_item))
            item_output_name = item_zip_file.replace('.zip', '')
            if os.path.exists(item_output_name):
                continue

            cmd = f'gsutil cp {remote_item} {args.output_dir}'
            run_subprocess(cmd, ret_output=False, verbose=args.verbose)
            cmd = f'unzip -d {item_output_name} {item_zip_file}'
            run_subprocess(cmd, ret_output=False, verbose=args.verbose)
            os.remove(item_zip_file)
            for one_file in glob.glob(os.path.join(item_output_name, '*')):
                if args.site not in one_file:
                    os.remove(one_file)
                else:
                    local_items_to_process.append(one_file)

        key_func = lambda x: re.search('html-(\d+)', x)[1]

        bounding_boxes, page_width_height = bb.get_bounding_boxes_for_files(local_items_to_process, key_func=key_func)
        bounding_box_output = list(map(lambda x: x.to_dict(orient='records'), bounding_boxes))
        with open(os.path.join(args.output_dir, f'bounding-boxes-{args.site}.jsonl'), 'w') as f:
            jsonlines.Writer(f).write_all(bounding_box_output)





