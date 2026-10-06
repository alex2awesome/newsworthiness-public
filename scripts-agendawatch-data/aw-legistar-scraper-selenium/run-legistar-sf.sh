for year in 2022 2023; do
    echo "Running for $year"
    python legistar_scraper/legistar_scraper.py \
        -i legistar_scraper/san-francisco-only.csv \
        -o "../../data/city-council-meeting-minutes/links-to-get/output-$year/" \
        -y $year \
        --browser-executable-path ~/.selenium-browsers/geckodriver
done