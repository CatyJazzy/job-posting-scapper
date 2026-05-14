#!/usr/bin/env python3
"""Download recruiting notice images/PDFs from supported sites.

Supported sites:
- Jobda: https://www.jobda.im/position
- Inthiswork: https://inthiswork.com/entry and category pages

The script intentionally uses only the Python standard library so it can be
shared as a small folder without dependency installation.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import html
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


JOBDA_LIST_URL = "https://api.jobda.im/position?page={page}&size={size}"
JOBDA_DETAIL_URL = "https://api.jobda.im/v2/position/{position_sn}"
JOBDA_DEFAULT_URL = "https://www.jobda.im/position"
INTHISWORK_DEFAULT_URL = "https://inthiswork.com/entry"

ASSET_EXT_RE = re.compile(r"\.(?:avif|bmp|gif|jpe?g|pdf|png|svg|webp)(?:[?#].*)?$", re.I)
IMAGE_EXT_RE = re.compile(r"\.(?:avif|bmp|gif|jpe?g|png|svg|webp)(?:[?#].*)?$", re.I)
PDF_EXT_RE = re.compile(r"\.pdf(?:[?#].*)?$", re.I)
BAD_URL_RE = re.compile(
    r"(favicon|apple-touch-icon|wp-smiley|/emoji/|/fusion-gfonts/|"
    r"\.woff2?|\.ttf|\.otf|googletagmanager|google-analytics|"
    r"facebook|naver|kakao|beusable|analytics|pixel)",
    re.I,
)


@dataclass
class Asset:
    site: str
    source_page_url: str
    posting_url: str
    posting_title: str
    asset_url: str
    asset_kind: str
    asset_source: str
    filename: str = ""
    save_status: str = "pending"
    save_path: str = ""
    error: str = ""


@dataclass
class Posting:
    site: str
    posting_id: str
    title: str
    url: str


def now_run_id() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def safe_title(value: str, default: str = "untitled", max_len: int = 80) -> str:
    text = html.unescape(value or "").strip()
    text = re.sub(r"\s+", " ", text)[:max_len]
    text = re.sub(r'[\\/:*?"<>|#%{}~&]+', "_", text)
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or default


def normalize_url(url: str, base_url: str = "") -> str:
    if not url:
        return ""
    value = html.unescape(url).strip().strip("'\"")
    if not value or value.startswith(("data:", "javascript:", "mailto:", "tel:")):
        return ""
    if value.startswith("//"):
        value = "https:" + value
    return urllib.parse.urljoin(base_url, value)


def dedupe_assets(assets: Iterable[Asset]) -> List[Asset]:
    seen = set()
    result: List[Asset] = []
    for asset in assets:
        clean = normalize_url(asset.asset_url)
        if not clean:
            continue
        parsed = urllib.parse.urlsplit(clean)
        key = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))
        if key in seen:
            continue
        seen.add(key)
        asset.asset_url = clean
        result.append(asset)
    return result


def asset_kind(url: str) -> str:
    if PDF_EXT_RE.search(url):
        return "pdf"
    if IMAGE_EXT_RE.search(url):
        return "image"
    return "unknown"


def extension_from_url(url: str, kind: str) -> str:
    path = urllib.parse.urlsplit(url).path
    match = re.search(r"\.([a-z0-9]{2,5})$", path, re.I)
    if match:
        return match.group(1).lower()
    return "pdf" if kind == "pdf" else "jpg"


def make_filename(site: str, run_id: str, index: int, title: str, url: str, kind: str) -> str:
    return f"{safe_title(site)}_{run_id}_{index + 1:03d}_{safe_title(title)}.{extension_from_url(url, kind)}"


def request_headers(referer: str = "") -> Dict[str, str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    if referer:
        headers["Referer"] = referer
    return headers


def fetch_bytes(url: str, referer: str = "", timeout: int = 25) -> bytes:
    request = urllib.request.Request(url, headers=request_headers(referer))
    context = ssl.create_default_context()
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        return response.read()


def fetch_text(url: str, referer: str = "", timeout: int = 25) -> str:
    data = fetch_bytes(url, referer=referer, timeout=timeout)
    return data.decode("utf-8", errors="replace")


def fetch_json(url: str, referer: str = "", timeout: int = 25) -> object:
    return json.loads(fetch_text(url, referer=referer, timeout=timeout))


def describe_exception(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        try:
            body = exc.read().decode("utf-8", errors="replace").strip()
        except Exception:  # noqa: BLE001
            body = ""
        return f"HTTP Error {exc.code}: {body[:500]}"
    return str(exc)


def is_downloadable_asset(url: str) -> bool:
    if not url or BAD_URL_RE.search(url):
        return False
    return bool(ASSET_EXT_RE.search(url))


def push_asset(
    assets: List[Asset],
    site: str,
    source_page_url: str,
    posting_url: str,
    posting_title: str,
    asset_url_value: str,
    asset_source: str,
) -> None:
    url = normalize_url(asset_url_value, source_page_url)
    if not is_downloadable_asset(url):
        return
    assets.append(
        Asset(
            site=site,
            source_page_url=source_page_url,
            posting_url=posting_url or source_page_url,
            posting_title=posting_title or "untitled",
            asset_url=url,
            asset_kind=asset_kind(url),
            asset_source=asset_source,
        )
    )


def jobda_position_id(url: str) -> str:
    match = re.search(r"jobda\.im/position/([^/?#]+)", url)
    return urllib.parse.unquote(match.group(1)) if match else ""


def fetch_jobda_positions(limit: int, referer: str) -> Tuple[List[Dict[str, object]], List[Dict[str, str]]]:
    positions: List[Dict[str, object]] = []
    errors: List[Dict[str, str]] = []
    remaining = max(1, limit)
    page = 0
    page_size = min(20, remaining)

    while remaining > 0:
        size = min(page_size, remaining)
        list_url = JOBDA_LIST_URL.format(page=page, size=size)
        print(f"[jobda] 목록 API를 조회합니다: {list_url}", flush=True)
        try:
            payload = fetch_json(list_url, referer=referer)
        except Exception as exc:  # noqa: BLE001
            if size > 10:
                errors.append({"phase": "jobda.list.retry", "message": f"{describe_exception(exc)}; size=10으로 재시도합니다."})
                page_size = 10
                continue
            errors.append({"phase": "jobda.list", "message": describe_exception(exc)})
            break

        page_positions = payload.get("positions", []) if isinstance(payload, dict) else []
        if not page_positions:
            break
        positions.extend([item for item in page_positions if isinstance(item, dict)])
        if len(page_positions) < size:
            break
        remaining = limit - len(positions)
        page += 1

    return positions[:limit], errors


def collect_jobda(limit: int, source_page_url: str = JOBDA_DEFAULT_URL) -> Tuple[List[Posting], List[Asset], List[Dict[str, str]]]:
    site = "jobda"
    source_page_url = source_page_url or JOBDA_DEFAULT_URL
    postings: List[Posting] = []
    assets: List[Asset] = []
    errors: List[Dict[str, str]] = []

    single_position_id = jobda_position_id(source_page_url)
    if single_position_id:
        print(f"[jobda] 상세 공고 1개를 수집합니다: {source_page_url}", flush=True)
        postings.append(
            Posting(
                site=site,
                posting_id=single_position_id,
                title=f"position_{single_position_id}",
                url=source_page_url,
            )
        )
    else:
        positions, list_errors = fetch_jobda_positions(limit, source_page_url)
        errors.extend(list_errors)
        for position in positions[:limit]:
            position_sn = str(position.get("positionSn") or "")
            if not position_sn:
                continue
            title = (
                position.get("positionName")
                or position.get("positionTitle")
                or position.get("companyName")
                or f"position_{position_sn}"
            )
            posting_url = f"https://www.jobda.im/position/{position_sn}/jd"
            postings.append(Posting(site=site, posting_id=position_sn, title=str(title), url=posting_url))

    print(f"[jobda] 상세 API {len(postings)}개를 조회합니다.", flush=True)
    for index, posting in enumerate(postings, start=1):
        print(f"[jobda] 상세 조회 {index}/{len(postings)}: {posting.url}", flush=True)
        detail_url = JOBDA_DETAIL_URL.format(position_sn=urllib.parse.quote(posting.posting_id))
        try:
            detail = fetch_json(detail_url, referer=posting.url)
        except Exception as exc:  # noqa: BLE001
            errors.append({"phase": "jobda.detail", "postingUrl": posting.url, "message": describe_exception(exc)})
            continue
        if not isinstance(detail, dict):
            continue
        basic = detail.get("basicInfo") if isinstance(detail.get("basicInfo"), dict) else {}
        company = detail.get("companyInfo") if isinstance(detail.get("companyInfo"), dict) else {}
        detail_title = basic.get("positionName") or basic.get("positionTitle") or company.get("companyName")
        if detail_title:
            posting.title = str(detail_title)

        posting_assets: List[Asset] = []
        job_description = basic.get("jobDescription")
        if isinstance(job_description, str) and job_description.strip():
            posting_assets.extend(
                collect_assets_from_html(
                    job_description,
                    posting.url,
                    site,
                    posting.url,
                    posting.title,
                    "jobda.basicInfo.jobDescription",
                )
            )

        if not posting_assets and basic.get("jobDescriptionImageUrl"):
            push_asset(
                posting_assets,
                site,
                source_page_url,
                posting.url,
                posting.title,
                str(basic["jobDescriptionImageUrl"]),
                "jobda.basicInfo.jobDescriptionImageUrl",
            )

        if not posting_assets:
            errors.append(
                {
                    "phase": "jobda.detail.empty",
                    "postingUrl": posting.url,
                    "message": "공고 본문 이미지/PDF를 찾지 못해 보조 이미지, 썸네일, 로고는 저장하지 않음",
                }
            )

        assets.extend(posting_assets)

    return postings, dedupe_assets(assets), errors


def extract_attr(tag: str, attr: str) -> str:
    pattern = re.compile(rf"""{re.escape(attr)}\s*=\s*(['"])(.*?)\1""", re.I | re.S)
    match = pattern.search(tag)
    return html.unescape(match.group(2)) if match else ""


def best_srcset(srcset: str, base_url: str) -> str:
    if not srcset:
        return ""
    parts = [part.strip().split()[0] for part in srcset.split(",") if part.strip()]
    return normalize_url(parts[-1], base_url) if parts else ""


def collect_assets_from_html(
    page_html: str,
    page_url: str,
    site: str,
    posting_url: str,
    posting_title: str,
    source_prefix: str,
) -> List[Asset]:
    assets: List[Asset] = []
    for tag in re.findall(r"<img\b[^>]*>", page_html, flags=re.I | re.S):
        chosen_attr = ""
        chosen_url = ""
        for attr in ("data-orig-file", "data-large-file"):
            value = extract_attr(tag, attr)
            if value:
                chosen_attr = attr
                chosen_url = value
                break
        if not chosen_url:
            srcset_url = best_srcset(extract_attr(tag, "srcset"), page_url)
            if srcset_url:
                chosen_attr = "srcset"
                chosen_url = srcset_url
        if not chosen_url:
            chosen_attr = "src"
            chosen_url = extract_attr(tag, "src")
        if chosen_url:
            push_asset(assets, site, page_url, posting_url, posting_title, chosen_url, f"{source_prefix}.img.{chosen_attr}")

    for tag in re.findall(r"<a\b[^>]*>", page_html, flags=re.I | re.S):
        href = extract_attr(tag, "href")
        if href:
            push_asset(assets, site, page_url, posting_url, posting_title, href, f"{source_prefix}.a.href")

    for match in re.findall(r"url\((['\"]?)(.*?)\1\)", page_html, flags=re.I | re.S):
        push_asset(assets, site, page_url, posting_url, posting_title, match[1], f"{source_prefix}.css.background")

    return dedupe_assets(assets)


def image_dimensions(data: bytes) -> Tuple[int, int]:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
        return int.from_bytes(data[6:8], "little"), int.from_bytes(data[8:10], "little")
    if data.startswith(b"\xff\xd8"):
        index = 2
        while index + 9 < len(data):
            if data[index] != 0xFF:
                index += 1
                continue
            marker = data[index + 1]
            index += 2
            if marker in (0xD8, 0xD9):
                continue
            if index + 2 > len(data):
                break
            segment_length = int.from_bytes(data[index:index + 2], "big")
            if segment_length < 2:
                break
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                if index + 7 <= len(data):
                    height = int.from_bytes(data[index + 3:index + 5], "big")
                    width = int.from_bytes(data[index + 5:index + 7], "big")
                    return width, height
                break
            index += segment_length
    if data.startswith(b"RIFF") and len(data) >= 30 and data[8:12] == b"WEBP":
        if data[12:16] == b"VP8X" and len(data) >= 30:
            width = int.from_bytes(data[24:27], "little") + 1
            height = int.from_bytes(data[27:30], "little") + 1
            return width, height
    return 0, 0


def should_skip_image(asset: Asset, data: bytes) -> str:
    if asset.asset_kind != "image":
        return ""
    width, height = image_dimensions(data)
    if not width or not height:
        return ""
    if width <= 300 and height <= 160:
        return f"작은 로고/아이콘으로 판단해 저장하지 않음 ({width}x{height})"
    if asset.site == "inthiswork" and asset.asset_source.startswith("inthiswork.detail"):
        if width * height < 350_000:
            return f"인디스워크 본문 내 작은 보조 이미지로 판단해 저장하지 않음 ({width}x{height})"
    return ""


def parse_inthiswork_cards(page_html: str, page_url: str) -> List[Dict[str, str]]:
    cards: List[Dict[str, str]] = []
    entry_starts = [
        match.start()
        for match in re.finditer(
            r"<div\b[^>]*class=(['\"])[^'\"]*\bdpt-entry(?:\s|['\"])",
            page_html,
            flags=re.I,
        )
    ]
    for idx, start in enumerate(entry_starts):
        end = entry_starts[idx + 1] if idx + 1 < len(entry_starts) else len(page_html)
        entry = page_html[start:end]
        open_tag = entry.split(">", 1)[0] + ">"
        title = extract_attr(open_tag, "data-title")
        post_id = extract_attr(open_tag, "data-id")
        href_match = re.search(r"<a\b[^>]*href=(['\"])(.*?)\1[^>]*class=(['\"])[^'\"]*(?:dpt-title-link|dpt-permalink)[^'\"]*\3", entry, flags=re.I | re.S)
        if not href_match:
            href_match = re.search(r"<a\b[^>]*class=(['\"])[^'\"]*(?:dpt-title-link|dpt-permalink)[^'\"]*\1[^>]*href=(['\"])(.*?)\2", entry, flags=re.I | re.S)
            href = href_match.group(3) if href_match else ""
        else:
            href = href_match.group(2)
        url = normalize_url(href, page_url)
        cards.append({"id": post_id, "title": title or post_id or "inthiswork-post", "url": url, "html": entry})
    return cards


def inthiswork_archive_id(url: str) -> str:
    match = re.search(r"^https://inthiswork\.com/archives/(\d+)/?$", url.split("#")[0])
    return match.group(1) if match else ""


def extract_inthiswork_post_scope(page_html: str, post_id: str) -> str:
    start = -1
    if post_id:
        start = page_html.find(f'id="post-{post_id}"')
    if start < 0:
        start = page_html.find('class="post-content"')
    if start < 0:
        return page_html

    content_start = page_html.find('class="post-content"', start)
    if content_start >= 0:
        start = content_start

    end_markers = [
        '<div class="fusion-meta-tb',
        '<section id="comments"',
        '<div id="comments"',
        '<footer',
    ]
    ends = [page_html.find(marker, start) for marker in end_markers]
    ends = [end for end in ends if end > start]
    end = min(ends) if ends else min(len(page_html), start + 300_000)
    return page_html[start:end]


def collect_inthiswork_detail_assets(
    detail_html: str,
    detail_url: str,
    title: str,
    post_id: str,
) -> List[Asset]:
    site = "inthiswork"
    scope = extract_inthiswork_post_scope(detail_html, post_id)
    figure_chunks = re.findall(
        r"<figure\b(?=[^>]*class=(?:['\"])[^'\"]*\bwp-block-image\b[^'\"]*(?:['\"]))[^>]*>.*?</figure>",
        scope,
        flags=re.I | re.S,
    )

    assets: List[Asset] = []
    for figure in figure_chunks:
        assets.extend(
            collect_assets_from_html(
                figure,
                detail_url,
                site,
                detail_url,
                title,
                "inthiswork.detail.figure",
            )
        )

    if assets:
        return dedupe_assets(assets)

    fallback_chunks = []
    for tag in re.findall(r"<img\b[^>]*>", scope, flags=re.I | re.S):
        tag_class = extract_attr(tag, "class")
        if "wp-image-" in tag_class and "wp-post-image" not in tag_class:
            fallback_chunks.append(tag)
    for tag in fallback_chunks[:5]:
        assets.extend(
            collect_assets_from_html(
                tag,
                detail_url,
                site,
                detail_url,
                title,
                "inthiswork.detail.wp-image",
            )
        )
    return dedupe_assets(assets)


def collect_inthiswork(url: str, limit: int, detail_limit: int) -> Tuple[List[Posting], List[Asset], List[Dict[str, str]]]:
    site = "inthiswork"
    page_url = url or INTHISWORK_DEFAULT_URL
    errors: List[Dict[str, str]] = []
    print(f"[inthiswork] 목록 페이지를 조회합니다: {page_url}", flush=True)
    try:
        page_html = fetch_text(page_url)
    except Exception as exc:  # noqa: BLE001
        return [], [], [{"phase": "inthiswork.list", "message": str(exc)}]

    cards = parse_inthiswork_cards(page_html, page_url)[:limit]
    print(f"[inthiswork] 목록 카드 {len(cards)}개를 찾았습니다.", flush=True)
    postings = [
        Posting(site=site, posting_id=card["id"], title=card["title"], url=card["url"])
        for card in cards
    ]

    assets: List[Asset] = []
    archive_cards = []
    for card in cards:
        if inthiswork_archive_id(card["url"]):
            archive_cards.append(card)
        else:
            errors.append(
                {
                    "phase": "inthiswork.skip",
                    "postingUrl": card["url"],
                    "message": "상세 페이지 URL이 /archives/{id} 형식이 아니어서 목록 썸네일을 저장하지 않고 건너뜀",
                }
            )

    detail_count = len(archive_cards) if detail_limit <= 0 else min(len(archive_cards), detail_limit)
    detail_cards = archive_cards[:detail_count]

    print(f"[inthiswork] 상세 페이지 {len(detail_cards)}개를 조회합니다.", flush=True)
    for index, card in enumerate(detail_cards, start=1):
        print(f"[inthiswork] 상세 조회 {index}/{len(detail_cards)}: {card['url']}", flush=True)
        try:
            detail_html = fetch_text(card["url"], referer=page_url)
        except Exception as exc:  # noqa: BLE001
            errors.append({"phase": "inthiswork.detail", "postingUrl": card["url"], "message": str(exc)})
            continue
        detail_assets = collect_inthiswork_detail_assets(
            detail_html,
            card["url"],
            card["title"],
            inthiswork_archive_id(card["url"]) or card["id"],
        )
        if not detail_assets:
            errors.append({"phase": "inthiswork.detail.empty", "postingUrl": card["url"], "message": "상세 본문 공고 이미지를 찾지 못함"})
        assets.extend(detail_assets)

    return postings, dedupe_assets(assets), errors


def write_asset(asset: Asset, output_dir: Path, retries: int = 2) -> Asset:
    output_path = output_dir / asset.filename
    for attempt in range(retries + 1):
        try:
            data = fetch_bytes(asset.asset_url, referer=asset.posting_url)
            skip_reason = should_skip_image(asset, data)
            if skip_reason:
                asset.save_status = "skipped"
                asset.save_path = ""
                asset.error = skip_reason
                return asset
            output_path.write_bytes(data)
            asset.save_status = "saved"
            asset.save_path = str(output_path)
            asset.error = ""
            return asset
        except Exception as exc:  # noqa: BLE001
            asset.error = str(exc)
            if attempt < retries:
                time.sleep(0.7 * (attempt + 1))
    asset.save_status = "failed"
    return asset


def assign_filenames(assets: List[Asset], site: str, run_id: str) -> None:
    for index, asset in enumerate(assets):
        asset.filename = make_filename(site, run_id, index, asset.posting_title, asset.asset_url, asset.asset_kind)


def save_all_assets(assets: List[Asset], output_dir: Path, workers: int) -> List[Asset]:
    output_dir.mkdir(parents=True, exist_ok=True)
    if not assets:
        return []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = [executor.submit(write_asset, asset, output_dir) for asset in assets]
        return [future.result() for future in concurrent.futures.as_completed(futures)]


def manifest(
    site: str,
    run_id: str,
    output_dir: Path,
    postings: Sequence[Posting],
    assets: Sequence[Asset],
    errors: Sequence[Dict[str, str]],
) -> Dict[str, object]:
    return {
        "tool": "notice-file-collector",
        "version": "0.1.0",
        "site": site,
        "runId": run_id,
        "collectedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "outputDir": str(output_dir),
        "postingCount": len(postings),
        "assetCount": len(assets),
        "savedAssetCount": sum(1 for asset in assets if asset.save_status == "saved"),
        "skippedAssetCount": sum(1 for asset in assets if asset.save_status == "skipped"),
        "failedAssetCount": sum(1 for asset in assets if asset.save_status == "failed"),
        "postings": [asdict(posting) for posting in postings],
        "assets": [asdict(asset) for asset in assets],
        "errors": list(errors),
    }


def collect_site(args: argparse.Namespace, site: str, run_root: Path) -> Tuple[str, Path, Dict[str, object]]:
    print(f"\n[{site}] 수집을 시작합니다.", flush=True)
    if site == "jobda":
        postings, assets, errors = collect_jobda(args.limit, args.jobda_url)
    elif site == "inthiswork":
        postings, assets, errors = collect_inthiswork(args.inthiswork_url, args.limit, args.detail_limit)
    else:
        raise ValueError(f"Unsupported site: {site}")

    run_id = now_run_id()
    output_dir = run_root / f"{site}_{run_id}"
    assign_filenames(assets, site, run_id)
    print(f"\n[{site}] 공고 {len(postings)}개, 파일 후보 {len(assets)}개를 찾았습니다.")
    if errors:
        print(f"[{site}] 확인이 필요한 항목 {len(errors)}개가 있습니다.", flush=True)
        for error in errors[:5]:
            phase = error.get("phase", "unknown")
            message = error.get("message", "")
            posting_url = error.get("postingUrl", "")
            suffix = f" ({posting_url})" if posting_url else ""
            print(f"[{site}] - {phase}: {message}{suffix}", flush=True)
        if len(errors) > 5:
            print(f"[{site}] - 나머지 {len(errors) - 5}개는 manifest.json에서 확인할 수 있습니다.", flush=True)
    saved_assets = save_all_assets(assets, output_dir, workers=args.workers)
    # Preserve original order for manifest readability.
    saved_by_url = {asset.asset_url: asset for asset in saved_assets}
    ordered_assets = [saved_by_url.get(asset.asset_url, asset) for asset in assets]

    data = manifest(site, run_id, output_dir, postings, ordered_assets, errors)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifest.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[{site}] 저장 성공 {data['savedAssetCount']}개, 제외 {data['skippedAssetCount']}개, 실패 {data['failedAssetCount']}개")
    print(f"[{site}] 결과 폴더: {output_dir}")
    return site, output_dir, data


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Jobda/Inthiswork recruiting notice image collector")
    parser.add_argument("--site", choices=["jobda", "inthiswork", "both"], default="both", help="수집 대상 사이트")
    parser.add_argument("--limit", type=int, default=40, help="목록에서 처리할 최대 공고 수")
    parser.add_argument("--detail-limit", type=int, default=0, help="인디스워크 상세 페이지 fetch 최대 개수. 0이면 처리 대상 전체")
    parser.add_argument("--out", default="collected", help="결과 저장 루트 폴더")
    parser.add_argument("--workers", type=int, default=4, help="파일 다운로드 동시 작업 수")
    parser.add_argument("--jobda-url", default=JOBDA_DEFAULT_URL, help="Jobda 목록 또는 상세 URL")
    parser.add_argument("--inthiswork-url", default=INTHISWORK_DEFAULT_URL, help="인디스워크 목록/카테고리 URL")
    parser.add_argument("--interactive", action="store_true", help="대화형 메뉴를 표시")
    return parser.parse_args(argv)


def interactive_args(args: argparse.Namespace) -> argparse.Namespace:
    print("\n공고 파일 수집기")
    print("1. Jobda 수집")
    print("2. 인디스워크 수집")
    print("3. 둘 다 수집")
    choice = input("선택하세요 [3]: ").strip() or "3"
    args.site = {"1": "jobda", "2": "inthiswork", "3": "both"}.get(choice, "both")

    limit = input(f"사이트별 최대 공고 수 [{args.limit}]: ").strip()
    if limit:
        args.limit = int(limit)

    out = input(f"저장 폴더 [{args.out}]: ").strip()
    if out:
        args.out = out
    else:
        print(f"기본 저장 폴더를 사용합니다: {args.out}")

    if args.site in ("jobda", "both"):
        url = input(f"Jobda URL [{args.jobda_url}]: ").strip()
        if url:
            args.jobda_url = url
        else:
            print(f"기본 Jobda URL을 사용합니다: {args.jobda_url}")

    if args.site in ("inthiswork", "both"):
        url = input(f"인디스워크 URL [{args.inthiswork_url}]: ").strip()
        if url:
            args.inthiswork_url = url
        else:
            print(f"기본 인디스워크 URL을 사용합니다: {args.inthiswork_url}")
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if args.interactive:
        args = interactive_args(args)

    sites = ["jobda", "inthiswork"] if args.site == "both" else [args.site]
    run_root = Path(args.out).expanduser().resolve()
    run_root.mkdir(parents=True, exist_ok=True)

    summaries = []
    for site in sites:
        try:
            summaries.append(collect_site(args, site, run_root))
        except KeyboardInterrupt:
            raise
        except Exception as exc:  # noqa: BLE001
            print(f"[{site}] 수집 실패: {exc}", file=sys.stderr)

    print("\n완료")
    for site, output_dir, data in summaries:
        print(f"- {site}: 저장 {data['savedAssetCount']}개 / 실패 {data['failedAssetCount']}개 -> {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
