#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import argparse
from datetime import datetime

import pdfplumber
import pandas as pd


# --- Preis (toleriert auch "€ ." wie in manchen Extraktionen) ---
RE_PRICE = re.compile(r"Gesamtpreis\s+(\d{1,3}(?:\.\d{3})*,\d{2})\s*€", re.IGNORECASE)

# --- Datum-Quellen (Priorität) ---
RE_DATE_FAHRTANTRITT = re.compile(r"Fahrtantritt\s+am\s+(\d{2}\.\d{2}\.\d{4})", re.IGNORECASE)
RE_DATE_GUELTIGKEIT  = re.compile(r"Gültigkeit:\s*(\d{2}\.\d{2}\.\d{4})\s*00:00\s*Uhr", re.IGNORECASE)
RE_DATE_AM_ANY       = re.compile(r"\bam\s+(\d{2}\.\d{2}\.\d{4})\b", re.IGNORECASE)  # fallback (z.B. in Überschrift)

# --- Zeile mit Start/Ziel: NUR diese Zeile auswerten, nicht über Zeilenumbruch hinaus! ---
RE_ROUTE_LINE = re.compile(r"^(Einfache\s+Fahrt|Hinfahrt)\s+(.+?)\s*$", re.IGNORECASE | re.MULTILINE)

# Trennzeichen, falls es mal explizit vorhanden ist
RE_ROUTE_SPLIT_SEP = re.compile(r"\s*(?:-|–|—|→|->|›|>|<)\s*")


def normalize_text(text: str) -> str:
    text = text.replace("\r", "\n").replace("\u00A0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_text_from_pdf(path: str) -> str:
    parts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            if t.strip():
                parts.append(t)
    return normalize_text("\n".join(parts))


def to_iso_date(d: str) -> str:
    try:
        return datetime.strptime(d, "%d.%m.%Y").strftime("%Y-%m-%d")
    except ValueError:
        return d


def parse_date(text: str):
    m = RE_DATE_FAHRTANTRITT.search(text)
    if m:
        return to_iso_date(m.group(1))

    m = RE_DATE_GUELTIGKEIT.search(text)
    if m:
        return to_iso_date(m.group(1))

    # Fallback: irgendein "am DD.MM.YYYY" – aber NICHT "Gebucht am ..."
    for m in RE_DATE_AM_ANY.finditer(text):
        # kleiner Schutz gegen Buchungsdatum
        left = text[max(0, m.start() - 30):m.start()].lower()
        if "gebucht" in left:
            continue
        return to_iso_date(m.group(1))

    return None


def parse_price(text: str):
    m = RE_PRICE.search(text)
    return m.group(1) if m else None  # bleibt im Format "99,99"


def score_ending(s: str) -> int:
    s_low = s.lower().strip()
    endings = ("hbf", "hauptbahnhof", "+city", "city", "bf")
    return 3 if any(s_low.endswith(e) for e in endings) else 0


def split_start_ziel(route_part: str):
    route_part = route_part.strip()

    # Wenn Via: doch mal in derselben Zeile landet: abschneiden
    route_part = route_part.split(" Via:", 1)[0].split(" Via", 1)[0].split("Via:", 1)[0].strip()

    # 1) Wenn explizites Trennzeichen da ist:
    parts = RE_ROUTE_SPLIT_SEP.split(route_part, maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        return parts[0].strip(), parts[1].strip()

    # 2) Heuristik: bestes Token-Split anhand typischer Endungen (Hbf, +City, ...)
    tokens = route_part.split()
    if len(tokens) < 2:
        return route_part or None, None

    best = None
    best_score = -10

    for k in range(1, len(tokens)):
        a = " ".join(tokens[:k]).strip()
        b = " ".join(tokens[k:]).strip()

        if not a or not b:
            continue

        score = 0
        score += score_ending(a) + score_ending(b)

        # kleine Plausibilitäten
        if any(c.isalpha() for c in a): score += 1
        if any(c.isalpha() for c in b): score += 1
        if 3 <= len(a) <= 80: score += 1
        if 3 <= len(b) <= 80: score += 1
        if ":" in a or ":" in b: score -= 3

        if score > best_score:
            best_score = score
            best = (a, b)

    return best if best else (route_part, None)


def parse_route(text: str):
    # Nimm die erste passende Zeile "Einfache Fahrt ..." / "Hinfahrt ..."
    m = RE_ROUTE_LINE.search(text)
    if not m:
        return None, None, None

    kind = m.group(1).strip()
    route_part = m.group(2).strip()

    start, ziel = split_start_ziel(route_part)
    return kind, start, ziel


def iter_pdfs(folder: str, recursive: bool):
    if recursive:
        for root, _, files in os.walk(folder):
            for fn in files:
                if fn.lower().endswith(".pdf"):
                    yield os.path.join(root, fn)
    else:
        for fn in os.listdir(folder):
            if fn.lower().endswith(".pdf"):
                yield os.path.join(folder, fn)


def main():
    ap = argparse.ArgumentParser(description="Deutche Bahn (DB) Ticket PDFs -> CSV (Datum/Preis/Start/Ziel)")
    ap.add_argument("folder", help="folder containing PDF-Tickets")
    ap.add_argument("-o", "--out", default="tickets.csv", help="output file CSV (Default: tickets.csv))")
    ap.add_argument("--sep", default=";", help=r"CSV-Trennzeichen (z.B. ';' ',' '\t' '|'). Default: ';'")
    ap.add_argument("--recursive", action="store_true", help="search sufolders recursively")
    ap.add_argument("--encoding", default="utf-8-sig", help="Encoding (Default: utf-8-sig for MS Excel)")
    args = ap.parse_args()

    sep = args.sep.encode("utf-8").decode("unicode_escape")

    pdfs = sorted(iter_pdfs(args.folder, args.recursive))
    if not pdfs:
        raise SystemExit("Keine PDFs gefunden.")

    rows = []
    for p in pdfs:
        try:
            text = extract_text_from_pdf(p)
            rows.append({
                "Datei": os.path.basename(p),
                "Datum": parse_date(text),
                "Preis": parse_price(text),
                "Fahrtart": parse_route(text)[0],
                "Start": parse_route(text)[1],
                "Ziel": parse_route(text)[2],
            })
        except Exception as e:
            rows.append({
                "Datei": os.path.basename(p),
                "Datum": None,
                "Preis": None,
                "Fahrtart": None,
                "Start": None,
                "Ziel": None,
                "Fehler": str(e),
            })

    df = pd.DataFrame(rows)
    df.to_csv(args.out, index=False, sep=sep, encoding=args.encoding)
    print(f"CSV erstellt: {args.out} (sep={repr(sep)})")


if __name__ == "__main__":
    main()
