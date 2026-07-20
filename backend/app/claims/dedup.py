"""Deduplicazione dei documenti.

Pipeline (D.2 della ricerca):
1. normalizzazione URL e rimozione parametri di tracking;
2. hash esatto del contenuto disponibile;
3. SimHash 64-bit su shingles di parole per copie quasi identiche;
4. similarità Jaccard sui shingles come conferma;
5. clustering temporale implicito (i confronti avvengono per security).

Cento articoli che riscrivono la stessa notizia = UNA famiglia di duplicati
= UNA sola origine informativa.
"""
from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "msclkid", "mc_cid", "mc_eid", "ref", "referrer",
    "cmpid", "ito", "ncid", "sr_share", "smid", "partner",
}

_WORD_RE = re.compile(r"[a-zà-ù0-9$%]+")


def normalize_url(url: str) -> str:
    """URL canonico: lowercase host, no tracking params, no fragment, no slash finale."""
    parsed = urlparse(url.strip())
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
             if k.lower() not in TRACKING_PARAMS]
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((
        parsed.scheme.lower() or "https",
        parsed.netloc.lower(),
        path,
        "",
        urlencode(sorted(query)),
        "",
    ))


def content_hash(text: str) -> str:
    normalized = " ".join(_WORD_RE.findall(text.lower()))
    return hashlib.sha256(normalized.encode()).hexdigest()


def _shingles(text: str, k: int = 3) -> list[str]:
    words = _WORD_RE.findall(text.lower())
    if len(words) < k:
        return [" ".join(words)] if words else []
    return [" ".join(words[i:i + k]) for i in range(len(words) - k + 1)]


def simhash(text: str) -> int:
    """SimHash 64-bit su shingles di 3 parole."""
    shingle_list = _shingles(text)
    if not shingle_list:
        return 0
    vector = [0] * 64
    for sh in shingle_list:
        h = int.from_bytes(hashlib.md5(sh.encode()).digest()[:8], "big")
        for bit in range(64):
            vector[bit] += 1 if (h >> bit) & 1 else -1
    result = 0
    for bit in range(64):
        if vector[bit] > 0:
            result |= 1 << bit
    # firma nel range signed 64-bit per il BigInteger del DB
    if result >= 1 << 63:
        result -= 1 << 64
    return result


def hamming_distance(a: int, b: int) -> int:
    return ((a ^ b) & ((1 << 64) - 1)).bit_count()


def jaccard_similarity(text_a: str, text_b: str) -> float:
    sa, sb = set(_shingles(text_a)), set(_shingles(text_b))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


# soglie di duplicazione
SIMHASH_MAX_HAMMING = 8   # pre-filtro veloce su testi lunghi
JACCARD_MIN = 0.5         # conferma quando SimHash è vicino
JACCARD_STRONG = 0.65     # da sola basta (SimHash è instabile su testi brevi)


def is_near_duplicate(text_a: str, text_b: str,
                      simhash_a: int | None = None, simhash_b: int | None = None) -> bool:
    """Quasi-duplicato se: hash esatto uguale, oppure SimHash vicino con
    Jaccard di conferma, oppure similarità Jaccard forte."""
    if content_hash(text_a) == content_hash(text_b):
        return True
    sa = simhash_a if simhash_a is not None else simhash(text_a)
    sb = simhash_b if simhash_b is not None else simhash(text_b)
    if hamming_distance(sa, sb) <= SIMHASH_MAX_HAMMING \
            and jaccard_similarity(text_a, text_b) >= JACCARD_MIN:
        return True
    return jaccard_similarity(text_a, text_b) >= JACCARD_STRONG
