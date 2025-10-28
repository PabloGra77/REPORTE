import pandas as pd
import streamlit as st
from datetime import datetime, timedelta, time
from io import BytesIO
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.enums import TA_CENTER
import unicodedata

# =========================
# CONFIGURACIÓN DE LA APP
# =========================
st.set_page_config(page_title="GIA - SLA inteligente (1 archivo)", page_icon="🤖", layout="wide")

st.markdown("""
<style>
body {background:#0E1117; color:white;}
.metric-card { background:#1E1E1E; border:1px solid #3A86FF33; border-radius:12px; padding:14px; text-align:center; box-shadow:0 0 6px rgba(58,134,255,0.25);}
.metric-value { font-size:22px; font-weight:800; }
.metric-label { color:#FF9F1C; font-size:12px; }
hr {border:0; height:1px; background:#333; margin:18px 0;}
</style>
""", unsafe_allow_html=True)

st.markdown("<h2 style='color:#3A86FF'>🤖 GIA — SLA automático con horario laboral</h2>", unsafe_allow_html=True)
st.markdown("<div style='color:#DADADA;'>IPS Goleman | Inteligencia para el Soporte</div>", unsafe_allow_html=True)

# =========================
# PARÁMETROS DE NEGOCIO
# =========================
# Horario laboral por día (0=Lunes ... 6=Domingo) en hora local
# L-J 07:00–17:00, V 07:00–16:00, S 08:00–13:00, D cerrado
WORK_SCHEDULE = {
    0: [(time(7, 0), time(17, 0))],  # Lunes
    1: [(time(7, 0), time(17, 0))],  # Martes
    2: [(time(7, 0), time(17, 0))],  # Miércoles
    3: [(time(7, 0), time(17, 0))],  # Jueves
    4: [(time(7, 0), time(16, 0))],  # Viernes
    5: [(time(8, 0), time(13, 0))],  # Sábado
    6: []                             # Domingo
}

# SLA por prioridad (en HORAS hábiles)
# Nota: interpretamos 1 "día" de SLA = 8 horas hábiles
PRIORITY_SLA_HOURS = {
    "muy alta": 4,
    "alta": 8,
    "media": 2 * 8,   # 2 días hábiles
    "baja":  4 * 8    # 4 días hábiles
}

# =========================
# UTILIDADES
# =========================
def strip_accents(s: str) -> str:
    if s is None:
        return ""
    return "".join(ch for ch in unicodedata.normalize("NFD", str(s)) if unicodedata.category(ch) != "Mn")

def norm(s: str) -> str:
    return strip_accents(s).strip().lower()

def read_any(file):
    if file.name.lower().endswith(".csv"):
        return pd.read_csv(file, sep=None, engine="python", on_bad_lines="skip", encoding="utf-8")
    return pd.read_excel(file)

def to_ts(s):
    # Intento flexible de parsear fecha/hora
    if pd.isna(s): 
        return pd.NaT
    return pd.to_datetime(s, errors="coerce", dayfirst=True, utc=False)

def business_seconds_between(start: datetime, end: datetime) -> float:
    """Calcula segundos hábiles entre dos timestamps usando WORK_SCHEDULE."""
    if pd.isna(start) or pd.isna(end) or end <= start:
        return 0.0

    total = 0.0
    cur = start
    # Iteramos día por día hasta 'end' (límite de seguridad 365 días)
    for _ in range(370):
        day = cur.date()
        day_start = datetime.combine(day, time.min)
        day_end = datetime.combine(day, time.max)

        # intervalos laborales del día
        for (h_ini, h_fin) in WORK_SCHEDULE[cur.weekday()]:
            seg_ini = datetime.combine(day, h_ini)
            seg_fin = datetime.combine(day, h_fin)

            # tramo efectivo que solapa con [start, end]
            tramo_ini = max(cur, seg_ini)
            tramo_fin = min(end, seg_fin)

            if tramo_fin > tramo_ini:
                total += (tramo_fin - tramo_ini).total_seconds()

        # pasar al siguiente día a las 00:00
        next_day = day_end + timedelta(seconds=1)
        if next_day >= end:
            break
        cur = next_day

    return total

def horas_habiles(start, end):
    return business_seconds_between(start, end) / 3600.0

def sla_limit_hours(priority_val: str) -> float:
    p = norm(priority_val)
    # buscar coincidencia aproximada
    for key in PRIORITY_SLA_HOURS:
        if key in p:
            return PRIORITY_SLA_HOURS[key]
    # si no se encuentra, asumir 8h (un día)
    return 8.0

# =========================
# RELOJES (diferencia horaria)
# =========================
st.markdown("### 🕒 Reloj")
col_r1, col_r2, col_r3 = st.columns(3)
offset = col_r1.number_input("Diferencia (horas) Servidor GIA vs. hora local", value=5.0, step=0.5)
now_local = datetime.now()
now_server = now_local + timedelta(hours=offset)
col_r2.markdown(f"<div class='metric-card'><div class='metric-value'>{now_local.strftime('%Y-%m-%d %H:%M:%S')}</div><div class='metric-label'>Hora Local</div></div>", unsafe_allow_html=True)
col_r3.markdown(f"<div class='metric-card'><div class='metric-value'>{now_server.strftime('%Y-%m-%d %H:%M:%S')}</div><div class='metric-label'>Hora Servidor (estimada)</div></div>", unsafe_allow_html=True)

st.markdown("<hr>", unsafe_allow_html=True)

# =========================
# CARGA DE ARCHIVO DETALLADO
# =========================
uploaded = st.file_uploader("📁 Subir reporte detallado (CSV o XLSX) exportado de GIA/GLPI", type=["csv", "xlsx"])

if not uploaded:
    st.info("Sube el archivo detallado para calcular el SLA automáticamente.")
    st.stop()

df = read_any(uploaded)
df.columns = [str(c).strip() for c in df.columns]

# Detectar columnas (nombres típicos de GLPI en español)
def pick_col(posibles, requerido=True, fallback=None):
    for c in df.columns:
        nc = norm(c)
        if any(p in nc for p in posibles):
            return c
    if fallback and fallback in df.columns:
        return fallback
    if requerido:
        st.error(f"❌ No encontré columna requerida. Busqué: {posibles}")
        st.stop()
    return None

col_creacion = pick_col(["creacion", "apertura", "fecha de creacion", "fecha de apertura", "created"])
col_cierre   = pick_col(["cierre", "resolucion", "resolución", "fecha de cierre", "solucion", "closed"], requerido=False)
col_prioridad= pick_col(["prioridad", "urgencia", "priority"])
col_tecnico  = pick_col(["asignado a", "tecnico", "técnico", "responsable", "assigned"], fallback="Asignado a - Técnico")
col_estado   = pick_col(["estado", "status"], requerido=False)
col_caso     = pick_col(["categoria", "categoría", "asunto", "titulo", "título", "tema", "subject"], requerido=False)

# Parsear fechas
df["_creacion"] = df[col_creacion].apply(to_ts)
if col_cierre:
    df["_cierre"] = df[col_cierre].apply(to_ts)
else:
    df["_cierre"] = pd.NaT

# Duración en horas hábiles (solo si cerrado)
df["Horas hábiles"] = df.apply(
    lambda r: horas_habiles(r["_creacion"], r["_cierre"]) if pd.notna(r["_cierre"]) else 0.0,
    axis=1
)

# Límite SLA por prioridad (horas hábiles)
df["SLA (h)"] = df[col_prioridad].apply(sla_limit_hours)

# Estado SLA
def estado_sla(row):
    if pd.isna(row["_cierre"]):
        return "Abierto"
    return "Cumplido" if row["Horas hábiles"] <= row["SLA (h)"] else "Tardío"

df["Estado SLA"] = df.apply(estado_sla, axis=1)

# =========================
# RESUMEN POR TÉCNICO
# =========================
# Asignados = todos los casos del técnico
# Resueltos = cerrados
# Tardíos = cerrados fuera de SLA
def is_closed(row):
    if pd.notna(row["_cierre"]):
        return True
    if col_estado:
        return norm(row[col_estado]).startswith("res") or "cerr" in norm(row[col_estado])
    return False

df["_cerrado"] = df.apply(is_closed, axis=1)
df["_tardio"]  = (df["_cerrado"]) & (df["Estado SLA"] == "Tardío")

resumen = (
    df.groupby(col_tecnico)
      .agg(Asignados=("Estado SLA", "count"),
           Resueltos=("_cerrado", "sum"),
           Tardíos=("_tardio", "sum"))
      .reset_index()
)

resumen["SLA (%)"] = ((resumen["Resueltos"] - resumen["Tardíos"]) / (resumen["Asignados"] + 1e-9)) * 100

# =========================
# UI: MÉTRICAS + TABLAS
# =========================
st.subheader("📈 Resumen SLA por técnico")
c1, c2, c3, c4 = st.columns(4)
c1.markdown(f"<div class='metric-card'><div class='metric-value'>{int(resumen['Asignados'].sum())}</div><div class='metric-label'>Asignados (total)</div></div>", unsafe_allow_html=True)
c2.markdown(f"<div class='metric-card'><div class='metric-value'>{int(resumen['Resueltos'].sum())}</div><div class='metric-label'>Resueltos (total)</div></div>", unsafe_allow_html=True)
c3.markdown(f"<div class='metric-card'><div class='metric-value'>{int(resumen['Tardíos'].sum())}</div><div class='metric-label'>Tardíos (total)</div></div>", unsafe_allow_html=True)
c4.markdown(f"<div class='metric-card'><div class='metric-value'>{resumen['SLA (%)'].mean():.2f}%</div><div class='metric-label'>SLA promedio</div></div>", unsafe_allow_html=True)

st.dataframe(resumen[[col_tecnico, "Asignados", "Resueltos", "Tardíos", "SLA (%)"]], use_container_width=True)

st.markdown("<hr>", unsafe_allow_html=True)
st.subheader("🧾 Detalle y filtros")

tec_list = sorted(df[col_tecnico].dropna().unique().tolist())
tec_sel = st.selectbox("👤 Técnico", tec_list) if tec_list else None

if tec_sel:
    df_view = df[df[col_tecnico] == tec_sel].copy()
else:
    df_view = df.copy()

cols_show = [c for c in [col_caso, col_prioridad, col_tecnico, col_creacion, col_cierre, col_estado, "Horas hábiles", "SLA (h)", "Estado SLA"] if c in df_view.columns or c in ["Horas hábiles", "SLA (h)", "Estado SLA"]]
st.dataframe(df_view[cols_show], use_container_width=True)

# =========================
# PDF (sin Kaleido)
# =========================
st.markdown("<hr>", unsafe_allow_html=True)
st.subheader("📄 Descargar reporte PDF")

def build_pdf(df_sum: pd.DataFrame, df_tardios: pd.DataFrame) -> bytes:
    buf = BytesIO()
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")

    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=30, bottomMargin=20)
    styles = getSampleStyleSheet()
    title = ParagraphStyle('t', parent=styles['Title'], alignment=TA_CENTER, textColor=colors.HexColor("#3A86FF"))

    story = []
    story.append(Paragraph("GIA — Reporte de SLA", title))
    story.append(Paragraph(f"Fecha (local): {fecha}", styles["Normal"]))
    story.append(Paragraph(f"Diferencia horaria estimada servidor: {offset:+.1f} h", styles["Normal"]))
    story.append(Spacer(1, 8))

    # Resumen
    story.append(Paragraph("Resumen por técnico", styles["Heading3"]))
    header = [col_tecnico, "Asignados", "Resueltos", "Tardíos", "SLA (%)"]
    data = [header] + df_sum[[col_tecnico, "Asignados", "Resueltos", "Tardíos", "SLA (%)"]].round(2).values.tolist()
    table = Table(data, colWidths=[120, 70, 70, 70, 70])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#3A86FF")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('GRID',  (0,0), (-1,-1), 0.3, colors.gray),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold')
    ]))
    story.append(table)
    story.append(Spacer(1, 10))

    # Tardíos (top 15)
    if not df_tardios.empty:
        story.append(Paragraph("Casos tardíos (primeros 15)", styles["Heading3"]))
        cols_det = [c for c in [col_caso, col_tecnico, col_prioridad, col_creacion, col_cierre, "Horas hábiles", "SLA (h)"] if c]
        det = [ [str(c) for c in cols_det] ]
        for _, r in df_tardios.head(15).iterrows():
            det.append([str(r.get(c, "")) for c in cols_det])
        tbl2 = Table(det, colWidths=[80]*len(cols_det))
        tbl2.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#118AB2")),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('GRID',  (0,0), (-1,-1), 0.3, colors.gray),
        ]))
        story.append(tbl2)

    doc.build(story)
    pdf = buf.getvalue()
    buf.close()
    return pdf

df_tardios = df[df["Estado SLA"] == "Tardío"].copy()
pdf_bytes = build_pdf(resumen, df_tardios)
st.download_button("📥 Descargar PDF de SLA", pdf_bytes, file_name="GIA_reporte_SLA.pdf")
