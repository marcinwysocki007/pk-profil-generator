import streamlit as st
import anthropic
import json
import os
import re
import base64
import tempfile
from datetime import datetime
from pathlib import Path

from profil_generator import generate

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
- verfuegbarkeit: Format "ab DD.MM.YY" (z.B. "ab 14.05.26")
- alter: Format "XX (Jg. YYYY)" – oder "" wenn unbekannt
- groesse_gewicht: Format "XXX–XXX cm, XX–XX kg"
- deutsch_level: 0=Keine, 1=Grundkenntnisse, 2=Mittelstufe, 3=Fortgeschritten, 4=Gut
- mobilitaet: z.B. "Vollständig mobil, Rollstuhlfähig, Bettlägerig"
- Persönlichkeit + Hobbys: ins Deutsche übersetzen
- beschreibung: 3–4 professionelle Sätze auf Deutsch
- besondere_merkmale: akzeptierte Erkrankungen / besondere Fähigkeiten zusammenfassen
- "" für unbekannte Felder, niemals Gehalt oder Kontaktdaten

Antworte NUR mit dem JSON-Objekt:
{
  "name": "", "geschlecht": "Weiblich", "verfuegbarkeit": "",
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
    name      = daten["name"].lower().replace(" ", "_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename  = f"{name}_{timestamp}.pdf"
    out_path  = STORAGE_DIR / filename
    generate(daten, output_path=str(out_path))
    with open(out_path, "rb") as f:
        return filename, f.read()


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
                new_color = st.color_picker("Primärfarbe", comp.get("color_primary", "#6B491A"), key=f"c_{cid}")

                logo_upload = st.file_uploader("Logo (PNG/JPG)", type=["png","jpg","jpeg"],
                                               key=f"l_{cid}")
                if logo_upload:
                    logo_path = str(COMPANIES_DIR / f"{cid}_logo{Path(logo_upload.name).suffix}")
                    with open(logo_path, "wb") as f:
                        f.write(logo_upload.read())
                    comp["logo"] = logo_path
                    st.image(logo_path, width=120)
                elif comp.get("logo") and os.path.exists(comp["logo"]):
                    st.image(comp["logo"], width=120)

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
    new_co_name  = st.text_input("Name", key="new_co_name")
    new_co_color = st.color_picker("Primärfarbe", "#6B491A", key="new_co_color")
    new_co_logo  = st.file_uploader("Logo (optional)", type=["png","jpg","jpeg"], key="new_co_logo")

    if st.button("Unternehmen anlegen", use_container_width=True):
        if new_co_name.strip():
            cid = slug(new_co_name)
            logo_path = ""
            if new_co_logo:
                logo_path = str(COMPANIES_DIR / f"{cid}_logo{Path(new_co_logo.name).suffix}")
                with open(logo_path, "wb") as f:
                    f.write(new_co_logo.read())
            companies[cid] = {
                "name":          new_co_name.strip(),
                "color_primary": new_co_color,
                "logo":          logo_path,
            }
            save_companies(companies)
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

# ── Gespeicherte Profile ─────────────────────────────────────────
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
