# newsworthiness

Which public documents become news, and can we predict it? This repository holds the research code behind Alexander Spangher's work on *newsworthiness prediction*. We focus on one city: roughly 15,000 policy items passed by the San Francisco Board of Supervisors over ten years, about 200,000 San Francisco Chronicle articles, and 3,200 hours of meeting video. The pipeline (1) collects news homepages and parses their layouts to learn how outlets prioritize stories; (2) scrapes council agendas and minutes from Legistar and transcribes and diarizes meeting audio; (3) links policies to the articles that cover them with a probabilistic relational modeling chain that beats retrieval baselines, finding that about 7% of policies get covered; (4) fine-tunes language models on policy text, transcripts and public comment to predict coverage; and (5) evaluates the rankings with journalists. The homepage-layout code is continued in the separate `homepage-newsworthiness-with-internet-archive` repository.

## Related paper

"Tracking the Newsworthiness of Public Documents" (Spangher, Ferrara, Welsh, Peng, Tumgoren, May). An EMNLP-2023-formatted draft is in `latex/emnlp2023/`; a 2024 ACM-formatted revision titled "Surfacing Newsworthy Public Documents As Leads" is in `latex/c_j_2024/`. Cleaned code and data release: https://github.com/alex2awesome/newsworthiness-public.

## Layout

- `scripts-homepage-data/` -- homepage capture (wget; Playwright/SingleFile on Google Cloud Run) and DOM bounding-box extraction (`get_bounding_boxes_from_html.py`).
- `scripts-article-data/` -- article fetchers: `scrape_articles.py`, Common Crawl index and Cloud Function fetchers, a Scrapy spider, SimCSE sentence embeddings.
- `scripts-agendawatch-data/` -- Legistar scraper, Whisper/WhisperX transcription (`run-whisper-x.py`), speaker diarization.
- `modeling/` -- BigBird homepage-placement model, GPT-3 pairwise and absolute-position fine-tuning sets, meeting-minute summarization.
- `notebooks/` -- about 35 dated notebooks (Oct 2022 - Mar 2024) driving each stage: layout parsing, LATimes/SFChron processing, minutes-to-article linking, matching baselines, transcript analysis, human-evaluation examples.
- `layout-parsing/`, `bin/` -- layout-parser experiments; vendored third-party tools.
- `latex/` -- paper drafts. `data-to-submit/`, `emnlp-data.zip` -- released CSVs.

## How to run

The project is notebook-driven; read `notebooks/` in date order. Key scripts: `bash scripts-agendawatch-data/aw-legistar-scraper-selenium/run-legistar-sf.sh` (agendas), `python scripts-agendawatch-data/run-whisper-x.py --input-dir ... --output-dir ...` (transcripts), `python scripts-article-data/scrape_articles.py --help` (articles), `bash modeling/basic-homepage-model/train_models.sh` (placement model).

## Data

Raw data (homepage HTML and screenshots, articles, meeting PDFs, audio) lives in gitignored `data/`, `notebooks/cache/` and `scripts-*/data/`, totals roughly 100 GB, and is not included. The shareable release is `data-to-submit/full-meeting-row-df.csv` (41k meeting items) and `final-matching-articles-and-meetings.csv` (6k linked item/article pairs).

## Status

Last commit June 2023; files edited through June 2024 (paper revision and matching baselines).

## About this public copy

This repository is a code-only export of the private research repository (October 2026): scripts,
notebooks, modeling code and the paper LaTeX, with all data, model files and caches removed and all
credentials replaced by environment-variable lookups (`HF_TOKEN`, `GITHUB_TOKEN`). The vendored copy of
Ben Welsh's news-homepages tooling is omitted; use <https://github.com/palewire/news-homepages>.
Paths in scripts refer to the original data layout and will need adjusting. This is an open mentorship
project; see <https://www.alexander-spangher.com/wishlist.html>.
