# DSE247 paper archive

All DSE past papers published on <https://dse247.com/>, fetched and grouped locally.

## Layout

```
papers/<Subject>/<Language>/<Section>/<Year or Topic>/<file>.pdf
```

```
papers/
  Physics/
    English/
      DSE Past Paper/2012/2012p1a.pdf, 2012p1b.pdf, 2012p2.pdf, 2012ans.pdf
      By Topic/1temperature.pdf ... 13Gravitation.pdf
    Chinese/
      DSE Past Paper/2012/...
  Maths/
    English/
      CE Past Paper/1980/...
      DSE Past Paper/2012/...
      By Topic/...
    Chinese/...
  English/
    English/
      A-Level Past Paper/1989/...
      CE Past Paper/Recording/...
      DSE Past Paper/2012/...
```

Grouping comes from the page's own tab (language) and section headings, so the
folders mirror how the site organises the papers. `papers/index.csv` records the
source URL, label and byte size of every paper.

## Results

1675 PDFs, 5.46 GiB, 13 subjects (site-wide crawl on 2026-10-28).

| Subject | Files | Size |
| --- | --- | --- |
| Maths | 293 | 0.63 GiB |
| M2 | 174 | 0.27 GiB |
| BAFS | 164 | 0.66 GiB |
| English | 161 | 0.54 GiB |
| LS | 145 | 0.29 GiB |
| Chemistry | 140 | 0.56 GiB |
| Economics | 135 | 0.45 GiB |
| Physics | 116 | 0.48 GiB |
| ICT | 106 | 0.35 GiB |
| Geography | 98 | 0.76 GiB |
| M1 | 74 | 0.29 GiB |
| THS | 35 | 0.05 GiB |
| Chinese History | 34 | 0.14 GiB |

## Usage

Python 3 stdlib only, no packages.

```bash
python3 fetch_papers.py --dry-run   # crawl and list what would be fetched
python3 fetch_papers.py             # crawl + download (--jobs N, default 6)
python3 fetch_papers.py --verify    # compare index.csv with the files on disk
```

Re-running is safe: pages are cached in `.cache/`, finished files are skipped,
failed ones are retried.

## Known gaps

16 of 1691 linked papers are dead links on the server (the site answers HTTP 200
with a "Not Found" HTML page). They are listed by `--verify` and in the `failed`
rows of `papers/index.csv`:

- Maths 2023 answer, Maths sample-paper answer (English + Chinese)
- M1/M2 2023 answer
- M2 CE 2005 answer
- Economics by-topic bk1 / bk10-17, Economics 2022 p1+p2 (Chinese)
- BAFS by-topic P2A book 1 / book 2
- Chemistry 2018 performance report, Geography 2019 performance report
- ICT sample-paper answer (Chinese), LS 2022 answer (Chinese)

The site also served some anchors with several URLs concatenated and some via a
dead `ftp.pp.flowdigital.com.hk` host; the script splits the former and rewrites
the latter to the site's https mirror, which is how THS and 14 extra M2 papers
were recovered.
