#!/usr/bin/env python3
"""Build a minimal Happ subscription from RU-tested free node sources."""

from __future__ import annotations

import base64
import json
import re
import socket
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
SUB_DIR = ROOT / "sub"
COUNTRY_DIR = SUB_DIR / "countries"
META_DIR = ROOT / "meta"

BRAND = "svoyskiy.ru"
BRAND_URL = "https://svoyskiy.ru"
REPO_URL = "https://github.com/svoyskiy666/VPN-FOR-HAPP-"

# Prefer sources that already HTTP-test nodes (especially RU-oriented).
SOURCES = [
    "https://raw.githubusercontent.com/haker23378-netizen/free-vpn-telegram/main/output/subscription.txt",
    "https://raw.githubusercontent.com/haker23378-netizen/free-vpn-telegram/main/output/sub/vless.txt",
    "https://raw.githubusercontent.com/Au1rxx/free-vpn-subscriptions/main/output/v2ray-base64.txt",
    "https://raw.githubusercontent.com/Au1rxx/free-vpn-subscriptions/main/output/by-country/v2ray-base64-NL.txt",
    "https://raw.githubusercontent.com/Au1rxx/free-vpn-subscriptions/main/output/by-country/v2ray-base64-DE.txt",
    "https://raw.githubusercontent.com/Au1rxx/free-vpn-subscriptions/main/output/by-country/v2ray-base64-FI.txt",
    "https://raw.githubusercontent.com/barry-far/V2ray-config/main/Sub1.txt",
    "https://raw.githubusercontent.com/MatinGhanbari/v2ray-configs/main/subscriptions/filtered/subs/vless.txt",
]

PROTO_RE = re.compile(
    r"^(?:vless|vmess|trojan|ss|socks|hysteria2|hy2)://\S+",
    re.IGNORECASE,
)

COUNTRY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("NL", re.compile(r"\b(NL|Netherlands|Holland|Нидерланды)\b|🇳🇱", re.I)),
    ("DE", re.compile(r"\b(DE|Germany|Deutschland|Германия)\b|🇩🇪", re.I)),
    ("FI", re.compile(r"\b(FI|Finland|Финляндия)\b|🇫🇮", re.I)),
    ("SE", re.compile(r"\b(SE|Sweden|Швеция)\b|🇸🇪", re.I)),
    ("PL", re.compile(r"\b(PL|Poland|Польша)\b|🇵🇱", re.I)),
    ("TR", re.compile(r"\b(TR|Turkey|Türkiye|Турция)\b|🇹🇷", re.I)),
    ("GB", re.compile(r"\b(GB|UK|United[- ]?Kingdom|Britain)\b|🇬🇧", re.I)),
    ("FR", re.compile(r"\b(FR|France|Франция)\b|🇫🇷", re.I)),
    ("US", re.compile(r"\b(US|USA|United[- ]?States|America|США)\b|🇺🇸", re.I)),
    ("JP", re.compile(r"\b(JP|Japan|Япония)\b|🇯🇵", re.I)),
    ("SG", re.compile(r"\b(SG|Singapore|Сингапур)\b|🇸🇬", re.I)),
    ("RU", re.compile(r"\b(RU|Russia|Россия)\b|🇷🇺", re.I)),
]

COUNTRY_FLAGS = {
    "NL": "🇳🇱",
    "DE": "🇩🇪",
    "FI": "🇫🇮",
    "SE": "🇸🇪",
    "PL": "🇵🇱",
    "TR": "🇹🇷",
    "GB": "🇬🇧",
    "FR": "🇫🇷",
    "US": "🇺🇸",
    "JP": "🇯🇵",
    "SG": "🇸🇬",
    "RU": "🇷🇺",
    "OTHER": "🌍",
}

PREFERRED = ["NL", "DE", "FI", "SE", "PL", "TR", "GB", "FR", "US", "JP", "SG", "OTHER"]
SKIP = {"RU"}

MAX_TOTAL = 60
MAX_PER_COUNTRY = 12
TCP_WORKERS = 40
TCP_TIMEOUT = 2.5
USER_AGENT = f"{BRAND}-HappUpdater/3.0 (+{REPO_URL})"

SUB_SIMPLE = f"https://cdn.jsdelivr.net/gh/svoyskiy666/VPN-FOR-HAPP-@main/sub/simple.txt"
SUB_MIRROR = (
    "https://ghproxy.net/https://raw.githubusercontent.com/"
    "svoyskiy666/VPN-FOR-HAPP-/main/sub/simple.txt"
)


def b64_text(text: str) -> str:
    return "base64:" + base64.b64encode(text.encode("utf-8")).decode("ascii")


def fetch(url: str, timeout: int = 45) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        print(f"[warn] fetch failed: {url} ({exc})")
        return None
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def maybe_b64_decode(text: str) -> str:
    compact = "".join(text.split())
    if len(compact) < 16 or not re.fullmatch(r"[A-Za-z0-9+/=_-]+", compact):
        return text
    padded = compact + "=" * (-len(compact) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8", errors="ignore")
    except Exception:
        return text
    if "://" in decoded:
        return decoded
    return text


def extract_links(text: str) -> list[str]:
    content = maybe_b64_decode(text)
    links: list[str] = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("happ://"):
            continue
        for part in re.split(r"[\s]+", line):
            part = part.strip().strip("`\"'")
            if PROTO_RE.match(part):
                links.append(part)
    return links


def node_key(link: str) -> str:
    return link.split("#", 1)[0].lower()


def node_name(link: str) -> str:
    if "#" not in link:
        return ""
    return unquote(link.split("#", 1)[1]).strip()


def detect_country(link: str) -> str:
    hay = f"{node_name(link)} {link}"
    for code, pattern in COUNTRY_PATTERNS:
        if pattern.search(hay):
            return code
    return "OTHER"


def link_scheme(link: str) -> str:
    return link.split("://", 1)[0].lower() if "://" in link else "vpn"


def protocol_score(link: str) -> int:
    scheme = link_scheme(link)
    low = link.lower()
    score = 0
    if scheme in ("hysteria2", "hy2"):
        score += 55
    elif scheme == "vless" and "reality" in low:
        score += 50
    elif scheme == "vless":
        score += 35
    elif scheme == "trojan":
        score += 25
    elif scheme == "vmess":
        score += 12
    elif scheme == "ss":
        score += 5
    if "xtls-rprx-vision" in low:
        score += 8
    if "security=reality" in low or "security=tls" in low:
        score += 5
    return score


def country_rank(code: str) -> int:
    try:
        return PREFERRED.index(code)
    except ValueError:
        return 99


def rename_node(link: str, country: str, index: int) -> str:
    flag = COUNTRY_FLAGS.get(country, "🌍")
    base = link.split("#", 1)[0]
    return f"{base}#{flag} {country}-{index:02d} {BRAND}"


def extract_host_port(link: str) -> tuple[str, int] | None:
    try:
        raw = link.split("#", 1)[0]
        scheme = link_scheme(raw)
        if scheme == "vmess":
            payload = raw.split("://", 1)[1]
            pad = payload + "=" * (-len(payload) % 4)
            data = json.loads(base64.urlsafe_b64decode(pad.encode("ascii")).decode("utf-8", "ignore"))
            host = str(data.get("add") or "").strip()
            port = int(data.get("port") or 0)
            return (host, port) if host and port else None
        if scheme == "ss":
            rest = raw.split("://", 1)[1]
            if "@" in rest:
                hostport = rest.rsplit("@", 1)[1]
                host, port_s = hostport.split(":")[:2]
                return host, int(port_s)
            pad = rest + "=" * (-len(rest) % 4)
            decoded = base64.urlsafe_b64decode(pad.encode("ascii")).decode("utf-8", "ignore")
            if "@" in decoded:
                hostport = decoded.rsplit("@", 1)[1]
                host, port_s = hostport.split(":")[:2]
                return host, int(port_s)
            return None
        parsed = urlparse(raw)
        if parsed.hostname and parsed.port:
            return parsed.hostname, int(parsed.port)
    except Exception:
        return None
    return None


def tcp_alive(link: str) -> bool:
    hp = extract_host_port(link)
    if not hp:
        return False
    host, port = hp
    try:
        with socket.create_connection((host, port), timeout=TCP_TIMEOUT):
            return True
    except OSError:
        return False


def filter_alive(links: list[str]) -> list[str]:
    if not links:
        return []
    print(f"[info] TCP-checking {len(links)} nodes...")
    alive: list[str] = []
    with ThreadPoolExecutor(max_workers=TCP_WORKERS) as pool:
        futs = {pool.submit(tcp_alive, link): link for link in links}
        for fut in as_completed(futs):
            link = futs[fut]
            try:
                if fut.result():
                    alive.append(link)
            except Exception:
                pass
    order = {node_key(x): i for i, x in enumerate(links)}
    alive.sort(key=lambda x: order.get(node_key(x), 10**9))
    print(f"[info] alive {len(alive)}/{len(links)}")
    return alive


def prioritize(links: list[str]) -> list[str]:
    by_country: dict[str, list[str]] = defaultdict(list)
    scored = sorted(
        links,
        key=lambda l: (-protocol_score(l), country_rank(detect_country(l))),
    )
    for link in scored:
        code = detect_country(link)
        if code in SKIP:
            continue
        by_country[code].append(link)

    selected: list[str] = []
    for code in PREFERRED:
        bucket = by_country.get(code, [])
        selected.extend(bucket[:MAX_PER_COUNTRY])
        if len(selected) >= MAX_TOTAL:
            return selected[:MAX_TOTAL]
    return selected[:MAX_TOTAL]


def subscription_header_lines() -> list[str]:
    """Minimal Happ metadata only — no routing/per-app (those broke DNS for users)."""
    announce = (
        f"VPN от {BRAND}. Выбери сервер и жми подключить. "
        f"Если нет интернета — Happ → Настройки → Приложения → только Discord/Chrome. "
        f"{BRAND_URL}"
    )
    return [
        f"#profile-title: {BRAND}",
        f"#profile-web-page-url: {BRAND_URL}",
        f"#support-url: {BRAND_URL}",
        f"#announce: {b64_text(announce)}",
        f"#sub-info-color: blue",
        f"#sub-info-text: VPN от {BRAND} — сайт {BRAND_URL}",
        f"#sub-info-button-text: Сайт {BRAND}",
        f"#sub-info-button-link: {BRAND_URL}",
        "#profile-update-interval: 1",
    ]


def write_subscription(path: Path, links: list[str]) -> None:
    body = "\n".join(subscription_header_lines() + links) + "\n"
    path.write_text(base64.b64encode(body.encode("utf-8")).decode("ascii") + "\n", encoding="utf-8")


def write_plain(path: Path, links: list[str]) -> None:
    body = "\n".join(subscription_header_lines() + links) + "\n"
    path.write_text(body, encoding="utf-8")


def update_readme_status(status: dict) -> None:
    readme = ROOT / "README.md"
    if not readme.exists():
        return
    text = readme.read_text(encoding="utf-8")
    start, end = "<!-- STATUS:START -->", "<!-- STATUS:END -->"
    block = (
        f"{start}\n"
        f"**Обновлено:** `{status['updated_at']}` · "
        f"**Серверов:** `{status['total_nodes']}` · "
        f"**VPN:** [`{BRAND}`]({BRAND_URL})\n"
        f"{end}"
    )
    if start in text and end in text:
        text = re.sub(re.escape(start) + r".*?" + re.escape(end), block, text, count=1, flags=re.S)
    readme.write_text(text, encoding="utf-8")


def main() -> int:
    SUB_DIR.mkdir(parents=True, exist_ok=True)
    COUNTRY_DIR.mkdir(parents=True, exist_ok=True)
    META_DIR.mkdir(parents=True, exist_ok=True)

    seen: set[str] = set()
    unique: list[str] = []
    source_stats: list[dict] = []

    for url in SOURCES:
        print(f"[info] fetching {url}")
        raw = fetch(url)
        if raw is None:
            source_stats.append({"url": url, "ok": False, "nodes": 0})
            continue
        links = extract_links(raw)
        added = 0
        for link in links:
            key = node_key(link)
            if key in seen:
                continue
            # Prefer modern protocols for RU DPI.
            if link_scheme(link) not in ("vless", "hysteria2", "hy2", "trojan"):
                continue
            seen.add(key)
            unique.append(link)
            added += 1
        source_stats.append({"url": url, "ok": True, "nodes": added})
        print(f"[info] +{added} unique ({len(links)} raw)")

    scored = sorted(unique, key=lambda l: (-protocol_score(l), country_rank(detect_country(l))))
    candidates = scored[:250]
    alive = filter_alive(candidates)
    selected = prioritize(alive if alive else candidates)
    if not alive:
        print("[warn] no TCP-alive nodes, using untested fallback")

    renamed: list[str] = []
    counters: dict[str, int] = defaultdict(int)
    by_country: dict[str, list[str]] = defaultdict(list)
    for link in selected:
        country = detect_country(link)
        counters[country] += 1
        pretty = rename_node(link, country, counters[country])
        renamed.append(pretty)
        by_country[country].append(pretty)

    # Primary simple subscription (new name = no CDN/old-settings cache).
    write_subscription(SUB_DIR / "simple.txt", renamed)
    write_subscription(SUB_DIR / "happ.txt", renamed)
    write_subscription(SUB_DIR / "happ-lite.txt", renamed[:40])
    write_subscription(SUB_DIR / "wifi-safe.txt", renamed[:40])
    write_plain(SUB_DIR / "happ-plain.txt", renamed)

    for old in COUNTRY_DIR.glob("*.txt"):
        old.unlink()
    country_files: dict[str, int] = {}
    for code, links in sorted(by_country.items()):
        write_subscription(COUNTRY_DIR / f"{code}.txt", links[:20])
        country_files[code] = len(links[:20])

    eu: list[str] = []
    for code in ("NL", "DE", "FI", "SE", "PL", "TR", "GB"):
        eu.extend(by_country.get(code, [])[:10])
    if eu:
        write_subscription(SUB_DIR / "discord-youtube.txt", eu[:40])

    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    status = {
        "updated_at": updated_at,
        "brand": BRAND,
        "website": BRAND_URL,
        "total_nodes": len(renamed),
        "unique_collected": len(unique),
        "countries": len(country_files),
        "by_country": dict(sorted(country_files.items(), key=lambda x: (-x[1], x[0]))),
        "sources": source_stats,
        "subscription": {
            "simple": SUB_SIMPLE,
            "mirror": SUB_MIRROR,
        },
    }
    (META_DIR / "status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (META_DIR / "last_update.txt").write_text(updated_at + "\n", encoding="utf-8")
    update_readme_status(status)
    print(f"[ok] {len(renamed)} nodes → sub/simple.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
