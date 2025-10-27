import pandas as pd
import streamlit as st
import plotly.express as px
from datetime import datetime
from io import BytesIO
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
import tempfile

# ==============================
# CONFIGURACIÓN DE LA APP
# ==============================
st.set_page_config(page_title="GIA - SLA por Técnico", page_icon="🤖", layout="wide")

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
sla_file = col1.file_uploader("📊 Cargar archivo SLA (tecnicos.csv)", type=["csv", "xlsx"])
detalle_file = col2.file_uploader("📁 Cargar archivo de Detalle de Casos (glpi_6.csv)", type=["csv", "xlsx"])

if not sla_file or not detalle_file:
    st.info("Por favor, sube ambos archivos para generar el informe.")
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

# ==============================
# PROCESAR SLA (tecnicos.csv)
# ==============================
df_sla.columns = [c.strip() for c in df_sla.columns]
col_tecnico = df_sla.columns[0]
col_abiertos = [c for c in df_sla.columns if "abiert" in c.lower() or "asign" in c.lower()][0]
col_resueltos = [c for c in df_sla.columns if "resuelt" in c.lower()][0]
col_tardios = [c for c in df_sla.columns if "tard" in c.lower() or "vencid" in c.lower()][0]

for c in [col_abiertos, col_resueltos, col_tardios]:
    df_sla[c] = pd.to_numeric(df_sla[c], errors="coerce").fillna(0)

# Cálculo de SLA
df_sla["SLA (%)"] = ((df_sla[col_resueltos] - df_sla[col_tardios]) / (df_sla[col_abiertos] + 1e-9)) * 100

# ==============================
# VISUALIZACIÓN SLA
# ==============================
st.subheader("📈 Cumplimiento de SLA por Técnico")

c1, c2, c3 = st.columns(3)
c1.metric("Casos Asignados (Total)", int(df_sla[col_abiertos].sum()))
c2.metric("Casos Resueltos (Total)", int(df_sla[col_resueltos].sum()))
c3.metric("Casos Tardíos (Total)", int(df_sla[col_tardios].sum()))

sla_promedio = df_sla["SLA (%)"].mean()
st.markdown(f"<div class='metric-card'><div class='metric-value'>{sla_promedio:.2f}%</div><div class='metric-label'>Cumplimiento SLA Promedio</div></div>", unsafe_allow_html=True)

st.dataframe(df_sla[[col_tecnico, col_abiertos, col_resueltos, col_tardios, "SLA (%)"]], use_container_width=True)

fig = px.bar(df_sla, x=col_tecnico, y="SLA (%)",
             color="SLA (%)", color_continuous_scale="Viridis",
             title="Cumplimiento del SLA por Técnico")
st.plotly_chart(fig, use_container_width=True)

# ==============================
# DETALLE DE CASOS
# ==============================
st.markdown("<hr>", unsafe_allow_html=True)
st.subheader("🧾 Detalle de Casos por Técnico")

# Buscar la columna del técnico en el detalle
col_tecnico_detalle = None
for c in df_detalle.columns:
    if any(k in c.lower() for k in ["tecn", "asignado", "respon", "autor"]):
        col_tecnico_detalle = c
        break

if not col_tecnico_detalle:
    st.error("❌ No se encontró la columna del técnico en el archivo de detalle.")
    st.stop()

# Selector de técnico
tecnicos = sorted(df_detalle[col_tecnico_detalle].dropna().unique().tolist())
tecnico_sel = st.selectbox("👤 Selecciona un técnico para ver sus casos:", tecnicos)

# Mostrar casos de ese técnico
df_filtrado = df_detalle[df_detalle[col_tecnico_detalle] == tecnico_sel]
st.write(f"📋 Casos asignados a **{tecnico_sel}**: {len(df_filtrado)}")
st.dataframe(df_filtrado, use_container_width=True)

# ==============================
# GENERAR PDF
# ==============================
st.markdown("<hr>", unsafe_allow_html=True)
st.subheader("📄 Generar reporte PDF")

def generar_pdf(df_sla, tecnico_sel, df_filtrado, fig):
    buffer = BytesIO()
    fecha = datetime.now().strftime("%Y-%m-%d")
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=30, bottomMargin=20)
    styles = getSampleStyleSheet()
    title = ParagraphStyle('title', parent=styles['Title'], alignment=TA_CENTER, textColor=colors.HexColor("#3A86FF"))

    story = []
    story.append(Paragraph(f"Reporte GIA - Cumplimiento SLA ({fecha})", title))
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"Cumplimiento promedio del SLA: {df_sla['SLA (%)'].mean():.2f}%", styles["Normal"]))
    story.append(Spacer(1, 10))

    # Tabla de SLA
    data = [["Técnico", "Asignados", "Resueltos", "Tardíos", "SLA (%)"]]
    for _, r in df_sla.iterrows():
        data.append([r[col_tecnico], int(r[col_abiertos]), int(r[col_resueltos]), int(r[col_tardios]), f"{r['SLA (%)']:.2f}%"])

    tabla = Table(data, colWidths=[90, 80, 80, 80, 70])
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#3A86FF")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('GRID', (0,0), (-1,-1), 0.3, colors.gray)
    ]))
    story.append(tabla)
    story.append(Spacer(1, 15))

    # Agregar gráfico
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    fig.write_image(tmp.name, width=800, height=400)
    story.append(Image(tmp.name, width=6.3*inch, height=3.2*inch))
    story.append(Spacer(1, 20))

    # Detalle del técnico seleccionado
    story.append(Paragraph(f"Detalle de casos del técnico: {tecnico_sel}", styles["Heading3"]))
    story.append(Spacer(1, 10))
    cols = list(df_filtrado.columns[:5])
    data_det = [cols] + df_filtrado[cols].astype(str).values.tolist()[:10]  # muestra los primeros 10
    tabla_det = Table(data_det, colWidths=[90]*len(cols))
    tabla_det.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#118AB2")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('GRID', (0,0), (-1,-1), 0.3, colors.gray)
    ]))
    story.append(tabla_det)

    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf

pdf_bytes = generar_pdf(df_sla, tecnico_sel, df_filtrado, fig)
st.download_button("📥 Descargar Reporte PDF", pdf_bytes, file_name="reporte_SLA_GIA.pdf")
