import re
from collections import Counter

TOKEN_RE = re.compile(r"\S+")

def shape(token):
    t = token.strip("()[]{}<>\"'“”‘’,;")
    if not t:
        return None
    if re.fullmatch(r"https?://\S+", t, re.I):
        return "url"
    if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", t):
        return "email"
    if re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}", t):
        return "ipv4"
    if re.fullmatch(r"v?\d+(?:\.\d+){1,}(?:[-+][A-Za-z0-9.-]+)?", t, re.I):
        return "version_like"
    if re.fullmatch(r"\d{1,2}:\d{2}(?:\s?[AP]M)?", t, re.I):
        return "time_like"
    if re.fullmatch(r"\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}", t):
        return "date_like"
    if re.fullmatch(r"[+-]?(?:\d+\.\d*|\.\d+)", t):
        return "decimal_like"
    if re.fullmatch(r"\d+/\d+", t):
        return "slash_numeric"
    if re.fullmatch(r"\d+(?:\.\d+)?%", t):
        return "percent"
    if re.fullmatch(r"[A-Za-z]+[-_/]?\d+[A-Za-z0-9._/-]*", t) or re.fullmatch(r"\d+[A-Za-z][A-Za-z0-9._/-]*", t):
        return "mixed_alnum"
    if re.fullmatch(r"[A-Z]{2,}s?", t):
        return "uppercase_sequence"
    if any(ch in t for ch in "^_#@/\\:=+"):
        return "symbolic"
    return None

def covered_shapes(records):
    c = Counter()
    for r in records:
        for u in r.get("units", []):
            s = shape(u.get("surface",""))
            if s:
                c[s] += 1
    return c

def discover(text, records, rare_below=3):
    covered = covered_shapes(records)
    candidates, seen = [], set()
    for m in TOKEN_RE.finditer(text):
        token = m.group(0)
        s = shape(token)
        if not s:
            continue
        key = (s, token)
        if key in seen:
            continue
        seen.add(key)
        if covered[s] < rare_below:
            candidates.append({
                "surface": token,
                "shape": s,
                "benchmark_shape_count": covered[s],
                "start": m.start(),
                "end": m.end(),
                "reason": "unseen_shape" if covered[s] == 0 else "rare_shape"
            })
    return candidates
