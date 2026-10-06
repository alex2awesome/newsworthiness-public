# first navigate to cc-index-server
# activate a py39 environment
# conda install uwsgi
# conda install brotlipy
# conda install pyyaml==5.4.1
# then, install: pip install -r requirements.txt
## it's as simple as running this in the `cc-index-server/` directory (in this folder):
cdx-server


## to get all URLs locally, in a new window, run this:
python cc_index_utils.py --domain nytimes.com --output-file nytimes-cc-articles-to-fetch.txt.gz