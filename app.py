import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet

# ==========================
# CONFIGURACIÓN GENERAL
# ==========================
st.set_page_config(page_title="Panel GIA", page_icon="🤖", layout="wide")

st.markdown("""
<style>
.title {
    text-align: center;
    font-size: 40px;
    font-weight: bold;
    color: #3A86FF;
}
.subtitle {
    text-align: center;
    color: #FF9F1C;
    font-size: 18px;
    margin-bottom: 30px;
}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="title">🤖 Panel de Estadísticas GIA</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">IPS Goleman | Plataforma GIA - Inteligencia para el Soporte</div>', unsafe_allow_html=True)

st.markdown("""
Sube tu archivo **Excel (.xlsx)** o **CSV (.csv)** exportado del sistema **GIA**  
para generar reportes de rendimiento técnico.  
> *Nota:* La columna “Cantidad de casos abiertos” se interpreta como “Casos asignados”.
""")

# ==========================
# SUBIR ARCHIVO
# ==========================
uploaded_file = st.file_uploader("📁 Cargar archivo Excel o CSV", type=["xlsx", "csv"])

# ==========================
# PROCESAR DATOS
# ==========================
if uploaded_file:
    try:
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file, sep=None, engine="python")
        else:
            df = pd.read_excel(uploaded_file)

        df = df.fillna(0)

        # Definir columnas
        COL_TECNICO   = df.columns[0]
        COL_ASIGNADOS = "Casos asignados"
        COL_RESUELTOS = "Cantidad de casos resueltos"
        COL_TARDIOS   = "Cantidad de casos tardíos"

        if "Cantidad de casos abiertos" in df.columns:
            df[COL_ASIGNADOS] = df["Cantidad de casos abiertos"]

        df.iloc[:, 0] = df.iloc[:, 0].astype(str).str.strip()
        df = df[~df.iloc[:, 0].isin(["", "0", "nan", "None"])].reset_index(drop=True)

        for c in [COL_ASIGNADOS, COL_RESUELTOS, COL_TARDIOS]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

        # ==========================
        # FILTRO DE TÉCNICOS
        # ==========================
        st.subheader("🧹 Filtrar técnicos del análisis")
        tecnicos = sorted(df[COL_TECNICO].unique())
        tecnicos_excluir = st.multiselect(
            "Selecciona técnicos que quieras excluir del reporte (opcional):",
            options=tecnicos,
            help="Puedes quitar técnicos para ver cómo cambia el rendimiento general."
        )
        if tecnicos_excluir:
            df = df[~df[COL_TECNICO].isin(tecnicos_excluir)]

        # ==========================
        # CÁLCULOS
        # ==========================
        df["Eficiencia (%)"] = (df[COL_RESUELTOS] / (df[COL_ASIGNADOS] + 1e-9)) * 100
        df["Cumplimiento SLA (%)"] = ((df[COL_RESUELTOS] - df[COL_TARDIOS]) / (df[COL_RESUELTOS] + 1e-9)) * 100
        df["Eficacia Global (%)"] = ((df[COL_RESUELTOS] - df[COL_TARDIOS]) / (df[COL_ASIGNADOS] + 1e-9)) * 100

        df_validos = df[(df[COL_ASIGNADOS] > 0) | (df[COL_RESUELTOS] > 0)].copy()
        max_asignados = df_validos[COL_ASIGNADOS].max() if len(df_validos) else 1
        df_validos["Rendimiento Global"] = (
            ((df_validos["Eficiencia (%)"] + df_validos["Cumplimiento SLA (%)"]) / 2)
            * ((1 + (df_validos[COL_ASIGNADOS] / max_asignados)) / 2)
        )

        # ==========================
        # TÉCNICOS DESTACADOS
        # ==========================
        if len(df_validos) > 0:
            try:
                mejor_tecnico = df_validos.loc[df_validos["Rendimiento Global"].idxmax(), COL_TECNICO]
                tecnico_mas_solicitado = df_validos.loc[df_validos[COL_ASIGNADOS].idxmax(), COL_TECNICO]
                tecnico_mas_eficaz = df_validos.loc[df_validos["Eficacia Global (%)"].idxmax(), COL_TECNICO]
                eficacia_valor = round(df_validos["Eficacia Global (%)"].max(), 2)
                peor_tecnico = df_validos.loc[df_validos["Rendimiento Global"].idxmin(), COL_TECNICO]
            except Exception:
                mejor_tecnico = tecnico_mas_solicitado = tecnico_mas_eficaz = peor_tecnico = "—"
                eficacia_valor = 0.0
        else:
            mejor_tecnico = tecnico_mas_solicitado = tecnico_mas_eficaz = peor_tecnico = "—"
            eficacia_valor = 0.0

        eficiencia_prom = round(df_validos["Eficiencia (%)"].mean(), 2) if len(df_validos) else 0.0
        sla_prom = round(df_validos["Cumplimiento SLA (%)"].mean(), 2) if len(df_validos) else 0.0

        # ==========================
        # TABLA DE RESULTADOS
        # ==========================
        st.subheader("📋 Tabla de resultados")
        st.dataframe(df_validos, use_container_width=True)

        # ==========================
        # RESUMEN GENERAL
        # ==========================
        resumen = f"""
        ### 📊 Resumen General
        - 🧩 **Eficiencia promedio:** {eficiencia_prom}%
        - ⏱️ **Cumplimiento SLA promedio:** {sla_prom}%
        - 👥 **Técnico más solicitado:** {tecnico_mas_solicitado}
        - 🥇 **Mejor técnico:** {mejor_tecnico}
        - 💥 **Técnico más eficaz:** {tecnico_mas_eficaz} ({eficacia_valor}%)
        - 🧰 **Técnico con menor rendimiento:** {peor_tecnico}
        """
        st.markdown(resumen)

        # ==========================
        # GENERAR PDF
        # ==========================
        def generar_pdf():
            buffer = BytesIO()
            fecha = datetime.now().strftime("%Y-%m-%d")
            nombre_pdf = f"reporte_GIA_{fecha}.pdf"

            doc = SimpleDocTemplate(buffer, pagesize=A4)
            styles = getSampleStyleSheet()
            story = []

            story.append(Paragraph("📘 Reporte GIA", styles["Title"]))
            story.append(Paragraph(f"Fecha de generación: {fecha}", styles["Normal"]))
            story.append(Spacer(1, 12))
            story.append(Paragraph("Resumen General", styles["Heading2"]))

            datos_tabla = [
                ["Indicador", "Valor"],
                ["Eficiencia promedio", f"{eficiencia_prom}%"],
                ["Cumplimiento SLA promedio", f"{sla_prom}%"],
                ["Técnico más solicitado", tecnico_mas_solicitado],
                ["Mejor técnico", mejor_tecnico],
                ["Más eficaz", f"{tecnico_mas_eficaz} ({eficacia_valor}%)"],
                ["Menor rendimiento", peor_tecnico],
            ]
            tabla = Table(datos_tabla, colWidths=[3 * inch, 3 * inch])
            tabla.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#3A86FF")),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.gray),
            ]))
            story.append(tabla)
            story.append(Spacer(1, 12))
            story.append(Paragraph("Datos Generales por Técnico", styles["Heading2"]))

            # Añadir tabla de técnicos
            tabla_tecnicos = [df_validos.columns.tolist()] + df_validos.values.tolist()
            t = Table(tabla_tecnicos, repeatRows=1)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#FF9F1C")),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.gray),
                ('FONTSIZE', (0, 0), (-1, -1), 7)
            ]))
            story.append(t)
            story.append(Spacer(1, 12))
            story.append(Paragraph("Fin del reporte.", styles["Italic"]))

            doc.build(story)
            pdf = buffer.getvalue()
            buffer.close()
            return nombre_pdf, pdf

        nombre_pdf, pdf = generar_pdf()
        st.download_button(
            label="📄 Descargar Reporte GIA (PDF)",
            data=pdf,
            file_name=nombre_pdf,
            mime="application/pdf"
        )

    except Exception as e:
        st.error(f"❌ Error al procesar el archivo: {e}")

else:
    st.info("📄 Sube un archivo Excel o CSV del sistema GIA para comenzar el análisis.")
