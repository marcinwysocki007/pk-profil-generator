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
    "besondere_merkmale": "Langjährige Erfahrung mit Demenz im fortgeschrittenen Stadium sowie sichere Begleitung bei Palliativ- und Sterbephasen",
    "andere_sprachen":    "Polnisch (Muttersprache)",

    # Firmen-Branding (wie in der App) – für realistischen Footer-/Farbtest
    "company_name":  "vitanas",
    "logo_pfad":     "test_assets/vitanas_logo.png",
    "color_primary": "#dd978e",
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


# ── Werte-Filter ─────────────────────────────────────────────────

# Werte ohne Aussage für den Kunden – solche Zeilen werden nicht gezeigt
_LEERWERTE = {
    "", "-", "–", "—", "nicht relevant", "nicht spezifiziert", "nicht angegeben",
    "keine angabe", "keine angaben", "k.a.", "k. a.", "unbekannt", "n/a", "none", "null",
}


def has_value(v) -> bool:
    return v is not None and str(v).strip().lower().rstrip(".") not in _LEERWERTE


# ── Fluss-Layout mit automatischem Seitenumbruch ─────────────────

MX         = 15*mm
KW         = W - 2*MX
GAP        = 6*mm
BOTTOM     = 20*mm      # Inhalte enden oberhalb des Footers (Linie bei 13 mm)
ROW_MIN    = 10*mm
ROW_PAD    = 5.5*mm
LEAD       = 4.5*mm
FONT_SIZE  = 9.5
PAGE_SPACE = H - 15*mm - 40*mm - 8*mm - BOTTOM   # nutzbare Höhe unter dem Header


class Layout:
    """Verfolgt die y-Position und beginnt neue Seiten, wenn der Platz nicht reicht."""

    def __init__(self, c, d):
        self.c, self.d = c, d
        self.y = None
        self.fresh = False   # True, solange auf der aktuellen Seite noch nichts steht

    def new_page(self):
        c, d = self.c, self.d
        if self.y is not None:
            draw_footer(c, d.get("company_name"), d.get("logo_pfad"))
            c.showPage()
        c.setFillColor(C_ROSA_BG)
        c.rect(0, 0, W, H, fill=1, stroke=0)
        hy = draw_header(c, d["name"], d["geschlecht"], d.get("foto_pfad"),
                         d.get("logo_pfad"), d.get("company_name"))
        self.y = hy - 8*mm
        self.fresh = True

    def space(self):
        return self.y - BOTTOM

    def reserve(self, h):
        """Neue Seite, falls ein Block der Höhe h nicht mehr passt."""
        if h > self.space() and not self.fresh:
            self.new_page()

    def advance(self, h):
        self.y -= h + GAP
        self.fresh = False

    def finish(self):
        draw_footer(self.c, self.d.get("company_name"), self.d.get("logo_pfad"))


def _row_geometry(c, label, value, split, right_align):
    lbl_w = KW * split - 12*mm
    val_w = KW * (1 - split) - (9*mm if right_align else 5*mm)
    llines = wrap(c, label, "Arial", FONT_SIZE, lbl_w)
    vlines = wrap(c, str(value), "Arial-B", FONT_SIZE, val_w)
    h = max(ROW_MIN, max(len(llines), len(vlines)) * LEAD + ROW_PAD)
    return llines, vlines, h


def _draw_lines_centered(c, lines, x, row_top, rh, right=False):
    y = row_top - rh / 2 + (len(lines) - 1) * LEAD / 2 - 1.5*mm
    for ln in lines:
        (c.drawRightString if right else c.drawString)(x, y, ln)
        y -= LEAD


def table_card(lay, title, rows, split=0.55, right_align=False, hdr_h=17*mm):
    """Karte mit Titel und Label/Wert-Zeilen. Zeilen ohne Aussage entfallen,
    Zeilen wachsen mit dem Text, bei Platzmangel geht die Karte auf der nächsten Seite weiter."""
    c = lay.c
    rows = [(l, v, lila) for l, v, lila in rows if has_value(v)]
    if not rows:
        return
    geo = [_row_geometry(c, l, v, split, right_align) for l, v, _ in rows]

    # Kleine Karten nicht teilen, sondern komplett auf die nächste Seite
    total = hdr_h + sum(g[2] for g in geo)
    if total <= PAGE_SPACE / 2:
        lay.reserve(total)

    i, first = 0, True
    while i < len(rows):
        # Mindestens zwei Zeilen (oder alle restlichen) sollen unter den Titel passen
        need = hdr_h + sum(g[2] for g in geo[i:i+2])
        lay.reserve(need)

        avail = lay.space() - hdr_h
        j, used = i, 0
        while j < len(rows) and used + geo[j][2] <= avail:
            used += geo[j][2]
            j += 1
        if j == i:                              # Einzelzeile höher als Seite – trotzdem setzen
            used, j = geo[i][2], i + 1
        if len(rows) - j == 1 and j - i >= 3:  # keine einzelne Zeile allein auf der Folgeseite
            j -= 1
            used -= geo[j][2]

        top = lay.y
        card(c, MX, top - hdr_h - used, KW, hdr_h + used)
        c.setFillColor(C_DUNKEL)
        c.setFont("Arial-B", 12)
        c.drawString(MX + 5*mm, top - 10.5*mm, title if first else f"{title} (Fortsetzung)")
        separator(c, MX, top - hdr_h, KW)

        row_top = top - hdr_h
        for k in range(i, j):
            label, _, lila = rows[k]
            llines, vlines, rh = geo[k]
            if k > i:
                separator(c, MX, row_top, KW)
            c.setFillColor(C_GRAU)
            c.setFont("Arial", FONT_SIZE)
            _draw_lines_centered(c, llines, MX + 8*mm, row_top, rh)
            c.setFillColor(C_LILA if lila else C_DUNKEL)
            c.setFont("Arial-B", FONT_SIZE)
            if right_align:
                _draw_lines_centered(c, vlines, MX + KW - 5*mm, row_top, rh, right=True)
            else:
                _draw_lines_centered(c, vlines, MX + KW * split, row_top, rh)
            row_top -= rh

        lay.advance(hdr_h + used)
        i, first = j, False
        if i < len(rows):
            lay.new_page()


def draw_info_box(c, x, y, w, title, text, accent=None, bg=None):
    """Infobox mit linkem Akzentbalken – gibt Höhe zurück."""
    if accent is None:
        accent = C_LILA
    if bg is None:
        bg = C_EMPF
    bh = info_box_height(c, w, text)

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
    draw_text(c, tx, y - 17*mm, text, "Arial", 10, C_GRAU, w - 22*mm, 5.2*mm)

    return bh


def info_box_height(c, w, text):
    lines = wrap(c, text, "Arial", 10, w - 22*mm)
    return max(28*mm, 15*mm + len(lines) * 5.2*mm)


def language_card(lay):
    c, d = lay.c, lay.d
    txt_w = KW - 10*mm
    lines = wrap(c, d.get("deutsch_text", ""), "Arial", 9.5, txt_w)
    # Skala-Beschriftungen enden bei ca. 29 mm unter der Kartenoberkante
    sh = 35*mm + len(lines) * 5*mm + 1*mm
    lay.reserve(sh)
    y = lay.y
    card(c, MX, y - sh, KW, sh)

    draw_flag_de(c, MX + 5*mm, y - 9*mm)
    c.setFillColor(C_DUNKEL)
    c.setFont("Arial-B", 11)
    c.drawString(MX + 14*mm, y - 7.5*mm, "Deutschkenntnisse")

    draw_language_scale(c, MX + 5*mm, y - 19*mm, KW - 10*mm, d["deutsch_level"])

    c.setFillColor(C_GRAU)
    c.setFont("Arial", 9.5)
    ty = y - 34*mm
    for line in lines:
        c.drawString(MX + 5*mm, ty, line)
        ty -= 5*mm
    lay.advance(sh)


# ── Seiten ───────────────────────────────────────────────────────

def section_profil(lay):
    """Seite 1: Über, Deutschkenntnisse, wichtigste Profildetails."""
    c, d = lay.c, lay.d

    if has_value(d.get("beschreibung")):
        bh = info_box_height(c, KW, d["beschreibung"])
        lay.reserve(bh)
        draw_info_box(c, MX, lay.y, KW, f"Über {d['name']}", d["beschreibung"])
        lay.advance(bh)

    language_card(lay)

    table_card(lay, "Wichtigste Profildetails", [
        ("Nationalität",      d.get("nationalitaet"),   True),
        ("Geschlecht",        d.get("geschlecht"),      True),
        ("Alter",             d.get("alter"),           False),
        ("Größe und Gewicht", d.get("groesse_gewicht"), False),
        ("Führerschein",      d.get("fuehrerschein"),   False),
        ("Raucher",           d.get("raucher"),         False),
        ("Pflegeberuf",       d.get("pflegeberuf"),     False),
        ("Pflegeerfahrung",   d.get("erfahrung"),       False),
    ], split=0.45, right_align=True, hdr_h=15*mm)


def section_anforderungen(lay):
    """Seite 2: Anforderungen & weitere Informationen."""
    d = lay.d

    # Anzahl Patienten schöner darstellen: "1 Person" / "3 Personen"
    pat = str(d.get("patienten_anzahl", "")).strip()
    if pat.isdigit():
        pat = f"{pat} Person" if pat == "1" else f"{pat} Personen"

    # Geschlecht: "Alle" → "Keine Präferenz"
    geschl = str(d.get("geschlecht_akzeptiert", "")).strip()
    if geschl.lower() in ("alle", "alle geschlechter", "egal", "beide", "m/w", "männlich/weiblich"):
        geschl = "Keine Präferenz"

    table_card(lay, "Anforderungen & Präferenzen der Betreuungskraft", [
        ("Anzahl Patienten",         pat,                         False),
        ("Geschlecht Patient",       geschl,                      True),
        ("Mobilität",                d.get("mobilitaet"),         True),
        ("Heben & Lagern",           d.get("heben_lagern"),       False),
        ("Demenz akzeptiert",        d.get("demenz"),             False),
        ("Nachteinsätze",            d.get("nachteinsaetze"),     False),
        ("Weitere Personen im Haus", d.get("andere_haushalt"),    False),
        ("Familie in der Nähe",      d.get("familie_naehe"),      False),
        ("Tiere im Haushalt",        d.get("tiere"),              False),
        ("Urbanisierung",            d.get("urbanisierung"),      False),
        ("Unterbringung",            d.get("unterbringung"),      False),
        ("Bevorzugte Gegend",        d.get("praeferierte_gegend"), False),
    ])

    table_card(lay, "Weitere Informationen", [
        ("Persönlichkeit",     d.get("persoenlichkeit"),    False),
        ("Hobbys",             d.get("hobbys"),             False),
        ("Weitere Sprachen",   d.get("andere_sprachen"),    True),
        ("Besondere Merkmale", d.get("besondere_merkmale"), False),
    ])


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

    lay = Layout(c, daten)
    lay.new_page()
    section_profil(lay)
    lay.new_page()
    section_anforderungen(lay)
    lay.finish()
    c.save()

    print(f"PDF erstellt: {output}")
    return output


if __name__ == "__main__":
    generate()
