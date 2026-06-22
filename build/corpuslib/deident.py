"""Respondent de-identification, lifted from cert_layoff_lab's
render_summary.py (the validated implementation behind that repo's privacy
audit). Replaces roster names with pseudonymous refs (R1..Rn); over-redaction
is the safe direction, so ambiguous fuzzy matches redact to a neutral
placeholder. Also carries the District (ALJ) citation helpers."""

import re

_SMALL_WORDS = {"of", "and", "the", "for", "de", "del", "la", "las", "los"}
_ALJ_SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "esq", "esq."}

# Frequent capitalized words in these decisions that must never fuzzy-match
# a roster surname.
_FUZZY_STOP = {
    "district", "respondent", "respondents", "education", "code", "board",
    "accusation", "april", "march", "english", "spanish", "french", "german",
    "county", "school", "services", "section", "american", "resolution",
    "february", "january", "title", "master", "doctor", "found", "order",
    "judge", "court", "state", "notice", "hearing", "evidence", "credential",
}


def title_case(s):
    words = (s or "").strip().split()
    out = []
    for i, w in enumerate(words):
        lw = w.lower()
        out.append(lw if (lw in _SMALL_WORDS and i > 0) else lw.capitalize())
    return " ".join(out)


def district_short(raw):
    """ "SAN JUAN UNIFIED SCHOOL DISTRICT" -> "San Juan Unified" — the
    volumes' citation style keeps the organizational qualifier (Unified,
    Union High, ...) but drops the "School District" tail."""
    t = title_case(raw)
    t = re.sub(r"\s+School District$", "", t)
    t = re.sub(r"\s+District$", "", t)
    return t


def alj_surname(raw):
    toks = [t for t in (raw or "").replace(",", " ").split()
            if t.lower() not in _ALJ_SUFFIXES]
    return toks[-1] if toks else ""


def sub_capitalized(pat, ref, text):
    """pat.subn(ref, text), except all-lowercase matches are left alone."""
    cnt = 0

    def repl(m):
        nonlocal cnt
        if m.group(0).islower():
            return m.group(0)
        cnt += 1
        return ref
    return pat.sub(repl, text), cnt


def _dist1(a, b):
    """Levenshtein distance <= 1 (equal, or one sub/ins/del)."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    if len(a) > len(b):
        a, b = b, a
    for i in range(len(b)):
        if a == b[:i] + b[i + 1:]:
            return True
    return False


def deidentify(text, rec):
    """Replace respondent names with their pseudonymous roster refs (R1..Rn).

    Substitution is deterministic from the record's own roster: full name
    first (longest match), then bare capitalized surname — guarded against
    colliding with the ALJ's surname or the district name, where the same
    string is a different person."""
    ident = rec.get("identity") or {}
    alj = alj_surname((ident.get("alj") or {}).get("raw") or "").lower()
    dist = ((ident.get("district") or {}).get("raw") or "").lower()
    subs = []  # (match string, ref)
    firsts = set()  # roster first-name tokens, for the stranded-name pass
    for r in (rec.get("outcome") or {}).get("roster") or []:
        name, ref = (r.get("name") or "").strip(), r.get("ref")
        if not name or not ref:
            continue
        if "," in name:  # "Last, First" form
            last = name.split(",")[0].strip()
            first = name.split(",", 1)[1].strip()
            subs.append((f"{first} {last}", ref))
        else:
            parts = name.split()
            last, first = parts[-1], parts[0]
        subs.append((name, ref))
        firsts.add(first.split()[0].lower())
        if (len(last) >= 3 and last.lower() != alj
                and last.lower() not in dist):
            subs.append((last, ref))
    subs.sort(key=lambda s: -len(s[0]))
    n = 0
    for s, ref in subs:
        # case-insensitive: rosters are often ALL CAPS while the model writes
        # names in title case. Surname-only substitution skips all-lowercase
        # matches — a surname that is also an English word ("How", "Term")
        # must not eat the common word ("...does not prescribe how...").
        pat = re.compile(rf"\b{re.escape(s)}\b", re.IGNORECASE)
        if " " in s:
            text, k = pat.subn(ref, text)
        else:
            text, k = sub_capitalized(pat, ref, text)
        n += k
    # Fuzzy backstop: extraction sometimes spells a respondent's surname one
    # edit off the roster ("Myer" / "Myers"), which the exact pass misses.
    surnames = {}
    for s, ref in subs:
        # short surnames are exact-match only: at <5 chars, edit-distance-1
        # starts colliding with ordinary capitalized words
        if " " not in s and len(s) >= 5:
            surnames.setdefault(s.lower(), set()).add(ref)
    for tok in set(re.findall(r"\b[A-Z][A-Za-zà-ÿ'\-]{2,}\b", text)):
        tl = tok.lower()
        if tok.isupper() or tl == alj or tl in dist or tl in _FUZZY_STOP:
            continue
        hits = set()
        for sn, refs in surnames.items():
            if abs(len(sn) - len(tl)) <= 1 and _dist1(tl, sn):
                hits |= refs
        if hits:
            repl = hits.pop() if len(hits) == 1 else "[a respondent]"
            text, k = re.subn(rf"\b{re.escape(tok)}\b", repl, text)
            n += k
    # Stranded first names: when only the surname matched (roster spelling
    # drift), the model's "Vickie Ensley" becomes "Vickie R1". Collapse a
    # leading token that is a roster first name onto the ref that follows it.
    def _strand(m):
        nonlocal n
        if m.group(1).lower() in firsts:
            n += 1
            return m.group(2)
        return m.group(0)
    text = re.sub(r"\b([A-Za-zà-ÿ'\-]+)\s+(R\d+\b|\[a respondent\])",
                  _strand, text)
    return text, n
