docker build -t singlefile-webapp .
docker tag singlefile-webapp-playwright gcr.io/usc-research/singlefile-webapp-playwright
docker push gcr.io/usc-research/singlefile-webapp-playwright
curl -d 'url=https://web.archive.org/web/20230101000014/nytimes.com/' https://singlefile-webapp-playwright-4-ukvxfz3sya-uw.a.run.app

https://singlefile-webapp-playwright-4-ukvxfz3sya-uw.a.run.app
