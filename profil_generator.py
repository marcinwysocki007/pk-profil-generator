#!/usr/bin/env python3
"""
Profil der Betreuungsperson – PDF Generator

Verwendung:
  1. DATEN-Dictionary unten ausfüllen
  2. python3 profil_generator.py
  3. Ausgabe: profil_[name].pdf
"""

import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ================================================================
# DATEN – Hier für jede neue Betreuungsperson anpassen
# ================================================================
DATEN = {
    # Grunddaten
    "name":        "Mariola",
    "geschlecht":  "Weiblich",
    "foto_pfad":   "Mariola-foto.png",

    # Deutschkenntnisse: 0=Grundlegend, 1=Kommunikativ, 2=Sehr gut
    "deutsch_level": 1,
    "deutsch_text": (
        "Die Betreuungsperson kennt einzelne deutsche Wörter und einfache Redewendungen, "
        "versteht jedoch nur wenig zusammenhängende Sprache. "
        "Die Verständigung gelingt vor allem über Gesten und einfache Zeichen – "
        "längere Gespräche sind kaum möglich. "
        "Ergänzende Übersetzungs-Apps erleichtern den Alltag deutlich."
    ),

    # Profildetails Seite 1
    "verfuegbarkeit":  "ab 14.05.26",
    "nationalitaet":   "Polnisch",
    "alter":           "56  (Jg. 1970)",
    "groesse_gewicht": "171–180 cm, 81–90 kg",
    "fuehrerschein":   "Nein",
    "raucher":         "Nein",
    "pflegeberuf":     "Nein",
    "erfahrung":       "7 Jahre",

    # Zusammenfassung (oben im Profil)
    "beschreibung": (
        "Mariola ist eine herzliche und erfahrene Betreuungsperson aus Polen "
        "mit 7 Jahren Erfahrung in der häuslichen Pflege. "
        "Sie verfügt über umfangreiche Erfahrung mit demenzkranken Patienten – "
        "von frühen bis zu fortgeschrittenen Stadien. "
        "Als sehr familiäre Person schätzt sie die gemeinsame Zeit mit den "
        "Betreuten und bringt durch ihre geduldige, einfühlsame Art von Beginn "
        "an Wärme und Vertrauen in jede Betreuungssituation."
    ),

    # Profildetails Seite 2 – Anforderungen
    "patienten_anzahl":      "1",
    "geschlecht_akzeptiert": "Alle",
    "mobilitaet":            "Vollständig mobil, Rollstuhlfähig",
    "heben_lagern":          "Nicht relevant",
    "demenz":                "Nicht relevant",
    "nachteinsaetze":        "Nicht relevant",
    "andere_haushalt":       "Nein",
    "familie_naehe":         "Nicht relevant",
    "tiere":                 "Nicht relevant",
    "urbanisierung":         "Stadt, Großstadt, Dorf",
    "unterbringung":         "",
    "praeferierte_gegend":   "",

    # Persönlichkeit & Extras
    "hobbys":             "Kochen, Sport",
    "persoenlichkeit":    "Hilfsbereit, offen, geduldig, einfühlsam",
    "besondere_merkmale": "Erfahrung mit Demenz (frühes bis fortgeschrittenes Stadium)",
    "andere_sprachen":    "Polnisch (Muttersprache)",
}
# ================================================================

# ── Schriften registrieren ──────────────────────────────────────
_SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
_FONT_LOCAL   = os.path.join(_SCRIPT_DIR, "fonts")
_FONT_MACOS   = "/System/Library/Fonts/Supplemental"
FONT_DIR      = _FONT_LOCAL if os.path.exists(os.path.join(_FONT_LOCAL, "Arial.ttf")) else _FONT_MACOS
pdfmetrics.registerFont(TTFont("Arial",    os.path.join(FONT_DIR, "Arial.ttf")))
pdfmetrics.registerFont(TTFont("Arial-B",  os.path.join(FONT_DIR, "Arial Bold.ttf")))
pdfmetrics.registerFont(TTFont("Arial-I",  os.path.join(FONT_DIR, "Arial Italic.ttf")))
pdfmetrics.registerFont(TTFont("Arial-BI", os.path.join(FONT_DIR, "Arial Bold Italic.ttf")))

# ── Farben aus Hex-String ────────────────────────────────────────
def _hex(h):
    h = h.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return colors.Color(r/255, g/255, b/255)

def _tint(h, t):
    """Mische Primärfarbe mit Weiß: t=0.0 → reine Farbe, t=1.0 → Weiß."""
    h = h.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return colors.Color((r + (255-r)*t)/255, (g + (255-g)*t)/255, (b + (255-b)*t)/255)

def palette_from_hex(primary_hex: str) -> dict:
    """Leitet aus einer Primärfarbe die vollständige Palette ab."""
    return {
        "C_LILA":      _hex(primary_hex),
        "C_LILA_HELL": _tint(primary_hex, 0.45),
        "C_ROSA_BG":   _tint(primary_hex, 0.93),
        "C_EMPF":      _tint(primary_hex, 0.87),
        "C_TRENN":     _tint(primary_hex, 0.72),
    }

# Aktive Farben (werden in generate() gesetzt)
C_LILA      = _hex("#9C2C8C")
C_LILA_HELL = _tint("#9C2C8C", 0.45)
C_ROSA_BG   = _tint("#9C2C8C", 0.93)
C_EMPF      = _tint("#9C2C8C", 0.87)
C_TRENN     = _tint("#9C2C8C", 0.72)
C_KARTE     = colors.white
C_DUNKEL    = colors.Color(30/255,  30/255,  30/255)
C_GRAU      = colors.Color(115/255, 115/255, 115/255)
C_WEISS     = colors.white

W, H = A4   # 595.28 × 841.89 pt


# ── Hilfsfunktionen ─────────────────────────────────────────────

def wrap(c, text, font, size, max_w):
    """Wörter umbrechen → Liste von Zeilen."""
    words = text.split()
    lines, line = [], ""
    for word in words:
        test = (line + " " + word).strip()
        if c.stringWidth(test, font, size) <= max_w:
            line = test
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def wrap_trunc(c, text, font, size, max_w, max_lines=5):
    """Wie wrap(), aber nach max_lines Zeilen mit '...' abschneiden."""
    lines = wrap(c, text, font, size, max_w)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and c.stringWidth(last + " ...", font, size) > max_w:
            last = last.rsplit(" ", 1)[0] if " " in last else last[:-1]
        lines[-1] = last + " ..."
    return lines


def draw_text(c, x, y, text, font, size, color, max_w, leading):
    """Mehrzeiliger Text – gibt neue y-Position zurück."""
    c.setFont(font, size)
    c.setFillColor(color)
    for line in wrap(c, text, font, size, max_w):
        c.drawString(x, y, line)
        y -= leading
    return y


def draw_flag_de(c, x, y, w=7*mm, h=4.5*mm):
    """Kleine deutsche Flagge (Schwarz-Rot-Gold)."""
    bh = h / 3
    for col, offset in [
        (colors.black,                2*bh),
        (colors.Color(.87, .17, .17), bh),
        (colors.Color(1.0, .82, .0),  0),
    ]:
        c.setFillColor(col)
        c.rect(x, y + offset, w, bh, fill=1, stroke=0)


def card(c, x, y, w, h, r=5*mm, bg=C_KARTE):
    """Abgerundete Karte mit Rahmen."""
    c.setFillColor(bg)
    c.setStrokeColor(C_TRENN)
    c.setLineWidth(0.5)
    c.roundRect(x, y, w, h, r, fill=1, stroke=1)


def separator(c, x, y, w):
    c.setStrokeColor(C_TRENN)
    c.setLineWidth(0.3)
    c.line(x + 4*mm, y, x + w - 4*mm, y)


# ── Seitenkomponenten ────────────────────────────────────────────

def draw_header(c, name, geschlecht, foto_pfad=None, logo_pfad=None, company_name=None):
    mx, my = 15*mm, 15*mm
    hw = W - 2*mx
    hh = 40*mm
    hy = H - my - hh   # untere Kante des Headers

    # Lila Hintergrund
    c.setFillColor(C_LILA)
    c.roundRect(mx, hy, hw, hh, 8*mm, fill=1, stroke=0)

    # Foto
    r     = 15.5*mm
    cx_f  = mx + r + 8*mm
    cy_f  = hy + hh / 2

    if foto_pfad and os.path.exists(foto_pfad):
        c.saveState()
        p = c.beginPath()
        p.circle(cx_f, cy_f, r)
        c.clipPath(p, stroke=0, fill=0)
        c.drawImage(foto_pfad, cx_f - r, cy_f - r, 2*r, 2*r,
                    preserveAspectRatio=True, anchor="c")
        c.restoreState()
    else:
        c.setFillColor(colors.Color(1, 1, 1, 0.22))
        c.circle(cx_f, cy_f, r, fill=1, stroke=0)
        c.setFillColor(C_WEISS)
        c.setFont("Arial", 8)
        c.drawCentredString(cx_f, cy_f + 2, "Foto")
        c.setFont("Arial", 7)
        c.drawCentredString(cx_f, cy_f - 6, "einfügen")

    # Weißer Ring ums Foto
    c.setStrokeColor(C_WEISS)
    c.setLineWidth(2)
    c.circle(cx_f, cy_f, r, fill=0, stroke=1)

    # Geschlechts-Badge unten rechts am Foto
    bx = cx_f + r * 0.68
    by = hy + 3.5*mm
    c.setFillColor(C_WEISS)
    c.circle(bx, by, 3.5*mm, fill=1, stroke=0)
    c.setFillColor(C_LILA)
    sym = "♀" if geschlecht == "Weiblich" else "♂"
    c.setFont("Arial", 8)
    c.drawCentredString(bx, by - 2.5, sym)

    # Name & Untertitel
    tx = cx_f + r + 10*mm
    c.setFillColor(colors.Color(1, 1, 1, 0.75))
    c.setFont("Arial", 10)
    c.drawString(tx, hy + hh - 13*mm, "Profil der Betreuungsperson")
    c.setFillColor(C_WEISS)
    c.setFont("Arial-B", 22)
    c.drawString(tx, hy + 10*mm, name)

    return hy   # untere Kante des Headers


def draw_footer(c, company_name=None, logo_pfad=None):
    """Footer mit Firmenlogo links und Claim rechts."""
    if not company_name and not (logo_pfad and os.path.exists(logo_pfad)):
        return
    mx  = 15*mm
    fw  = W - 2*mx
    fy  = 9*mm   # Mittellinie Footer

    # Weißer Hintergrund für Footer
    c.setFillColor(colors.white)
    c.rect(0, 0, W, fy + 6*mm, fill=1, stroke=0)

    # Trennlinie
    c.setStrokeColor(C_TRENN)
    c.setLineWidth(0.4)
    c.line(mx, fy + 4*mm, mx + fw, fy + 4*mm)

    # Logo links
    logo_h = 7*mm
    logo_w = 30*mm
    if logo_pfad and os.path.exists(logo_pfad):
        c.drawImage(logo_pfad, mx, fy - logo_h / 2, logo_w, logo_h,
                    preserveAspectRatio=True, anchor="sw", mask="auto")

    # Text rechts
    if company_name:
        c.setFillColor(C_GRAU)
        c.setFont("Arial", 8)
        c.drawRightString(mx + fw, fy - 2.5, f"Personalprofil exklusiv für Kunden von")
        c.setFont("Arial-B", 8)
        c.setFillColor(C_LILA)
        c.drawRightString(mx + fw, fy - 2.5 - 3.5*mm, company_name)


def draw_language_scale(c, x, y, w, level):
    labels = ["Keine", "Grundlegend", "Kommunikativ", "Gut", "Sehr gut"]
    n   = len(labels) - 1
    gap = (w - 10*mm) / n
    sx  = x + 5*mm

    # Verbindungslinie
    c.setStrokeColor(C_TRENN)
    c.setLineWidth(1.5)
    c.line(sx, y, sx + n*gap, y)

    for i in range(n + 1):
        px = sx + i * gap
        if i == level:
            # Aktiver Punkt – ausgefüllt, Label fett
            c.setFillColor(C_LILA)
            c.circle(px, y, 5*mm, fill=1, stroke=0)
            c.setFillColor(C_LILA)
            c.setFont("Arial-B", 9)
            c.drawCentredString(px, y - 8*mm, labels[i])
        else:
            # Inaktiver Punkt – nur kleiner Kreis + Label
            c.setFillColor(C_TRENN)
            c.circle(px, y, 1.5*mm, fill=1, stroke=0)
            c.setFillColor(C_GRAU)
            c.setFont("Arial", 8)
            c.drawCentredString(px, y - 6*mm, labels[i])


def draw_badge(c, right_x, row_y, text, row_h=9*mm):
    """Lila Verfügbarkeits-Badge."""
    font, size = "Arial-B", 9
    bw  = c.stringWidth(text, font, size) + 8*mm
    bh  = 5.5*mm
    bx  = right_x - bw - 5*mm
    by  = row_y + (row_h - bh) / 2
    c.setFillColor(C_LILA)
    c.roundRect(bx, by, bw, bh, 2.5*mm, fill=1, stroke=0)
    c.setFillColor(C_WEISS)
    c.setFont(font, size)
    c.drawCentredString(bx + bw / 2, by + 1.5*mm, text)


def draw_table_row(c, x, y, w, label, value,
                   row_h=11*mm, lila_val=False, sep=True,
                   label_ratio=0.55):
    if sep:
        separator(c, x, y + row_h, w)
    mid   = x + w * label_ratio
    cy    = y + row_h / 2 - 1.5*mm   # vertikale Mitte der Zeile
    # Label
    c.setFillColor(C_GRAU)
    c.setFont("Arial", 9.5)
    c.drawString(x + 8*mm, cy, label)
    # Wert
    c.setFillColor(C_LILA if lila_val else C_DUNKEL)
    c.setFont("Arial-B", 9.5)
    val_x = mid + 4*mm
    val_w = w - w * label_ratio - 12*mm
    vlines = wrap(c, str(value), "Arial-B", 9.5, val_w)
    n_v    = len(vlines)
    vy     = y + row_h / 2 + (n_v - 1) * 2.25*mm - 1.5*mm
    if n_v == 1:
        c.drawRightString(x + w - 5*mm, cy, vlines[0])
    else:
        for ln in vlines:
            c.drawString(val_x, vy, ln)
            vy -= 4.5*mm


def draw_info_box(c, x, y, w, title, text, accent=None, bg=None):
    """Infobox mit linkem Akzentbalken – gibt Höhe zurück."""
    if accent is None:
        accent = C_LILA
    if bg is None:
        bg = C_EMPF
    text_w = w - 22*mm
    lines  = wrap(c, text, "Arial", 10, text_w)
    bh     = max(28*mm, 16*mm + len(lines) * 5.2*mm)

    card(c, x, y - bh, w, bh, bg=bg)

    # Linker Akzentbalken
    c.setFillColor(accent)
    c.roundRect(x, y - bh, 3.5*mm, bh, 3*mm, fill=1, stroke=0)

    # Titel
    tx = x + 8*mm
    c.setFillColor(C_DUNKEL)
    c.setFont("Arial-B", 11)
    c.drawString(tx, y - 10*mm, title)

    # Text
    draw_text(c, tx, y - 17*mm, text, "Arial", 10, C_GRAU, text_w, 5.2*mm)

    return bh


# ── Seiten ───────────────────────────────────────────────────────

def page1(c, d):
    mx = 15*mm
    kw = W - 2*mx

    # Hintergrund
    c.setFillColor(C_ROSA_BG)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    # Header
    hy = draw_header(c, d["name"], d["geschlecht"], d.get("foto_pfad"), d.get("logo_pfad"), d.get("company_name"))
    y  = hy - 8*mm

    # ── 1. Zusammenfassung (OBEN) ────────────────────────────────
    bh = draw_info_box(c, mx, y, kw, f"Über {d['name']}", d["beschreibung"])
    y -= bh + 6*mm

    # ── 2. Sprachkenntnisse ──────────────────────────────────────
    txt_w    = kw - 10*mm
    txt_font, txt_size, txt_lead = "Arial", 9.5, 5*mm
    dt_lines = wrap(c, d["deutsch_text"], txt_font, txt_size, txt_w)
    # Skala-Beschriftungen enden bei ca. y-32mm → Text erst ab y-36mm
    sh = 40*mm + len(dt_lines) * txt_lead + 4*mm
    card(c, mx, y - sh, kw, sh)

    draw_flag_de(c, mx + 5*mm, y - 9*mm)
    c.setFillColor(C_DUNKEL)
    c.setFont("Arial-B", 11)
    c.drawString(mx + 14*mm, y - 7.5*mm, "Deutschkenntnisse")

    draw_language_scale(c, mx + 5*mm, y - 20*mm, kw - 10*mm, d["deutsch_level"])

    # Trennlinie zwischen Skala und Beschreibungstext
    c.setStrokeColor(C_TRENN)
    c.setLineWidth(0.3)
    c.line(mx + 4*mm, y - 34*mm, mx + kw - 4*mm, y - 34*mm)

    c.setFillColor(C_GRAU)
    c.setFont(txt_font, txt_size)
    ty = y - 37*mm
    for line in dt_lines:
        c.drawString(mx + 5*mm, ty, line)
        ty -= txt_lead
    y -= sh + 6*mm

    # ── 3. Wichtigste Profildetails ──────────────────────────────
    row_h = 11*mm
    rows1 = [
        ("Verfügbarkeit",                  d["verfuegbarkeit"],  "badge"),
        ("Nationalität",                   d["nationalitaet"],   True),
        ("Geschlecht",                     d["geschlecht"],      True),
        ("Alter",                          d["alter"],           False),
        ("Größe und Gewicht",              d["groesse_gewicht"], False),
        ("Führerschein",                   d["fuehrerschein"],   False),
        ("Raucher",                        d["raucher"],         False),
        ("Pflegeberuf",                    d["pflegeberuf"],     False),
        ("Pflegeerfahrung",               d["erfahrung"],       False),
    ]
    hdr1 = 24*mm
    rows1 = [(l, v, vt) for l, v, vt in rows1
             if str(v).strip() not in ("", "-")]
    th = hdr1 + len(rows1) * row_h
    card(c, mx, y - th, kw, th)

    c.setFillColor(C_DUNKEL)
    c.setFont("Arial-B", 12)
    c.drawString(mx + 5*mm, y - 10*mm, "Wichtigste Profildetails")
    separator(c, mx, y - hdr1, kw)

    ry = y - hdr1
    for i, (label, value, vtype) in enumerate(rows1):
        if vtype == "badge":
            if i > 0:
                separator(c, mx, ry + row_h, kw)
            c.setFillColor(C_GRAU)
            c.setFont("Arial", 9.5)
            c.drawString(mx + 8*mm, ry + row_h / 2 - 1.5*mm, label)
            draw_badge(c, mx + kw, ry, value, row_h)
        else:
            draw_table_row(c, mx, ry, kw, label, value,
                           row_h=row_h, lila_val=bool(vtype), sep=(i > 0))
        ry -= row_h

    draw_footer(c, d.get("company_name"), d.get("logo_pfad"))

    y -= th


def page2(c, d):
    mx = 15*mm
    kw = W - 2*mx

    c.setFillColor(C_ROSA_BG)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    hy = draw_header(c, d["name"], d["geschlecht"], d.get("foto_pfad"), d.get("logo_pfad"), d.get("company_name"))
    y  = hy - 8*mm

    def val_ok(v):
        return v and str(v).strip() not in ("", "-")

    # ── Anforderungen ────────────────────────────────────────────
    row_h = 12*mm
    rows2 = [
        ("Anzahl Patienten",           d["patienten_anzahl"],        False),
        ("Geschlecht Patient",         d["geschlecht_akzeptiert"],   True),
        ("Mobilität",                  d["mobilitaet"],              True),
        ("Heben & Lagern",             d["heben_lagern"],            False),
        ("Demenz akzeptiert",          d["demenz"],                  False),
        ("Nachteinsätze",              d["nachteinsaetze"],          False),
        ("Weitere Personen im Haus",   d["andere_haushalt"],         False),
        ("Familie in der Nähe",        d["familie_naehe"],           False),
        ("Tiere im Haushalt",          d.get("tiere", ""),           False),
    ]
    # Optionale Felder nur wenn befüllt
    if val_ok(d.get("urbanisierung")):
        rows2.append(("Urbanisierung", d["urbanisierung"], False))
    if val_ok(d.get("unterbringung")):
        rows2.append(("Unterbringung", d["unterbringung"], False))
    if val_ok(d.get("praeferierte_gegend")):
        rows2.append(("Bevorzugte Gegend", d["praeferierte_gegend"], False))

    # Nur Zeilen mit echtem Wert anzeigen
    rows2 = [(l, v, lv) for l, v, lv in rows2 if val_ok(v)]

    hdr2 = 25*mm
    th = hdr2 + len(rows2) * row_h
    card(c, mx, y - th, kw, th)

    c.setFillColor(C_DUNKEL)
    c.setFont("Arial-B", 12)
    c.drawString(mx + 5*mm, y - 11*mm, "Anforderungen & Präferenzen")
    separator(c, mx, y - hdr2, kw)

    ry = y - hdr2
    for i, (label, value, lila_v) in enumerate(rows2):
        if i > 0:
            separator(c, mx, ry + row_h, kw)

        c.setFillColor(C_GRAU)
        c.setFont("Arial", 9.5)
        label_max = kw * 0.58
        llines = wrap(c, label, "Arial", 9.5, label_max)
        n_l    = len(llines)
        ly     = ry + row_h / 2 + (n_l - 1) * 2.25*mm - 1.5*mm
        for j, ll in enumerate(llines):
            c.drawString(mx + 8*mm, ly - j * 4.5*mm, ll)

        c.setFillColor(C_LILA if lila_v else C_DUNKEL)
        c.setFont("Arial-B", 9.5)
        val_x  = mx + kw * 0.62
        val_w  = kw * 0.38 - 5*mm
        vlines = wrap(c, str(value), "Arial-B", 9.5, val_w)
        n_v    = len(vlines)
        vy     = ry + row_h / 2 + (n_v - 1) * 2.25*mm - 1.5*mm
        for vl in vlines:
            c.drawString(val_x, vy, vl)
            vy -= 4.5*mm

        ry -= row_h

    y -= th + 6*mm

    # ── Persönlichkeit / Extras (nur wenn befüllt) ───────────────
    extra_rows = []
    if val_ok(d.get("persoenlichkeit")):
        extra_rows.append(("Persönlichkeit",       d["persoenlichkeit"],    False))
    if val_ok(d.get("hobbys")):
        extra_rows.append(("Hobbys",               d["hobbys"],             False))
    if val_ok(d.get("besondere_merkmale")):
        bm = str(d["besondere_merkmale"])
        MAX_BM = 120
        if len(bm) > MAX_BM:
            bm = bm[:MAX_BM].rsplit(" ", 1)[0].rstrip(",") + " ..."
        extra_rows.append(("Besondere Merkmale", bm, False))
    if val_ok(d.get("andere_sprachen")):
        extra_rows.append(("Weitere Sprachen",     d["andere_sprachen"],    True))

    if extra_rows:
        hdr3    = 24*mm
        val_x   = mx + kw * 0.55
        val_w   = kw * 0.45 - 5*mm

        # Dynamische Zeilenhöhen – passt sich an langen Texten an
        row_heights = []
        for label, value, lila_v in extra_rows:
            vlines = wrap_trunc(c, str(value), "Arial-B", 9.5, val_w)
            rh = max(row_h, len(vlines) * 4.5*mm + 4*mm)
            row_heights.append(rh)

        eh = hdr3 + sum(row_heights)
        card(c, mx, y - eh, kw, eh)

        c.setFillColor(C_DUNKEL)
        c.setFont("Arial-B", 12)
        c.drawString(mx + 5*mm, y - 11*mm, "Weitere Informationen")
        separator(c, mx, y - hdr3, kw)

        # Top-Down: row_y_top startet am Separator und geht nach unten
        row_y_top = y - hdr3
        for i, (label, value, lila_v) in enumerate(extra_rows):
            rh_i     = row_heights[i]
            center_y = row_y_top - rh_i / 2
            if i > 0:
                separator(c, mx, row_y_top, kw)
            c.setFillColor(C_GRAU)
            c.setFont("Arial", 9.5)
            c.drawString(mx + 8*mm, center_y - 1.5*mm, label)
            c.setFillColor(C_LILA if lila_v else C_DUNKEL)
            c.setFont("Arial-B", 9.5)
            vlines = wrap_trunc(c, str(value), "Arial-B", 9.5, val_w)
            n_v    = len(vlines)
            vy     = center_y + (n_v - 1) * 2.25*mm - 1.5*mm
            for vl in vlines:
                c.drawString(val_x, vy, vl)
                vy -= 4.5*mm
            row_y_top -= rh_i

    draw_footer(c, d.get("company_name"), d.get("logo_pfad"))


# ── Hauptprogramm ────────────────────────────────────────────────

def generate(daten=None, output_path=None):
    global C_LILA, C_LILA_HELL, C_ROSA_BG, C_EMPF, C_TRENN
    if daten is None:
        daten = DATEN

    # Farben aktivieren – entweder custom hex oder Fallback
    primary = daten.get("color_primary", "#9C2C8C")
    bc = palette_from_hex(primary)
    C_LILA      = bc["C_LILA"]
    C_LILA_HELL = bc["C_LILA_HELL"]
    C_ROSA_BG   = bc["C_ROSA_BG"]
    C_EMPF      = bc["C_EMPF"]
    C_TRENN     = bc["C_TRENN"]

    name   = daten["name"]
    output = output_path or f"profil_{name.lower()}.pdf"
    c = pdf_canvas.Canvas(str(output), pagesize=A4)
    c.setTitle(f"Profil der Betreuungsperson – {name}")

    page1(c, daten)
    c.showPage()
    page2(c, daten)
    c.save()

    print(f"PDF erstellt: {output}")
    return output


if __name__ == "__main__":
    generate()
