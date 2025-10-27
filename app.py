import pandas as pd
import streamlit as st
import plotly.express as px
from datetime import datetime
from io import BytesIO
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4

# ==============================
# CONFIGURACIÓN DE LA APP
# ==============================
st.set_page_config(page_title="GIA - SLA y Detalle de Casos", page_icon="🤖", layout="wide")

st.markdown("""
<style>
body {background-color:#0E1117; color:white;}
.metric-card {
    background:#1E1E1E; border:1px solid #3A86FF33;
    border-radius:12px; padding:14px; text-align:center;
    box-shadow:0 0 6px rgba(58,134,255,0.25);
}
.metric-value { font-size:22px; font-weight:800; }
.metric-label { color:#FF9F1C; font-size:12px; }
hr {border:0; height:1px; background:#333; margin:18px 0;}
</style>
""", unsafe_allow_html=True)

st.markdown("<h2 style='color:#3A86FF'>🤖 GIA — Cumplimiento SLA y Detalle de Casos</h2>", unsafe_allow_html=True)
st.markdown("<div style='color:#DADADA;'>IPS Goleman | Inteligencia para el Soporte</div>", unsafe_allow_html=True)
st.markdown("<hr>", unsafe_allow_html=True)

# ==============================
# CARGA DE ARCHIVOS
# ==============================
col1, col2 = st.columns(2)
sla_file = col1.file_uploader("📊 Cargar archivo de SLA (tecnicos.csv)", type=["csv", "xlsx"])
detalle_file = col2.file_uploader("📁 Cargar archivo de Detalle de Casos (glpi_6.csv)", type=["csv", "xlsx"])

if not sla_file or not detalle_file:
    st.info("Por favor, sube ambos archivos para generar el informe completo.")
    st.stop()

# ==============================
# LECTURA DE ARCHIVOS
# ==============================
def leer_archivo(file):
    if file.name.endswith(".csv"):
        return pd.read_csv(file, sep=None, engine="python", on_bad_lines="skip")
    else:
        return pd.read_excel(file)

df_sla = leer_archivo(sla_file)
df_detalle = leer_archivo(detalle_file)

# Normalizar nombres de columnas
df_sla.columns = [c.strip() for c in df_sla.columns]
df_detalle.columns = [c.strip() for c in df_detalle.columns]

# ==============================
# PANEL 1️⃣: CUMPLIMIENTO SLA
# ==============================
st.subheader("📈 Cumplimiento de SLA por Técnico")

# Detectar columnas clave automáticamente
col_tecnico = df_sla.columns[0]
col_abiertos = [c for c in df_sla.columns if "abiert" in c.lower() or "asign" in c.lower()][0]
col_resueltos = [c for c in df_sla.columns if "resuelt" in c.lower()][0]
col_tardios = [c for c in df_sla.columns if "tard" in c.lower() or "vencid" in c.lower()][0]

# Limpiar y convertir a numérico
for c in [col_abiertos, col_resueltos, col_tardios]:
    df_sla[c] = pd.to_numeric(df_sla[c], errors="coerce").fillna(0)

# Cálculos
df_sla["Eficiencia (%)"] = (df_sla[col_resueltos] / (df_sla[col_abiertos] + 1e-9)) * 100
df_sla["Eficacia (%)"] = ((df_sla[col_resueltos] - df_sla[col_tardios]) / (df_sla[col_abiertos] + 1e-9)) * 100
df_sla["Cumplimiento SLA (%)"] = (df_sla["Eficiencia (%)"] + df_sla["Eficacia (%)"]) / 2

# Métricas globales
eficiencia_prom = df_sla["Eficiencia (%)"].mean()
eficacia_prom = df_sla["Eficacia (%)"].mean()
sla_prom = df_sla["Cumplimiento SLA (%)"].mean()

# Mostrar métricas globales
c1, c2, c3 = st.columns(3)
c1.markdown(f"<div class='metric-card'><div class='metric-value'>{eficiencia_prom:.2f}%</div><div class='metric-label'>Eficiencia Promedio</div></div>", unsafe_allow_html=True)
c2.markdown(f"<div class='metric-card'><div class='metric-value'>{eficacia_prom:.2f}%</div><div class='metric-label'>Eficacia Promedio</div></div>", unsafe_allow_html=True)
c3.markdown(f"<div class='metric-card'><div class='metric-value'>{sla_prom:.2f}%</div><div class='metric-label'>Cumplimiento SLA Global</div></div>", unsafe_allow_html=True)

# Tabla
st.dataframe(df_sla, use_container_width=True)

# Gráficos
fig1 = px.bar(df_sla, x=col_tecnico, y=["Eficiencia (%)", "Eficacia (%)", "Cumplimiento SLA (%)"],
              barmode="group", color_discrete_sequence=["#3A86FF", "#06D6A0", "#FFD166"],
              title="Cumplimiento de SLA por Técnico")
st.plotly_chart(fig1, use_container_width=True)

# ==============================
# PANEL 2️⃣: DETALLE DE CASOS
# ==============================
st.markdown("<hr>", unsafe_allow_html=True)
st.subheader("🧾 Detalle de Casos por Técnico")

# Verificar columnas necesarias
if "Asignado a - Técnico" not in df_detalle.columns:
    posibles = [c for c in df_detalle.columns if "tecn" in c.lower() or "asign" in c.lower()]
    if posibles:
        col_tecnico_detalle = posibles[0]
    else:
        st.error("❌ No se encontró la columna del técnico en el archivo de detalle.")
        st.stop()
else:
    col_tecnico_detalle = "Asignado a - Técnico"

# Selector de técnico
tecnicos = sorted(df_detalle[col_tecnico_detalle].dropna().unique().tolist())
tecnico_seleccionado = st.selectbox("👤 Selecciona un técnico para ver su detalle:", tecnicos)

# Filtrar y mostrar
df_filtrado = df_detalle[df_detalle[col_tecnico_detalle] == tecnico_seleccionado]
st.write(f"📋 Casos del técnico **{tecnico_seleccionado}**: {len(df_filtrado)} registros encontrados.")
st.dataframe(df_filtrado, use_container_width=True)

# ==============================
# DESCARGAR REPORTE PDF
# ==============================
def generar_pdf(df_sla, tecnico):
    buffer = BytesIO()
    fecha = datetime.now().strftime("%Y-%m-%d")
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    title = ParagraphStyle('title', parent=styles['Title'], alignment=TA_CENTER, textColor=colors.HexColor("#3A86FF"))

    story = []
    story.append(Paragraph(f"Reporte GIA - SLA y Detalle de Casos ({fecha})", title))
    story.append(Spacer(1, 10))

    story.append(Paragraph(f"Técnico: {tecnico}", styles["Heading3"]))
    story.append(Spacer(1, 5))

    # SLA general
    story.append(Paragraph(f"Eficiencia Promedio: {eficiencia_prom:.2f}%<br/>Eficacia Promedio: {eficacia_prom:.2f}%<br/>SLA Global: {sla_prom:.2f}%", styles["Normal"]))
    story.append(Spacer(1, 10))

    # Tabla SLA
    data = [df_sla.columns.tolist()] + df_sla.values.tolist()
    tabla = Table(data, colWidths=[110]*len(df_sla.columns))
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#3A86FF")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('GRID', (0,0), (-1,-1), 0.3, colors.gray)
    ]))
    story.append(tabla)
    story.append(Spacer(1, 15))

    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf

pdf_bytes = generar_pdf(df_sla, tecnico_seleccionado)
st.download_button("📄 Descargar Reporte PDF", pdf_bytes, file_name="reporte_sla_y_detalle.pdf")
