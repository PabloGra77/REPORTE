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

# Detectar modo TV por query string (?tv=1)
try:
    is_tv = "tv" in st.query_params and st.query_params.get("tv") in ("1", "true", "True")
except Exception:
    # Compatibilidad con versiones antiguas
    is_tv = False

# Tema oscuro forzado (para TODOS los usuarios)
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
.stDownloadButton button {
  background:#3A86FF !important; color:white !important; border:none !important;
}
.stDownloadButton button:hover { background:#5FA8FF !important; }
hr {border:0; height:1px; background:#333; margin:18px 0;}
</style>
""", unsafe_allow_html=True)

# =========================
# PARÁMETROS DE NEGOCIO
# =========================
# Horario laboral por día (0=Lunes ... 6=Domingo)
WORK_SCHEDULE = {
    0:[(time(7,0), time(17,0))],
    1:[(time(7,0), time(17,0))],
    2:[(time(7,0), time(17,0))],
    3:[(time(7,0), time(17,0))],
    4:[(time(7,0), time(16,0))],  # Viernes (ajustado)
    5:[(time(8,0), time(13,0))],  # Sábado
    6:[]                          # Domingo
}

# SLA por prioridad (HORAS hábiles) — 1 día = 8h hábiles
PRIORITY_SLA_HOURS = {"muy alta":4, "alta":8, "media":16, "baja":32}

# =========================
# UTILIDADES
# =========================
def strip_accents(s: str) -> str:
    if s is None: return ""
    return "".join(ch for ch in unicodedata.normalize("NFD", str(s)) if unicodedata.category(ch) != "Mn")

def norm(s: str) -> str:
    return strip_accents(str(s)).lower().strip()

def read_any(file):
    name = file.name.lower()
    if name.endswith(".csv"):
        # detector robusto de separador
        try:
            return pd.read_csv(file, sep=None, engine="python", on_bad_lines="skip")
        except Exception:
            file.seek(0)
            return pd.read_csv(file, on_bad_lines="skip")
    return pd.read_excel(file)

def to_ts(s):
    if pd.isna(s): return pd.NaT
    # Permitir dd/mm/yyyy y yyyy-mm-dd, etc.
    return pd.to_datetime(s, errors="coerce", dayfirst=True, utc=False)

def business_seconds_between(start: datetime, end: datetime) -> float:
    """Segundos hábiles entre dos timestamps (usando WORK_SCHEDULE)."""
    if pd.isna(start) or pd.isna(end) or end <= start:
        return 0.0
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
        if nxt >= end:
            break
        cur = nxt
    return total

def horas_habiles(start, end) -> float:
    return business_seconds_between(start, end) / 3600.0

def sla_limit_hours(priority_val: str) -> float:
    p = norm(priority_val)
    for key, hrs in PRIORITY_SLA_HOURS.items():
        if key in p:
            return hrs
    return 8.0  # por defecto 1 día hábil

def pick_col(df: pd.DataFrame, posibles, requerido=True, fallback=None):
    for c in df.columns:
        if any(p in norm(c) for p in posibles):
            return c
    if fallback and fallback in df.columns:
        return fallback
    if requerido:
        st.error(f"❌ No encontré columna requerida. Busqué: {posibles}")
        st.stop()
    return None

def safe_bar(fig_df, x, y, **kwargs):
    if fig_df.empty:
        st.warning("Sin datos suficientes para graficar.")
        return
    fig = px.bar(fig_df, x=x, y=y, **kwargs)
    st.plotly_chart(fig, use_container_width=True)

# =========================
# BLOQUES COMUNES
# =========================
def calcular_sla(df: pd.DataFrame, offset_hours: float, col_crea, col_cierre, col_prior, col_tec, col_estado):
    # Ajuste de tiempos: restar offset para llevar a hora Bogotá
    df["_crea_raw"] = df[col_crea].apply(to_ts)
    df["_cierre_raw"] = df[col_cierre].apply(to_ts) if col_cierre else pd.NaT
    df["_crea"] = df["_crea_raw"].apply(lambda t: t - timedelta(hours=offset_hours) if pd.notna(t) else pd.NaT)
    df["_cierre"] = df["_cierre_raw"].apply(lambda t: t - timedelta(hours=offset_hours) if pd.notna(t) else pd.NaT)

    # Horas hábiles y límite SLA por prioridad
    df["Horas hábiles"] = df.apply(
        lambda r: horas_habiles(r["_crea"], r["_cierre"]) if pd.notna(r["_cierre"]) else 0.0, axis=1
    )
    df["SLA (h)"] = df[col_prior].apply(sla_limit_hours)

    # Estado SLA
    def estado_sla(row):
        if pd.isna(row["_cierre"]):
            return "Abierto"
        return "Cumplido" if row["Horas hábiles"] <= row["SLA (h)"] else "Tardío"
    df["Estado SLA"] = df.apply(estado_sla, axis=1)

    # Heurística de cerrado si falta fecha cierre pero “estado” sugiere resuelto
    def is_closed(row):
        if pd.notna(row["_cierre"]):
            return True
        if col_estado:
            e = norm(row[col_estado])
            return e.startswith("res") or "cerr" in e
        return False

    df["_cerrado"] = df.apply(is_closed, axis=1)
    df["_tardio"] = (df["_cerrado"]) & (df["Estado SLA"] == "Tardío")

    # Resumen por técnico
    resumen = (
        df.groupby(col_tec)
          .agg(Asignados=(col_crea, "count"),
               Resueltos=("_cerrado", "sum"),
               Tardíos=("_tardio", "sum"))
          .reset_index()
    )
    resumen["SLA (%)"] = ((resumen["Resueltos"] - resumen["Tardíos"]) / (resumen["Asignados"] + 1e-9)) * 100

    # Fechas visibles (en Bogotá)
    df["Apertura (Bogotá)"] = df["_crea"]
    df["Cierre (Bogotá)"] = df["_cierre"]

    return df, resumen

def pdf_resumen(resumen: pd.DataFrame, col_tec_name: str, tecnico_filtrado: str | None, desfase_horas: float):
    buf = BytesIO()
    fecha = datetime.now(ZoneInfo("America/Bogota")).strftime("%d/%m/%Y – %H:%M (hora local Bogotá)")
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=30, bottomMargin=20)
    styles = getSampleStyleSheet()
    title = ParagraphStyle('t', parent=styles['Title'], alignment=TA_CENTER, textColor=colors.HexColor("#3A86FF"))

    story = []
    story.append(Paragraph("GIA – Reporte de SLA", title))
    story.append(Paragraph(f"Generado el {fecha}", styles["Normal"]))
    story.append(Paragraph(f"Desfase servidor estimado: {desfase_horas:+.1f} h", styles["Normal"]))
    if tecnico_filtrado:
        story.append(Paragraph(f"Técnico filtrado: <b>{tecnico_filtrado}</b>", styles["Normal"]))
    story.append(Spacer(1, 10))

    data = [["Técnico", "Asignados", "Resueltos", "Tardíos", "SLA (%)"]]
    for _, r in resumen.iterrows():
        data.append([r[col_tec_name], int(r["Asignados"]), int(r["Resueltos"]), int(r["Tardíos"]), f"{r['SLA (%)']:.2f}%"])
    tbl = Table(data, colWidths=[120, 70, 70, 70, 70])
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#3A86FF")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('GRID', (0,0), (-1,-1), 0.3, colors.gray)
    ]))
    story.append(tbl)
    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes

# =========================
# UI – PANEL PRINCIPAL
# =========================
if not is_tv:
    st.markdown("<h2 style='color:#3A86FF'>🤖 GIA — Análisis de SLA</h2>", unsafe_allow_html=True)
    st.caption("IPS Goleman | Inteligencia para el Soporte")
    st.markdown("<hr>", unsafe_allow_html=True)

    # Offset (desfase servidor vs Bogotá)
    offset = st.number_input("Diferencia horaria Servidor vs Bogotá (horas)", value=5.0, step=0.5)
    now_bog = datetime.now(ZoneInfo("America/Bogota"))
    server_est = now_bog + timedelta(hours=offset)
    c1, c2 = st.columns(2)
    c1.markdown(f"<div class='metric-card'><div class='metric-value'>{now_bog.strftime('%Y-%m-%d %H:%M:%S')}</div><div class='metric-label'>Hora Bogotá</div></div>", unsafe_allow_html=True)
    c2.markdown(f"<div class='metric-card'><div class='metric-value'>{server_est.strftime('%Y-%m-%d %H:%M:%S')}</div><div class='metric-label'>Hora Servidor (estimada)</div></div>", unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)
    uploaded = st.file_uploader("📎 Subir reporte exportado desde GLPI (Detallado de casos)", type=["csv","xlsx"])
    if not uploaded:
        st.info("Sube tu archivo para generar el informe.")
        st.stop()

    df = read_any(uploaded)
    df.columns = [str(c).strip() for c in df.columns]

    # Detección de columnas
    col_crea   = pick_col(df, ["apertura", "creacion", "fecha de apertura", "fecha de creacion", "created"])
    col_cierre = pick_col(df, ["cierre", "resol", "fecha de cierre", "closed"], requerido=False)
    col_prior  = pick_col(df, ["prioridad", "urgencia", "priority"])
    col_tec    = pick_col(df, ["asignado a", "tecn", "técn", "responsable", "assigned"], fallback="Asignado a - Técnico")
    col_estado = pick_col(df, ["estado", "status"], requerido=False)

    # Calcular SLA
    df_calc, resumen = calcular_sla(df.copy(), offset, col_crea, col_cierre, col_prior, col_tec, col_estado)

    # Filtro: solo un técnico
    st.subheader("📌 Filtros")
    solo_uno = st.checkbox("Consultar un solo técnico")
    tec_sel = None
    if solo_uno:
        tec_list = sorted([x for x in df_calc[col_tec].dropna().unique().tolist()])
        tec_sel = st.selectbox("👤 Técnico", tec_list) if tec_list else None
        if tec_sel:
            df_scope = df_calc[df_calc[col_tec] == tec_sel].copy()
            resumen_scope = resumen[resumen[col_tec] == tec_sel].copy()
        else:
            df_scope = df_calc.copy()
            resumen_scope = resumen.copy()
    else:
        df_scope = df_calc.copy()
        resumen_scope = resumen.copy()

    # KPIs
    st.subheader("📈 Resumen SLA")
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f"<div class='metric-card'><div class='metric-value'>{int(resumen_scope['Asignados'].sum())}</div><div class='metric-label'>Asignados</div></div>", unsafe_allow_html=True)
    c2.markdown(f"<div class='metric-card'><div class='metric-value'>{int(resumen_scope['Resueltos'].sum())}</div><div class='metric-label'>Resueltos</div></div>", unsafe_allow_html=True)
    c3.markdown(f"<div class='metric-card'><div class='metric-value'>{int(resumen_scope['Tardíos'].sum())}</div><div class='metric-label'>Tardíos</div></div>", unsafe_allow_html=True)
    c4.markdown(f"<div class='metric-card'><div class='metric-value'>{resumen_scope['SLA (%)'].mean():.2f}%</div><div class='metric-label'>SLA promedio</div></div>", unsafe_allow_html=True)

    st.dataframe(resumen_scope[[col_tec, "Asignados", "Resueltos", "Tardíos", "SLA (%)"]], use_container_width=True)

    # Gráfico barras SLA por técnico
    st.subheader("📈 SLA (%) por técnico")
    if not resumen_scope.empty:
        fig_bar = px.bar(
            resumen_scope.sort_values("SLA (%)", ascending=False),
            x=col_tec, y="SLA (%)",
            color="SLA (%)",
            color_continuous_scale=["#EF476F","#FFD166","#06D6A0"],
            title="Cumplimiento SLA (%) por Técnico",
            text_auto=".2f",
        )
        fig_bar.update_layout(template="plotly_dark")
        st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.warning("No hay datos para graficar el SLA por técnico.")

    # Gráfico pie Cumplido vs Tardío (solo si hay cerrados)
    st.subheader("📊 Distribución de casos cerrados")
    cerrados = df_scope[df_scope["_cerrado"] == True]
    if not cerrados.empty:
        cumplidos = int((cerrados["Estado SLA"] == "Cumplido").sum())
        tardios   = int((cerrados["Estado SLA"] == "Tardío").sum())
        if (cumplidos + tardios) > 0:
            pie = px.pie(
                pd.DataFrame({"Estado": ["Cumplido", "Tardío"], "Cantidad": [cumplidos, tardios]}),
                names="Estado", values="Cantidad",
                color="Estado", color_discrete_map={"Cumplido": "#06D6A0", "Tardío": "#EF476F"},
                title="Cumplido vs Tardío",
            )
            pie.update_layout(template="plotly_dark")
            st.plotly_chart(pie, use_container_width=True)
        else:
            st.info("No hay suficientes casos cerrados para distribuir (todos abiertos).")
    else:
        st.info("No hay casos cerrados en el conjunto filtrado.")

    # Detalle de casos (Bogotá)
    st.subheader("🧾 Detalle de casos (Bogotá)")
    cols_show = [c for c in [
        "Apertura (Bogotá)", "Cierre (Bogotá)", col_tec, col_prior, col_estado,
        "Horas hábiles", "SLA (h)", "Estado SLA"
    ] if c in df_scope.columns]
    st.dataframe(df_scope[cols_show], use_container_width=True)

    # PDF con fecha/hora Bogotá
    st.subheader("📄 Reporte PDF")
    pdf_bytes = pdf_resumen(resumen_scope.rename(columns={col_tec: "Técnico"}), "Técnico", tec_sel if solo_uno else None, offset)
    fecha_btn = datetime.now(ZoneInfo("America/Bogota")).strftime("%d-%m-%Y_%H%M")
    st.download_button(
        label=f"📥 Descargar reporte PDF de SLA (generado el {fecha_btn})",
        data=pdf_bytes,
        file_name=f"GIA_SLA_{fecha_btn}.pdf",
        mime="application/pdf"
    )

# =========================
# UI – PANEL TV (simple y claro)
# =========================
else:
    # Título grande
    st.markdown("<h1 style='text-align:center;color:#3A86FF;'>📺 GIA | Rendimiento del Equipo</h1>", unsafe_allow_html=True)
    st.caption("IPS Goleman | Inteligencia para el Soporte")
    st.markdown("<hr>", unsafe_allow_html=True)

    # Pedir archivo (no guardamos en disco para evitar errores)
    uploaded = st.file_uploader("📎 Subir reporte exportado desde GLPI (Detallado de casos)", type=["csv","xlsx"])
    if not uploaded:
        st.info("Sube el reporte para visualizar el panel.")
        st.stop()

    # Offset fijo visible (puedes ajustar si lo necesitas en TV)
    offset = st.number_input("Desfase servidor vs Bogotá (horas)", value=5.0, step=0.5)

    df = read_any(uploaded)
    df.columns = [str(c).strip() for c in df.columns]

    col_crea   = pick_col(df, ["apertura", "creacion", "fecha de apertura", "fecha de creacion", "created"])
    col_cierre = pick_col(df, ["cierre", "resol", "fecha de cierre", "closed"], requerido=False)
    col_prior  = pick_col(df, ["prioridad", "urgencia", "priority"])
    col_tec    = pick_col(df, ["asignado a", "tecn", "técn", "responsable", "assigned"], fallback="Asignado a - Técnico")
    col_estado = pick_col(df, ["estado", "status"], requerido=False)

    df_calc, resumen = calcular_sla(df.copy(), offset, col_crea, col_cierre, col_prior, col_tec, col_estado)

    if resumen.empty:
        st.warning("No hay datos para mostrar en el Panel TV.")
        st.stop()

    # Ranking horizontal por SLA (%)
    fig = px.bar(
        resumen.sort_values("SLA (%)", ascending=True),
        x="SLA (%)", y=col_tec, orientation="h",
        color="SLA (%)", text_auto=".1f",
        color_continuous_scale=["#EF476F","#FFD166","#06D6A0"],
        title="Cumplimiento SLA por Técnico"
    )
    fig.update_layout(template="plotly_dark", height=620,
                      title_font=dict(size=28, color="#3A86FF"),
                      font=dict(size=18, color="white"),
                      margin=dict(l=120, r=40, t=80, b=40))
    st.plotly_chart(fig, use_container_width=True)

    # Promedio global + hora Bogotá
    prom = resumen["SLA (%)"].mean()
    hora_bog = datetime.now(ZoneInfo("America/Bogota")).strftime("%d/%m/%Y – %H:%M:%S")
    st.markdown(f"<h2 style='text-align:center;color:#06D6A0;'>SLA Global: {prom:.2f}%</h2>", unsafe_allow_html=True)
    st.markdown(f"<p style='text-align:center;color:#AAA;'>Actualizado: {hora_bog} (Bogotá)</p>", unsafe_allow_html=True)
