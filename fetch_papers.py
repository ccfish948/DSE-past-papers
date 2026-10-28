#!/usr/bin/env python3
"""Fetch all DSE past papers from dse247.com and organise them on disk.

Layout written under papers/:

    papers/<Subject>/<Language>/<Section>/<Group>/<file>.pdf

e.g. papers/Physics/English/DSE Past Paper/2012/2012p1a.pdf

Usage:
    python3 fetch_papers.py --dry-run     # crawl only, print inventory
    python3 fetch_papers.py [--jobs N]    # crawl + download (default 6 jobs)
"""

import argparse
import csv
import hashlib
import html as htmllib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BASE = "https://dse247.com"
HOME = BASE + "/"
ROOT = Path(__file__).resolve().parent
OUT = ROOT / "papers"
CACHE = ROOT / ".cache"
UA = "Mozilla/5.0 (X11; Linux x86_64) dse247-archiver/1.0"

_served = {"html": 0, "cached": 0}


def _norm(text):
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", "", text))).strip()


def get(url, binary=False, timeout=90, retries=4):
    """GET with an on-disk cache keyed by URL; returns (bytes, from_cache)."""
    key = hashlib.sha1(url.encode()).hexdigest()
    cache_file = CACHE / key
    if cache_file.exists():
        data = cache_file.read_bytes()
        _served["cached"] += 1
        return data
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
            if not binary:
                CACHE.mkdir(exist_ok=True)
                cache_file.write_bytes(data)
            _served["html"] += 1
            return data
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET failed: {url}: {last}")


def slugify(text, fallback="misc"):
    text = _norm(text).replace("/", "-").replace("\\", "-")
    text = re.sub(r'[:*?"<>|\x00-\x1f]', "", text)
    text = re.sub(r"\s+", " ", text).strip(" .-")
    return text[:120] or fallback


def normalize_url(href):
    """Repair malformed source hrefs.

    The site contains anchors whose href holds several URLs concatenated, and
    some papers are still linked through a dead ftp host that mirrors
    /wp-content/uploads/storage; those are pulled over https instead.
    """
    href = htmllib.unescape(href.strip())
    parts = [p for p in re.split(r"(?=https?://|ftp://)", href) if p]
    urls = []
    for part in parts:
        if part.startswith("ftp://"):
            tail = part.split("/wp-content/uploads/", 1)
            if len(tail) == 2:
                part = f"{BASE}/wp-content/uploads/{tail[1]}"
            else:
                urls.append(part)
                continue
        if part.startswith("/"):
            part = BASE + part
        urls.append(part)
    return urls


def safe_name(url):
    name = urllib.request.unquote(url.rsplit("/", 1)[-1])
    name = re.sub(r'[:*?"<>|\x00-\x1f]', "", name).strip(" .-")
    return name or "paper.pdf"


def subject_pages():
    """Subject index pages linked from the homepage."""
    home = get(HOME).decode("utf-8", "replace")
    urls = []
    for href, label in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', home, re.S):
        if "/subject/" in href and href not in urls:
            urls.append(href)
    if not urls:
        sys.exit("no subject pages found on homepage")
    return urls


SECTION_ALIASES = {"CE": "CE Past Paper", "DSE": "DSE Past Paper", "A-Level": "A-Level Past Paper"}
LANG_ALIASES = {"中文": "Chinese"}


def split_panes(main):
    """Split the Bricks tab content into (tab title, html) panes, in order."""
    starts = [m.start() for m in re.finditer(r'class="[^"]*tab-pane[^"]*"', main)]
    titles = [_norm(x) for x in re.findall(r"<h5[^>]*>(.*?)</h5>", main, re.S)]
    if not starts:
        return [("", main)]
    panes = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(main)
        panes.append((titles[i] if i < len(titles) else "", main[start:end]))
    return panes


def parse_subject(url):
    """Return (subject_name, [entries]) for one subject page.

    Each tab pane is one language; within it an <h2> starts a section, an <h3>
    without a link is a group heading (year/topic), an <h3> wrapping a link is
    one paper.
    """
    page = get(url).decode("utf-8", "replace")
    main = page[page.find("<main"):page.find("</main>")]
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", main, re.S)
    subject = "Unknown"
    if h1:
        # "DSE Past Paper Physics 物理試題庫" -> "Physics"
        label = _norm(h1.group(1)).replace("DSE Past Paper", "", 1)
        label = re.split(r"\s*[\u3400-\u9fff]", label, maxsplit=1)[0]
        subject = slugify(label, "Unknown")

    entries = []
    token_re = re.compile(r"<(h2|h3)\b([^>]*)>(.*?)</\1>", re.S | re.I)
    for tab_name, pane in split_panes(main):
        lang = LANG_ALIASES.get(tab_name, tab_name or "English")
        section, group = "", ""
        for m in token_re.finditer(pane):
            tag, text = m.group(1).lower(), _norm(m.group(3))
            if tag == "h2":
                section = SECTION_ALIASES.get(text, text)
                group = ""
                continue
            if "<a" in m.group(3).lower():
                # paper cell; anchors with an empty/absent href are broken
                # site placeholders ("Performance", "E2)") and are skipped.
                link = re.search(r'<a\b[^>]*href="([^"]+)"', m.group(3), re.I)
                href = htmllib.unescape(link.group(1)) if link else ""
                if re.search(r"\.(pdf|zip)(?:\?|$)", href, re.I):
                    for url in normalize_url(href):
                        entries.append(
                            {
                                "subject": subject,
                                "language": lang,
                                "section": section,
                                "group": group,
                                "label": text,
                                "url": url,
                            }
                        )
            elif text:
                group = text
    return subject, entries


def plan_paths(entries):
    """Assign each entry a relative path, resolving name collisions."""
    used, plan = {}, []
    for e in entries:
        name = safe_name(e["url"])
        rel_dir = Path(
            slugify(e["subject"]),
            slugify(e["language"]),
            slugify(e["section"], "Unfiled"),
        )
        if e["group"]:
            rel_dir /= slugify(e["group"])
        rel = rel_dir / name
        n = used.get(str(rel))
        if n:
            used[str(rel)] = n + 1
            stem, dot, ext = name.rpartition(".")
            rel = rel_dir / f"{stem} ({slugify(e['label'], 'dup')}){dot}{ext}"
        else:
            used[str(rel)] = 1
        plan.append((e, rel))
    return plan


def download_one(item):
    entry, rel, counter = item
    dest = OUT / rel
    if dest.exists() and dest.stat().st_size > 0:
        return entry, rel, "skipped", dest.stat().st_size, ""
    try:
        data = get(entry["url"], binary=True)
        if not entry["url"].lower().endswith(".zip") and data[:5] != b"%PDF-":
            if data.lstrip()[:1] == b"<":
                raise RuntimeError("missing on server (HTML not-found page)")
            raise RuntimeError(f"not a PDF payload ({len(data)} bytes)")
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        tmp.write_bytes(data)
        tmp.replace(dest)
        done = counter[0] = counter[0] + 1
        print(f"[{done}] {rel} ({len(data) // 1024} KiB)", flush=True)
        return entry, rel, "downloaded", len(data), ""
    except Exception as exc:  # noqa: BLE001 - report and continue
        print(f"[!] {rel}: {exc}", file=sys.stderr, flush=True)
        return entry, rel, "failed", 0, str(exc)


def verify():
    """Check every expected file exists at its recorded size and is a PDF."""
    index = OUT / "index.csv"
    if not index.exists():
        print("no index.csv yet; run the fetch first")
        return 1
    rows = list(csv.DictReader(index.open(encoding="utf-8")))
    problems = []
    for row in rows:
        dest = OUT / row["file"]
        if row["status"] == "failed":
            problems.append(f"failed: {row['file']} ({row['error']})")
            continue
        if not dest.exists():
            problems.append(f"missing: {row['file']}")
        elif dest.stat().st_size != int(row["bytes"]):
            problems.append(f"size mismatch: {row['file']}")
        elif dest.open("rb").read(5) != b"%PDF-" and not row["file"].endswith(".zip"):
            problems.append(f"not a pdf: {row['file']}")
    on_disk = sum(1 for p in OUT.rglob("*") if p.is_file() and p.name != "index.csv")
    ok = sum(1 for r in rows if r["status"] != "failed")
    print(f"index: {len(rows)} rows, {ok} downloaded, {len(rows) - ok} failed")
    print(f"disk:  {on_disk} files, {sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file()) / 2**30:.2f} GiB")
    for line in problems:
        print(" ", line)
    return 1 if problems else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="crawl only, no downloads")
    ap.add_argument("--verify", action="store_true", help="check the downloaded tree against index.csv")
    ap.add_argument("--jobs", type=int, default=6)
    args = ap.parse_args()

    if args.verify:
        sys.exit(verify())

    subjects = subject_pages()
    print(f"subjects: {len(subjects)}", flush=True)
    all_entries = []
    for url in subjects:
        name, entries = parse_subject(url)
        print(f"  {name}: {len(entries)} papers  ({url})", flush=True)
        all_entries.extend(entries)

    # dedupe identical URLs while keeping the first (canonical) placement
    seen, unique = set(), []
    for e in all_entries:
        if e["url"] in seen:
            continue
        seen.add(e["url"])
        unique.append(e)
    plan = plan_paths(unique)
    total = len(plan)
    print(f"unique papers: {total}")

    if args.dry_run:
        for e, rel in plan[:20]:
            print(f"  {rel}")
        print("  ...")
        return

    OUT.mkdir(exist_ok=True)
    (ROOT / "inventory.json").write_text(json.dumps([e for e, _ in plan], ensure_ascii=False, indent=1))

    counter = [0]
    tasks = [(e, rel, counter) for e, rel in plan]
    rows = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for entry, rel, status, size, err in pool.map(download_one, tasks):
            rows.append(
                {
                    "subject": entry["subject"],
                    "language": entry["language"],
                    "section": entry["section"],
                    "group": entry["group"],
                    "label": entry["label"],
                    "file": str(rel),
                    "url": entry["url"],
                    "bytes": size,
                    "status": status,
                    "error": err,
                }
            )

    with (OUT / "index.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    ok = sum(1 for r in rows if r["status"] != "failed")
    failed = total - ok
    size_mb = sum(r["bytes"] for r in rows) / 1048576
    print(f"\ndone: {ok}/{total} files, {size_mb:.0f} MiB, {failed} failed")
    print(f"index: {OUT / 'index.csv'}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
