# Derby Name Scraper

Scrapes roller derby names from:

- <https://www.derbyrollcall.com/everyone>
- <https://rollerderbyroster.com/view-names/>

Then saves deduplicated names to CSV.

For `rollerderbyroster.com`, the scraper automatically iterates alphabet pages (`?ini=A` through `?ini=Z`) to fetch all names.

## Setup (uv)

```powershell
uv sync
```

## Run

```powershell
uv run python scrape_derby_names.py
```

Default output is `data/derby_names.csv`.

To customize output path:

```powershell
uv run python scrape_derby_names.py --output data/names.csv
```

To override sources, pass one or more `--url` flags:

```powershell
uv run python scrape_derby_names.py --url https://www.derbyrollcall.com/everyone --url https://rollerderbyroster.com/view-names/
```