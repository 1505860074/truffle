r"""抓取用于风格评估的测试图片。

优先使用公开 API / 公共版权来源，尊重站点条款与速率限制：
- wikimedia：Wikimedia Commons 搜索（无需 key，注意许可证）
- unsplash：Unsplash API（需要 Access Key）
- pexels：Pexels API（需要 API Key）
- urls：从文本文件读取直链

示例：
    .\.venv\Scripts\python.exe scripts\fetch_test_images.py --source wikimedia `
        --query "portrait photography" --count 100 --out test_images

    .\.venv\Scripts\python.exe scripts\fetch_test_images.py --source unsplash `
        --query "beauty portrait" --count 50 --api-key YOUR_KEY --out test_images

下载图片只用于本地测试，请自行确认许可证与隐私要求。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

UA = "TruffleTestImageFetcher/1.0 (local evaluation; contact: local)"
EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
WIKI_API = "https://commons.wikimedia.org/w/api.php"


def _request(url: str, headers: dict | None = None, timeout: int = 30) -> bytes:
    merged = {"User-Agent": UA}
    if headers:
        merged.update(headers)
    req = urllib.request.Request(url, headers=merged)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def _safe_name(value: str, fallback: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return value or fallback


def _download(url: str, out_dir: Path, name_hint: str, max_bytes: int) -> Path | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as response:
            data = response.read(max_bytes + 1)
            if len(data) > max_bytes:
                return None
            content_type = response.headers.get("Content-Type", "")
        if "image" not in content_type.lower() and not data[:4].startswith(b"\x89PNG") and data[:2] != b"\xff\xd8":
            return None
        digest = hashlib.sha1(data).hexdigest()[:12]
        suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
        if suffix not in EXTS:
            suffix = ".jpg"
        name = _safe_name(Path(urllib.parse.urlparse(url).path).stem, name_hint)
        path = out_dir / f"{name}_{digest}{suffix}"
        path.write_bytes(data)
        return path
    except Exception:
        return None


def _wikimedia(query: str, count: int, out_dir: Path, max_bytes: int, delay: float) -> list[Path]:
    saved: list[Path] = []
    offset = 0
    while len(saved) < count:
        params = {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "generator": "search",
            "gsrsearch": f"filetype:bitmap {query}",
            "gsrnamespace": "6",
            "gsrlimit": min(50, count - len(saved)),
            "gsroffset": offset,
            "prop": "imageinfo",
            "iiprop": "url|mime|size",
        }
        url = WIKI_API + "?" + urllib.parse.urlencode(params)
        try:
            payload = json.loads(_request(url).decode("utf-8"))
        except Exception:
            break
        pages = payload.get("query", {}).get("pages", [])
        if not pages:
            break
        for page in pages:
            info = (page.get("imageinfo") or [{}])[0]
            image_url = info.get("url", "")
            mime = str(info.get("mime", ""))
            if not image_url or not mime.startswith("image/"):
                continue
            if mime not in ("image/jpeg", "image/png", "image/webp"):
                continue
            path = _download(image_url, out_dir, page.get("title", "image"), max_bytes)
            if path is not None:
                saved.append(path)
            if len(saved) >= count:
                break
            time.sleep(delay)
        offset += len(pages)
        if "continue" not in payload:
            break
    return saved


def _unsplash(query: str, count: int, api_key: str, out_dir: Path, max_bytes: int) -> list[Path]:
    saved: list[Path] = []
    page = 1
    while len(saved) < count:
        params = urllib.parse.urlencode(
            {"query": query, "per_page": min(30, count - len(saved)), "page": page,
             "client_id": api_key}
        )
        try:
            payload = json.loads(_request("https://api.unsplash.com/search/photos?" + params).decode("utf-8"))
        except Exception:
            break
        results = payload.get("results", [])
        if not results:
            break
        for item in results:
            url = (item.get("urls") or {}).get("regular")
            if not url:
                continue
            path = _download(url, out_dir, str(item.get("id", "unsplash")), max_bytes)
            if path is not None:
                saved.append(path)
            if len(saved) >= count:
                break
        page += 1
    return saved


def _pexels(query: str, count: int, api_key: str, out_dir: Path, max_bytes: int) -> list[Path]:
    saved: list[Path] = []
    page = 1
    while len(saved) < count:
        params = urllib.parse.urlencode({"query": query, "per_page": min(80, count - len(saved)), "page": page})
        try:
            payload = json.loads(
                _request(
                    "https://api.pexels.com/v1/search?" + params,
                    headers={"Authorization": api_key},
                ).decode("utf-8")
            )
        except Exception:
            break
        photos = payload.get("photos", [])
        if not photos:
            break
        for item in photos:
            url = (item.get("src") or {}).get("large2x") or (item.get("src") or {}).get("large")
            if not url:
                continue
            path = _download(url, out_dir, str(item.get("id", "pexels")), max_bytes)
            if path is not None:
                saved.append(path)
            if len(saved) >= count:
                break
        page += 1
    return saved


def _randomuser(count: int, out_dir: Path, max_bytes: int, delay: float) -> list[Path]:
    """randomuser.me 的人像照片（无需 key），适合人脸/肤色快速测试。"""
    saved: list[Path] = []
    page = 0
    while len(saved) < count:
        limit = min(100, count - len(saved))
        url = f"https://randomuser.me/api/?results={limit}&page={page}"
        try:
            payload = json.loads(_request(url).decode("utf-8"))
        except Exception:
            break
        results = payload.get("results", [])
        if not results:
            break
        for item in results:
            picture = item.get("picture") or {}
            image_url = picture.get("large") or picture.get("medium")
            if not image_url:
                continue
            path = _download(image_url, out_dir, f"portrait_{len(saved)}", max_bytes)
            if path is not None:
                saved.append(path)
            if len(saved) >= count:
                break
            time.sleep(delay)
        page += 1
    return saved


def _picsum(count: int, out_dir: Path, max_bytes: int, delay: float) -> list[Path]:
    """Lorem Picsum 的通用照片（无需 key），适合色调/影调测试。"""
    saved: list[Path] = []
    page = 1
    while len(saved) < count:
        url = f"https://picsum.photos/v2/list?page={page}&limit={min(50, count - len(saved))}"
        try:
            items = json.loads(_request(url).decode("utf-8"))
        except Exception:
            break
        if not items:
            break
        for item in items:
            download_url = item.get("download_url")
            if not download_url:
                continue
            path = _download(download_url, out_dir, f"photo_{item.get('id', len(saved))}", max_bytes)
            if path is not None:
                saved.append(path)
            if len(saved) >= count:
                break
            time.sleep(delay)
        page += 1
    return saved


def _urls_file(path: Path, out_dir: Path, max_bytes: int, delay: float) -> list[Path]:
    saved: list[Path] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        url = line.strip()
        if not url or url.startswith("#"):
            continue
        downloaded = _download(url, out_dir, "url", max_bytes)
        if downloaded is not None:
            saved.append(downloaded)
        time.sleep(delay)
    return saved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        choices=["auto", "randomuser", "picsum", "wikimedia", "unsplash", "pexels", "urls"],
        default="auto",
    )
    parser.add_argument("--query", default="portrait photography")
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--out", type=Path, default=Path("test_images"))
    parser.add_argument("--api-key", default="")
    parser.add_argument("--urls-file", type=Path, default=None)
    parser.add_argument("--max-bytes", type=int, default=20 * 1024 * 1024)
    parser.add_argument("--delay", type=float, default=0.6)
    args = parser.parse_args()

    out_dir = args.out / args.source
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.source == "auto":
        saved = _randomuser(args.count, out_dir, args.max_bytes, args.delay)
        if not saved:
            saved = _picsum(args.count, out_dir, args.max_bytes, args.delay)
    elif args.source == "randomuser":
        saved = _randomuser(args.count, out_dir, args.max_bytes, args.delay)
    elif args.source == "picsum":
        saved = _picsum(args.count, out_dir, args.max_bytes, args.delay)
    elif args.source == "wikimedia":
        saved = _wikimedia(args.query, args.count, out_dir, args.max_bytes, args.delay)
    elif args.source == "unsplash":
        if not args.api_key:
            print("Unsplash 需要 --api-key")
            return 2
        saved = _unsplash(args.query, args.count, args.api_key, out_dir, args.max_bytes)
    elif args.source == "pexels":
        if not args.api_key:
            print("Pexels 需要 --api-key")
            return 2
        saved = _pexels(args.query, args.count, args.api_key, out_dir, args.max_bytes)
    else:
        if args.urls_file is None:
            print("--source urls 需要 --urls-file")
            return 2
        saved = _urls_file(args.urls_file, out_dir, args.max_bytes, args.delay)

    meta = {
        "source": args.source,
        "query": args.query,
        "count": len(saved),
        "files": [path.name for path in saved],
        "note": "仅用于本地测试；请确认图片许可证与隐私要求。",
    }
    (out_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"下载 {len(saved)} 张到 {out_dir}")
    return 0 if saved else 1


if __name__ == "__main__":
    raise SystemExit(main())
