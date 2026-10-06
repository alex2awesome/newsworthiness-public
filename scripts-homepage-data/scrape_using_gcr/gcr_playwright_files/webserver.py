import random
v
from flask import Flask, request, Response
import os
from playwright.sync_api import sync_playwright

server = Flask(__name__)

USER_AGENT = [
    'Mozilla/5.0 (X11; CrOS i686 3912.101.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/27.0.1453.116 Safari/537.36',
    'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.17 (KHTML, like Gecko) Chrome/24.0.1312.60 Safari/537.17',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_8_2) AppleWebKit/537.17 (KHTML, like Gecko) Chrome/24.0.1309.0 Safari/537.17',
    'Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.15 (KHTML, like Gecko) Chrome/24.0.1295.0 Safari/537.15',
    'Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.14 (KHTML, like Gecko) Chrome/24.0.1292.0 Safari/537.14',
    'Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.13 (KHTML, like Gecko) Chrome/24.0.1290.1 Safari/537.13',
]

@server.route('/', methods=['POST'])
def run_playwright():
    url = request.form.get('url')
    if url:
        with sync_playwright() as p:
            # Open a browser
            browser = p.chromium.launch(channel="chrome", headless=True, args=['--disable-web-security'])
            context = browser.new_context(user_agent=random.choice(USER_AGENT), screen={
                'width': 1200,
                'height': 2040
            })
            page = context.new_page()
            page.route("**/*",
                       lambda route: route.abort() if route.request.resource_type == "image" else route.continue_())

            page.add_init_script(path="single-file-bootstrap.js")
            page.add_init_script(path="single-file-hooks-frames.js")
            page.add_init_script(path="single-file-frames.js")
            page.goto(url, wait_until="load", timeout=90_000)
            page.evaluate(open("single-file.js").read())
            page_content = page.evaluate("""
                    () => singlefile.getPageData({
                            removeHiddenElements: true,
                            removeUnusedStyles: true,
                            removeUnusedFonts: true,
                            removeImports: false,
                            blockScripts: false,
                            blockAudios: true,
                            blockVideos: true,
                            blockImages: true,
                            compressHTML: false,
                            removeAlternativeFonts: true,
                            removeAlternativeMedias: true,
                            removeAlternativeImages: true,
                    });
            """)
            page_html_content = page_content.get("content")
    else:
        return Response('Error: url parameter not found.', status=500)
    return Response(
        page_html_content,
        mimetype="text/html",
    )


if __name__ == '__main__':
    server.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)), threaded=False)
