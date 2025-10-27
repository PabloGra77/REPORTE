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
# CONFIGURACIÓN INICIAL
# ==============================
st.set_page_config(page_title="GIA - Comparador de Reportes GLPI", page_icon="🤖", layout="wide")

st.markdown("""
<style>
body {background-color:#0E1117; color:white;}
.badge { display:inline-block; padding:4px 10px; border-radius:999px; background:#23262F; border:1px solid #3A86FF55; font-size:12px; }
.metric-card { background:#1E1E1E; border:1px solid #3A86FF33; border-radius:12px; padding:14px; text-align:center; box-shadow:0 0 6px rgba(58,134,255,0.25); }
.metric-value { font-size:22px; font-weight:800; }
.metric-label { color:#FF9F1C; font-size:12px; }
hr {border:0; height:1px; background:#333; margin:18px 0;}
</style>
""", unsafe_allow_html=True)

st.markdown("<h2 style='color:#3A86FF'>🤖 GIA — Comparador de Reportes GLPI por Categoría</h2>", unsafe_allow_html=True)
st.markdown("<div class='badge'>IPS Goleman | Inteligencia para el Soporte</div>", unsafe_allow_html=True)
st.markdown("<hr>", unsafe_allow_html=True)

# ==============================
# FUNCIONES
# ==============================
def leer_csv_flexible(archivo):
    """Lee CSV con o sin encabezado, detectando separadores automáticamente."""
    try:
        df = pd.read_csv(archivo, sep=None, engine="python", on_bad_lines="skip")
        if df.columns[0].startswith("Unnamed") or "columna" in df.columns[0].lower():
            df.columns = [f"Columna_{i+1}" for i in range(df.shape[1])]
    except Exception:
        df = pd.read_csv(archivo, header=None, sep=None, engine="python", on_bad_lines="skip")
        df.columns = [f"Columna_{i+1}" for i in range(df.shape[1])]
    return df

def generar_pdf_tabla(df_resumen, kpis):
    buffer = BytesIO()
    fecha = datetime.now().strftime("%Y-%m-%d")
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    title = ParagraphStyle('title', parent=styles['Title'], alignment=TA_CENTER, textColor=colors.HexColor("#3A86FF"))

    story = []
    story.append(Paragraph(f"Reporte GIA - Comparación de Casos ({fecha})", title))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        f"Casos asignados: {kpis['asignados']} | Resueltos: {kpis['resueltos']} | Tardíos: {kpis['tardios']} | "
        f"Eficiencia Prom: {kpis['eficiencia_prom']:.2f}% | Eficacia Prom: {kpis['eficacia_prom']:.2f}%",
        styles["Normal"]
    ))
    story.append(Spacer(1, 10))

    data = [df_resumen.columns.tolist()] + df_resumen.values.tolist()
    tabla = Table(data, colWidths=[120, 90, 90, 90, 90, 90])
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

# ==============================
# INTERFAZ
# ==============================
st.subheader("📁 Cargar archivos para comparar")

col1, col2 = st.columns(2)
archivo_detalle = col1.file_uploader("📄 Archivo Detallado (glpi_6.csv)", type=["csv", "xlsx"])
archivo_resumen = col2.file_uploader("📄 Archivo Resumen (glpi_7.csv)", type=["csv", "xlsx"])

if archivo_detalle and archivo_resumen:
    try:
        # Leer archivos
        df_detalle = leer_csv_flexible(archivo_detalle)
        df_resumen = leer_csv_flexible(archivo_resumen)

        # Validar columnas necesarias
        if "Categoría" not in df_detalle.columns:
            st.error("❌ No se encontró la columna 'Categoría' en el archivo de detalle.")
            st.stop()

        if "Asignado a - Técnico" not in df_detalle.columns:
            posibles = [c for c in df_detalle.columns if "técnico" in c.lower() or "asignado" in c.lower()]
            if posibles:
                tecnico_col = posibles[0]
                st.info(f"✅ Se detectó la columna del técnico: **{tecnico_col}**")
            else:
                st.error("❌ No se encontró la columna del técnico ('Asignado a - Técnico').")
                st.stop()
        else:
            tecnico_col = "Asignado a - Técnico"

        # Para el archivo resumen, usar la primera columna como Categoría
        col_categoria_resumen = df_resumen.columns[0]
        st.info(f"✅ Se usará la columna '{col_categoria_resumen}' como categoría en el archivo resumen.")

        # Detectar columnas de abiertos, resueltos y tardíos
        col_abiertos = [c for c in df_resumen.columns if "abiert" in c.lower() or "asign" in c.lower()]
        col_resueltos = [c for c in df_resumen.columns if "resuelt" in c.lower()]
        col_tardios = [c for c in df_resumen.columns if "tard" in c.lower() or "vencid" in c.lower()]

        if not (col_abiertos and col_resueltos and col_tardios):
            st.error("❌ No se detectaron columnas de abiertos, resueltos o tardíos en el archivo resumen.")
            st.stop()

        col_abiertos, col_resueltos, col_tardios = col_abiertos[0], col_resueltos[0], col_tardios[0]

        # Cruce por Categoría
        df_merged = pd.merge(
            df_resumen,
            df_detalle[["Categoría", tecnico_col]],
            left_on=col_categoria_resumen,
            right_on="Categoría",
            how="left"
        )

        # Agrupar por técnico
        resumen = df_merged.groupby(tecnico_col).agg({
            col_abiertos: "sum",
            col_resueltos: "sum",
            col_tardios: "sum"
        }).reset_index()

        resumen = resumen.rename(columns={
            tecnico_col: "Técnico",
            col_abiertos: "Casos asignados (abiertos)",
            col_resueltos: "Casos resueltos",
            col_tardios: "Casos tardíos"
        })

        resumen["Eficiencia (%)"] = (resumen["Casos resueltos"] / (resumen["Casos asignados (abiertos)"] + 1e-9)) * 100
        resumen["Eficacia (%)"] = ((resumen["Casos resueltos"] - resumen["Casos tardíos"]) / (resumen["Casos asignados (abiertos)"] + 1e-9)) * 100

        # ==============================
        # VISUALIZACIÓN Y KPIs
        # ==============================
        asignados_tot = int(resumen["Casos asignados (abiertos)"].sum())
        resueltos_tot = int(resumen["Casos resueltos"].sum())
        tardios_tot = int(resumen["Casos tardíos"].sum())
        eficiencia_prom = float(resumen["Eficiencia (%)"].mean())
        eficacia_prom = float(resumen["Eficacia (%)"].mean())

        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(f"<div class='metric-card'><div class='metric-value'>{asignados_tot}</div><div class='metric-label'>Asignados</div></div>", unsafe_allow_html=True)
        c2.markdown(f"<div class='metric-card'><div class='metric-value'>{resueltos_tot}</div><div class='metric-label'>Resueltos</div></div>", unsafe_allow_html=True)
        c3.markdown(f"<div class='metric-card'><div class='metric-value'>{tardios_tot}</div><div class='metric-label'>Tardíos</div></div>", unsafe_allow_html=True)
        c4.markdown(f"<div class='metric-card'><div class='metric-value'>{eficiencia_prom:.2f}%</div><div class='metric-label'>Eficiencia Prom.</div></div>", unsafe_allow_html=True)

        st.markdown("<hr>", unsafe_allow_html=True)
        st.dataframe(resumen, use_container_width=True)

        fig1 = px.bar(resumen, x="Técnico", y=["Casos asignados (abiertos)", "Casos resueltos", "Casos tardíos"],
                      barmode="group", color_discrete_sequence=["#3A86FF", "#06D6A0", "#EF476F"],
                      title="Casos por Técnico")
        st.plotly_chart(fig1, use_container_width=True)

        fig2 = px.bar(resumen, x="Técnico", y=["Eficiencia (%)", "Eficacia (%)"],
                      barmode="group", color_discrete_sequence=["#FFD166", "#118AB2"],
                      title="Eficiencia y Eficacia por Técnico")
        st.plotly_chart(fig2, use_container_width=True)

        pdf = generar_pdf_tabla(
            resumen[["Técnico", "Casos asignados (abiertos)", "Casos resueltos", "Casos tardíos", "Eficiencia (%)", "Eficacia (%)"]],
            {"asignados": asignados_tot, "resueltos": resueltos_tot, "tardios": tardios_tot,
             "eficiencia_prom": eficiencia_prom, "eficacia_prom": eficacia_prom}
        )
        st.download_button("📄 Descargar Reporte PDF", pdf, file_name="reporte_gia_comparativo.pdf")

    except Exception as e:
        st.error(f"❌ Error al procesar los archivos: {e}")
else:
    st.info("Sube los dos archivos (detalle y resumen) para generar la comparación.")
