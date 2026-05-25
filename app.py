import streamlit as st
import anthropic
import json
import os
import re
import io
import base64
import hashlib
import tempfile
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from PIL import Image

from profil_generator import generate


def _color_distance(h1: str, h2: str) -> float:
    r1,g1,b1 = int(h1[1:3],16), int(h1[3:5],16), int(h1[5:7],16)
    r2,g2,b2 = int(h2[1:3],16), int(h2[3:5],16), int(h2[5:7],16)
    return ((r1-r2)**2 + (g1-g2)**2 + (b1-b2)**2) ** 0.5


def extract_dominant_colors(img_bytes: bytes, n: int = 5) -> list:
    """Gibt bis zu n distinkte Markenfarben aus einem Logo zurück."""
    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    bg = Image.new("RGB", img.size, (255, 255, 255))
    bg.paste(img, mask=img.split()[3])
    img = bg.resize((100, 100))
    img_q = img.quantize(colors=16, method=Image.Quantize.FASTOCTREE)
    palette = img_q.getpalette()[:48]  # 16 Farben × 3
    color_counts = {}
    for px in img_q.getdata():
        color_counts[px] = color_counts.get(px, 0) + 1

    def score(idx):
        r, g, b = palette[idx*3], palette[idx*3+1], palette[idx*3+2]
        if max(r,g,b) > 230 or max(r,g,b) < 25:
            return 0
        saturation = max(r,g,b) - min(r,g,b)
        if saturation < 20:
            return 0
        return color_counts.get(idx, 0) * (1 + saturation / 128)

    ranked = sorted(range(16), key=score, reverse=True)
    result = []
    for idx in ranked:
        if len(result) >= n:
            break
        if score(idx) == 0:
            break
        r, g, b = palette[idx*3], palette[idx*3+1], palette[idx*3+2]
        h = "#{:02x}{:02x}{:02x}".format(r, g, b)
        if not any(_color_distance(h, prev) < 35 for prev in result):
            result.append(h)

    return result or ["#6B491A"]


def show_color_swatches(colors: list, selected_key: str, button_key_prefix: str,
                        picker_key: str = None):
    """Zeigt farbige Swatches; Klick setzt selected_key UND picker_key und rerunnt."""
    active = st.session_state.get(selected_key, colors[0] if colors else "#6B491A")
    cols = st.columns(len(colors))
    for i, (col, c) in enumerate(zip(cols, colors)):
        with col:
            border = "2px solid #333" if c == active else "1px solid #ddd"
            st.markdown(
                f'<div style="background:{c};height:28px;border-radius:4px;'
                f'border:{border};margin-bottom:3px"></div>',
                unsafe_allow_html=True,
            )
            if st.button(c, key=f"{button_key_prefix}_{i}", use_container_width=True):
                st.session_state[selected_key] = c
                if picker_key:
                    st.session_state[picker_key] = c  # color_picker Widget-State direkt setzen
                st.rerun()

# ── Pfade ────────────────────────────────────────────────────────
BASE_DIR      = Path(os.path.dirname(os.path.abspath(__file__)))
STORAGE_DIR   = BASE_DIR / "generated_profiles"
COMPANIES_DIR = BASE_DIR / "company_assets"
COMPANIES_FILE = BASE_DIR / "companies.json"
CALC_FILE      = BASE_DIR / "calculations.json"
STORAGE_DIR.mkdir(exist_ok=True)
COMPANIES_DIR.mkdir(exist_ok=True)

# ── Unternehmen laden / speichern ────────────────────────────────
def load_companies() -> dict:
    if COMPANIES_FILE.exists():
        with open(COMPANIES_FILE) as f:
            return json.load(f)
    return {}

def save_companies(data: dict):
    with open(COMPANIES_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    save_companies_to_github(data)


def push_to_github(filename: str, data, binary: bool = False):
    """Schreibt eine Datei via GitHub API ins Repo."""
    import urllib.request
    import urllib.error

    token = st.secrets.get("GITHUB_TOKEN", "") or os.environ.get("GITHUB_TOKEN", "")
    repo  = st.secrets.get("GITHUB_REPO", "") or os.environ.get("GITHUB_REPO", "")
    if not token or not repo:
        return

    url = f"https://api.github.com/repos/{repo}/contents/{filename}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
        "User-Agent": "PK-Profil-App",
    }

    sha = None
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as resp:
            sha = json.loads(resp.read())["sha"]
    except urllib.error.HTTPError as e:
        if e.code != 404:
            return

    if binary:
        content_b64 = base64.b64encode(data).decode()
    else:
        content_b64 = base64.b64encode(
            json.dumps(data, indent=2, ensure_ascii=False).encode()
        ).decode()

    body_dict = {"message": f"Update {filename}", "content": content_b64}
    if sha:
        body_dict["sha"] = sha

    try:
        req = urllib.request.Request(
            url, data=json.dumps(body_dict).encode(), headers=headers, method="PUT"
        )
        urllib.request.urlopen(req)
    except Exception:
        pass


@st.cache_data(ttl=300)
def list_github_profiles() -> list:
    """Gibt Liste von (name, sha) aller PDFs aus generated_profiles/ auf GitHub zurück."""
    import urllib.request, urllib.error
    token = st.secrets.get("GITHUB_TOKEN", "") or os.environ.get("GITHUB_TOKEN", "")
    repo  = st.secrets.get("GITHUB_REPO", "") or os.environ.get("GITHUB_REPO", "")
    if not token or not repo:
        return []
    url = f"https://api.github.com/repos/{repo}/contents/generated_profiles"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json",
               "User-Agent": "PK-Profil-App"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            files = json.loads(resp.read())
        return sorted(
            [(f["name"], f["sha"]) for f in files if f["name"].endswith(".pdf")],
            reverse=True
        )
    except Exception:
        return []


def fetch_github_pdf(sha: str) -> bytes:
    """Lädt PDF-Bytes via GitHub Blob SHA."""
    import urllib.request
    token = st.secrets.get("GITHUB_TOKEN", "") or os.environ.get("GITHUB_TOKEN", "")
    repo  = st.secrets.get("GITHUB_REPO", "") or os.environ.get("GITHUB_REPO", "")
    url = f"https://api.github.com/repos/{repo}/git/blobs/{sha}"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json",
               "User-Agent": "PK-Profil-App"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return base64.b64decode(json.loads(resp.read())["content"])
    except Exception:
        return b""


def save_companies_to_github(data: dict):
    push_to_github("companies.json", data)


def get_logo_path(comp: dict) -> str:
    """Gibt Pfad zum Logo zurück – dekodiert aus base64, wenn lokale Datei fehlt."""
    logo_path = comp.get("logo", "")
    if logo_path and os.path.exists(logo_path):
        return logo_path
    logo_data = comp.get("logo_data", "")
    if not logo_data:
        return ""
    try:
        ext = comp.get("logo_ext", ".png")
        tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
        tmp.write(base64.b64decode(logo_data))
        tmp.close()
        return tmp.name
    except Exception:
        return ""


def load_calculations() -> list:
    if CALC_FILE.exists():
        with open(CALC_FILE) as f:
            return json.load(f)
    # Fallback: aus GitHub laden
    import urllib.request, urllib.error
    token = st.secrets.get("GITHUB_TOKEN", "") or os.environ.get("GITHUB_TOKEN", "")
    repo  = st.secrets.get("GITHUB_REPO", "") or os.environ.get("GITHUB_REPO", "")
    if token and repo:
        try:
            url = f"https://api.github.com/repos/{repo}/contents/calculations.json"
            req = urllib.request.Request(url, headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "PK-Profil-App",
            })
            with urllib.request.urlopen(req) as resp:
                file_info = json.loads(resp.read())
            data = json.loads(base64.b64decode(file_info["content"]))
            with open(CALC_FILE, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return data
        except Exception:
            pass
    return []

def save_calculation_entry(entry: dict):
    calcs = load_calculations()
    calcs.insert(0, entry)
    calcs = calcs[:100]
    with open(CALC_FILE, "w") as f:
        json.dump(calcs, f, indent=2, ensure_ascii=False)
    push_to_github("calculations.json", calcs)

def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")

# ── Sprachtext ───────────────────────────────────────────────────
DEUTSCH_TEXTS = {
    0: "Die Betreuungsperson kennt einige wenige deutsche Wörter, kann sich jedoch kaum verbal verständigen. Die Kommunikation gelingt vor allem über Gesten, einfache Zeichen und Körpersprache. Für den Pflegealltag empfehlen wir Übersetzungs-Apps als ergänzende Hilfe.",
    1: "Die Betreuungsperson spricht einfache Sätze auf Deutsch und kann grundlegende Bedürfnisse und Anweisungen verstehen. Kurze Alltagsgespräche sind möglich, für komplexere Themen ist auf beiden Seiten etwas Geduld gefragt. Die Sprachkenntnisse reichen für den grundlegenden Pflegealltag aus.",
    2: "Die Betreuungsperson verständigt sich in den meisten alltäglichen Situationen sicher auf Deutsch. Gespräche über Tagesabläufe, Wohlbefinden und einfache Anweisungen gelingen zuverlässig. Ein leichter Akzent ist möglich, beeinträchtigt die Verständigung im Pflegealltag jedoch nicht.",
}

# ── Claude ───────────────────────────────────────────────────────
EXTRACTION_PROMPT = """\
Du liest Pflegekraft-Profildaten aus mamamia-Portal-Screenshots aus und gibst ein JSON-Objekt zurück.

Regeln:
- name: NUR Vorname – KEIN Nachname, niemals Familienname
- nachname_initial: NUR der erste Buchstabe des Nachnamens (Großbuchstabe), z.B. "K"
- verfuegbarkeit: Format "ab DD.MM.YY" (z.B. "ab 14.05.26")
- alter: Format "XX (Jg. YYYY)" – oder "" wenn unbekannt
- groesse_gewicht: Format "XXX–XXX cm, XX–XX kg"
- deutsch_level: 0=Grundlegend, 1=Kommunikativ, 2=Sehr gut
- mobilitaet: z.B. "Vollständig mobil, Rollstuhlfähig, Bettlägerig"
- Persönlichkeit + Hobbys: ins Deutsche übersetzen
- beschreibung: PFLICHTFELD – verfasse selbst 3–4 professionelle Sätze auf Deutsch, die die Pflegekraft vorstellen. Nutze dafür Erfahrung, Persönlichkeit, Sprachkenntnisse, Nationalität und besondere Fähigkeiten. Nur Vorname verwenden. Niemals leer lassen.
- besondere_merkmale: akzeptierte Erkrankungen / besondere Fähigkeiten zusammenfassen
- heben_lagern, demenz, nachteinsaetze, andere_haushalt, familie_naehe, tiere: Verwende exakt "Ja", "Nein" oder "Nicht relevant" (nicht "Unwichtig", nicht "kein Problem" o.ä.)
- NIEMALS aufnehmen: Nachname, Telefonnummer, E-Mail, Adresse, Gehalt, Kontonummer

Antworte NUR mit dem JSON-Objekt:
{
  "name": "", "nachname_initial": "", "geschlecht": "Weiblich", "verfuegbarkeit": "",
  "nationalitaet": "", "alter": "", "groesse_gewicht": "",
  "fuehrerschein": "", "raucher": "", "pflegeberuf": "", "erfahrung": "",
  "deutsch_level": 2,
  "patienten_anzahl": "", "geschlecht_akzeptiert": "", "mobilitaet": "",
  "heben_lagern": "", "demenz": "", "nachteinsaetze": "",
  "andere_haushalt": "", "familie_naehe": "", "tiere": "",
  "urbanisierung": "", "unterbringung": "", "praeferierte_gegend": "",
  "hobbys": "", "persoenlichkeit": "", "besondere_merkmale": "",
  "andere_sprachen": "", "beschreibung": ""
}"""


def get_client():
    key = st.secrets.get("ANTHROPIC_API_KEY", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        st.error("ANTHROPIC_API_KEY fehlt. Bitte in den App-Einstellungen hinterlegen.")
        st.stop()
    return anthropic.Anthropic(api_key=key)


def extract_from_images(files, client) -> dict:
    content = []
    for f in files:
        data = f.read()
        mt = "image/jpeg" if f.name.lower().endswith((".jpg", ".jpeg")) else "image/png"
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": mt,
                       "data": base64.b64encode(data).decode()}
        })
    content.append({"type": "text", "text": EXTRACTION_PROMPT})
    resp = get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": content}]
    )
    raw = resp.content[0].text
    return json.loads(raw[raw.find("{"):raw.rfind("}") + 1])


def build_daten(ext: dict, foto_path: str, company: dict) -> dict:
    level = int(ext.get("deutsch_level", 2))
    return {
        "color_primary":         company.get("color_primary", "#9C2C8C"),
        "logo_pfad":             get_logo_path(company),
        "company_name":          company.get("name", ""),
        "name":                  ext.get("name", "Unbekannt"),
        "nachname_initial":      ext.get("nachname_initial", "").upper()[:1],
        "geschlecht":            ext.get("geschlecht", "Weiblich"),
        "foto_pfad":             foto_path,
        "deutsch_level":         level,
        "deutsch_text":          DEUTSCH_TEXTS.get(level, DEUTSCH_TEXTS[2]),
        "verfuegbarkeit":        ext.get("verfuegbarkeit", ""),
        "nationalitaet":         ext.get("nationalitaet", ""),
        "alter":                 ext.get("alter", ""),
        "groesse_gewicht":       ext.get("groesse_gewicht", ""),
        "fuehrerschein":         ext.get("fuehrerschein", ""),
        "raucher":               ext.get("raucher", ""),
        "pflegeberuf":           ext.get("pflegeberuf", ""),
        "erfahrung":             ext.get("erfahrung", ""),
        "beschreibung":          ext.get("beschreibung", ""),
        "patienten_anzahl":      ext.get("patienten_anzahl", ""),
        "geschlecht_akzeptiert": ext.get("geschlecht_akzeptiert", ""),
        "mobilitaet":            ext.get("mobilitaet", ""),
        "heben_lagern":          ext.get("heben_lagern", ""),
        "demenz":                ext.get("demenz", ""),
        "nachteinsaetze":        ext.get("nachteinsaetze", ""),
        "andere_haushalt":       ext.get("andere_haushalt", ""),
        "familie_naehe":         ext.get("familie_naehe", ""),
        "tiere":                 ext.get("tiere", ""),
        "urbanisierung":         ext.get("urbanisierung", ""),
        "unterbringung":         ext.get("unterbringung", ""),
        "praeferierte_gegend":   ext.get("praeferierte_gegend", ""),
        "hobbys":                ext.get("hobbys", ""),
        "persoenlichkeit":       ext.get("persoenlichkeit", ""),
        "besondere_merkmale":    ext.get("besondere_merkmale", ""),
        "andere_sprachen":       ext.get("andere_sprachen", ""),
    }


def make_pdf(daten: dict) -> tuple[str, bytes]:
    vorname  = daten["name"].split()[0] if daten["name"].strip() else "Profil"
    initial  = daten.get("nachname_initial", "").upper()[:1]
    firma    = re.sub(r"[^a-zA-Z0-9äöüÄÖÜß]", "", daten.get("company_name", "Firma"))
    name_part = f"{vorname}-{initial}" if initial else vorname
    filename  = f"{name_part}_{firma}.pdf"
    out_path  = STORAGE_DIR / filename
    generate(daten, output_path=str(out_path))
    with open(out_path, "rb") as f:
        return filename, f.read()


# ── Preiskalkulator Konfiguration ────────────────────────────────

BASE_PRICE = 2150

# Beschreibungen nur für Sprachlevel
OPTION_DESCRIPTIONS = {
    "Deutschkenntnisse": {
        "Grundlegend":  "Grundlegend – einfache Sätze, wenig Konversation (A1/A2)",
        "Kommunikativ": "Kommunikativ – Alltagsgespräche gut möglich (B1/B2)",
        "Sehr gut":     "Sehr gut – fließend, auch im Pflegealltag sicher (C1/C2)",
    },
}

PRICE_CONFIG = OrderedDict([
    ("Betreuung für",               OrderedDict([("1 Patient", 0), ("2 Patienten", 300)])),
    ("Weitere Personen im Haushalt", OrderedDict([("Nein", 0), ("Ja", 200)])),
    ("Deutschkenntnisse",           OrderedDict([("Grundlegend", 0), ("Kommunikativ", 300), ("Sehr gut", 600)])),
    ("Erfahrung",                   OrderedDict([("Einsteiger", 0), ("Erfahren", 0), ("Sehr erfahren", 150)])),
    ("Führerschein",                OrderedDict([("Egal", 0), ("Ja", 100), ("Nein", 0)])),
    ("Geschlecht",                  OrderedDict([("Egal", 0), ("Weiblich", 0), ("Männlich", 0)])),
    ("Mobilität",                   OrderedDict([
        ("Mobil – geht selbstständig", 0),
        ("Eingeschränkt – nur mit Rollator", 0),
        ("Auf Rollstuhl angewiesen", 100),
        ("Bettlägerig", 100),
    ])),
    ("Nachteinsätze",               OrderedDict([("Nein", 0), ("Gelegentlich", 50), ("Täglich (1×)", 100), ("Mehrmals nachts", 300)])),
    ("Pflegegrad",                  OrderedDict([
        ("Kein Pflegegrad", 0), ("Pflegegrad 1", 0), ("Pflegegrad 2", 0),
        ("Pflegegrad 3", 0), ("Pflegegrad 4", 0), ("Pflegegrad 5", 50),
    ])),
])

PRICE_PROMPT = """\
Analysiere die Patienteninformationen und ordne sie den Preiskategorien zu.
Wähle immer exakt eine der aufgeführten Optionen – kein Freitext.

Wichtige Unterscheidung bei "Betreuung für":
- "2 Patienten": NUR wenn beide Personen aktiv gepflegt/betreut werden müssen
- "1 Patient": wenn eine Person der Patient ist und der Partner/Mitbewohner
  selbstständig ist, mithilft oder einfach im Haushalt lebt → dann
  "Weitere Personen im Haushalt" = "Ja"

Kategorien und gültige Optionen:
- Betreuung für: "1 Patient" | "2 Patienten"
- Weitere Personen im Haushalt: "Nein" | "Ja"
- Deutschkenntnisse: "Grundlegend" | "Kommunikativ" | "Sehr gut"
- Erfahrung: "Einsteiger" | "Erfahren" | "Sehr erfahren"
- Führerschein: "Egal" | "Ja" | "Nein"
- Geschlecht: "Egal" | "Weiblich" | "Männlich"
- Mobilität: "Mobil – geht selbstständig" | "Eingeschränkt – nur mit Rollator" | "Auf Rollstuhl angewiesen" | "Bettlägerig"
- Nachteinsätze: "Nein" | "Gelegentlich" | "Täglich (1×)" | "Mehrmals nachts"
- Pflegegrad: "Kein Pflegegrad" | "Pflegegrad 1" | "Pflegegrad 2" | "Pflegegrad 3" | "Pflegegrad 4" | "Pflegegrad 5"

Wenn eine Info fehlt oder unklar ist → günstigste/neutralste Option.
Antworte NUR mit dem JSON-Objekt:
{
  "Betreuung für": "...",
  "Weitere Personen im Haushalt": "...",
  "Deutschkenntnisse": "...",
  "Erfahrung": "...",
  "Führerschein": "...",
  "Geschlecht": "...",
  "Mobilität": "...",
  "Nachteinsätze": "...",
  "Pflegegrad": "..."
}"""


def extract_price_fields(text: str, image_files: list, client) -> dict:
    """Liest Patienteninfos aus und gibt Preiskategorien-Zuordnung zurück."""
    content = []
    for f in image_files:
        data = f.read()
        mt = "image/jpeg" if f.name.lower().endswith((".jpg", ".jpeg")) else "image/png"
        content.append({"type": "image",
                         "source": {"type": "base64", "media_type": mt,
                                    "data": base64.b64encode(data).decode()}})
    if text.strip():
        content.append({"type": "text", "text": f"Patienteninfos:\n{text.strip()}"})
    content.append({"type": "text", "text": PRICE_PROMPT})

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{"role": "user", "content": content}],
    )
    raw = resp.content[0].text
    return json.loads(raw[raw.find("{"):raw.rfind("}") + 1])


# ── Streamlit Layout ─────────────────────────────────────────────

st.set_page_config(page_title="Lennarts Generator", page_icon="📋", layout="centered")

st.markdown("""
<style>
/* ── Layout ── */
.block-container { max-width: 800px; padding-top: 2rem; padding-bottom: 3rem; }

/* ── Hauptbereich: weißer Inhalts-Container ── */
section[data-testid="stMain"] > div > div > div > div {
    background: transparent;
}

/* ── Eingabefelder: weiß mit klarer Border ── */
.stTextInput input,
.stTextArea textarea,
.stNumberInput input {
    background: white !important;
    border: 1.5px solid #e0e0e0 !important;
    border-radius: 8px !important;
    color: #1a1a1a !important;
}
.stTextInput input:focus,
.stTextArea textarea:focus,
.stNumberInput input:focus {
    border-color: #1a1a1a !important;
    box-shadow: 0 0 0 3px rgba(26,26,26,0.08) !important;
}

/* ── Selectbox ── */
.stSelectbox > div > div {
    background: white !important;
    border: 1.5px solid #e0e0e0 !important;
    border-radius: 8px !important;
}

/* ── Expander ── */
.streamlit-expanderHeader {
    border-radius: 10px !important;
    font-weight: 600 !important;
}

/* ── Buttons ── */
.stButton > button {
    border-radius: 8px;
    font-weight: 600;
    border: 1.5px solid #e0e0e0;
    transition: all 0.15s ease;
}
.stButton > button:hover {
    border-color: #1a1a1a;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}
.stButton > button[kind="primary"] {
    background: #1a1a1a !important;
    color: white !important;
    border-color: #1a1a1a !important;
}

/* ── Divider ── */
hr { border-color: #e8e8e8 !important; margin: 1.5rem 0 !important; }

/* ── Metric-Karten ── */
[data-testid="metric-container"] {
    background: white;
    border: 1px solid #e8e8e8;
    border-radius: 12px;
    padding: 1rem 1.2rem;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05);
}

/* ── Tabs – subtil ── */
.stTabs [data-baseweb="tab-list"] {
    gap: 2px;
    background: transparent;
    padding: 0;
    border-bottom: 1px solid #e0e0e0;
    margin-bottom: 1.8rem;
}
.stTabs [data-baseweb="tab"] {
    height: 38px;
    padding: 0 20px;
    font-size: 0.9rem;
    font-weight: 500;
    border-radius: 0;
    color: #999;
    background: transparent;
}
.stTabs [aria-selected="true"] {
    background: transparent !important;
    color: #1a1a1a !important;
    border-bottom: 2px solid #1a1a1a !important;
    font-weight: 700 !important;
}
.stTabs [data-baseweb="tab"]:hover:not([aria-selected="true"]) {
    color: #555 !important;
    background: transparent !important;
}
.stTabs [data-baseweb="tab-highlight"] { display: none; }
.stTabs [data-baseweb="tab-border"] { display: none; }

/* ── Primary Action Buttons – sehr prominent ── */
.stButton > button[kind="primary"] {
    background: #1a1a1a !important;
    color: white !important;
    border: none !important;
    border-radius: 10px !important;
    padding: 0.6rem 1.5rem !important;
    font-size: 1.05rem !important;
    font-weight: 700 !important;
    box-shadow: 0 4px 14px rgba(0,0,0,0.18) !important;
    transition: all 0.15s ease !important;
}
.stButton > button[kind="primary"]:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 20px rgba(0,0,0,0.24) !important;
}
</style>
""", unsafe_allow_html=True)

# ── Sidebar: Unternehmens-Verwaltung ─────────────────────────────
with st.sidebar:
    st.header("Unternehmen")

    companies = load_companies()

    if companies:
        for cid, comp in list(companies.items()):
            with st.expander(comp["name"]):
                new_name  = st.text_input("Name", comp["name"], key=f"n_{cid}")
                default_c = st.session_state.get(f"_auto_{cid}", comp.get("color_primary", "#6B491A"))
                new_color = st.color_picker("Primärfarbe", default_c, key=f"c_{cid}")

                logo_upload = st.file_uploader("Logo (PNG/JPG)", type=["png","jpg","jpeg"],
                                               key=f"l_{cid}")
                if logo_upload:
                    logo_bytes = logo_upload.read()
                    logo_path = str(COMPANIES_DIR / f"{cid}_logo{Path(logo_upload.name).suffix}")
                    with open(logo_path, "wb") as f:
                        f.write(logo_bytes)
                    comp["logo"]      = logo_path
                    comp["logo_data"] = base64.b64encode(logo_bytes).decode()
                    comp["logo_ext"]  = Path(logo_upload.name).suffix
                    logo_hash = hashlib.md5(logo_bytes).hexdigest()
                    if st.session_state.get(f"_logo_hash_{cid}") != logo_hash:
                        colors_list = extract_dominant_colors(logo_bytes)
                        st.session_state[f"_colors_{cid}"]    = colors_list
                        st.session_state[f"_auto_{cid}"]      = colors_list[0]
                        st.session_state[f"_logo_hash_{cid}"] = logo_hash
                    st.image(logo_bytes, width=120)
                elif comp.get("logo") and os.path.exists(comp["logo"]):
                    st.image(comp["logo"], width=120)
                elif comp.get("logo_data"):
                    st.image(base64.b64decode(comp["logo_data"]), width=120)

                colors_list = st.session_state.get(f"_colors_{cid}", [])
                if colors_list:
                    st.caption("Farben aus dem Logo – klicken zum Auswählen:")
                    show_color_swatches(colors_list, f"_auto_{cid}", f"sw_{cid}",
                                        picker_key=f"c_{cid}")

                col_s, col_d = st.columns(2)
                with col_s:
                    if st.button("Speichern", key=f"s_{cid}"):
                        new_id = slug(new_name)
                        comp["name"]          = new_name
                        comp["color_primary"] = new_color
                        if new_id != cid:
                            companies[new_id] = companies.pop(cid)
                        save_companies(companies)
                        st.rerun()
                with col_d:
                    if st.button("Löschen", key=f"del_{cid}", type="secondary"):
                        del companies[cid]
                        save_companies(companies)
                        st.rerun()

    st.divider()
    st.subheader("Neues Unternehmen")
    new_co_name = st.text_input("Name", key="new_co_name")
    new_co_logo = st.file_uploader("Logo (optional)", type=["png","jpg","jpeg"],
                                   key="new_co_logo")

    # Farbe aus Logo extrahieren oder manuell wählen
    if new_co_logo:
        logo_bytes = new_co_logo.read()
        new_co_logo.seek(0)
        logo_hash = hashlib.md5(logo_bytes).hexdigest()
        if st.session_state.get("_new_co_logo_hash") != logo_hash:
            colors_list = extract_dominant_colors(logo_bytes)
            st.session_state["_new_co_colors"]    = colors_list
            st.session_state["_new_co_auto_color"] = colors_list[0]
            st.session_state["_new_co_logo_hash"]  = logo_hash
        st.image(logo_bytes, width=100)

    new_co_colors = st.session_state.get("_new_co_colors", [])
    if new_co_colors:
        st.caption("Farben aus dem Logo – klicken zum Auswählen:")
        show_color_swatches(new_co_colors, "_new_co_auto_color", "sw_new",
                            picker_key="new_co_color")

    default_color = st.session_state.get("_new_co_auto_color", "#6B491A")
    new_co_color  = st.color_picker("Primärfarbe", default_color, key="new_co_color")

    if st.button("Unternehmen anlegen", use_container_width=True):
        if new_co_name.strip():
            cid = slug(new_co_name)
            logo_path = ""
            logo_b64  = ""
            logo_ext  = ""
            if new_co_logo:
                new_co_logo.seek(0)
                logo_bytes_new = new_co_logo.read()
                logo_path = str(COMPANIES_DIR / f"{cid}_logo{Path(new_co_logo.name).suffix}")
                with open(logo_path, "wb") as f:
                    f.write(logo_bytes_new)
                logo_b64 = base64.b64encode(logo_bytes_new).decode()
                logo_ext = Path(new_co_logo.name).suffix
            companies[cid] = {
                "name":          new_co_name.strip(),
                "color_primary": new_co_color,
                "logo":          logo_path,
                "logo_data":     logo_b64,
                "logo_ext":      logo_ext,
            }
            save_companies(companies)
            st.session_state.pop("_new_co_auto_color", None)
            st.rerun()
        else:
            st.warning("Bitte einen Namen eingeben.")

# ── Hauptbereich: Profil erstellen ───────────────────────────────
st.title("Lennarts Generator")

tab1, tab2 = st.tabs(["📋  Pflegeprofil erstellen", "💰  Preiskalkulator"])

# ════════════════════════════════════════════════════════════════
# TAB 1 – Pflegeprofil
# ════════════════════════════════════════════════════════════════
with tab1:
    st.caption("Foto + Portal-Screenshots hochladen — PDF wird automatisch erstellt")

    companies = load_companies()
    if not companies:
        st.warning("Bitte zuerst ein Unternehmen in der Seitenleiste anlegen.")
        st.stop()

    company_options = {v["name"]: k for k, v in companies.items()}
    selected_name   = st.selectbox("Unternehmen", list(company_options.keys()))
    selected_id     = company_options[selected_name]
    selected_co     = companies[selected_id]

    # Farbvorschau
    st.markdown(
        f'<div style="display:inline-block;width:18px;height:18px;border-radius:4px;'
        f'background:{selected_co.get("color_primary","#000")};vertical-align:middle;'
        f'margin-right:8px"></div>'
        f'<span style="color:gray;font-size:0.85em">{selected_co.get("color_primary","")}</span>',
        unsafe_allow_html=True
    )
    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        photo_file = st.file_uploader("Foto der Pflegekraft",
                                      type=["jpg","jpeg","png"])
    with col2:
        screenshot_files = st.file_uploader("Portal-Screenshots (1–10)",
                                            type=["jpg","jpeg","png"],
                                            accept_multiple_files=True)

    if st.button("Profil erstellen", type="primary", use_container_width=True, icon="🚀"):
        if not photo_file:
            st.error("Bitte ein Foto hochladen.")
        elif not screenshot_files:
            st.error("Bitte mindestens einen Portal-Screenshot hochladen.")
        else:
            with st.status("Daten werden ausgelesen…", expanded=True) as status:
                try:
                    st.write("Claude liest die Screenshots aus…")
                    extracted = extract_from_images(screenshot_files, get_client())
                    name = extracted.get("name", "Unbekannt")
                    st.write(f"Erkannt: **{name}** · {extracted.get('verfuegbarkeit','?')}")

                    suffix = Path(photo_file.name).suffix
                    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
                    tmp.write(photo_file.read())
                    tmp.close()

                    daten = build_daten(extracted, tmp.name, selected_co)

                    st.write("PDF wird generiert…")
                    filename, pdf_bytes = make_pdf(daten)
                    os.unlink(tmp.name)
                    push_to_github(f"generated_profiles/{filename}", pdf_bytes, binary=True)

                    status.update(label="Fertig!", state="complete")
                    st.success(f"Profil für **{name}** ({selected_name}) erstellt")
                    st.download_button("PDF herunterladen", data=pdf_bytes,
                                       file_name=filename, mime="application/pdf",
                                       use_container_width=True, icon="📥")

                except json.JSONDecodeError:
                    status.update(state="error")
                    st.error("Daten konnten nicht ausgelesen werden.")
                except Exception as e:
                    status.update(state="error")
                    st.error(f"Fehler: {e}")

    st.divider()
    st.subheader("Gespeicherte Profile")
    local_pdfs = sorted(STORAGE_DIR.glob("*.pdf"), key=os.path.getmtime, reverse=True)

    if local_pdfs:
        for pdf_path in local_pdfs[:30]:
            mtime = datetime.fromtimestamp(os.path.getmtime(pdf_path))
            col_a, col_b = st.columns([4, 1])
            with col_a:
                st.write(f"📄 {pdf_path.stem} — {mtime.strftime('%d.%m.%Y %H:%M')}")
            with col_b:
                with open(pdf_path, "rb") as f:
                    st.download_button("↓", data=f.read(), file_name=pdf_path.name,
                                       mime="application/pdf", key=str(pdf_path))
    else:
        col_info, col_load = st.columns([3, 1])
        with col_info:
            st.info("Keine lokalen Profile – aus GitHub laden?")
        with col_load:
            if st.button("🔄 Laden", key="load_gh_profiles"):
                st.session_state["gh_profiles_loaded"] = True

        if st.session_state.get("gh_profiles_loaded"):
            with st.spinner("Profile werden geladen…"):
                gh_profiles = list_github_profiles()
            if gh_profiles:
                for name_gh, sha in gh_profiles[:30]:
                    col_a, col_b = st.columns([4, 1])
                    with col_a:
                        st.write(f"📄 {Path(name_gh).stem}")
                    with col_b:
                        if st.button("↓", key=f"gh_{sha}"):
                            with st.spinner("Lade…"):
                                pdf_data = fetch_github_pdf(sha)
                            if pdf_data:
                                st.download_button("Speichern", data=pdf_data,
                                                   file_name=name_gh, mime="application/pdf",
                                                   key=f"dl_{sha}")
            else:
                st.info("Noch keine Profile in GitHub.")


# ════════════════════════════════════════════════════════════════
# TAB 2 – Preiskalkulator
# ════════════════════════════════════════════════════════════════
with tab2:
    st.caption("Patienteninfos hochladen oder einfügen – Felder werden automatisch vorausgefüllt.")

    # ── Patienteninfos hochladen ──────────────────────────────────
    with st.expander("📂 Patienteninfos auslesen (optional)", expanded=True):
        patient_text  = st.text_area("Freitext (Anfrage, Beschreibung, Notizen…)",
                                     height=120, key="calc_text",
                                     placeholder="z.B. 'Ehepaar, PG3, braucht Rollstuhl, keine Nachteinsätze…'")
        patient_imgs  = st.file_uploader("Oder Screenshots / Bilder hochladen",
                                         type=["jpg","jpeg","png"],
                                         accept_multiple_files=True, key="calc_imgs")
        if st.button("Felder automatisch ausfüllen", key="calc_extract",
                     use_container_width=True, icon="🔍"):
            if not patient_text.strip() and not patient_imgs:
                st.warning("Bitte Text eingeben oder Bilder hochladen.")
            else:
                with st.spinner("Claude liest die Anforderungen aus…"):
                    try:
                        result = extract_price_fields(patient_text, patient_imgs or [], get_client())
                        for cat, options in PRICE_CONFIG.items():
                            val = result.get(cat)
                            if val and val in options:
                                st.session_state[f"calc_radio_{cat}"] = val
                        st.success("Felder wurden vorausgefüllt – bitte prüfen und anpassen.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Fehler beim Auslesen: {e}")

    st.divider()

    # ── Preisfelder ───────────────────────────────────────────────
    total = BASE_PRICE
    surcharges = []

    for cat, options in PRICE_CONFIG.items():
        opt_list = list(options.keys())

        # Label mit Aufpreis-Hinweisen + optionaler Beschreibung
        descs = OPTION_DESCRIPTIONS.get(cat, {})
        def fmt(o, opts=options, d=descs):
            label = d.get(o, o)
            p = opts[o]
            return f"{label}  (+{p} €)" if p > 0 else label

        selected = st.radio(cat, opt_list, index=0,
                            format_func=fmt, horizontal=not bool(descs),
                            key=f"calc_radio_{cat}")
        surcharge = options[selected]
        if surcharge > 0:
            surcharges.append((cat, selected, surcharge))
        total += surcharge

    # ── Partnerprovision ──────────────────────────────────────────
    st.divider()
    col_pv1, col_pv2 = st.columns([2, 1])
    with col_pv1:
        provision_input = st.number_input("Partnerprovision (€)", min_value=0.0,
                                          value=10.0, step=1.0, format="%.2f",
                                          key="calc_provision")
    with col_pv2:
        provision_unit = st.radio("pro", ["Monat", "Tag"], horizontal=True,
                                  index=1, key="calc_provision_unit")

    provision_eur = provision_input if provision_unit == "Monat" else provision_input * 30
    gesamt        = total + provision_eur

    # ── Preisanzeige ──────────────────────────────────────────────
    def fmt_eur(v):
        return f"{v:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")

    if surcharges or provision_input > 0:
        with st.expander("Aufschläge im Detail", expanded=False):
            st.write(f"Basispreis 24h-Betreuung: **{fmt_eur(BASE_PRICE)}**")
            for cat, sel, val in surcharges:
                st.write(f"+ {cat} ({sel}): **+{fmt_eur(val)}**")
            if provision_input > 0:
                label = f"{fmt_eur(provision_input)}/Tag × 30" if provision_unit == "Tag" else f"{fmt_eur(provision_input)}/Monat"
                st.write(f"+ Partnerprovision ({label}): **+{fmt_eur(provision_eur)}**")

    col_m, col_t = st.columns(2)
    with col_m:
        st.metric("💶 Monatssatz", fmt_eur(gesamt))
    with col_t:
        st.metric("📅 Tagessatz", fmt_eur(gesamt / 30))

    # ── Antwort + Speichern ───────────────────────────────────────
    st.divider()

    anfrage_text = st.session_state.get("calc_text", "").strip()
    monat_str    = fmt_eur(gesamt)

    if provision_input > 0:
        preis_info = (
            f"{fmt_eur(total)} zzgl. Ihrer Provision {fmt_eur(provision_eur)} "
            f"= {monat_str} gesamt"
        )
    else:
        preis_info = f"{monat_str} pro Monat"

    if st.button("✍️ Antwort generieren", key="gen_response", use_container_width=True):
        response_prompt = f"""Erstelle aus der folgenden Anfrage zwei Dinge:

1. Einen kurzen Geschäftsbrief auf Deutsch. Halte dich exakt an diese Struktur – nicht mehr, nicht weniger:

   "Guten Tag [nur Herr/Frau + Nachname des Absenders – niemals Vorname],

   für Ihren Kunden [Patientenname und Ort] übermittle ich Ihnen 2 passende Personalvorschläge. [Ein einziger kurzer Satz, der zeigt dass wir die Situation gelesen haben – die wichtigste Anforderung oder Besonderheit in einem Halbsatz, ohne alles aufzuzählen.]

   Die Kosten liegen bei {preis_info}, zzgl. Fahrtkosten 125 € pro Strecke.

   Bitte geben Sie uns kurz Bescheid, damit wir die Pflegekraft festmachen können. 😊"

   Regeln:
   - Genau diese 4 Absätze – der situative Satz gehört zu Absatz 2, kein eigener Absatz
   - Maximal 1 Satz zur Situation, keine Aufzählung
   - Falls kein Absendername erkennbar: "Guten Tag,"
   - Niemals den Vornamen verwenden, immer nur Herr/Frau + Nachname
   - Falls kein Patientenname erkennbar: "für Ihren Kunden"

2. Eine kurze interne Bezeichnung (z.B. "Familie Müller – Berlin, PG3")

Anfrage:
{anfrage_text if anfrage_text else "(keine Angabe)"}

Antworte NUR mit diesem JSON, kein Markdown drumherum:
{{
  "antwort": "der fertige Text",
  "bezeichnung": "kurze interne Bezeichnung"
}}"""

        with st.spinner("…"):
            try:
                resp = get_client().messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=800,
                    messages=[{"role": "user", "content": response_prompt}],
                )
                raw = resp.content[0].text
                data = json.loads(raw[raw.find("{"):raw.rfind("}")+1])
                st.session_state["calc_response"]   = data.get("antwort", raw)
                st.session_state["calc_label"]       = data.get("bezeichnung", "")
            except Exception as e:
                st.error(f"Fehler: {e}")

    if st.session_state.get("calc_response"):
        st.text_area("Antworttext (bearbeitbar)",
                     value=st.session_state["calc_response"],
                     height=220, key="calc_response_area")

    # ── Im Tool speichern ─────────────────────────────────────────
    st.divider()
    label_input = st.text_input("Bezeichnung für diese Kalkulation",
                                placeholder="z.B. Familie Müller – PG3 Ehepaar",
                                key="calc_label")
    if st.button("💾 Kalkulation speichern", use_container_width=True):
        selections = {
            cat: st.session_state.get(f"calc_radio_{cat}", list(PRICE_CONFIG[cat].keys())[0])
            for cat in PRICE_CONFIG
        }
        entry = {
            "datum":       datetime.now().strftime("%d.%m.%Y %H:%M"),
            "label":       label_input.strip() or "Ohne Bezeichnung",
            "anfrage":     anfrage_text,
            "selections":  selections,
            "provision":   provision_input,
            "provision_unit": provision_unit,
            "monatssatz":  round(gesamt, 2),
            "tagessatz":   round(gesamt / 30, 2),
        }
        save_calculation_entry(entry)
        st.success("Gespeichert!")

    # ── Gespeicherte Kalkulationen ────────────────────────────────
    st.subheader("📂 Gespeicherte Kalkulationen")
    calcs = load_calculations()
    if calcs:
        for i, c in enumerate(calcs):
            label = c.get("label") or c.get("kontakt") or "Kalkulation"
            with st.expander(f"{c['datum']}  –  {label}  |  {fmt_eur(c['monatssatz'])}/Monat"):
                for cat, sel in c.get("selections", {}).items():
                    surcharge = PRICE_CONFIG.get(cat, {}).get(sel, 0)
                    suffix = f" (+{fmt_eur(surcharge)})" if surcharge > 0 else ""
                    st.write(f"**{cat}:** {sel}{suffix}")
                if c.get("provision", 0) > 0:
                    st.write(f"**Provision:** {fmt_eur(c['provision'])} / {c.get('provision_unit','Monat')}")
                st.write(f"**Monatssatz:** {fmt_eur(c['monatssatz'])}  |  **Tagessatz:** {fmt_eur(c['tagessatz'])}")
                if c.get("anfrage"):
                    st.caption(f"Anfrage: {c['anfrage'][:200]}…" if len(c['anfrage']) > 200 else f"Anfrage: {c['anfrage']}")
                if st.button("🗑 Löschen", key=f"del_calc_{i}"):
                    calcs.pop(i)
                    with open(CALC_FILE, "w") as f:
                        json.dump(calcs, f, indent=2, ensure_ascii=False)
                    st.rerun()
    else:
        st.info("Noch keine Kalkulationen gespeichert.")
