#!/usr/bin/env python3
"""Aggregate free public proxy nodes into Happ-compatible subscriptions."""

from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
SUB_DIR = ROOT / "sub"
COUNTRY_DIR = SUB_DIR / "countries"
META_DIR = ROOT / "meta"

# Public free subscription sources (already published on GitHub).
SOURCES = [
    "https://raw.githubusercontent.com/Au1rxx/free-vpn-subscriptions/main/output/v2ray-base64.txt",
    "https://raw.githubusercontent.com/awesome-vpn/awesome-vpn/master/all",
    "https://raw.githubusercontent.com/barry-far/V2ray-config/main/Sub1.txt",
    "https://raw.githubusercontent.com/barry-far/V2ray-config/main/Sub2.txt",
    "https://raw.githubusercontent.com/barry-far/V2ray-config/main/Sub3.txt",
    "https://raw.githubusercontent.com/ebrasha/free-v2ray-public-list/main/V2Ray-Config-By-EbraSha.txt",
    "https://raw.githubusercontent.com/MatinGhanbari/v2ray-configs/main/subscriptions/v2ray/super-sub.txt",
    "https://raw.githubusercontent.com/MatinGhanbari/v2ray-configs/main/subscriptions/filtered/subs/vless.txt",
    "https://raw.githubusercontent.com/MatinGhanbari/v2ray-configs/main/subscriptions/filtered/subs/hysteria2.txt",
]

PROTO_RE = re.compile(
    r"^(?:vless|vmess|trojan|ss|socks|hysteria2|hy2)://\S+",
    re.IGNORECASE,
)

# Country detection from node name / fragment.
COUNTRY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("US", re.compile(r"\b(US|USA|United[- ]?States|America|США|美国|美國)\b|🇺🇸", re.I)),
    ("DE", re.compile(r"\b(DE|Germany|Deutschland|Германия|德国|德國)\b|🇩🇪", re.I)),
    ("NL", re.compile(r"\b(NL|Netherlands|Holland|Нидерланды|荷兰|荷蘭)\b|🇳🇱", re.I)),
    ("GB", re.compile(r"\b(GB|UK|United[- ]?Kingdom|Britain|England|Британия|英国|英國)\b|🇬🇧", re.I)),
    ("FR", re.compile(r"\b(FR|France|Франция|法国|法國)\b|🇫🇷", re.I)),
    ("FI", re.compile(r"\b(FI|Finland|Финляндия|芬兰|芬蘭)\b|🇫🇮", re.I)),
    ("SE", re.compile(r"\b(SE|Sweden|Швеция|瑞典)\b|🇸🇪", re.I)),
    ("TR", re.compile(r"\b(TR|Turkey|Türkiye|Турция|土耳其)\b|🇹🇷", re.I)),
    ("JP", re.compile(r"\b(JP|Japan|Япония|日本)\b|🇯🇵", re.I)),
    ("KR", re.compile(r"\b(KR|Korea|Южная[- ]?Корея|韩国|韓國)\b|🇰🇷", re.I)),
    ("SG", re.compile(r"\b(SG|Singapore|Сингапур|新加坡)\b|🇸🇬", re.I)),
    ("HK", re.compile(r"\b(HK|Hong[- ]?Kong|Гонконг|香港)\b|🇭🇰", re.I)),
    ("TW", re.compile(r"\b(TW|Taiwan|Тайвань|台湾|台灣)\b|🇹🇼", re.I)),
    ("CA", re.compile(r"\b(CA|Canada|Канада|加拿大)\b|🇨🇦", re.I)),
    ("AU", re.compile(r"\b(AU|Australia|Австралия|澳大利亚|澳洲)\b|🇦🇺", re.I)),
    ("IN", re.compile(r"\b(IN|India|Индия|印度)\b|🇮🇳", re.I)),
    ("BR", re.compile(r"\b(BR|Brazil|Бразилия|巴西)\b|🇧🇷", re.I)),
    ("RU", re.compile(r"\b(RU|Russia|Россия|俄国|俄羅斯)\b|🇷🇺", re.I)),
    ("UA", re.compile(r"\b(UA|Ukraine|Украина|乌克兰|烏克蘭)\b|🇺🇦", re.I)),
    ("PL", re.compile(r"\b(PL|Poland|Польша|波兰|波蘭)\b|🇵🇱", re.I)),
    ("IT", re.compile(r"\b(IT|Italy|Италия|意大利)\b|🇮🇹", re.I)),
    ("ES", re.compile(r"\b(ES|Spain|Испания|西班牙)\b|🇪🇸", re.I)),
    ("CH", re.compile(r"\b(CH|Switzerland|Швейцария|瑞士)\b|🇨🇭", re.I)),
    ("AT", re.compile(r"\b(AT|Austria|Австрия|奥地利|奧地利)\b|🇦🇹", re.I)),
    ("IE", re.compile(r"\b(IE|Ireland|Ирландия|爱尔兰|愛爾蘭)\b|🇮🇪", re.I)),
    ("AE", re.compile(r"\b(AE|UAE|Dubai|ОАЭ|阿联酋)\b|🇦🇪", re.I)),
    ("IL", re.compile(r"\b(IL|Israel|Израиль|以色列)\b|🇮🇱", re.I)),
]

COUNTRY_FLAGS = {
    "US": "🇺🇸",
    "DE": "🇩🇪",
    "NL": "🇳🇱",
    "GB": "🇬🇧",
    "FR": "🇫🇷",
    "FI": "🇫🇮",
    "SE": "🇸🇪",
    "TR": "🇹🇷",
    "JP": "🇯🇵",
    "KR": "🇰🇷",
    "SG": "🇸🇬",
    "HK": "🇭🇰",
    "TW": "🇹🇼",
    "CA": "🇨🇦",
    "AU": "🇦🇺",
    "IN": "🇮🇳",
    "BR": "🇧🇷",
    "RU": "🇷🇺",
    "UA": "🇺🇦",
    "PL": "🇵🇱",
    "IT": "🇮🇹",
    "ES": "🇪🇸",
    "CH": "🇨🇭",
    "AT": "🇦🇹",
    "IE": "🇮🇪",
    "AE": "🇦🇪",
    "IL": "🇮🇱",
    "OTHER": "🌍",
}

MAX_TOTAL = 400
MAX_PER_COUNTRY_FILE = 80
MAX_PER_COUNTRY_IN_MAIN = 35
USER_AGENT = "VPN-FOR-HAPP-Updater/1.0 (+https://github.com/svoyskiy666/VPN-FOR-HAPP-)"


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
    if "://" in decoded or PROTO_RE.search(decoded.splitlines()[0] if decoded else ""):
        return decoded
    return text


def extract_links(text: str) -> list[str]:
    content = maybe_b64_decode(text)
    links: list[str] = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Some feeds put multiple links on one line.
        for part in re.split(r"[\s]+", line):
            part = part.strip().strip("`\"'")
            if PROTO_RE.match(part):
                links.append(part)
    return links


def node_key(link: str) -> str:
    """Dedupe key without fragment/name."""
    if "#" in link:
        link = link.split("#", 1)[0]
    return link.lower()


def node_name(link: str) -> str:
    if "#" not in link:
        return ""
    return unquote(link.split("#", 1)[1]).strip()


def detect_country(link: str) -> str:
    name = node_name(link)
    hay = f"{name} {link}"
    for code, pattern in COUNTRY_PATTERNS:
        if pattern.search(hay):
            return code
    return "OTHER"


def link_scheme(link: str) -> str:
    head = link.split("://", 1)[0] if "://" in link else "vpn"
    return head.upper()


def rename_node(link: str, country: str, index: int) -> str:
    flag = COUNTRY_FLAGS.get(country, "🌍")
    base = link.split("#", 1)[0]
    proto = link_scheme(link)
    title = f"{flag} {country}-{index:02d} [{proto}]"
    # Keep title reasonably short for Happ.
    return f"{base}#{title}"


def prioritize(links: Iterable[str]) -> list[str]:
    """Prefer tested/quality-looking sources order already applied; then diversify countries."""
    by_country: dict[str, list[str]] = defaultdict(list)
    for link in links:
        by_country[detect_country(link)].append(link)

    selected: list[str] = []
    # Round-robin across countries for diversity.
    pools = {code: lst[:] for code, lst in by_country.items()}
    while len(selected) < MAX_TOTAL and any(pools.values()):
        progressed = False
        for code in sorted(pools.keys(), key=lambda c: (c == "OTHER", c)):
            bucket = pools[code]
            if not bucket:
                continue
            taken = sum(1 for x in selected if detect_country(x) == code)
            if taken >= MAX_PER_COUNTRY_IN_MAIN and code != "OTHER":
                # Soft cap — skip for now, maybe take later if room remains.
                continue
            selected.append(bucket.pop(0))
            progressed = True
            if len(selected) >= MAX_TOTAL:
                break
        if not progressed:
            # Fill remaining slots ignoring soft caps.
            for code in sorted(pools.keys()):
                while pools[code] and len(selected) < MAX_TOTAL:
                    selected.append(pools[code].pop(0))
            break
    return selected


def write_subscription(path: Path, links: list[str], title: str) -> None:
    body_lines = [
        f"#profile-title: {title}",
        "#profile-update-interval: 1",
        f"#profile-web-page-url: https://github.com/svoyskiy666/VPN-FOR-HAPP-",
        *links,
    ]
    plain = "\n".join(body_lines) + "\n"
    path.write_text(base64.b64encode(plain.encode("utf-8")).decode("ascii") + "\n", encoding="utf-8")


def write_plain(path: Path, links: list[str]) -> None:
    path.write_text("\n".join(links) + "\n", encoding="utf-8")


def update_readme_status(status: dict) -> None:
    readme = ROOT / "README.md"
    if not readme.exists():
        return
    text = readme.read_text(encoding="utf-8")
    start = "<!-- STATUS:START -->"
    end = "<!-- STATUS:END -->"
    block = (
        f"{start}\n"
        f"**Обновлено:** `{status['updated_at']}` · "
        f"**Серверов:** `{status['total_nodes']}` · "
        f"**Локаций:** `{status['countries']}`\n"
        f"{end}"
    )
    if start in text and end in text:
        text = re.sub(
            re.escape(start) + r".*?" + re.escape(end),
            block,
            text,
            count=1,
            flags=re.S,
        )
    else:
        text = block + "\n\n" + text
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
            seen.add(key)
            unique.append(link)
            added += 1
        source_stats.append({"url": url, "ok": True, "nodes": added})
        print(f"[info] +{added} unique from source ({len(links)} raw)")

    selected = prioritize(unique)
    renamed: list[str] = []
    counters: dict[str, int] = defaultdict(int)
    by_country: dict[str, list[str]] = defaultdict(list)

    for link in selected:
        country = detect_country(link)
        counters[country] += 1
        pretty = rename_node(link, country, counters[country])
        renamed.append(pretty)
        by_country[country].append(pretty)

    write_subscription(SUB_DIR / "happ.txt", renamed, "VPN-FOR-HAPP")
    write_plain(SUB_DIR / "happ-plain.txt", renamed)

    # Per-country subscriptions for Happ.
    for old in COUNTRY_DIR.glob("*.txt"):
        old.unlink()
    country_files: dict[str, int] = {}
    for code, links in sorted(by_country.items()):
        trimmed = links[:MAX_PER_COUNTRY_FILE]
        if not trimmed:
            continue
        write_subscription(COUNTRY_DIR / f"{code}.txt", trimmed, f"HAPP-{code}")
        country_files[code] = len(trimmed)

    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    status = {
        "updated_at": updated_at,
        "total_nodes": len(renamed),
        "unique_collected": len(unique),
        "countries": len(country_files),
        "by_country": dict(sorted(country_files.items(), key=lambda x: (-x[1], x[0]))),
        "sources": source_stats,
        "subscription": {
            "main": "https://raw.githubusercontent.com/svoyskiy666/VPN-FOR-HAPP-/main/sub/happ.txt",
            "cdn": "https://cdn.jsdelivr.net/gh/svoyskiy666/VPN-FOR-HAPP-@main/sub/happ.txt",
            "plain": "https://raw.githubusercontent.com/svoyskiy666/VPN-FOR-HAPP-/main/sub/happ-plain.txt",
        },
    }
    (META_DIR / "status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (META_DIR / "last_update.txt").write_text(updated_at + "\n", encoding="utf-8")
    update_readme_status(status)

    print(f"[ok] wrote {len(renamed)} nodes across {len(country_files)} locations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
