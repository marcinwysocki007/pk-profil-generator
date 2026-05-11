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


def save_companies_to_github(data: dict):
    """Schreibt companies.json via GitHub API zurück ins Repo (nur wenn Token vorhanden)."""
    import urllib.request
    import urllib.error

    token = st.secrets.get("GITHUB_TOKEN", "") or os.environ.get("GITHUB_TOKEN", "")
    repo  = st.secrets.get("GITHUB_REPO", "") or os.environ.get("GITHUB_REPO", "")
    if not token or not repo:
        return  # Kein GitHub-Token → nur lokal speichern

    path = "companies.json"
    url  = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
        "User-Agent": "PK-Profil-App",
    }

    # Aktuellen SHA holen
    sha = None
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as resp:
            file_info = json.loads(resp.read())
        sha = file_info["sha"]
    except urllib.error.HTTPError as e:
        if e.code != 404:
            return  # Unbekannter Fehler → abbrechen

    # Inhalt hochladen
    content_b64 = base64.b64encode(
        json.dumps(data, indent=2, ensure_ascii=False).encode()
    ).decode()

    body_dict = {"message": "Update companies.json", "content": content_b64}
    if sha:
        body_dict["sha"] = sha

    try:
        req = urllib.request.Request(
            url, data=json.dumps(body_dict).encode(), headers=headers, method="PUT"
        )
        urllib.request.urlopen(req)
    except Exception:
        pass  # Lokale Kopie ist gespeichert – Fehler ignorieren


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


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")

# ── Sprachtext ───────────────────────────────────────────────────
DEUTSCH_TEXTS = {
    0: "Die Betreuungsperson spricht kein Deutsch.",
    1: "Die Betreuungsperson hat Grundkenntnisse und versteht einfache Sätze.",
    2: "Die Betreuungsperson spricht in einfachen Sätzen und kann sich im Alltag verständigen.",
    3: "Die Betreuungsperson spricht fortgeschrittenes Deutsch und verständigt sich gut.",
    4: "Die Betreuungsperson spricht sehr gut Deutsch und kommuniziert fließend.",
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
- deutsch_level: 0=Keine, 1=Grundkenntnisse, 2=Mittelstufe, 3=Fortgeschritten, 4=Gut
- mobilitaet: z.B. "Vollständig mobil, Rollstuhlfähig, Bettlägerig"
- Persönlichkeit + Hobbys: ins Deutsche übersetzen
- beschreibung: PFLICHTFELD – verfasse selbst 3–4 professionelle Sätze auf Deutsch, die die Pflegekraft vorstellen. Nutze dafür Erfahrung, Persönlichkeit, Sprachkenntnisse, Nationalität und besondere Fähigkeiten. Nur Vorname verwenden. Niemals leer lassen.
- besondere_merkmale: akzeptierte Erkrankungen / besondere Fähigkeiten zusammenfassen
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

PRICE_CONFIG = OrderedDict([
    ("Betreuung für",               OrderedDict([("1 Person", 0), ("Ehepaar", 300)])),
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
    ("Weitere Personen im Haushalt", OrderedDict([("Nein", 0), ("Ja", 200)])),
])

PRICE_PROMPT = """\
Analysiere die Patienteninformationen und ordne sie den Preiskategorien zu.
Wähle immer exakt eine der aufgeführten Optionen – kein Freitext.

Kategorien und gültige Optionen:
- Betreuung für: "1 Person" | "Ehepaar"
- Deutschkenntnisse: "Grundlegend" | "Kommunikativ" | "Sehr gut"
- Erfahrung: "Einsteiger" | "Erfahren" | "Sehr erfahren"
- Führerschein: "Egal" | "Ja" | "Nein"
- Geschlecht: "Egal" | "Weiblich" | "Männlich"
- Mobilität: "Mobil – geht selbstständig" | "Eingeschränkt – nur mit Rollator" | "Auf Rollstuhl angewiesen" | "Bettlägerig"
- Nachteinsätze: "Nein" | "Gelegentlich" | "Täglich (1×)" | "Mehrmals nachts"
- Pflegegrad: "Kein Pflegegrad" | "Pflegegrad 1" | "Pflegegrad 2" | "Pflegegrad 3" | "Pflegegrad 4" | "Pflegegrad 5"
- Weitere Personen im Haushalt: "Nein" | "Ja"

Wenn eine Info fehlt oder unklar ist → günstigste/neutralste Option.
Antworte NUR mit dem JSON-Objekt:
{
  "Betreuung für": "...",
  "Deutschkenntnisse": "...",
  "Erfahrung": "...",
  "Führerschein": "...",
  "Geschlecht": "...",
  "Mobilität": "...",
  "Nachteinsätze": "...",
  "Pflegegrad": "...",
  "Weitere Personen im Haushalt": "..."
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

st.set_page_config(page_title="Pflegeprofil Generator", page_icon="📋", layout="centered")

st.markdown("""
<style>
.block-container { max-width: 760px; }
.stButton > button { border-radius: 8px; }
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
st.title("Pflegeprofil Generator")
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

tab1, tab2 = st.tabs(["📋 Pflegeprofil erstellen", "💰 Preiskalkulator"])

# ════════════════════════════════════════════════════════════════
# TAB 1 – Pflegeprofil
# ════════════════════════════════════════════════════════════════
with tab1:
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
    pdf_files = sorted(STORAGE_DIR.glob("*.pdf"), key=os.path.getmtime, reverse=True)
    if pdf_files:
        for pdf_path in pdf_files[:30]:
            mtime = datetime.fromtimestamp(os.path.getmtime(pdf_path))
            col_a, col_b = st.columns([4, 1])
            with col_a:
                st.write(f"📄 {pdf_path.stem} — {mtime.strftime('%d.%m.%Y %H:%M')}")
            with col_b:
                with open(pdf_path, "rb") as f:
                    st.download_button("↓", data=f.read(), file_name=pdf_path.name,
                                       mime="application/pdf", key=str(pdf_path))
    else:
        st.info("Noch keine Profile erstellt.")


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

        # Label mit Aufpreis-Hinweisen
        def fmt(o, opts=options):
            p = opts[o]
            return f"{o}  (+{p} €)" if p > 0 else o

        selected = st.radio(cat, opt_list, index=0,
                            format_func=fmt, horizontal=True,
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
                                          value=0.0, step=1.0, format="%.2f",
                                          key="calc_provision")
    with col_pv2:
        provision_unit = st.radio("pro", ["Monat", "Tag"], horizontal=True,
                                  key="calc_provision_unit")

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

    # ── Kalkulation speichern ─────────────────────────────────────
    st.divider()
    summary_lines = [
        f"Preiskalkulation – {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        "=" * 42,
    ]
    for cat in PRICE_CONFIG:
        sel_val = st.session_state.get(f"calc_radio_{cat}", list(PRICE_CONFIG[cat].keys())[0])
        surcharge = PRICE_CONFIG[cat][sel_val]
        suffix = f"  (+{fmt_eur(surcharge)})" if surcharge > 0 else ""
        summary_lines.append(f"{cat}: {sel_val}{suffix}")
    summary_lines += ["=" * 42, f"Basispreis:  {fmt_eur(BASE_PRICE)}"]
    for cat, sel, val in surcharges:
        summary_lines.append(f"+ {cat} ({sel}): +{fmt_eur(val)}")
    if provision_input > 0:
        prov_label = f"{fmt_eur(provision_input)}/Tag × 30" if provision_unit == "Tag" else f"{fmt_eur(provision_input)}/Monat"
        summary_lines.append(f"+ Partnerprovision ({prov_label}): +{fmt_eur(provision_eur)}")
    summary_lines += ["=" * 42, f"Monatssatz:  {fmt_eur(gesamt)}", f"Tagessatz:   {fmt_eur(gesamt / 30)}"]
    anfrage_text = st.session_state.get("calc_text", "").strip()
    if anfrage_text:
        summary_lines += ["", "Anfrage:", anfrage_text]
    summary_text = "\n".join(summary_lines)

    col_dl, col_gen = st.columns(2)
    with col_dl:
        st.download_button(
            "💾 Kalkulation speichern",
            data=summary_text.encode("utf-8"),
            file_name=f"Kalkulation_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
            mime="text/plain",
            use_container_width=True,
        )

    # ── Antworttext generieren ────────────────────────────────────
    st.subheader("✉️ Antwort auf Anfrage")

    # Preisinfo aufbauen
    monat_str = fmt_eur(gesamt)
    tag_str   = fmt_eur(gesamt / 30)
    if provision_input > 0:
        preis_info = (
            f"Unser Preis beträgt {fmt_eur(total)} pro Monat zzgl. einer Partnerprovision "
            f"von {fmt_eur(provision_eur)} – Gesamtmonatssatz {monat_str} (Tagessatz {tag_str})."
        )
    else:
        preis_info = f"Unser Monatssatz beträgt {monat_str} (Tagessatz {tag_str})."

    # Gewählte Optionen als Kontext für Claude
    optionen_text = "\n".join(
        f"- {cat}: {st.session_state.get(f'calc_radio_{cat}', list(PRICE_CONFIG[cat].keys())[0])}"
        for cat in PRICE_CONFIG
    )

    if st.button("Antwort generieren", key="gen_response", use_container_width=True, icon="✍️"):
        response_prompt = f"""Du bist ein professioneller Kundenbetreuer bei einem 24h-Pflegevermittlungs-Unternehmen.
Schreibe eine kurze, professionelle Antwort auf eine Anfrage auf Deutsch.

Die Antwort soll:
- Warmherzig auf die konkreten Wünsche und Bedürfnisse aus der Anfrage eingehen
- Den Preis klar nennen: {preis_info}
- Erwähnen, dass wir passende Profile bereits übermitteln werden
- Freundlich aber klar darauf hinweisen, dass bei Interesse eine schnelle Rückmeldung nötig ist, um die Pflegekraft zu sichern
- Professionell und persönlich klingen, ca. 150–200 Wörter
- Ohne Betreffzeile, direkt als Fließtext beginnen

Anfragedaten (aus Kalkulator):
{optionen_text}

Anfrage-Originaltext:
{anfrage_text if anfrage_text else "(kein Freitext – beziehe dich auf die Kalkulatordaten)"}

Antworte NUR mit dem fertigen Antworttext."""

        with st.spinner("Antwort wird generiert…"):
            try:
                resp = get_client().messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=600,
                    messages=[{"role": "user", "content": response_prompt}],
                )
                st.session_state["calc_response"] = resp.content[0].text
            except Exception as e:
                st.error(f"Fehler: {e}")

    if st.session_state.get("calc_response"):
        st.text_area(
            "Generierter Antworttext (bearbeitbar & kopierbar)",
            value=st.session_state["calc_response"],
            height=280,
            key="calc_response_area",
        )
        st.caption("↑ Text anklicken → Strg+A / ⌘A → Strg+C / ⌘C zum Kopieren")
