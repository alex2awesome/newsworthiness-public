docker build -t singlefile-webapp .
docker tag singlefile-webapp gcr.io/usc-research/singlefile-webapp
docker push gcr.io/usc-research/singlefile-webapp
curl -d 'url=http://www.example.com/' https://singlefile-webapp-ukvxfz3sya-uc.a.run.app