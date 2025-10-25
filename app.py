import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
from datetime import datetime
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
)
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
import tempfile

# ==========================
# CONFIGURACIÓN GLOBAL
# ==========================
st.set_page_config(page_title="Panel GIA", page_icon="🤖", layout="wide")

# ============
# ESTILO CSS GIA
# ============
st.markdown("""
<style>
body {background-color:#0E1117; color:white;}
.banner {
    background: linear-gradient(90deg, #3A86FF, #FF9F1C);
    padding: 18px; border-radius: 12px;
    display: flex; align-items: center; justify-content: flex-start;
    box-shadow: 0 0 20px rgba(255,159,28,0.3); margin-bottom: 25px;
}
.banner-text { font-size: 32px; font-weight: bold; color: white; }
.banner-sub { font-size: 16px; color: #F8F9FA; }
.metric-card {
    background-color:#1E1E1E; padding:16px; border-radius:14px; text-align:center;
    border:1px solid #3A86FF33; box-shadow:0 0 8px rgba(58,134,255,0.25);
}
.metric-value { font-size:22px; font-weight:800; color:#FFFFFF; }
.metric-label { color:#FF9F1C; font-size:13px; }
.badge { display:inline-block; padding:2px 8px; border-radius:999px; background:#23262F; border:1px solid #3A86FF55; font-size:12px; }
hr {border:0;height:1px;background:#333;margin:20px 0;}
.small { font-size:13px; color:#DADADA; }
</style>
""", unsafe_allow_html=True)

# ============
# ENCABEZADO
# ============
st.markdown("""
<div class="banner">
  <div>
    <div class="banner-text">🤖 GIA - Panel de Estadísticas</div>
    <div class="banner-sub">IPS Goleman | Inteligencia para el Soporte</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ==========================
# CARGA DEL ARCHIVO
# ==========================
uploaded_file = st.file_uploader("📁 Cargar archivo Excel o CSV", type=["xlsx", "csv"])

if uploaded_file:
    try:
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file, sep=None, engine="python")
        else:
            df = pd.read_excel(uploaded_file)
        df = df.fillna(0)

        COL_TECNICO = df.columns[0]
        if "Cantidad de casos abiertos" in df.columns:
            df["Casos asignados"] = df["Cantidad de casos abiertos"]

        df.iloc[:, 0] = df.iloc[:, 0].astype(str).str.strip()
        df = df[~df.iloc[:, 0].isin(["", "0", "nan", "None"])].reset_index(drop=True)

        for c in ["Casos asignados", "Cantidad de casos resueltos", "Cantidad de casos tardíos"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

        # ==========================
        # FILTRO DE TÉCNICOS
        # ==========================
        st.markdown("### 🧹 Filtrar Técnicos")
        tecnicos = sorted(df[COL_TECNICO].unique())
        excluir = st.multiselect("Selecciona técnicos para excluir:", tecnicos)
        if excluir:
            df = df[~df[COL_TECNICO].isin(excluir)]

        # ==========================
        # CÁLCULOS POR TÉCNICO
        # ==========================
        df["Eficiencia (%)"] = (df["Cantidad de casos resueltos"] / (df["Casos asignados"] + 1e-9)) * 100
        df["Cumplimiento SLA (%)"] = ((df["Cantidad de casos resueltos"] - df["Cantidad de casos tardíos"]) /
                                      (df["Cantidad de casos resueltos"] + 1e-9)) * 100
        df["Eficacia Global (%)"] = ((df["Cantidad de casos resueltos"] - df["Cantidad de casos tardíos"]) /
                                     (df["Casos asignados"] + 1e-9)) * 100

        df_validos = df.copy()
        max_asignados = df_validos["Casos asignados"].max() if len(df_validos) else 1
        df_validos["Rendimiento Global"] = (
            ((df_validos["Eficiencia (%)"] + df_validos["Cumplimiento SLA (%)"]) / 2)
            * ((1 + (df_validos["Casos asignados"] / max_asignados)) / 2)
        )

        # ==========================
        # TOTALES & MÉTRICAS DE GRUPO
        # ==========================
        tot_asignados = df_validos["Casos asignados"].sum()
        tot_resueltos = df_validos["Cantidad de casos resueltos"].sum()
        tot_tardios  = df_validos["Cantidad de casos tardíos"].sum()
        pendientes   = max(tot_asignados - tot_resueltos, 0)
        n_tecnicos   = df_validos[COL_TECNICO].nunique()

        eficiencia_prom = round(df_validos["Eficiencia (%)"].mean(), 2)
        sla_prom        = round(df_validos["Cumplimiento SLA (%)"].mean(), 2)
        eficacia_prom   = round(df_validos["Eficacia Global (%)"].mean(), 2)

        eff_grupo = (tot_resueltos / (tot_asignados + 1e-9)) * 100
        sla_grupo = ((tot_resueltos - tot_tardios) / (tot_resueltos + 1e-9)) * 100
        efc_grupo = ((tot_resueltos - tot_tardios) / (tot_asignados + 1e-9)) * 100
        indice_salud = round((eff_grupo + sla_grupo + efc_grupo) / 3, 2)

        # ==========================
        # DESTACADOS
        # ==========================
        mejor          = df_validos.loc[df_validos["Rendimiento Global"].idxmax(), COL_TECNICO] if len(df_validos) else "—"
        mas_solicitado = df_validos.loc[df_validos["Casos asignados"].idxmax(), COL_TECNICO]    if len(df_validos) else "—"
        mas_eficaz     = df_validos.loc[df_validos["Eficacia Global (%)"].idxmax(), COL_TECNICO] if len(df_validos) else "—"
        mas_eficaz_val = round(df_validos["Eficacia Global (%)"].max(), 2) if len(df_validos) else 0.0
        peor           = df_validos.loc[df_validos["Rendimiento Global"].idxmin(), COL_TECNICO] if len(df_validos) else "—"

        # ==========================
        # RESUMEN GENERAL
        # ==========================
        st.markdown("## <span class='badge'>📊 Resumen General</span>", unsafe_allow_html=True)

        c1,c2,c3,c4 = st.columns(4)
        c1.markdown(f"<div class='metric-card'><div class='metric-value'>{eficiencia_prom:.2f}%</div><div class='metric-label'>Eficiencia Promedio</div></div>", unsafe_allow_html=True)
        c2.markdown(f"<div class='metric-card'><div class='metric-value'>{sla_prom:.2f}%</div><div class='metric-label'>Cumplimiento SLA Promedio</div></div>", unsafe_allow_html=True)
        c3.markdown(f"<div class='metric-card'><div class='metric-value'>{eficacia_prom:.2f}%</div><div class='metric-label'>Eficacia Promedio</div></div>", unsafe_allow_html=True)
        c4.markdown(f"<div class='metric-card'><div class='metric-value'>{indice_salud:.2f}%</div><div class='metric-label'>Salud del Grupo</div></div>", unsafe_allow_html=True)

        c5,c6,c7,c8 = st.columns(4)
        c5.markdown(f"<div class='metric-card'><div class='metric-value'>{mas_solicitado}</div><div class='metric-label'>Técnico más solicitado</div></div>", unsafe_allow_html=True)
        c6.markdown(f"<div class='metric-card'><div class='metric-value'>{mejor}</div><div class='metric-label'>Mejor Técnico</div></div>", unsafe_allow_html=True)
        c7.markdown(f"<div class='metric-card'><div class='metric-value'>{mas_eficaz}</div><div class='metric-label'>Más eficaz ({mas_eficaz_val:.2f}%)</div></div>", unsafe_allow_html=True)
        c8.markdown(f"<div class='metric-card'><div class='metric-value'>{peor}</div><div class='metric-label'>Menor rendimiento</div></div>", unsafe_allow_html=True)

        # ==========================
        # PDF EXPORT
        # ==========================
        def generar_pdf():
            buffer = BytesIO()
            fecha = datetime.now().strftime("%Y-%m-%d")
            nombre_pdf = f"reporte_GIA_{fecha}.pdf"
            doc = SimpleDocTemplate(buffer, pagesize=A4)
            story = []

            styles = getSampleStyleSheet()
            style_h1 = ParagraphStyle('h1', parent=styles['Heading1'], alignment=TA_CENTER, textColor=colors.HexColor("#3A86FF"))
            style_text = ParagraphStyle('text', parent=styles['Normal'], fontSize=11, leading=15)

            story.append(Paragraph("📘 Reporte GIA", style_h1))
            story.append(Paragraph(f"Fecha: {fecha}", style_text))
            story.append(Spacer(1, 12))
            story.append(Paragraph(f"Eficiencia Prom: {eficiencia_prom}% | SLA: {sla_prom}% | Eficacia: {eficacia_prom}% | Salud: {indice_salud}%", style_text))
            story.append(Spacer(1, 6))
            story.append(Paragraph(f"Más solicitado: {mas_solicitado} | Mejor técnico: {mejor}", style_text))
            story.append(Paragraph(f"Más eficaz: {mas_eficaz} ({mas_eficaz_val}%) | Peor: {peor}", style_text))
            story.append(Spacer(1, 12))
            story.append(Paragraph(f"Totales → Asignados: {tot_asignados} | Resueltos: {tot_resueltos} | Tardíos: {tot_tardios} | Pendientes: {pendientes}", style_text))

            doc.build(story)
            pdf = buffer.getvalue()
            buffer.close()
            return nombre_pdf, pdf

        nombre_pdf, pdf = generar_pdf()
        st.download_button("📄 Descargar Reporte GIA (PDF)", pdf, nombre_pdf, "application/pdf")

    except Exception as e:
        st.error(f"❌ Error al procesar el archivo: {e}")

else:
    st.info("📄 Sube tu archivo Excel o CSV del sistema GIA para comenzar.")
