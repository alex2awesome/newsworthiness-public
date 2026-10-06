import subprocess
from flask import Flask, request, Response
import os
import random

server = Flask(__name__)

SINGLEFILE_EXECUTABLE = '/node_modules/single-file-cli/single-file'
BROWSER_PATH = '/opt/google/chrome/google-chrome'
BROWSER_ARGS = '["--no-sandbox"]'
USER_AGENT = [
    'Mozilla/5.0 (X11; CrOS i686 3912.101.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/27.0.1453.116 Safari/537.36',
    'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.17 (KHTML, like Gecko) Chrome/24.0.1312.60 Safari/537.17',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_8_2) AppleWebKit/537.17 (KHTML, like Gecko) Chrome/24.0.1309.0 Safari/537.17',
    'Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.15 (KHTML, like Gecko) Chrome/24.0.1295.0 Safari/537.15',
    'Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.14 (KHTML, like Gecko) Chrome/24.0.1292.0 Safari/537.14',
    'Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.13 (KHTML, like Gecko) Chrome/24.0.1290.1 Safari/537.13',
]


@server.route('/', methods=['POST'])
def singlefile():
    url = request.form.get('url')
    if url:
        p = subprocess.Popen([
                SINGLEFILE_EXECUTABLE,
                '--browser-executable-path=' + BROWSER_PATH,
                "--browser-args='%s'" % BROWSER_ARGS,
                request.form['url'],
                "--block-images",
                "--user-agent", f"'{random.choice(USER_AGENT)}'",
                '--dump-content',
            ],
            stdout=subprocess.PIPE
        )
    else:
        return Response('Error: url parameter not found.', status=500)
    singlefile_html = p.stdout.read()
    return Response(
        singlefile_html,
        mimetype="text/html",
    )


if __name__ == '__main__':
    server.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
