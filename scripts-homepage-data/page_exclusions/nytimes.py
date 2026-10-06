import pickle
import os
here = os.path.dirname(__file__)
import sys
sys.path.insert(0, here)
sys.path.insert(0, os.path.join(here, '../'))
from model_utils import ClusterAssignment as ClusterAssignment
import get_bounding_boxes_from_html as bb
import pandas as pd


_c = None
def get_kmeans():
    global _c
    if _c is None:
        with open(os.path.join(here, 'nytimes_predictor.pkl'), 'rb') as f:
            _c = pickle.load(f)
    return _c


def score_webpage(page, raw_html, file_on_disk, *args, **kwargs):
    """Determine whether we should include the webpage or not.

    Reasons for not including the web-page:
        * the layout is a mobile-only layout.
        * more TK
    """
    page.goto('file://' + file_on_disk, timeout=None)

    model_weights = bb.load_model_files_and_helper_scripts(page)
    page.evaluate(bb.instantiate_model_js % model_weights)
    page.evaluate(bb.get_link_divs_js)
    b = bb.get_bounding_box_info(page)
    bb_df = pd.DataFrame(b['bounding_boxes'])
    bb_df['page_width'] = b['width']
    bb_df['page_height'] = b['height']
    return get_kmeans().predict(bb_df)




