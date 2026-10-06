#!/usr/bin/env bash

output_dir=/dev/shm
while getopts u:s:e:o:c: flag
do
    case "${flag}" in
        u) site=${OPTARG};;
        s) from_date=${OPTARG};;
        e) to_date=${OPTARG};;
        o) output_dir=${OPTARG};;
    esac
done
echo "site: $site";
echo "from-date: $from_date";
echo "to-date: $to_date";

echo waybackpack ${site} --from-date ${from_date} --to-date ${to_date} --list
wayback_sites=$(waybackpack ${site} --from-date ${from_date} --to-date ${to_date} --list)

echo $wayback_sites
urls=$(echo ${wayback_sites} | tr " " "\n")

echo $wayback_sites > "site-all.txt"
failed_urls=()

for i in 1 2
do
  for url in $urls
  do
    echo Retrieving $url...
    wget \
        -U 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36' \
        --no-clobber \
        --page-requisites \
        --convert-links \
        --timestamping \
        --reject '*.js,*.ico,*.txt,*.gif,*.jpg,*.jpeg,*.png,*.mp3,*.pdf,*.tgz,*.flv,*.avi,*.mpeg,*.iso' \
        --ignore-tags=img \
        --domains web.archive.org \
        --no-parent ${url} \
        -P $output_dir

    if [[ $? -ne 0 ]]; then
        echo "wget failed $url"
        failed_urls+=(url)
    fi
  done
  urls=failed_urls
  failed_urls=()
  echo Retrying $i with $urls...
done

joined_urls=$(IFS=  ; echo "${failed_urls[*]}")
echo $joined_urls > "site-failed.txt"

