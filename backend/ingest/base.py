from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime
from html import unescape
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import arxiv
import requests
from bs4 import BeautifulSoup

from backend.ingest.store import StoredAcademicDocument, init_db, upsert_document


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_BUCKET_ROOT = ROOT_DIR / "backend" / "ingest_bucket"
DEFAULT_DB_PATH = DEFAULT_BUCKET_ROOT / "academic_documents.db"
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_USER_AGENT = "k_lib-ingest/0.1 (+https://local.dev)"


class IngestError(RuntimeError):
    """Raised when a source cannot be processed."""


@dataclass
class PaperRecord:
    title: str
    url: str
    published_at: str | None = None
    download_url: str | None = None
    record_id: str | None = None
    summary: str | None = None
    sequence: int | None = None


@dataclass
class AcademicDocument:
    source_id: str
    source: str
    type: str
    full_pdf: bytes
    title: str | None = None
    url: str | None = None
    published_at: str | None = None
    record_id: str | None = None
    pdf_url: str | None = None


@dataclass
class SourceDefinition:
    source_id: str
    label: str
    main_category: str
    sub_category: str
    homepage_url: str
    access: str
    notes: str
    fetcher: Callable[["SourceDefinition", date | None, date | None], list[PaperRecord]]


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def parse_loose_date(value: str | None) -> date | None:
    if not value:
        return None

    text = value.strip()
    patterns = (
        "%Y-%m-%d",
        "%d %b %Y",
        "%d %B %Y",
        "%b %d, %Y",
        "%B %d, %Y",
        "%B %Y",
        "%b %Y",
        "%Y",
    )
    for pattern in patterns:
        try:
            parsed = datetime.strptime(text, pattern).date()
            if pattern == "%Y":
                return parsed.replace(month=1, day=1)
            if pattern in {"%B %Y", "%b %Y"}:
                return parsed.replace(day=1)
            return parsed
        except ValueError:
            continue

    matched = re.search(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}",
        text,
        flags=re.IGNORECASE,
    )
    if matched:
        try:
            return datetime.strptime(matched.group(0), "%B %d, %Y").date()
        except ValueError:
            pass
    return None


def iso_or_none(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    return value.isoformat()


def in_range(candidate: date | None, start_date: date | None, end_date: date | None) -> bool:
    if candidate is None:
        return start_date is None and end_date is None
    if start_date and candidate < start_date:
        return False
    if end_date and candidate > end_date:
        return False
    return True


def _candidate_dates(text: str) -> list[date]:
    results: list[date] = []

    for pattern in (
        r"\b(20\d{2})-(\d{2})-(\d{2})\b",
        r"\b(20\d{2})/(\d{2})/(\d{2})\b",
    ):
        for year, month, day in re.findall(pattern, text):
            try:
                results.append(date(int(year), int(month), int(day)))
            except ValueError:
                pass

    month_pattern = (
        r"\b("
        r"January|February|March|April|May|June|July|August|September|October|November|December"
        r")\s+(\d{1,2}),\s*(20\d{2})\b"
    )
    for month_name, day_text, year_text in re.findall(month_pattern, text, flags=re.IGNORECASE):
        try:
            results.append(datetime.strptime(f"{month_name} {day_text} {year_text}", "%B %d %Y").date())
        except ValueError:
            pass

    return results


def _strip_tags(value: str) -> str:
    clean = re.sub(r"<[^>]+>", " ", value)
    clean = unescape(clean)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


def _extract_html_candidates(html: str, base_url: str) -> list[PaperRecord]:
    anchor_pattern = re.compile(
        r"<a\b[^>]*href=[\"'](?P<href>[^\"']+)[\"'][^>]*>(?P<label>.*?)</a>",
        flags=re.IGNORECASE | re.DOTALL,
    )
    candidates: list[PaperRecord] = []
    seen: set[tuple[str, str]] = set()

    for match in anchor_pattern.finditer(html):
        href = match.group("href").strip()
        label = _strip_tags(match.group("label"))

        if not href or not label or len(label) < 8:
            continue
        if href.startswith("#") or href.startswith("javascript:"):
            continue

        absolute_url = urljoin(base_url, href)
        context_start = max(0, match.start() - 250)
        context_end = min(len(html), match.end() + 250)
        context = _strip_tags(html[context_start:context_end])
        dates = _candidate_dates(context)

        key = (label.lower(), absolute_url)
        if key in seen:
            continue
        seen.add(key)

        candidates.append(
            PaperRecord(
                title=label,
                url=absolute_url,
                download_url=absolute_url if absolute_url.lower().endswith(".pdf") else None,
                published_at=dates[0].isoformat() if dates else None,
                summary=context[:500] if context else None,
            )
        )

    return candidates


def _requests_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    return session


def fetch_html(url: str) -> str:
    session = _requests_session()
    response = session.get(url, timeout=DEFAULT_TIMEOUT_SECONDS)
    if response.status_code == 403 and "Just a moment" in response.text:
        raise IngestError(f"Blocked by anti-bot protection at {url}")
    response.raise_for_status()
    return response.text


def fetch_soup(url: str) -> BeautifulSoup:
    return BeautifulSoup(fetch_html(url), "html.parser")


def infer_document_type(source: SourceDefinition) -> str:
    _ = source
    return "academic"


def fetch_generic_html(source: SourceDefinition, start_date: date | None, end_date: date | None) -> list[PaperRecord]:
    session = _requests_session()
    response = session.get(source.homepage_url, timeout=DEFAULT_TIMEOUT_SECONDS)
    response.raise_for_status()

    candidates = _extract_html_candidates(response.text, source.homepage_url)
    filtered: list[PaperRecord] = []
    for item in candidates:
        published = parse_date(item.published_at)
        if in_range(published, start_date, end_date):
            filtered.append(item)

    if filtered:
        return filtered

    if start_date is None and end_date is None:
        return candidates
    return []


def fetch_private_placeholder(
    source: SourceDefinition, start_date: date | None, end_date: date | None
) -> list[PaperRecord]:
    _ = (source, start_date, end_date)
    return []


def fetch_arxiv_multi_category(
    source: SourceDefinition, start_date: date | None, end_date: date | None
) -> list[PaperRecord]:
    _ = source
    client = arxiv.Client()
    search = arxiv.Search(
        query=(
            "(cat:q-fin.* OR cat:math.* OR cat:cs.* OR cat:stat.* OR cat:cond-mat.*) "
            "AND (all:finance OR all:market OR all:trading OR all:asset OR all:portfolio "
            "OR all:volatility OR all:option OR all:derivative OR all:microstructure "
            "OR all:econophysics OR all:stochastic)"
        ),
        max_results=200,
        sort_by=arxiv.SortCriterion.SubmittedDate,
    )

    records: list[PaperRecord] = []
    for result in client.results(search):
        published = result.published.date()
        if in_range(published, start_date, end_date):
            paper_id = result.entry_id.rsplit("/", 1)[-1]
            records.append(
                PaperRecord(
                    title=result.title,
                    url=result.entry_id,
                    published_at=published.isoformat(),
                    download_url=result.pdf_url,
                    record_id=paper_id,
                    summary=result.summary,
                    sequence=len(records),
                )
            )
    return records


def fetch_jmlr(source: SourceDefinition, start_date: date | None, end_date: date | None) -> list[PaperRecord]:
    soup = fetch_soup("https://jmlr.org/papers")
    volume_link = None
    volume_year = None
    for anchor in soup.find_all("a", href=True):
        text = anchor.get_text(" ", strip=True)
        if text.startswith("Volume "):
            href = anchor["href"]
            if href.startswith("/"):
                volume_link = urljoin("https://jmlr.org", href)
            else:
                volume_link = urljoin("https://jmlr.org/papers/", href)
            year_match = re.search(r"(20\d{2})", text)
            volume_year = year_match.group(1) if year_match else None
            break
    if not volume_link:
        return []

    soup = fetch_soup(volume_link)
    records: list[PaperRecord] = []
    volume_slug_match = re.search(r"/v(\d+)/?$", volume_link)
    volume_number = volume_slug_match.group(1) if volume_slug_match else ""
    for idx, entry in enumerate(soup.find_all("dl")):
        dt = entry.find("dt")
        dd = entry.find("dd")
        if not dt or not dd:
            continue
        pdf_anchor = dd.find("a", href=re.compile(rf"^/papers/volume{volume_number}/.+\.pdf$"))
        if not pdf_anchor:
            continue
        pdf_url = urljoin("https://jmlr.org", pdf_anchor["href"])
        title = dt.get_text(" ", strip=True)
        if not title:
            continue
        published = f"{volume_year}-01-01" if volume_year else None
        paper_id = Path(urlparse(pdf_url).path).stem
        candidate_date = parse_date(published)
        if in_range(candidate_date, start_date, end_date):
            records.append(
                PaperRecord(
                    title=title,
                    url=pdf_url,
                    published_at=published,
                    download_url=pdf_url,
                    record_id=paper_id,
                    sequence=idx,
                )
            )
    return records


def fetch_neurips(source: SourceDefinition, start_date: date | None, end_date: date | None) -> list[PaperRecord]:
    soup = fetch_soup(source.homepage_url)
    proceedings_link = None
    proceedings_year = None
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if re.search(r"/paper_files/paper/20\d{2}$", href):
            proceedings_link = urljoin(source.homepage_url, href)
            year_match = re.search(r"(20\d{2})", href)
            proceedings_year = year_match.group(1) if year_match else None
            break
    if not proceedings_link or not proceedings_year:
        return []

    year_soup = fetch_soup(proceedings_link)
    records: list[PaperRecord] = []
    for idx, anchor in enumerate(year_soup.find_all("a", href=True)):
        href = anchor["href"]
        if "-Abstract-Conference.html" not in href:
            continue
        title = anchor.get_text(" ", strip=True)
        if not title or title.lower() == "report an issue":
            continue
        abs_url = urljoin(proceedings_link, href)
        published = f"{proceedings_year}-12-16"
        candidate_date = parse_date(published)
        if in_range(candidate_date, start_date, end_date):
            records.append(
                PaperRecord(
                    title=title,
                    url=abs_url,
                    published_at=published,
                    record_id=Path(urlparse(abs_url).path).stem,
                    sequence=idx,
                )
            )
    return records


def fetch_plos_computational_biology(
    source: SourceDefinition, start_date: date | None, end_date: date | None
) -> list[PaperRecord]:
    soup = fetch_soup(source.homepage_url)
    records: list[PaperRecord] = []
    seen: set[str] = set()
    for idx, anchor in enumerate(soup.find_all("a", href=True)):
        href = anchor["href"]
        if "/ploscompbiol/article?id=10.1371" not in href:
            continue
        article_url = urljoin(source.homepage_url, href)
        if article_url in seen:
            continue
        seen.add(article_url)
        title = anchor.get_text(" ", strip=True)
        if not title or len(title) < 12:
            continue
        parsed = urlparse(article_url)
        article_id = parse_qs(parsed.query).get("id", [None])[0]
        if not article_id:
            continue
        pdf_url = f"{parsed.scheme}://{parsed.netloc}/ploscompbiol/article/file?{urlencode({'id': article_id, 'type': 'printable'})}"
        records.append(
            PaperRecord(
                title=title,
                url=article_url,
                download_url=pdf_url,
                record_id=article_id,
                sequence=idx,
            )
        )

    if start_date or end_date:
        return [record for record in records if in_range(parse_date(record.published_at), start_date, end_date)]
    return records


def fetch_jasss(source: SourceDefinition, start_date: date | None, end_date: date | None) -> list[PaperRecord]:
    issues_url = "https://jasss.soc.surrey.ac.uk/index_by_issue.html"
    issues_soup = fetch_soup(issues_url)
    contents_url = None
    issue_date = None
    for anchor in issues_soup.find_all("a", href=True):
        href = anchor["href"]
        if href.endswith("/contents.html") or href.endswith("contents.html"):
            contents_url = urljoin(issues_url, href)
            text = anchor.get_text(" ", strip=True)
            year_match = re.search(r"(20\d{2})", text)
            if year_match:
                issue_date = f"{year_match.group(1)}-01-01"
            break
    if not contents_url:
        return []

    contents_soup = fetch_soup(contents_url)
    records: list[PaperRecord] = []
    seen: set[str] = set()
    for idx, anchor in enumerate(contents_soup.find_all("a", href=True)):
        href = anchor["href"]
        if not href.endswith(".html") or "contents" in href.lower():
            continue
        article_url = urljoin(contents_url, href)
        if article_url in seen:
            continue
        seen.add(article_url)
        title = anchor.get_text(" ", strip=True)
        if not title or len(title) < 12:
            continue
        if "corrigendum" in title.lower():
            continue
        pdf_url = f"https://jasss.soc.surrey.ac.uk/admin/get_pdf.php?source={article_url}"
        candidate_date = parse_date(issue_date)
        if in_range(candidate_date, start_date, end_date):
            records.append(
                PaperRecord(
                    title=title,
                    url=article_url,
                    published_at=issue_date,
                    download_url=pdf_url,
                    sequence=idx,
                )
            )
    return records


def fetch_algorithmic_finance(source: SourceDefinition, start_date: date | None, end_date: date | None) -> list[PaperRecord]:
    landing_html = fetch_html(source.homepage_url)
    if "/lander" in landing_html or "window.location.href=\"/lander\"" in landing_html:
        try:
            lander_html = fetch_html(urljoin(source.homepage_url, "/lander"))
        except Exception:
            lander_html = "Access Denied"
        if "forsale.godaddy.com" in lander_html or "Access Denied" in lander_html:
            raise IngestError(
                "Algorithmic Finance source site currently redirects to a parked/for-sale landing page; no live journal archive is available."
            )

    soup = BeautifulSoup(landing_html, "html.parser")
    records: list[PaperRecord] = []
    seen: set[str] = set()
    for idx, anchor in enumerate(soup.find_all("a", href=True)):
        href = anchor["href"]
        title = anchor.get_text(" ", strip=True)
        article_url = urljoin(source.homepage_url, href)
        if article_url in seen:
            continue
        if "article" not in href.lower() and not href.lower().endswith(".pdf"):
            continue
        if not title or len(title) < 12:
            continue
        seen.add(article_url)
        download_url = article_url if article_url.lower().endswith(".pdf") else None
        records.append(
            PaperRecord(
                title=title,
                url=article_url,
                download_url=download_url,
                sequence=idx,
            )
        )
    if start_date or end_date:
        return [record for record in records if in_range(parse_date(record.published_at), start_date, end_date)]
    return records


def fetch_annals_of_applied_statistics(
    source: SourceDefinition, start_date: date | None, end_date: date | None
) -> list[PaperRecord]:
    journal_url = "https://projecteuclid.org/journals/annals-of-applied-statistics"
    soup = fetch_soup(journal_url)
    records: list[PaperRecord] = []
    seen: set[str] = set()
    for idx, anchor in enumerate(soup.find_all("a", href=True)):
        href = anchor["href"]
        title = anchor.get_text(" ", strip=True)
        full_url = urljoin(journal_url, href)
        if full_url in seen:
            continue
        if "/journals/annals-of-applied-statistics/volume-" not in href:
            continue
        if not title or len(title) < 12 or "table of contents" in title.lower():
            continue
        seen.add(full_url)
        download_url = full_url.replace(".full", ".pdf") if full_url.endswith(".full") else full_url if full_url.endswith(".pdf") else None
        date_match = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+20\d{2}", title)
        published = None
        if date_match:
            parsed = parse_loose_date(date_match.group(0))
            published = parsed.isoformat() if parsed else None
        candidate_date = parse_date(published)
        if in_range(candidate_date, start_date, end_date):
            records.append(
                PaperRecord(
                    title=title,
                    url=full_url,
                    download_url=download_url,
                    published_at=published,
                    sequence=idx,
                )
            )
    return records


SSRN_FINANCE_GROUP_IDS = [
    "1504404",  # Capital Markets: Market Microstructure
    "1508951",  # Capital Markets: Asset Pricing & Valuation
    "1504400",  # Derivatives
    "1504392",  # Mutual Funds, Hedge Funds & Investment Industry
    "4058853",  # Technology & Investing
    "1153610",  # Econometrics: Methods - Special Topics
]


def fetch_ssrn(source: SourceDefinition, start_date: date | None, end_date: date | None) -> list[PaperRecord]:
    records: list[PaperRecord] = []
    seen: set[str] = set()
    for group_id in SSRN_FINANCE_GROUP_IDS:
        url = f"https://hq.ssrn.com/jour3/jeljour_results.cfm?form_name=journalbrowse&journal_id={group_id}"
        try:
            soup = fetch_soup(url)
        except IngestError as exc:
            raise IngestError(
                "SSRN is blocking automated server-side access with an anti-bot challenge from this environment."
            ) from exc
        for idx, anchor in enumerate(soup.find_all("a", href=True)):
            href = anchor["href"]
            if "papers.cfm?abstract_id=" not in href:
                continue
            paper_url = urljoin(url, href)
            if paper_url in seen:
                continue
            seen.add(paper_url)
            title = anchor.get_text(" ", strip=True)
            if not title or len(title) < 12:
                continue
            container_text = anchor.parent.get_text(" ", strip=True)
            published = None
            posted_match = re.search(r"Date Posted:\s*(\d{1,2}\s+\w+\s+\d{4})", container_text)
            if posted_match:
                parsed = parse_loose_date(posted_match.group(1))
                published = parsed.isoformat() if parsed else None
            candidate_date = parse_date(published)
            if in_range(candidate_date, start_date, end_date):
                records.append(
                    PaperRecord(
                        title=title,
                        url=paper_url,
                        published_at=published,
                        sequence=len(records) + idx,
                    )
                )
    return records


def choose_latest(records: list[PaperRecord]) -> PaperRecord | None:
    if not records:
        return None

    def sort_key(record: PaperRecord) -> tuple[date, int, str]:
        published = parse_date(record.published_at) or date.min
        sequence = record.sequence if record.sequence is not None else -1
        return (published, sequence, record.title.lower())

    return sorted(records, key=sort_key, reverse=True)[0]


def fetch_record_response(record: PaperRecord, url: str | None = None) -> requests.Response:
    target_url = url or record.download_url or record.url
    if not target_url:
        raise IngestError("Record is missing both url and download_url.")

    session = _requests_session()
    response = session.get(target_url, timeout=DEFAULT_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response


def _extract_pdf_links(html: str, base_url: str) -> list[str]:
    pdf_links = re.findall(r"""href=["']([^"']+\.pdf(?:\?[^"']*)?)["']""", html, flags=re.IGNORECASE)
    meta_links = re.findall(
        r"""content=["']([^"']+\.pdf(?:\?[^"']*)?)["']""",
        html,
        flags=re.IGNORECASE,
    )
    links = [urljoin(base_url, link) for link in pdf_links + meta_links]
    deduped: list[str] = []
    seen: set[str] = set()
    for link in links:
        if link not in seen:
            seen.add(link)
            deduped.append(link)
    return deduped


def resolve_pdf_url(record: PaperRecord) -> str:
    if record.download_url:
        return record.download_url
    if record.url.lower().endswith(".pdf"):
        return record.url

    if "papers.ssrn.com/sol3/papers.cfm" in record.url:
        html = fetch_html(record.url)
        matches = _extract_pdf_links(html, record.url)
        if matches:
            return matches[0]

    if "journals.plos.org" in record.url and "/article?" in record.url:
        parsed = urlparse(record.url)
        article_id = parse_qs(parsed.query).get("id", [None])[0]
        if article_id:
            return f"{parsed.scheme}://{parsed.netloc}/ploscompbiol/article/file?{urlencode({'id': article_id, 'type': 'printable'})}"

    if "jasss.soc.surrey.ac.uk" in record.url and record.url.endswith(".html"):
        return f"https://jasss.soc.surrey.ac.uk/admin/get_pdf.php?source={record.url}"

    if "papers.nips.cc" in record.url and record.url.endswith("-Abstract-Conference.html"):
        html = fetch_html(record.url)
        soup = BeautifulSoup(html, "html.parser")
        citation_pdf = soup.find("meta", attrs={"name": "citation_pdf_url"})
        if citation_pdf and citation_pdf.get("content"):
            return citation_pdf["content"]
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            text = anchor.get_text(" ", strip=True).lower()
            if text == "paper" or href.lower().endswith(".pdf"):
                return urljoin(record.url, href)

    response = fetch_record_response(record, record.url)
    candidates = _extract_pdf_links(response.text, record.url)
    if candidates:
        return candidates[0]
    raise IngestError(f"Could not resolve PDF link for record: {record.title}")


def fetch_pdf_bytes(record: PaperRecord) -> tuple[str, bytes]:
    pdf_url = resolve_pdf_url(record)
    response = fetch_record_response(record, pdf_url)
    content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
    if content_type != "application/pdf" and not pdf_url.lower().endswith(".pdf"):
        raise IngestError(f"Resolved URL is not a PDF for record: {record.title}")
    return pdf_url, response.content


def build_document(source: SourceDefinition, record: PaperRecord) -> AcademicDocument:
    pdf_url, full_pdf = fetch_pdf_bytes(record)
    return AcademicDocument(
        source_id=source.source_id,
        source=source.label,
        type=infer_document_type(source),
        full_pdf=full_pdf,
        title=record.title,
        url=record.url,
        published_at=record.published_at,
        record_id=record.record_id,
        pdf_url=pdf_url,
    )


def write_catalog(
    source: SourceDefinition,
    records: list[PaperRecord],
    start_date: date | None,
    end_date: date | None,
    output_dir: Path,
    error: str | None = None,
) -> Path:
    catalog = {
        "source_id": source.source_id,
        "source": source.label,
        "access": source.access,
        "notes": source.notes,
        "requested_range": {
            "start_date": iso_or_none(start_date),
            "end_date": iso_or_none(end_date),
        },
        "record_count": len(records),
        "error": error,
        "records": [asdict(record) for record in records],
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
    catalog_path = output_dir / "catalog.json"
    catalog_path.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    return catalog_path


def run_source(
    source: SourceDefinition,
    start_date: date | None = None,
    end_date: date | None = None,
    bucket_root: Path | None = None,
    db_path: Path | None = None,
) -> dict:
    bucket_root = bucket_root or DEFAULT_BUCKET_ROOT
    output_dir = bucket_root / source.source_id
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_path or DEFAULT_DB_PATH
    init_db(db_path)

    error = None
    records: list[PaperRecord] = []
    latest = None
    stored_in_db = False

    try:
        records = source.fetcher(source, start_date, end_date)
        latest = choose_latest(records)

        if source.access.lower() == "public" and latest is not None:
            try:
                latest_document = build_document(source, latest)
                upsert_document(
                    db_path,
                    StoredAcademicDocument(
                        source_id=latest_document.source_id,
                        source=latest_document.source,
                        type=latest_document.type,
                        title=latest_document.title,
                        url=latest_document.url,
                        published_at=latest_document.published_at,
                        pdf_url=latest_document.pdf_url,
                        full_pdf=latest_document.full_pdf,
                    ),
                )
                stored_in_db = True
            except Exception as exc:
                error = f"Document build failed: {exc}"
    except Exception as exc:
        error = f"Fetch failed: {exc}"

    catalog_path = write_catalog(source, records, start_date, end_date, output_dir, error=error)
    return {
        "source_id": source.source_id,
        "record_count": len(records),
        "latest_title": latest.title if latest else None,
        "document_type": infer_document_type(source),
        "database_path": str(db_path),
        "stored_in_db": stored_in_db,
        "catalog_path": str(catalog_path),
        "access": source.access,
        "error": error,
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest records for a single source.")
    parser.add_argument("--start-date", help="Inclusive start date in YYYY-MM-DD format.")
    parser.add_argument("--end-date", help="Inclusive end date in YYYY-MM-DD format.")
    parser.add_argument(
        "--bucket-root",
        default=str(DEFAULT_BUCKET_ROOT),
        help="Root directory for documents and catalogs.",
    )
    parser.add_argument(
        "--db-path",
        default=str(DEFAULT_DB_PATH),
        help="SQLite database for ingested PDFs.",
    )
    return parser


def main_for_source(source: SourceDefinition) -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    result = run_source(
        source=source,
        start_date=parse_date(args.start_date),
        end_date=parse_date(args.end_date),
        bucket_root=Path(args.bucket_root),
        db_path=Path(args.db_path),
    )
    print(json.dumps(result, indent=2))
