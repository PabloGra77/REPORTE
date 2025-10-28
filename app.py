import pandas as pd
import streamlit as st
import plotly.express as px
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from io import BytesIO
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.enums import TA_CENTER
import unicodedata

# =========================
# CONFIGURACIÓN GLOBAL
# =========================
st.set_page_config(page_title="GIA - SLA Inteligente", page_icon="🤖", layout="wide")

# Detección moderna del modo TV (Streamlit 1.37+)
params = st.query_params
is_tv = str(params.get("tv", "0")).lower() in ("1", "true", "yes")

# Tema oscuro fijo
st.markdown("""
<style>
:root, body, [data-testid="stAppViewContainer"] { background: #0E1117 !important; color: #FFF !important; }
* { color: #FFF; }
a { color: #5FA8FF !important; }
[data-testid="stHeader"], [data-testid="stToolbar"] { visibility: hidden !important; }
footer { visibility: hidden !important; }
.block-container { padding-top: 1.2rem; padding-bottom: 2rem; }
.metric-card {
  background:#1E1E1E; border:1px solid #3A86FF33;
  border-radius:12px; padding:14px; text-align:center;
  box-shadow:0 0 6px rgba(58,134,255,0.25);
}
.metric-value { font-size:22px; font-weight:800; color:white; }
.metric-label { color:#FF9F1C; font-size:12px; }
.stDownloadButton button { background:#3A86FF !important; color:white !important; border:none !important; }
.stDownloadButton button:hover { background:#5FA8FF !important; }
hr {border:0; height:1px; background:#333; margin:18px 0;}
</style>
""", unsafe_allow_html=True)

# =========================
# PARÁMETROS DE NEGOCIO
# =========================
WORK_SCHEDULE = {
    0:[(time(7,0), time(17,0))],
    1:[(time(7,0), time(17,0))],
    2:[(time(7,0), time(17,0))],
    3:[(time(7,0), time(17,0))],
    4:[(time(7,0), time(16,0))],  # Viernes
    5:[(time(8,0), time(13,0))],  # Sábado
    6:[]
}
PRIORITY_SLA_HOURS = {"muy alta":4, "alta":8, "media":16, "baja":32}

# =========================
# FUNCIONES AUXILIARES
# =========================
def strip_accents(s): return "".join(ch for ch in unicodedata.normalize("NFD", str(s)) if unicodedata.category(ch) != "Mn")
def norm(s): return strip_accents(str(s)).lower().strip()

def read_any(file):
    name = file.name.lower()
    if name.endswith(".csv"):
        try: return pd.read_csv(file, sep=None, engine="python", on_bad_lines="skip")
        except: 
            file.seek(0)
            return pd.read_csv(file, on_bad_lines="skip")
    return pd.read_excel(file)

def to_ts(s):
    if pd.isna(s): return pd.NaT
    return pd.to_datetime(s, errors="coerce", dayfirst=True, utc=False)

def business_seconds_between(start, end):
    if pd.isna(start) or pd.isna(end) or end <= start: return 0.0
    total = 0.0
    cur = start
    for _ in range(370):
        day = cur.date()
        for (h_ini, h_fin) in WORK_SCHEDULE[cur.weekday()]:
            seg_ini = datetime.combine(day, h_ini)
            seg_fin = datetime.combine(day, h_fin)
            tramo_ini = max(cur, seg_ini)
            tramo_fin = min(end, seg_fin)
            if tramo_fin > tramo_ini:
                total += (tramo_fin - tramo_ini).total_seconds()
        nxt = datetime.combine(day, time(23,59,59)) + timedelta(seconds=1)
        if nxt >= end: break
        cur = nxt
    return total

def horas_habiles(start, end): return business_seconds_between(start, end) / 3600.0

def sla_limit_hours(priority_val):
    p = norm(priority_val)
    for key, hrs in PRIORITY_SLA_HOURS.items():
        if key in p: return hrs
    return 8.0

def pick_col(df, posibles, requerido=True, fallback=None):
    for c in df.columns:
        if any(p in norm(c) for p in posibles): return c
    if fallback and fallback in df.columns: return fallback
    if requerido:
        st.error(f"❌ No encontré columna requerida: {posibles}")
        st.stop()
    return None

# =========================
# CÁLCULO SLA
# =========================
def calcular_sla(df, offset_hours, col_crea, col_cierre, col_prior, col_tec, col_estado):
    df["_crea_raw"]   = df[col_crea].apply(to_ts)
    df["_cierre_raw"] = df[col_cierre].apply(to_ts) if col_cierre else pd.NaT
    df["_crea"]   = df["_crea_raw"].apply(lambda t: t - timedelta(hours=offset_hours) if pd.notna(t) else pd.NaT)
    df["_cierre"] = df["_cierre_raw"].apply(lambda t: t - timedelta(hours=offset_hours) if pd.notna(t) else pd.NaT)

    df["Horas hábiles"] = df.apply(lambda r: horas_habiles(r["_crea"], r["_cierre"]) if pd.notna(r["_cierre"]) else 0.0, axis=1)
    df["SLA (h)"] = df[col_prior].apply(sla_limit_hours)

    def estado_sla(row):
        if pd.isna(row["_cierre"]): return "Abierto"
        return "Cumplido" if row["Horas hábiles"] <= row["SLA (h)"] else "Tardío"
    df["Estado SLA"] = df.apply(estado_sla, axis=1)

    df["_cerrado"] = df["_cierre"].notna()
    df["_tardio"]  = df["_cerrado"] & (df["Estado SLA"] == "Tardío")

    resumen = (
        df.groupby(col_tec)
          .agg(
              Asignados=(col_crea, "count"),
              Resueltos=("_cerrado", "sum"),
              Tardíos=("_tardio",  "sum")
          )
          .reset_index()
    )
    resumen["Abiertos"] = resumen["Asignados"] - resumen["Resueltos"]

    resumen["SLA (%)"] = resumen.apply(
        lambda r: ((r["Resueltos"] - r["Tardíos"]) / r["Resueltos"] * 100) if r["Resueltos"] > 0 else 0,
        axis=1
    )

    df["Apertura (Bogotá)"] = df["_crea"]
    df["Cierre (Bogotá)"]   = df["_cierre"]
    return df, resumen

# =========================
# PDF
# =========================
def pdf_resumen(resumen, col_tec_name, tecnico_filtrado, desfase_horas):
    buf = BytesIO()
    fecha = datetime.now(ZoneInfo("America/Bogota")).strftime("%d/%m/%Y – %H:%M (Bogotá)")
    doc = SimpleDocTemplate(buf, pagesize=A4)
    styles = getSampleStyleSheet()
    title = ParagraphStyle('t', parent=styles['Title'], alignment=TA_CENTER, textColor=colors.HexColor("#3A86FF"))
    story = [Paragraph("GIA – Reporte de SLA", title),
             Paragraph(f"Generado el {fecha}", styles['Normal']),
             Paragraph(f"Desfase servidor estimado: {desfase_horas:+.1f} h", styles['Normal'])]
    if tecnico_filtrado:
        story.append(Paragraph(f"Técnico filtrado: <b>{tecnico_filtrado}</b>", styles['Normal']))
    story.append(Spacer(1, 10))

    data = [["Técnico","Asignados","Abiertos","Resueltos","Tardíos","SLA (%)"]]
    for _, r in resumen.iterrows():
        data.append([r[col_tec_name], int(r["Asignados"]), int(r["Abiertos"]), int(r["Resueltos"]),
                     int(r["Tardíos"]), f"{r['SLA (%)']:.2f}%"])
    tbl = Table(data, colWidths=[120,60,60,60,60,60])
    tbl.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),colors.HexColor("#3A86FF")),
        ('TEXTCOLOR',(0,0),(-1,0),colors.white),
        ('ALIGN',(0,0),(-1,-1),'CENTER'),
        ('GRID',(0,0),(-1,-1),0.3,colors.gray)
    ]))
    story.append(tbl)
    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes

# =========================
# INTERFAZ PRINCIPAL / TV
# =========================
if not is_tv:
    st.markdown("<h2 style='color:#3A86FF'>🤖 GIA — Análisis de SLA</h2>", unsafe_allow_html=True)
    st.caption("IPS Goleman | Inteligencia para el Soporte")
    st.markdown("<hr>", unsafe_allow_html=True)

    offset = st.number_input("Diferencia horaria Servidor vs Bogotá (horas)", value=5.0, step=0.5)
    now_bog = datetime.now(ZoneInfo("America/Bogota"))
    server_est = now_bog + timedelta(hours=offset)
    c1,c2 = st.columns(2)
    c1.markdown(f"<div class='metric-card'><div class='metric-value'>{now_bog.strftime('%Y-%m-%d %H:%M:%S')}</div><div class='metric-label'>Hora Bogotá</div></div>", unsafe_allow_html=True)
    c2.markdown(f"<div class='metric-card'><div class='metric-value'>{server_est.strftime('%Y-%m-%d %H:%M:%S')}</div><div class='metric-label'>Hora Servidor</div></div>", unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)

    up = st.file_uploader("📎 Subir reporte exportado desde GLPI (Detallado de casos)", type=["csv","xlsx"])
    if not up: st.stop()

    df = read_any(up)
    df.columns = [str(c).strip() for c in df.columns]
    col_crea   = pick_col(df, ["apertura","creacion","created"])
    col_cierre = pick_col(df, ["cierre","resol","closed"], requerido=False)
    col_prior  = pick_col(df, ["prioridad","urgencia","priority"])
    col_tec    = pick_col(df, ["asignado a","asignado","tecn","responsable","assigned"], fallback="Asignado a - Técnico")
    col_estado = pick_col(df, ["estado","status"], requerido=False)

    df_calc, resumen_all = calcular_sla(df.copy(), offset, col_crea, col_cierre, col_prior, col_tec, col_estado)

    st.subheader("📌 Filtros")
    usar_uno = st.checkbox("Consultar un solo técnico")
    if usar_uno:
        lista_tec = sorted([x for x in df_calc[col_tec].dropna().unique().tolist()])
        tec_sel = st.selectbox("👤 Técnico", lista_tec) if lista_tec else None
        resumen = resumen_all[resumen_all[col_tec] == tec_sel].copy() if tec_sel else resumen_all.copy()
    else:
        tec_sel = None
        resumen = resumen_all.copy()

    # KPI
    st.subheader("📊 Resumen SLA")
    k1,k2,k3,k4,k5 = st.columns(5)
    k1.metric("Asignados", int(resumen["Asignados"].sum()))
    k2.metric("Abiertos",  int(resumen["Abiertos"].sum()))
    k3.metric("Resueltos", int(resumen["Resueltos"].sum()))
    k4.metric("Tardíos",   int(resumen["Tardíos"].sum()))
    k5.metric("SLA Promedio (%)", f"{resumen['SLA (%)'].mean():.2f}%")

    st.dataframe(resumen[[col_tec,"Asignados","Abiertos","Resueltos","Tardíos","SLA (%)"]], use_container_width=True)

    st.subheader("📈 SLA (%) por técnico")
    if not resumen.empty:
        fig = px.bar(resumen.sort_values("SLA (%)", ascending=False), x=col_tec, y="SLA (%)",
                     color="SLA (%)", text_auto=".2f",
                     color_continuous_scale=["#EF476F","#FFD166","#06D6A0"],
                     title="Cumplimiento SLA por Técnico")
        fig.update_layout(template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)

    # PDF
    st.subheader("📄 Reporte PDF")
    pdf_bytes = pdf_resumen(resumen.rename(columns={col_tec:"Técnico"}), "Técnico", tec_sel, offset)
    fecha_btn = datetime.now(ZoneInfo("America/Bogota")).strftime("%d-%m-%Y_%H%M")
    st.download_button(label=f"📥 Descargar reporte PDF de SLA (generado el {fecha_btn})",
                       data=pdf_bytes, file_name=f"GIA_SLA_{fecha_btn}.pdf", mime="application/pdf")

# =========================
# PANEL TV
# =========================
else:
    st.markdown("<h1 style='text-align:center;color:#3A86FF;'>📺 GIA | Rendimiento del Equipo</h1>", unsafe_allow_html=True)
    st.caption("IPS Goleman | Inteligencia para el Soporte")
    st.markdown("<hr>", unsafe_allow_html=True)

    up = st.file_uploader("📎 Subir reporte exportado desde GLPI (Detallado de casos)", type=["csv","xlsx"])
    if not up: st.stop()

    offset = st.number_input("Desfase servidor vs Bogotá (horas)", value=5.0, step=0.5)
    df = read_any(up)
    df.columns = [str(c).strip() for c in df.columns]
    col_crea   = pick_col(df, ["apertura","creacion","created"])
    col_cierre = pick_col(df, ["cierre","resol","closed"], requerido=False)
    col_prior  = pick_col(df, ["prioridad","urgencia","priority"])
    col_tec    = pick_col(df, ["asignado a","asignado","tecn","responsable","assigned"], fallback="Asignado a - Técnico")
    col_estado = pick_col(df, ["estado","status"], requerido=False)
    df_calc, resumen = calcular_sla(df.copy(), offset, col_crea, col_cierre, col_prior, col_tec, col_estado)

    if resumen.empty: st.stop()
    fig = px.bar(resumen.sort_values("SLA (%)", ascending=True),
                 x="SLA (%)", y=col_tec, orientation="h",
                 color="SLA (%)", text_auto=".1f",
                 color_continuous_scale=["#EF476F","#FFD166","#06D6A0"],
                 title="Cumplimiento SLA por Técnico")
    fig.update_layout(template="plotly_dark", height=620,
                      title_font=dict(size=28, color="#3A86FF"),
                      font=dict(size=18, color="white"),
                      margin=dict(l=120, r=40, t=80, b=40))
    st.plotly_chart(fig, use_container_width=True)

    prom = resumen["SLA (%)"].mean()
    hora_bog = datetime.now(ZoneInfo("America/Bogota")).strftime("%d/%m/%Y – %H:%M:%S")
    st.markdown(f"<h2 style='text-align:center;color:#06D6A0;'>SLA Global: {prom:.2f}%</h2>", unsafe_allow_html=True)
    st.markdown(f"<p style='text-align:center;color:#AAA;'>Actualizado: {hora_bog} (Bogotá)</p>", unsafe_allow_html=True)
