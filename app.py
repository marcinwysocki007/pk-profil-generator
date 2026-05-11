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
        "logo_pfad":             company.get("logo", ""),
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
                    logo_upload.seek(0)
                    logo_path = str(COMPANIES_DIR / f"{cid}_logo{Path(logo_upload.name).suffix}")
                    with open(logo_path, "wb") as f:
                        f.write(logo_bytes)
                    comp["logo"] = logo_path
                    logo_hash = hashlib.md5(logo_bytes).hexdigest()
                    if st.session_state.get(f"_logo_hash_{cid}") != logo_hash:
                        colors_list = extract_dominant_colors(logo_bytes)
                        st.session_state[f"_colors_{cid}"]   = colors_list
                        st.session_state[f"_auto_{cid}"]     = colors_list[0]
                        st.session_state[f"_logo_hash_{cid}"] = logo_hash
                    st.image(logo_path, width=120)
                elif comp.get("logo") and os.path.exists(comp["logo"]):
                    st.image(comp["logo"], width=120)

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
            if new_co_logo:
                new_co_logo.seek(0)
                logo_path = str(COMPANIES_DIR / f"{cid}_logo{Path(new_co_logo.name).suffix}")
                with open(logo_path, "wb") as f:
                    f.write(new_co_logo.read())
            companies[cid] = {
                "name":          new_co_name.strip(),
                "color_primary": new_co_color,
                "logo":          logo_path,
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
                                st.session_state[f"calc_sel_{cat}"] = list(options.keys()).index(val)
                        st.success("Felder wurden vorausgefüllt – bitte prüfen und anpassen.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Fehler beim Auslesen: {e}")

    st.divider()

    # ── Preisfelder ───────────────────────────────────────────────
    total = BASE_PRICE
    surcharges = []

    for cat, options in PRICE_CONFIG.items():
        opt_list   = list(options.keys())
        default_i  = st.session_state.get(f"calc_sel_{cat}", 0)
        default_i  = min(default_i, len(opt_list) - 1)

        # Label mit Aufpreis-Hinweisen
        def fmt(o, opts=options):
            p = opts[o]
            return f"{o}  (+{p} €)" if p > 0 else o

        selected = st.radio(cat, opt_list, index=default_i,
                            format_func=fmt, horizontal=True,
                            key=f"calc_radio_{cat}")
        surcharge = options[selected]
        if surcharge > 0:
            surcharges.append((cat, selected, surcharge))
        total += surcharge

    # ── Preisanzeige ──────────────────────────────────────────────
    st.divider()
    if surcharges:
        with st.expander("Aufschläge im Detail", expanded=False):
            st.write(f"Basispreis 24h-Betreuung: **{BASE_PRICE:,} €**".replace(",", "."))
            for cat, sel, val in surcharges:
                st.write(f"+ {cat} ({sel}): **+{val:,} €**".replace(",", "."))

    st.metric(label="💶 Monatlicher Gesamtpreis",
              value=f"{total:,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."))
