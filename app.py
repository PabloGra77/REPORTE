import pandas as pd
import streamlit as st
import plotly.express as px
from io import BytesIO
from datetime import datetime
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4

# ===============================
# CONFIGURACIÓN VISUAL
# ===============================
st.set_page_config(page_title="Panel GIA Lite", page_icon="🤖", layout="wide")

st.markdown("""
<style>
body {background-color:#0E1117; color:white;}
.metric-card {
    background-color:#1E1E1E; padding:14px; border-radius:12px; 
    border:1px solid #3A86FF33; box-shadow:0 0 6px rgba(58,134,255,0.25);
    text-align:center;
}
.metric-value {font-size:22px; font-weight:800; color:white;}
.metric-label {color:#FF9F1C; font-size:13px;}
hr {border:0; height:1px; background:#333; margin:20px 0;}
</style>
""", unsafe_allow_html=True)

st.markdown("<h2 style='color:#3A86FF'>🤖 Panel GIA Lite</h2>", unsafe_allow_html=True)
st.markdown("<p style='color:#ccc'>Análisis de desempeño de técnicos en GLPI - IPS Goleman</p>", unsafe_allow_html=True)

# ===============================
# CARGA DEL ARCHIVO
# ===============================
archivo = st.file_uploader("📂 Cargar archivo Excel o CSV", type=["xlsx", "csv"])

if archivo:
    try:
        # Leer el CSV o Excel
        if archivo.name.endswith(".csv"):
            df = pd.read_csv(archivo, sep=None, engine="python", on_bad_lines="skip")
        else:
            df = pd.read_excel(archivo)

        # Forzar encabezados como texto
        df.columns = df.columns.astype(str)

        # Tomar solo las columnas necesarias
        columnas_necesarias = [
            df.columns[0],  # Técnico
            "Cantidad de casos abiertos",
            "Cantidad de casos resueltos",
            "Cantidad de casos tardíos"
        ]
        df = df[columnas_necesarias].copy()

        # Renombrar para usar nombres más cortos
        df.columns = ["Técnico", "Casos asignados", "Casos resueltos", "Casos tardíos"]

        # Eliminar filas vacías o con encabezado repetido
        df = df[df["Técnico"].notna() & (df["Técnico"] != "")]
        df = df[df["Técnico"].str.lower() != "técnico"]

        # Convertir columnas numéricas
        for col in ["Casos asignados", "Casos resueltos", "Casos tardíos"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        # ===============================
        # CÁLCULOS
        # ===============================
        df["Eficiencia (%)"] = (df["Casos resueltos"] / (df["Casos asignados"] + 1e-9)) * 100
        df["Eficacia (%)"] = ((df["Casos resueltos"] - df["Casos tardíos"]) / (df["Casos asignados"] + 1e-9)) * 100

        # Promedios
        eficiencia_prom = round(df["Eficiencia (%)"].mean(), 2)
        eficacia_prom = round(df["Eficacia (%)"].mean(), 2)
        asignados = int(df["Casos asignados"].sum())
        resueltos = int(df["Casos resueltos"].sum())
        tardios = int(df["Casos tardíos"].sum())

        # ===============================
        # MÉTRICAS
        # ===============================
        c1, c2, c3 = st.columns(3)
        c1.markdown(f"<div class='metric-card'><div class='metric-value'>{asignados}</div><div class='metric-label'>Casos asignados</div></div>", unsafe_allow_html=True)
        c2.markdown(f"<div class='metric-card'><div class='metric-value'>{resueltos}</div><div class='metric-label'>Casos resueltos</div></div>", unsafe_allow_html=True)
        c3.markdown(f"<div class='metric-card'><div class='metric-value'>{tardios}</div><div class='metric-label'>Casos tardíos</div></div>", unsafe_allow_html=True)

        st.markdown("<hr>", unsafe_allow_html=True)

        # ===============================
        # GRÁFICOS
        # ===============================
        st.markdown("### 📊 Casos por técnico")
        fig1 = px.bar(df, x="Técnico", y=["Casos asignados", "Casos resueltos", "Casos tardíos"],
                      barmode="group", color_discrete_sequence=["#3A86FF", "#06D6A0", "#EF476F"])
        st.plotly_chart(fig1, use_container_width=True)

        st.markdown("### 🎯 Eficiencia y eficacia por técnico")
        fig2 = px.bar(df, x="Técnico", y=["Eficiencia (%)", "Eficacia (%)"],
                      barmode="group", color_discrete_sequence=["#FFD166", "#118AB2"])
        st.plotly_chart(fig2, use_container_width=True)

        # ===============================
        # PDF
        # ===============================
        def generar_pdf():
            buffer = BytesIO()
            fecha = datetime.now().strftime("%Y-%m-%d")
            doc = SimpleDocTemplate(buffer, pagesize=A4)
            story = []

            styles = getSampleStyleSheet()
            title = ParagraphStyle('title', parent=styles['Title'], alignment=TA_CENTER, textColor=colors.HexColor("#3A86FF"))
            normal = ParagraphStyle('normal', parent=styles['Normal'], alignment=TA_LEFT, fontSize=11)

            story.append(Paragraph(f"Reporte GIA Lite - {fecha}", title))
            story.append(Spacer(1, 12))
            story.append(Paragraph(f"Casos asignados: {asignados}", normal))
            story.append(Paragraph(f"Casos resueltos: {resueltos}", normal))
            story.append(Paragraph(f"Casos tardíos: {tardios}", normal))
            story.append(Paragraph(f"Eficiencia promedio: {eficiencia_prom:.2f}%", normal))
            story.append(Paragraph(f"Eficacia promedio: {eficacia_prom:.2f}%", normal))
            story.append(Spacer(1, 14))

            # Tabla de resumen
            tabla = Table(
                [df.columns.tolist()] + df.values.tolist(),
                colWidths=[120, 80, 80, 80, 80, 80]
            )
            tabla.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#3A86FF")),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('GRID', (0, 0), (-1, -1), 0.3, colors.gray),
            ]))
            story.append(tabla)

            doc.build(story)
            pdf = buffer.getvalue()
            buffer.close()
            return pdf

        pdf_data = generar_pdf()
        st.download_button("📄 Descargar Reporte (PDF)", pdf_data, file_name="reporte_gia_lite.pdf")

    except Exception as e:
        st.error(f"❌ Error al procesar el archivo: {e}")

else:
    st.info("📎 Sube tu archivo Excel o CSV para comenzar el análisis.")
