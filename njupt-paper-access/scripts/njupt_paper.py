#!/usr/bin/env python3
"""NJUPT-assisted scholarly discovery and licensed-paper collection."""

from __future__ import annotations

import argparse
import csv
import hashlib
import http.cookiejar
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.message import Message
from pathlib import Path
from typing import Any

PORTAL = "https://vpn.njupt.edu.cn/"
DOI_RE = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)?(10\.\d{4,9}/\S+)$", re.I)
SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
UNSAFE_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
HTML_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", flags=re.I | re.S)
PDF_META_RE = re.compile(
    r"<meta[^>]+(?:name|property)=[\"']citation_pdf_url[\"'][^>]+"
    r"content=[\"']([^\"']+)[\"']",
    flags=re.I,
)
DEFAULT_MAX_PDF_BYTES = 150 * 1024 * 1024


def default_home() -> Path:
    configured = os.environ.get("NJUPT_PAPER_HOME")
    if configured:
        return Path(configured).expanduser()
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "NjuptPaperAccess"
    return Path.home() / ".local" / "share" / "njupt-paper-access"


class Paths:
    def __init__(self) -> None:
        self.home = default_home()
        self.profile = self.home / "browser-profile"
        self.downloads = self.home / "downloads"
        self.collections = self.home / "collections"

    def ensure(self) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        self.profile.mkdir(parents=True, exist_ok=True)
        self.downloads.mkdir(parents=True, exist_ok=True)
        self.collections.mkdir(parents=True, exist_ok=True)


def browser_candidates() -> list[Path]:
    candidates: list[Path] = []
    if os.name == "nt":
        for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            root = os.environ.get(variable)
            if root:
                candidates.extend(
                    [
                        Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe",
                        Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                    ]
                )
    else:
        for command in (
            "google-chrome",
            "google-chrome-stable",
            "chromium",
            "chromium-browser",
            "microsoft-edge",
        ):
            found = shutil.which(command)
            if found:
                candidates.append(Path(found))
        if sys.platform == "darwin":
            candidates.extend(
                [
                    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                    Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
                ]
            )
    return [path for path in candidates if path.is_file()]


def find_browser() -> Path:
    candidates = browser_candidates()
    if not candidates:
        raise RuntimeError("Chrome or Edge was not found. Install one, then rerun this command.")
    return candidates[0]


def bridge_available() -> dict[str, Any]:
    result: dict[str, Any] = {
        "host": "vpn.njupt.edu.cn",
        "dns": False,
        "tcp_443": False,
    }
    try:
        addresses = socket.getaddrinfo("vpn.njupt.edu.cn", 443, type=socket.SOCK_STREAM)
        result["dns"] = bool(addresses)
        if addresses:
            with socket.create_connection((addresses[0][4][0], 443), timeout=5):
                result["tcp_443"] = True
    except OSError as exc:
        result["error"] = type(exc).__name__
    return result


def configure_download_preferences(paths: Paths) -> bool:
    """Point this dedicated Chrome profile's download directory at our watcher."""
    profile_default = paths.profile / "Default"
    profile_default.mkdir(parents=True, exist_ok=True)
    prefs_path = profile_default / "Preferences"
    singleton_lock = paths.profile / "SingletonLock"
    if singleton_lock.exists() or singleton_lock.is_symlink():
        return False
    prefs: dict[str, Any] = {}
    if prefs_path.exists():
        try:
            loaded = json.loads(prefs_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                prefs = loaded
        except (OSError, json.JSONDecodeError):
            return False
    download = prefs.get("download")
    if not isinstance(download, dict):
        download = {}
    download["default_directory"] = str(paths.downloads.resolve())
    download["prompt_for_download"] = False
    prefs["download"] = download
    temporary = prefs_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(prefs, ensure_ascii=False), encoding="utf-8")
    temporary.replace(prefs_path)
    return True


def normalize_target(target: str) -> str:
    stripped = target.strip()
    match = DOI_RE.match(stripped)
    if match:
        return "https://doi.org/" + urllib.parse.quote(match.group(1), safe="/:")
    parsed = urllib.parse.urlparse(stripped)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Provide an absolute http(s) URL or a DOI.")
    return stripped


def extract_doi(target: str) -> str | None:
    match = DOI_RE.match(target.strip())
    if match:
        return match.group(1).rstrip(".,;")
    parsed = urllib.parse.urlparse(target.strip())
    if parsed.netloc.casefold() in {"doi.org", "dx.doi.org"}:
        return urllib.parse.unquote(parsed.path.lstrip("/")) or None
    return None


def backend_headers(
    contact_email: str | None,
    *,
    accept: str,
    referer: str | None = None,
) -> dict[str, str]:
    suffix = f" (mailto:{contact_email})" if contact_email else ""
    headers = {
        "User-Agent": f"NJUPT-Paper-Access/2.0 academic-research-client{suffix}",
        "Accept": accept,
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
    }
    if referer:
        headers["Referer"] = referer
    return headers


def http_opener() -> urllib.request.OpenerDirector:
    cookies = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))


def resolve_target(
    opener: urllib.request.OpenerDirector,
    target: str,
    contact_email: str | None,
) -> dict[str, Any]:
    url = normalize_target(target)
    request = urllib.request.Request(
        url,
        headers=backend_headers(contact_email, accept="text/html,application/pdf;q=0.9,*/*;q=0.8"),
    )
    with opener.open(request, timeout=45) as response:
        content_type = response.headers.get_content_type()
        body = b""
        if content_type in {"text/html", "application/xhtml+xml"}:
            body = response.read(2 * 1024 * 1024)
        return {
            "requested_url": url,
            "final_url": response.geturl(),
            "status": getattr(response, "status", 200),
            "content_type": content_type,
            "body": body,
        }


def platform_name(final_url: str) -> str:
    host = urllib.parse.urlparse(final_url).netloc.casefold()
    if "ieeexplore.ieee.org" in host:
        return "IEEE Xplore"
    if "sciencedirect.com" in host or "linkinghub.elsevier.com" in host:
        return "Elsevier"
    if "springer.com" in host:
        return "Springer Nature"
    if "dl.acm.org" in host:
        return "ACM Digital Library"
    if "onlinelibrary.wiley.com" in host:
        return "Wiley Online Library"
    if "tandfonline.com" in host:
        return "Taylor & Francis"
    if "sagepub.com" in host or "sage.cnpereading.com" in host:
        return "SAGE Journals"
    if "nature.com" in host:
        return "Nature"
    if "iopscience.iop.org" in host:
        return "IOP"
    if "science.org" in host or "sciencemag.org" in host:
        return "Science"
    if "cnki.net" in host:
        return "CNKI"
    if "wanfangdata.com.cn" in host:
        return "Wanfang"
    return host or "unknown"


def html_meta_pdf_urls(body: bytes, final_url: str) -> list[str]:
    text = body.decode("utf-8", errors="replace")
    urls: list[str] = []
    for match in PDF_META_RE.finditer(text):
        candidate = urllib.parse.urljoin(final_url, match.group(1).replace("&amp;", "&"))
        if candidate not in urls:
            urls.append(candidate)
    return urls


def is_preprint_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.casefold()
    return (
        "arxiv.org" in host
        or "biorxiv.org" in host
        or "medrxiv.org" in host
        or parsed.path.casefold().startswith("/10.48550/")
    )


def direct_pdf_candidates(
    record: dict[str, Any],
    resolved: dict[str, Any],
    *,
    allow_institutional_direct: bool,
) -> list[tuple[str, str, dict[str, str]]]:
    doi = clean_doi(record.get("doi")) or extract_doi(str(record.get("url") or ""))
    final_url = str(resolved.get("final_url") or record.get("url") or "")
    platform = platform_name(final_url)
    candidates: list[tuple[str, str, dict[str, str]]] = []
    api_headers: dict[str, str] = {}

    open_access_url = str(record.get("open_access_url") or "")
    if open_access_url and not is_preprint_url(open_access_url):
        candidates.append((open_access_url, "OpenAlex OA URL", {}))
    if final_url.casefold().endswith(".pdf") or resolved.get("content_type") == "application/pdf":
        candidates.append((final_url, "resolved PDF", {}))

    allow_publisher_direct = allow_institutional_direct or record.get("open_access") is True
    if platform == "IEEE Xplore" and allow_publisher_direct:
        match = re.search(r"/document/(\d+)", final_url)
        if match:
            candidates.append(
                (
                    "https://ieeexplore.ieee.org/stampPDF/getPDF.jsp"
                    f"?tp=&arnumber={match.group(1)}",
                    "IEEE stamp PDF endpoint",
                    {},
                )
            )
    elif platform == "Elsevier":
        api_key = os.environ.get("ELSEVIER_API_KEY")
        if api_key and doi:
            api_headers = {"X-ELS-APIKey": api_key, "Accept": "application/pdf"}
            inst_token = os.environ.get("ELSEVIER_INST_TOKEN")
            if inst_token:
                api_headers["X-ELS-Insttoken"] = inst_token
            candidates.append(
                (
                    "https://api.elsevier.com/content/article/doi/"
                    + urllib.parse.quote(doi, safe="/:"),
                    "Elsevier official Article Retrieval API",
                    api_headers,
                )
            )
        pii_match = re.search(r"/pii/([A-Z0-9]+)", final_url, flags=re.I)
        if pii_match and allow_publisher_direct:
            candidates.append(
                (
                    "https://www.sciencedirect.com/science/article/pii/"
                    f"{pii_match.group(1)}/pdfft?isDTMRedir=true&download=true",
                    "ScienceDirect pdfft endpoint",
                    {},
                )
            )
    elif platform == "Springer Nature" and doi and allow_publisher_direct:
        candidates.append(
            (
                "https://link.springer.com/content/pdf/"
                + urllib.parse.quote(doi, safe="/:")
                + ".pdf",
                "Springer content/pdf endpoint",
                {},
            )
        )
    elif platform == "ACM Digital Library" and doi and allow_publisher_direct:
        candidates.append(
            (
                "https://dl.acm.org/doi/pdf/"
                + urllib.parse.quote(doi, safe="/:")
                + "?download=true",
                "ACM doi/pdf endpoint",
                {},
            )
        )
    elif platform == "Wiley Online Library" and doi:
        token = os.environ.get("WILEY_TDM_TOKEN")
        if token:
            api_headers = {"Wiley-TDM-Client-Token": token, "Accept": "application/pdf"}
            candidates.append(
                (
                    "https://api.wiley.com/onlinelibrary/tdm/v1/articles/"
                    + urllib.parse.quote(doi, safe="/:"),
                    "Wiley official TDM API",
                    api_headers,
                )
            )
        if allow_publisher_direct:
            candidates.append(
                (
                    "https://onlinelibrary.wiley.com/doi/pdfdirect/"
                    + urllib.parse.quote(doi, safe="/:")
                    + "?download=true",
                    "Wiley pdfdirect endpoint",
                    {},
                )
            )
    elif platform == "Taylor & Francis" and doi and allow_publisher_direct:
        candidates.append(
            (
                "https://www.tandfonline.com/doi/pdf/"
                + urllib.parse.quote(doi, safe="/:")
                + "?download=true",
                "Taylor & Francis doi/pdf endpoint",
                {},
            )
        )
    elif platform == "SAGE Journals" and doi and allow_publisher_direct:
        candidates.append(
            (
                "https://journals.sagepub.com/doi/pdf/"
                + urllib.parse.quote(doi, safe="/:")
                + "?download=true",
                "SAGE doi/pdf endpoint",
                {},
            )
        )
    elif platform == "Nature" and allow_publisher_direct:
        candidates.append(
            (
                final_url.rstrip("/") + ".pdf",
                "Nature article PDF endpoint",
                {},
            )
        )
    elif platform == "IOP" and doi and allow_publisher_direct:
        candidates.append(
            (
                "https://iopscience.iop.org/article/" + urllib.parse.quote(doi, safe="/:") + "/pdf",
                "IOPscience article PDF endpoint",
                {},
            )
        )

    if allow_publisher_direct:
        for meta_url in html_meta_pdf_urls(resolved.get("body", b""), final_url):
            candidates.append((meta_url, "citation_pdf_url metadata", {}))

    deduplicated: list[tuple[str, str, dict[str, str]]] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate[0] not in seen:
            seen.add(candidate[0])
            deduplicated.append(candidate)
    return deduplicated


def filename_from_response(response: Any, fallback: str) -> str:
    disposition = response.headers.get("Content-Disposition")
    if disposition:
        message = Message()
        message["Content-Disposition"] = disposition
        filename = message.get_filename()
        if filename:
            return Path(filename).name
    return fallback


def safe_pdf_filename(title: str | None, doi: str | None, fallback: str) -> str:
    stem = (title or doi or fallback).strip()
    stem = UNSAFE_FILENAME_RE.sub("-", stem)
    stem = re.sub(r"\s+", " ", stem).strip(" .-")[:120] or "paper"
    digest = hashlib.sha256((doi or fallback).encode()).hexdigest()[:10]
    return f"{stem}-{digest}.pdf"


def download_pdf_candidate(
    opener: urllib.request.OpenerDirector,
    url: str,
    destination: Path,
    *,
    referer: str | None,
    extra_headers: dict[str, str],
    contact_email: str | None,
) -> dict[str, Any]:
    headers = backend_headers(
        contact_email,
        accept="application/pdf,*/*;q=0.8",
        referer=referer,
    )
    headers.update(extra_headers)
    request = urllib.request.Request(url, headers=headers)
    max_bytes = int(os.environ.get("NJUPT_PAPER_MAX_PDF_BYTES", str(DEFAULT_MAX_PDF_BYTES)))
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + f".part-{os.getpid()}")
    try:
        with opener.open(request, timeout=120) as response:
            content_type = response.headers.get_content_type()
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > max_bytes:
                raise ValueError(f"PDF exceeds the {max_bytes}-byte limit")
            prefix = response.read(5)
            if prefix != b"%PDF-":
                sample = (prefix + response.read(8_192)).decode("latin1", errors="replace")
                return {
                    "ok": False,
                    "error": f"HTTP {getattr(response, 'status', 200)} returned "
                    f"{content_type}, not a PDF",
                    "sample": sample[:500],
                }
            total = len(prefix)
            with temporary.open("wb") as handle:
                handle.write(prefix)
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError(f"PDF exceeds the {max_bytes}-byte limit")
                    handle.write(chunk)
            temporary.replace(destination)
            filename = filename_from_response(response, destination.name)
            return {
                "ok": True,
                "saved": str(destination.resolve()),
                "bytes": total,
                "filename": filename,
                "content_type": content_type,
                "final_url": response.geturl(),
            }
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "error": f"HTTP {exc.code} {exc.reason}",
            "sample": exc.read(1_024).decode("latin1", errors="replace"),
        }
    except (OSError, ValueError, urllib.error.URLError) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        if temporary.exists():
            temporary.unlink()


def download_paper(
    opener: urllib.request.OpenerDirector,
    record: dict[str, Any],
    output_dir: Path,
    contact_email: str | None,
    *,
    allow_institutional_direct: bool,
) -> dict[str, Any]:
    target = str(record.get("doi") or record.get("url") or "").strip()
    if not target:
        return {"status": "failed", "error": "record has neither DOI nor URL"}
    result: dict[str, Any] = {
        "title": record.get("title"),
        "doi": clean_doi(record.get("doi")) or extract_doi(target),
        "requested_target": target,
    }
    try:
        resolved = resolve_target(opener, target, contact_email)
    except urllib.error.HTTPError as exc:
        resolved = {
            "requested_url": normalize_target(target),
            "final_url": exc.geturl() or normalize_target(target),
            "status": exc.code,
            "content_type": exc.headers.get_content_type(),
            "body": b"",
        }
    except (OSError, ValueError, urllib.error.URLError) as exc:
        result.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
        return result

    final_url = str(resolved.get("final_url") or "")
    platform = platform_name(final_url)
    doi = result["doi"]
    filename = safe_pdf_filename(
        str(record.get("title") or ""),
        doi if isinstance(doi, str) else None,
        target,
    )
    destination = output_dir / filename
    result.update(
        {
            "platform": platform,
            "landing_url": final_url,
        }
    )
    if destination.exists() and pdf_like(destination):
        result.update(
            {
                "status": "skipped_existing",
                "saved": str(destination.resolve()),
                "bytes": destination.stat().st_size,
            }
        )
        return result

    candidates = direct_pdf_candidates(
        record,
        resolved,
        allow_institutional_direct=allow_institutional_direct,
    )
    if not candidates:
        result.update(
            {
                "status": "manual_required",
                "error": (
                    "No open-access copy or licensed official TDM endpoint is available. "
                    "NJUPT library policy prohibits automated continuous downloading of "
                    "subscribed databases; open the publisher page and download this item "
                    "manually."
                ),
            }
        )
        return result
    errors: list[dict[str, Any]] = []
    for url, source, headers in candidates:
        attempt = download_pdf_candidate(
            opener,
            url,
            destination,
            referer=final_url,
            extra_headers=headers,
            contact_email=contact_email,
        )
        if attempt.get("ok"):
            result.update(
                {
                    "status": "downloaded",
                    "source": source,
                    "pdf_url": attempt.get("final_url") or url,
                    "saved": attempt["saved"],
                    "bytes": attempt["bytes"],
                }
            )
            return result
        errors.append({"source": source, "url": url, **attempt})
    result.update(
        {
            "status": "failed",
            "error": "all direct PDF endpoints failed",
            "attempts": errors,
        }
    )
    return result


def launch(paths: Paths, targets: list[str]) -> dict[str, Any]:
    paths.ensure()
    preferences_updated = configure_download_preferences(paths)
    browser = find_browser()
    command = [
        str(browser),
        f"--user-data-dir={paths.profile.resolve()}",
        "--new-window",
        "--no-first-run",
        "--no-default-browser-check",
        *targets,
    ]
    process_options: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        process_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        process_options["start_new_session"] = True
    process = subprocess.Popen(command, **process_options)
    return {
        "status": "browser_launched",
        "browser": str(browser),
        "pid": process.pid,
        "portal": PORTAL,
        "urls": targets,
        "profile": str(paths.profile.resolve()),
        "downloads": str(paths.downloads.resolve()),
        "download_preferences_updated": preferences_updated,
        "next": "Complete NJUPT SSO manually in the browser.",
    }


def request_json(url: str, contact_email: str | None) -> dict[str, Any]:
    headers = {
        "Accept": "application/json",
        "User-Agent": (
            "NJUPT-Paper-Access/1.0" + (f" (mailto:{contact_email})" if contact_email else "")
        ),
    }
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=25) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("API returned a non-object response")
    return payload


def clean_doi(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value.strip(), flags=re.I)
    return doi or None


def openalex_records(query: str, limit: int, email: str | None) -> list[dict[str, Any]]:
    params = {"search": query, "per-page": str(min(limit, 100))}
    if email:
        params["mailto"] = email
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
    payload = request_json(url, email)
    results = payload.get("results")
    records: list[dict[str, Any]] = []
    for item in results if isinstance(results, list) else []:
        if not isinstance(item, dict):
            continue
        location = item.get("primary_location")
        location = location if isinstance(location, dict) else {}
        source = location.get("source")
        source = source if isinstance(source, dict) else {}
        open_access = item.get("open_access")
        open_access = open_access if isinstance(open_access, dict) else {}
        doi = clean_doi(item.get("doi"))
        records.append(
            {
                "title": item.get("display_name") or item.get("title"),
                "doi": doi,
                "year": item.get("publication_year"),
                "venue": source.get("display_name"),
                "url": location.get("landing_page_url")
                or (f"https://doi.org/{doi}" if doi else None),
                "open_access": bool(open_access.get("is_oa")),
                "open_access_url": open_access.get("oa_url"),
                "source": "OpenAlex",
            }
        )
    return records


def crossref_records(query: str, limit: int, email: str | None) -> list[dict[str, Any]]:
    params = {
        "query.bibliographic": query,
        "rows": str(min(limit, 100)),
        "select": "DOI,title,author,container-title,published,URL,type",
    }
    if email:
        params["mailto"] = email
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode(params)
    payload = request_json(url, email)
    message = payload.get("message")
    message = message if isinstance(message, dict) else {}
    items = message.get("items")
    records: list[dict[str, Any]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        doi = clean_doi(item.get("DOI"))
        titles = item.get("title")
        title = titles[0] if isinstance(titles, list) and titles else None
        venues = item.get("container-title")
        venue = venues[0] if isinstance(venues, list) and venues else None
        published = item.get("published")
        date_parts = published.get("date-parts") if isinstance(published, dict) else None
        year = None
        if (
            isinstance(date_parts, list)
            and date_parts
            and isinstance(date_parts[0], list)
            and date_parts[0]
        ):
            year = date_parts[0][0]
        records.append(
            {
                "title": title,
                "doi": doi,
                "year": year,
                "venue": venue,
                "url": item.get("URL") or (f"https://doi.org/{doi}" if doi else None),
                "open_access": None,
                "open_access_url": None,
                "source": "Crossref",
            }
        )
    return records


def merge_records(records: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for record in records:
        key = str(record.get("doi") or record.get("title") or "").casefold().strip()
        if not key:
            continue
        existing = merged.get(key)
        if existing is None:
            merged[key] = record
            continue
        for field, value in record.items():
            if existing.get(field) in (None, "", False) and value not in (None, "", False):
                existing[field] = value
        sources = {existing.get("source"), record.get("source")}
        existing["source"] = "+".join(sorted(str(source) for source in sources if source))
    ordered = sorted(
        merged.values(),
        key=lambda item: (
            not bool(item.get("open_access")),
            -(int(item["year"]) if str(item.get("year") or "").isdigit() else 0),
            str(item.get("title") or "").casefold(),
        ),
    )
    return ordered[:limit]


def discover_records(
    query: str,
    limit: int,
    email: str | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    records: list[dict[str, Any]] = []
    for name, search in (("OpenAlex", openalex_records), ("Crossref", crossref_records)):
        try:
            records.extend(search(query, limit, email))
        except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError) as exc:
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
    return merge_records(records, limit), errors


def enrich_record(record: dict[str, Any], email: str | None) -> dict[str, Any]:
    enriched = dict(record)
    doi = clean_doi(enriched.get("doi")) or extract_doi(str(enriched.get("url") or ""))
    if doi:
        enriched["doi"] = doi
    if not doi or enriched.get("open_access") is not None:
        return enriched
    params = {"filter": f"doi:{doi}", "per-page": "1"}
    if email:
        params["mailto"] = email
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
    try:
        payload = request_json(url, email)
    except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError):
        return enriched
    results = payload.get("results")
    if not isinstance(results, list) or not results or not isinstance(results[0], dict):
        return enriched
    item = results[0]
    open_access = item.get("open_access")
    open_access = open_access if isinstance(open_access, dict) else {}
    location = item.get("primary_location")
    location = location if isinstance(location, dict) else {}
    source = location.get("source")
    source = source if isinstance(source, dict) else {}
    enriched.setdefault("title", item.get("display_name"))
    enriched.setdefault("year", item.get("publication_year"))
    enriched.setdefault("venue", source.get("display_name"))
    enriched["open_access"] = bool(open_access.get("is_oa"))
    enriched["open_access_url"] = open_access.get("oa_url")
    return enriched


def collect(query: str, limit: int, output: str | None, email: str | None) -> int:
    results, errors = discover_records(query, limit, email)
    payload = {
        "query": query,
        "count": len(results),
        "results": results,
        "errors": errors,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if output:
        target = Path(output).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + "\n", encoding="utf-8")
        print(
            json.dumps({"status": "written", "path": str(target.resolve()), "count": len(results)})
        )
    else:
        print(text)
    return 0 if results else 1


def load_batch_records(path: Path) -> list[dict[str, Any]]:
    if path.suffix.casefold() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        items = payload.get("results") if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise ValueError("JSON input must be a list or an object with a results list")
        return [
            item if isinstance(item, dict) else {"doi": str(item)}
            for item in items
            if isinstance(item, (dict, str))
        ]
    if path.suffix.casefold() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        return [
            {
                "title": row.get("title") or row.get("题名") or "",
                "doi": row.get("doi") or row.get("DOI") or "",
                "url": row.get("url") or row.get("URL") or "",
            }
            for row in rows
            if row.get("doi") or row.get("DOI") or row.get("url") or row.get("URL")
        ]
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        if value.casefold() == "doi" or value.casefold().startswith("doi,"):
            continue
        if "," in value and value.casefold().startswith(("http", "10.")):
            value = value.split(",", 1)[0].strip()
        try:
            normalized = normalize_target(value)
        except ValueError as exc:
            raise ValueError(f"line {line_number}: {exc}") from exc
        records.append({"doi": extract_doi(normalized), "url": normalized})
    return records


def batch_download(
    records: list[dict[str, Any]],
    output_dir: Path,
    *,
    contact_email: str | None,
    rate_limit: float,
    max_items: int,
) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    opener = http_opener()
    results: list[dict[str, Any]] = []
    limited = records[:max_items]
    for index, record in enumerate(limited, start=1):
        if index > 1:
            time.sleep(rate_limit)
        enriched = enrich_record(record, contact_email)
        result = download_paper(
            opener,
            enriched,
            output_dir,
            contact_email,
            allow_institutional_direct=False,
        )
        result["index"] = index
        results.append(result)
        manifest_path.write_text(
            json.dumps(
                {
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "total_requested": len(records),
                    "processed": len(results),
                    "results": results,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "index": index,
                    "total": len(limited),
                    "status": result.get("status"),
                    "doi": result.get("doi"),
                    "platform": result.get("platform"),
                    "saved": result.get("saved"),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    succeeded = sum(
        result.get("status") in {"downloaded", "skipped_existing"} for result in results
    )
    print(
        json.dumps(
            {
                "status": "complete" if succeeded == len(results) else "partial",
                "downloaded": succeeded,
                "attempted": len(results),
                "manifest": str(manifest_path.resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 0 if results and succeeded == len(results) else 1


def pdf_like(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(5) == b"%PDF-"
    except OSError:
        return False


def same_file_content(left: Path, right: Path) -> bool:
    if left.stat().st_size != right.stat().st_size:
        return False
    left_hash = hashlib.sha256(left.read_bytes()).digest()
    right_hash = hashlib.sha256(right.read_bytes()).digest()
    return left_hash == right_hash


def watch(paths: Paths, output: Path, timeout: int) -> int:
    paths.ensure()
    output.mkdir(parents=True, exist_ok=True)
    started_wall = time.time()
    started = time.monotonic()
    observations: dict[Path, tuple[int, int, int]] = {}
    collected: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    while time.monotonic() - started <= timeout:
        candidates = [
            path
            for path in paths.downloads.iterdir()
            if path.is_file()
            and path.suffix.casefold() == ".pdf"
            and not path.name.endswith(".crdownload")
            and path.stat().st_mtime >= started_wall - 5
        ]
        for path in candidates:
            stat = path.stat()
            previous = observations.get(path)
            stable_count = 1
            if previous and previous[:2] == (stat.st_size, stat.st_mtime_ns):
                stable_count = previous[2] + 1
            observations[path] = (stat.st_size, stat.st_mtime_ns, stable_count)
            if stable_count < 2:
                continue
            if not pdf_like(path):
                rejected.append({"path": str(path.resolve()), "reason": "not a PDF"})
                observations.pop(path, None)
                continue
            safe_name = SAFE_NAME_RE.sub("-", path.name).strip(".-") or "paper.pdf"
            if not safe_name.casefold().endswith(".pdf"):
                safe_name += ".pdf"
            destination = output / safe_name
            if destination.exists():
                if same_file_content(path, destination):
                    observations.pop(path, None)
                    continue
                destination = output / f"{path.stem}-{int(time.time())}.pdf"
            shutil.copy2(path, destination)
            collected.append(
                {
                    "source": str(path.resolve()),
                    "saved": str(destination.resolve()),
                    "bytes": destination.stat().st_size,
                }
            )
            observations.pop(path, None)
        if collected:
            break
        time.sleep(2)
    print(
        json.dumps(
            {
                "status": "collected" if collected else "timeout",
                "downloads": str(paths.downloads.resolve()),
                "output": str(output.resolve()),
                "collected": collected,
                "rejected": rejected,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if collected else 2


def doctor(paths: Paths) -> int:
    browser = browser_candidates()
    report = {
        "status": "ok" if browser else "missing_browser",
        "portal": PORTAL,
        "bridge": bridge_available(),
        "browser": str(browser[0]) if browser else None,
        "profile": str(paths.profile.resolve()),
        "downloads": str(paths.downloads.resolve()),
        "collections": str(paths.collections.resolve()),
        "credential_free": True,
        "backend_tokens": {
            "elsevier_api_key": bool(os.environ.get("ELSEVIER_API_KEY")),
            "elsevier_inst_token": bool(os.environ.get("ELSEVIER_INST_TOKEN")),
            "wiley_tdm_token": bool(os.environ.get("WILEY_TDM_TOKEN")),
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if browser and report["bridge"].get("dns") else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Find, open, and collect NJUPT-authorized scholarly papers."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="Check browser, paths, and WebVPN reachability.")
    subparsers.add_parser("paths", help="Print private data paths.")

    login = subparsers.add_parser("login", help="Open the NJUPT WebVPN login.")
    login.add_argument("--json", action="store_true", help="Print JSON status.")

    open_parser = subparsers.add_parser("open", help="Open a DOI or publisher URL.")
    open_parser.add_argument("target", help="DOI or absolute publisher URL.")
    open_parser.add_argument("--login", action="store_true", help="Open WebVPN too.")

    collect_parser = subparsers.add_parser("collect", help="Search public metadata APIs.")
    collect_parser.add_argument("query")
    collect_parser.add_argument("--limit", type=int, default=20)
    collect_parser.add_argument("--output")

    resolve_parser = subparsers.add_parser("resolve", help="Normalize a DOI or URL.")
    resolve_parser.add_argument("target")

    download_parser = subparsers.add_parser(
        "download",
        help="Download one DOI or publisher URL by direct backend request.",
    )
    download_parser.add_argument("target")
    download_parser.add_argument("--output-dir")

    batch_parser = subparsers.add_parser(
        "batch",
        help="Download a DOI list, collect JSON/CSV, or public-search result batch.",
    )
    batch_parser.add_argument("--input", help="TXT, CSV, or collect JSON input.")
    batch_parser.add_argument(
        "--doi",
        action="append",
        default=[],
        help="DOI or publisher URL; repeat for multiple records.",
    )
    batch_parser.add_argument("--query", help="Discover metadata publicly, then download.")
    batch_parser.add_argument("--limit", type=int, default=20)
    batch_parser.add_argument("--output-dir")
    batch_parser.add_argument("--rate-limit", type=float, default=5.0)
    batch_parser.add_argument("--max-items", type=int, default=100)

    watch_parser = subparsers.add_parser("watch", help="Collect a completed PDF download.")
    watch_parser.add_argument("--output", required=True)
    watch_parser.add_argument("--timeout", type=int, default=600)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    paths = Paths()
    try:
        if args.command == "doctor":
            return doctor(paths)
        if args.command == "paths":
            paths.ensure()
            print(
                json.dumps(
                    {
                        "home": str(paths.home.resolve()),
                        "profile": str(paths.profile.resolve()),
                        "downloads": str(paths.downloads.resolve()),
                    },
                    indent=2,
                )
            )
            return 0
        if args.command == "login":
            result = launch(paths, [PORTAL])
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "open":
            target = normalize_target(args.target)
            urls = [PORTAL, target] if args.login else [target]
            result = launch(paths, urls)
            result["target"] = target
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "resolve":
            print(json.dumps({"target": normalize_target(args.target)}, indent=2))
            return 0
        if args.command == "download":
            output_dir = (
                Path(args.output_dir).expanduser() if args.output_dir else paths.collections
            )
            output_dir.mkdir(parents=True, exist_ok=True)
            email = os.environ.get("NJUPT_PAPER_CONTACT_EMAIL")
            result = download_paper(
                http_opener(),
                {"doi": extract_doi(args.target), "url": normalize_target(args.target)},
                output_dir,
                email,
                allow_institutional_direct=True,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result.get("status") in {"downloaded", "skipped_existing"} else 1
        if args.command == "batch":
            if args.limit < 1 or args.limit > 100:
                raise ValueError("--limit must be between 1 and 100")
            if args.rate_limit < 2 or args.rate_limit > 60:
                raise ValueError("--rate-limit must be between 2 and 60 seconds")
            if args.max_items < 1 or args.max_items > 1_000:
                raise ValueError("--max-items must be between 1 and 1000")
            email = os.environ.get("NJUPT_PAPER_CONTACT_EMAIL")
            records: list[dict[str, Any]] = []
            if args.input:
                records.extend(load_batch_records(Path(args.input).expanduser()))
            for target in args.doi:
                records.append({"doi": extract_doi(target), "url": normalize_target(target)})
            if args.query:
                discovered, errors = discover_records(args.query, args.limit, email)
                if errors:
                    print(json.dumps({"discovery_errors": errors}, ensure_ascii=False))
                records.extend(discovered)
            if not records:
                raise ValueError("Provide --input, --doi, or --query")
            output_dir = (
                Path(args.output_dir).expanduser()
                if args.output_dir
                else paths.collections / datetime.now().strftime("batch-%Y%m%d-%H%M%S")
            )
            return batch_download(
                records,
                output_dir,
                contact_email=email,
                rate_limit=args.rate_limit,
                max_items=args.max_items,
            )
        if args.command == "collect":
            if args.limit < 1 or args.limit > 100:
                raise ValueError("--limit must be between 1 and 100")
            email = os.environ.get("NJUPT_PAPER_CONTACT_EMAIL")
            return collect(args.query, args.limit, args.output, email)
        if args.command == "watch":
            if args.timeout < 5 or args.timeout > 3600:
                raise ValueError("--timeout must be between 5 and 3600 seconds")
            return watch(paths, Path(args.output).expanduser(), args.timeout)
    except (OSError, RuntimeError, ValueError, urllib.error.URLError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
