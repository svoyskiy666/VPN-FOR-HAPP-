#!/usr/bin/env python3
"""Aggregate free public proxy nodes into Happ-compatible subscriptions for Russia."""

from __future__ import annotations

import base64
import json
import re
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
SUB_DIR = ROOT / "sub"
COUNTRY_DIR = SUB_DIR / "countries"
META_DIR = ROOT / "meta"

BRAND = "svoyskiy.ru"
BRAND_URL = "https://svoyskiy.ru"
REPO_URL = "https://github.com/svoyskiy666/VPN-FOR-HAPP-"

# Public free subscription sources.
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
    ("LV", re.compile(r"\b(LV|Latvia|Латвия|拉脱维亚)\b|🇱🇻", re.I)),
    ("EE", re.compile(r"\b(EE|Estonia|Эстония|爱沙尼亚)\b|🇪🇪", re.I)),
    ("LT", re.compile(r"\b(LT|Lithuania|Литва|立陶宛)\b|🇱🇹", re.I)),
    ("CZ", re.compile(r"\b(CZ|Czech|Чехия|捷克)\b|🇨🇿", re.I)),
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
    "LV": "🇱🇻",
    "EE": "🇪🇪",
    "LT": "🇱🇹",
    "CZ": "🇨🇿",
    "OTHER": "🌍",
}

# Best exits from Russia for Discord / YouTube / Google.
PREFERRED_COUNTRIES = [
    "FI",
    "NL",
    "DE",
    "SE",
    "PL",
    "LV",
    "EE",
    "LT",
    "CZ",
    "TR",
    "GB",
    "FR",
    "AT",
    "CH",
    "IE",
    "US",
    "CA",
    "JP",
    "SG",
    "HK",
    "TW",
    "KR",
    "AE",
    "AU",
    "OTHER",
]

# Skip RU exits in the main list — they don't bypass RU blocks.
SKIP_COUNTRIES = {"RU"}

MAX_TOTAL = 350
MAX_PER_COUNTRY_FILE = 80
MAX_PER_COUNTRY_IN_MAIN = 40
USER_AGENT = f"{BRAND}-HappUpdater/2.0 (+{REPO_URL})"


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
        for part in re.split(r"[\s]+", line):
            part = part.strip().strip("`\"'")
            if PROTO_RE.match(part):
                links.append(part)
    return links


def node_key(link: str) -> str:
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
    return head.lower()


def protocol_score(link: str) -> int:
    """Higher = better for RU DPI / Discord / YouTube."""
    scheme = link_scheme(link)
    low = link.lower()
    score = 0
    if scheme in ("hysteria2", "hy2"):
        score += 50
    elif scheme == "vless" and "reality" in low:
        score += 45
    elif scheme == "vless":
        score += 30
    elif scheme == "trojan":
        score += 25
    elif scheme == "vmess":
        score += 15
    elif scheme == "ss":
        score += 8
    else:
        score += 1
    if "xtls-rprx-vision" in low or "flow=xtls" in low:
        score += 8
    if "security=reality" in low or "security=tls" in low:
        score += 5
    if "insecure=1" in low or "allowinsecure=1" in low:
        score -= 3
    return score


def country_rank(code: str) -> int:
    try:
        return PREFERRED_COUNTRIES.index(code)
    except ValueError:
        return len(PREFERRED_COUNTRIES) + 1


def rename_node(link: str, country: str, index: int) -> str:
    flag = COUNTRY_FLAGS.get(country, "🌍")
    base = link.split("#", 1)[0]
    proto = link_scheme(link).upper()
    # Keep short: Happ title limit ~30 chars for nice UI.
    title = f"{flag} {country}-{index:02d} · {BRAND}"
    if len(title) > 40:
        title = f"{flag} {country}-{index:02d}"
    # serverDescription shows under the title in Happ.
    desc = b64_text(f"{proto} · VPN от {BRAND}")
    return f"{base}#{title}?serverDescription={desc.removeprefix('base64:')}"


def prioritize(links: list[str]) -> list[str]:
    scored: list[tuple[int, int, int, str]] = []
    for link in links:
        country = detect_country(link)
        if country in SKIP_COUNTRIES:
            continue
        scored.append((-protocol_score(link), country_rank(country), hash(node_key(link)) % 10_000, link))
    scored.sort()

    by_country: dict[str, list[str]] = defaultdict(list)
    for _, _, _, link in scored:
        by_country[detect_country(link)].append(link)

    selected: list[str] = []
    pools = {code: lst[:] for code, lst in by_country.items()}

    # First fill preferred countries with best protocols.
    for code in PREFERRED_COUNTRIES:
        bucket = pools.get(code, [])
        take = min(MAX_PER_COUNTRY_IN_MAIN, len(bucket), max(0, MAX_TOTAL - len(selected)))
        selected.extend(bucket[:take])
        pools[code] = bucket[take:]
        if len(selected) >= MAX_TOTAL:
            return selected

    # Fill remaining slots.
    while len(selected) < MAX_TOTAL and any(pools.values()):
        progressed = False
        for code in PREFERRED_COUNTRIES + sorted(set(pools) - set(PREFERRED_COUNTRIES)):
            if pools.get(code):
                selected.append(pools[code].pop(0))
                progressed = True
                if len(selected) >= MAX_TOTAL:
                    break
        if not progressed:
            break
    return selected


def build_routing_deeplink() -> str:
    """Global proxy + Cloudflare DNS so Discord/YouTube resolve outside RU blocks."""
    profile = {
        "Name": f"{BRAND}",
        "GlobalProxy": "true",
        "RemoteDNSType": "DoH",
        "RemoteDNSDomain": "https://cloudflare-dns.com/dns-query",
        "RemoteDNSIP": "1.1.1.1",
        "DomesticDNSType": "DoH",
        "DomesticDNSDomain": "https://dns.google/dns-query",
        "DomesticDNSIP": "8.8.8.8",
        "Geoipurl": "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geoip.dat",
        "Geositeurl": "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geosite.dat",
        "LastUpdated": str(int(time.time())),
        "DnsHosts": {
            "cloudflare-dns.com": "1.1.1.1",
            "dns.google": "8.8.8.8",
        },
        # Russian sites stay direct for speed; everything else (incl. YT/Discord) via VPN.
        "DirectSites": [
            "geosite:category-ru",
            "geosite:private",
            "domain:svoyskiy.ru",
        ],
        "DirectIp": [
            "geoip:private",
            "geoip:ru",
            "10.0.0.0/8",
            "172.16.0.0/12",
            "192.168.0.0/16",
            "169.254.0.0/16",
            "224.0.0.0/4",
            "255.255.255.255",
        ],
        "ProxySites": [
            "geosite:youtube",
            "geosite:discord",
            "geosite:google",
            "geosite:netflix",
            "geosite:twitter",
            "geosite:facebook",
            "geosite:instagram",
            "geosite:tiktok",
            "geosite:spotify",
            "geosite:openai",
            "geosite:telegram",
            "geosite:category-anticensorship",
            "domain:discord.com",
            "domain:discord.gg",
            "domain:discordapp.com",
            "domain:discord.media",
            "domain:googlevideo.com",
            "domain:youtube.com",
            "domain:youtu.be",
            "domain:ytimg.com",
            "domain:ggpht.com",
        ],
        "ProxyIp": [],
        "BlockSites": ["geosite:category-ads-all"],
        "BlockIp": [],
        "DomainStrategy": "IPIfNonMatch",
        "FakeDNS": "false",
    }
    raw = json.dumps(profile, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "happ://routing/onadd/" + base64.b64encode(raw).decode("ascii")


def subscription_header_lines() -> list[str]:
    announce = (
        f"VPN от {BRAND}. Для Discord/YouTube бери сервер 🇫🇮 FI / 🇳🇱 NL / 🇩🇪 DE. "
        f"Сайт: {BRAND_URL}"
    )
    info = f"VPN от {BRAND} — Discord, YouTube и сайты без блокировок"
    return [
        f"#profile-title: {BRAND}",
        f"#profile-web-page-url: {BRAND_URL}",
        f"#support-url: {BRAND_URL}",
        f"#announce: {b64_text(announce)}",
        f"#sub-info-color: blue",
        f"#sub-info-text: {info}",
        f"#sub-info-button-text: Сайт {BRAND}",
        f"#sub-info-button-link: {BRAND_URL}",
        "#profile-update-interval: 1",
        "#routing-enable: 1",
        # DPI bypass for Russian ISPs (helps YouTube/Discord TLS).
        "#fragmentation-enable: 1",
        "#fragmentation-packets: tlshello",
        "#fragmentation-length: 50-100",
        "#fragmentation-interval: 10-20",
        "#server-address-resolve-enable: 1",
        "#server-address-resolve-dns-domain: https://cloudflare-dns.com/dns-query",
        "#server-address-resolve-dns-ip: 1.1.1.1",
        build_routing_deeplink(),
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
    start = "<!-- STATUS:START -->"
    end = "<!-- STATUS:END -->"
    block = (
        f"{start}\n"
        f"**Обновлено:** `{status['updated_at']}` · "
        f"**Серверов:** `{status['total_nodes']}` · "
        f"**Локаций:** `{status['countries']}` · "
        f"**VPN:** [`{BRAND}`]({BRAND_URL})\n"
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

    write_subscription(SUB_DIR / "happ.txt", renamed)
    write_plain(SUB_DIR / "happ-plain.txt", renamed)

    for old in COUNTRY_DIR.glob("*.txt"):
        old.unlink()
    country_files: dict[str, int] = {}
    for code, links in sorted(by_country.items()):
        trimmed = links[:MAX_PER_COUNTRY_FILE]
        if not trimmed:
            continue
        write_subscription(COUNTRY_DIR / f"{code}.txt", trimmed)
        country_files[code] = len(trimmed)

    # Recommended EU pack for Discord/YouTube from Russia.
    recommended: list[str] = []
    for code in ("FI", "NL", "DE", "SE", "PL", "TR", "GB"):
        recommended.extend(by_country.get(code, [])[:15])
    if recommended:
        write_subscription(SUB_DIR / "discord-youtube.txt", recommended[:80])

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
            "main": f"https://raw.githubusercontent.com/svoyskiy666/VPN-FOR-HAPP-/main/sub/happ.txt",
            "discord_youtube": (
                "https://raw.githubusercontent.com/svoyskiy666/VPN-FOR-HAPP-/main/sub/discord-youtube.txt"
            ),
            "cdn": f"https://cdn.jsdelivr.net/gh/svoyskiy666/VPN-FOR-HAPP-@main/sub/happ.txt",
        },
    }
    (META_DIR / "status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (META_DIR / "last_update.txt").write_text(updated_at + "\n", encoding="utf-8")
    update_readme_status(status)

    print(f"[ok] wrote {len(renamed)} nodes / {len(country_files)} locations / brand={BRAND}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
