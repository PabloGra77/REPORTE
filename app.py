import pandas as pd
import streamlit as st
from datetime import datetime, timedelta, time
from io import BytesIO
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.enums import TA_CENTER
from zoneinfo import ZoneInfo
import unicodedata
import plotly.express as px

# =========================
# CONFIG
# =========================
st.set_page_config(page_title="GIA - SLA (1 archivo)", page_icon="🤖", layout="wide")
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
st.caption("IPS Goleman | Inteligencia para el Soporte")

# =========================
# PARÁMETROS DE NEGOCIO
# =========================
# Horario laboral por día (0=Lunes ... 6=Domingo)
WORK_SCHEDULE = {
    0: [(time(7, 0), time(17, 0))],  # Lunes
    1: [(time(7, 0), time(17, 0))],  # Martes
    2: [(time(7, 0), time(17, 0))],  # Miércoles
    3: [(time(7, 0), time(17, 0))],  # Jueves
    4: [(time(7, 0), time(16, 0))],  # Viernes
    5: [(time(8, 0), time(13, 0))],  # Sábado
    6: []                             # Domingo
}
# SLA por prioridad (en HORAS hábiles) 1 día = 8h hábiles
PRIORITY_SLA_HOURS = {
    "muy alta": 4,
    "alta": 8,
    "media": 16,  # 2 días hábiles
    "baja":  32   # 4 días hábiles
}

# =========================
# UTILIDADES
# =========================
def strip_accents(s: str) -> str:
    if s is None: return ""
    return "".join(ch for ch in unicodedata.normalize("NFD", str(s)) if unicodedata.category(ch) != "Mn")
def norm(s: str) -> str:
    return strip_accents(s).strip().lower()
def read_any(file):
    if file.name.lower().endswith(".csv"):
        return pd.read_csv(file, sep=None, engine="python", on_bad_lines="skip", encoding="utf-8")
    return pd.read_excel(file)
def to_ts(s):
    if pd.isna(s): return pd.NaT
    return pd.to_datetime(s, errors="coerce", dayfirst=True, utc=False)

def business_seconds_between(start: datetime, end: datetime) -> float:
    """Calcula segundos hábiles entre dos timestamps usando WORK_SCHEDULE (asumiendo zona local)."""
    if pd.isna(start) or pd.isna(end) or end <= start:
        return 0.0
    total = 0.0
    cur = start
    for _ in range(370):  # seguridad
        day = cur.date()
        # intervalos laborales del día
        for (h_ini, h_fin) in WORK_SCHEDULE[cur.weekday()]:
            seg_ini = datetime.combine(day, h_ini)
            seg_fin = datetime.combine(day, h_fin)
            tramo_ini = max(cur, seg_ini)
            tramo_fin = min(end, seg_fin)
            if tramo_fin > tramo_ini:
                total += (tramo_fin - tramo_ini).total_seconds()
        # pasar al siguiente día
        next_day = datetime.combine(day, time(23,59,59)) + timedelta(seconds=1)
        if next_day >= end:
            break
        cur = next_day
    return total

def horas_habiles(start, end):
    return business_seconds_between(start, end) / 3600.0

def sla_limit_hours(priority_val: str) -> float:
    p = norm(priority_val)
    for key, hrs in PRIORITY_SLA_HOURS.items():
        if key in p:
            return hrs
    return 8.0  # default

# =========================
# RELOJES Y OFFSET
# =========================
st.subheader("🕒 Reloj y desfase")
col_r1, col_r2, col_r3 = st.columns(3)
offset = col_r1.number_input("Diferencia (horas) Servidor GIA vs. Bogotá", value=5.0, step=0.5)

# Hora de Bogotá correcta con zona horaria
bogota_now = datetime.now(ZoneInfo("America/Bogota"))
server_est = bogota_now + timedelta(hours=offset)

col_r2.markdown(f"<div class='metric-card'><div class='metric-value'>{bogota_now.strftime('%Y-%m-%d %H:%M:%S')}</div><div class='metric-label'>Hora local (Bogotá)</div></div>", unsafe_allow_html=True)
col_r3.markdown(f"<div class='metric-card'><div class='metric-value'>{server_est.strftime('%Y-%m-%d %H:%M:%S')}</div><div class='metric-label'>Hora servidor (estimada)</div></div>", unsafe_allow_html=True)

st.markdown("<hr>", unsafe_allow_html=True)

# =========================
# ARCHIVO DETALLADO
# =========================
uploaded = st.file_uploader("📁 Subir reporte detallado (CSV/XLSX) exportado de GIA/GLPI", type=["csv","xlsx"])
if not uploaded:
    st.info("Sube el archivo detallado para calcular el SLA automáticamente.")
    st.stop()

df = read_any(uploaded)
df.columns = [str(c).strip() for c in df.columns]

def pick_col(posibles, requerido=True, fallback=None):
    for c in df.columns:
        if any(p in norm(c) for p in posibles):
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

# Parsear fechas (timestamps tal como vienen) y AJUSTAR a Bogotá restando offset
df["_creacion_raw"] = df[col_creacion].apply(to_ts)
df["_cierre_raw"]   = df[col_cierre].apply(to_ts) if col_cierre else pd.NaT

# Ajuste a zona local Bogotá “restando” el offset del servidor (tu requerimiento)
def adj(t):
    if pd.isna(t): return pd.NaT
    return t - timedelta(hours=offset)

df["_creacion"] = df["_creacion_raw"].apply(adj)
df["_cierre"]   = df["_cierre_raw"].apply(adj)

# Duración en horas hábiles locales (si está cerrado)
df["Horas hábiles"] = df.apply(
    lambda r: horas_habiles(r["_creacion"], r["_cierre"]) if pd.notna(r["_cierre"]) else 0.0,
    axis=1
)
df["SLA (h)"] = df[col_prioridad].apply(sla_limit_hours)

def estado_sla(row):
    if pd.isna(row["_cierre"]):
        return "Abierto"
    return "Cumplido" if row["Horas hábiles"] <= row["SLA (h)"] else "Tardío"
df["Estado SLA"] = df.apply(estado_sla, axis=1)

# Campos visibles con fechas AJUSTADAS (Bogotá)
df["Apertura (Bogotá)"] = df["_creacion"]
df["Cierre (Bogotá)"]   = df["_cierre"]

# =========================
# RESUMEN Y FILTROS
# =========================
st.subheader("📌 Filtros")
solo_uno = st.checkbox("Consultar un solo técnico")
tec_sel = None
tec_list = sorted(df[col_tecnico].dropna().unique().tolist())

if solo_uno:
    tec_sel = st.selectbox("👤 Técnico", tec_list) if tec_list else None

if tec_sel:
    df_scope = df[df[col_tecnico] == tec_sel].copy()
else:
    df_scope = df.copy()

# Cierre rápido/heurístico
def is_closed(row):
    if pd.notna(row["_cierre"]):
        return True
    if col_estado:
        e = norm(row[col_estado])
        return e.startswith("res") or "cerr" in e
    return False
df_scope["_cerrado"] = df_scope.apply(is_closed, axis=1)
df_scope["_tardio"]  = (df_scope["_cerrado"]) & (df_scope["Estado SLA"] == "Tardío")

resumen = (
    df_scope.groupby(col_tecnico)
            .agg(Asignados=("Estado SLA", "count"),
                 Resueltos=("_cerrado", "sum"),
                 Tardíos=("_tardio", "sum"))
            .reset_index()
)
resumen["SLA (%)"] = ((resumen["Resueltos"] - resumen["Tardíos"]) / (resumen["Asignados"] + 1e-9)) * 100

# =========================
# KPIs
# =========================
st.subheader("📈 Resumen SLA")
c1, c2, c3, c4 = st.columns(4)
c1.markdown(f"<div class='metric-card'><div class='metric-value'>{int(resumen['Asignados'].sum())}</div><div class='metric-label'>Asignados (scope)</div></div>", unsafe_allow_html=True)
c2.markdown(f"<div class='metric-card'><div class='metric-value'>{int(resumen['Resueltos'].sum())}</div><div class='metric-label'>Resueltos (scope)</div></div>", unsafe_allow_html=True)
c3.markdown(f"<div class='metric-card'><div class='metric-value'>{int(resumen['Tardíos'].sum())}</div><div class='metric-label'>Tardíos (scope)</div></div>", unsafe_allow_html=True)
c4.markdown(f"<div class='metric-card'><div class='metric-value'>{resumen['SLA (%)'].mean():.2f}%</div><div class='metric-label'>SLA promedio (scope)</div></div>", unsafe_allow_html=True)

st.dataframe(resumen[[col_tecnico, "Asignados", "Resueltos", "Tardíos", "SLA (%)"]], use_container_width=True)

# =========================
# GRÁFICOS DETALLADOS
# =========================
st.subheader("📊 Gráficos")
# 1) SLA por técnico (barras)
fig_bar = px.bar(
    resumen.sort_values("SLA (%)", ascending=False),
    x=col_tecnico, y="SLA (%)",
    color="SLA (%)",
    color_continuous_scale=["#EF476F","#FFD166","#06D6A0"],
    title="SLA (%) por técnico"
)
st.plotly_chart(fig_bar, use_container_width=True)

# 2) Cumplido vs Tardío (scope actual)
cumplidos = int((df_scope["_cerrado"] & (df_scope["Estado SLA"]=="Cumplido")).sum())
tardios   = int((df_scope["_cerrado"] & (df_scope["Estado SLA"]=="Tardío")).sum())
fig_pie = px.pie(
    pd.DataFrame({"Estado":["Cumplido","Tardío"], "Cantidad":[cumplidos, tardios]}),
    names="Estado", values="Cantidad",
    title="Distribución de casos cerrados: Cumplido vs Tardío",
    color="Estado", color_discrete_map={"Cumplido":"#06D6A0","Tardío":"#EF476F"}
)
st.plotly_chart(fig_pie, use_container_width=True)

# =========================
# DETALLE DE CASOS (scope)
# =========================
st.subheader("🧾 Detalle de casos (Bogotá)")
cols_show = [c for c in [col_caso, col_prioridad, col_tecnico, "Apertura (Bogotá)", "Cierre (Bogotá)", col_estado, "Horas hábiles", "SLA (h)", "Estado SLA"] if c in df_scope.columns]
st.dataframe(df_scope[cols_show], use_container_width=True)

# =========================
# PDF (sin imágenes para máxima compatibilidad)
# =========================
st.markdown("<hr>", unsafe_allow_html=True)
st.subheader("📄 Descargar reporte PDF")

def build_pdf(df_sum: pd.DataFrame, df_tardios: pd.DataFrame, technician: str|None) -> bytes:
    buf = BytesIO()
    fecha = datetime.now(ZoneInfo("America/Bogota")).strftime("%Y-%m-%d %H:%M")

    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=30, bottomMargin=20)
    styles = getSampleStyleSheet()
    title = ParagraphStyle('t', parent=styles['Title'], alignment=TA_CENTER, textColor=colors.HexColor("#3A86FF"))

    story = []
    story.append(Paragraph("GIA — Reporte de SLA (horario Bogotá)", title))
    story.append(Paragraph(f"Fecha (Bogotá): {fecha}", styles["Normal"]))
    story.append(Paragraph(f"Desfase servidor estimado: {offset:+.1f} h", styles["Normal"]))
    if technician:
        story.append(Paragraph(f"Técnico filtrado: <b>{technician}</b>", styles["Normal"]))
    story.append(Spacer(1, 8))

    # Resumen
    story.append(Paragraph("Resumen por técnico", styles["Heading3"]))
    header = ["Técnico", "Asignados", "Resueltos", "Tardíos", "SLA (%)"]
    data = [header] + df_sum[["Técnico","Asignados","Resueltos","Tardíos","SLA (%)"]].round(2).values.tolist()
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
        cols_det = [c for c in [col_caso, col_tecnico, col_prioridad, "Apertura (Bogotá)", "Cierre (Bogotá)", "Horas hábiles", "SLA (h)"] if c]
        det = [cols_det] + df_tardios[cols_det].astype(str).head(15).values.tolist()
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

# Preparar data para PDF (renombrar col_tecnico a "Técnico" para la tabla)
pdf_resumen = resumen.rename(columns={col_tecnico:"Técnico"}).copy()
pdf_tardios = df_scope[(df_scope["_cerrado"]) & (df_scope["Estado SLA"]=="Tardío")].copy()

pdf_bytes = build_pdf(pdf_resumen, pdf_tardios, tec_sel if solo_uno else None)
st.download_button("📥 Descargar PDF de SLA", pdf_bytes, file_name="GIA_reporte_SLA_Bogota.pdf")
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
