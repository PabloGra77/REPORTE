import re
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
st.set_page_config(page_title="GIA - Admin & Estadísticas", page_icon="🤖", layout="wide")

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

st.markdown("<h2 style='color:#3A86FF'>🤖 GIA — Panel de Administración y Estadísticas</h2>", unsafe_allow_html=True)
st.markdown("<div class='badge'>IPS Goleman | Inteligencia para el Soporte</div>", unsafe_allow_html=True)
st.markdown("<hr>", unsafe_allow_html=True)

panel = st.sidebar.radio("Selecciona panel", ["🛠️ Panel de Administración", "📊 Panel de Estadísticas"])

# ==============================
# FUNCIONES AUXILIARES
# ==============================
def clean_headers_and_read(uploaded):
    """Lee CSV/Excel, limpia encabezados y duplicados."""
    if uploaded.name.lower().endswith(".csv"):
        df = pd.read_csv(uploaded, sep=None, engine="python", on_bad_lines="skip", header=0)
    else:
        df = pd.read_excel(uploaded, header=0)
    cols, seen = [], {}
    for c in df.columns.astype(str):
        c2 = (c or "").strip()
        if c2 == "":
            c2 = "columna_sin_nombre"
        if c2 in seen:
            seen[c2] += 1
            c2 = f"{c2}_{seen[c2]}"
        else:
            seen[c2] = 0
        cols.append(c2)
    df.columns = cols
    df = df.loc[:, ~df.columns.duplicated()].copy()
    df.columns = [c.lower() for c in df.columns]
    return df

def find_column(df, candidates):
    for c in df.columns:
        for key in candidates:
            if key in c:
                return c
    return None

def generar_pdf_tabla(df_resumen, kpis):
    buffer = BytesIO()
    fecha = datetime.now().strftime("%Y-%m-%d")
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    title = ParagraphStyle('title', parent=styles['Title'], alignment=TA_CENTER, textColor=colors.HexColor("#3A86FF"))

    story = []
    story.append(Paragraph(f"Reporte GIA - Estadísticas por Técnico ({fecha})", title))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        f"Casos asignados (abiertos): {kpis['asignados']} | "
        f"Resueltos: {kpis['resueltos']} | "
        f"Tardíos: {kpis['tardios']} | "
        f"Eficiencia prom: {kpis['eficiencia_prom']:.2f}% | "
        f"Eficacia prom: {kpis['eficacia_prom']:.2f}%",
        styles["Normal"]
    ))
    story.append(Spacer(1, 10))

    data = [df_resumen.columns.tolist()] + df_resumen.values.tolist()
    tabla = Table(data, colWidths=[130, 90, 90, 90, 90, 90])
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
# PANEL ADMINISTRADOR
# ==============================
if panel == "🛠️ Panel de Administración":
    st.subheader("🛠️ Visualizador completo del reporte GLPI")

    uploaded_file = st.file_uploader("📁 Cargar archivo GLPI (CSV o XLSX)", type=["csv", "xlsx"])

    if uploaded_file is not None:
        try:
            df = clean_headers_and_read(uploaded_file)
            st.success(f"✅ Archivo cargado correctamente con {df.shape[0]} filas y {df.shape[1]} columnas.")

            st.markdown("### 🧾 Vista completa del archivo:")
            st.dataframe(df, use_container_width=True)

            st.markdown("### 📋 Columnas detectadas:")
            st.write(list(df.columns))

        except Exception as e:
            st.error(f"❌ Error al procesar el archivo: {e}")
    else:
        st.info("Sube tu archivo GLPI (CSV o Excel) para ver todas las columnas completas.")

# ==============================
# PANEL ESTADÍSTICO
# ==============================
if panel == "📊 Panel de Estadísticas":
    st.subheader("📊 Generar estadísticas desde reporte GLPI")
    up = st.file_uploader("📁 Subir reporte GLPI (CSV o XLSX)", type=["csv", "xlsx"])

    if up is None:
        st.info("Sube un archivo para continuar.")
    else:
        try:
            df = clean_headers_and_read(up)

            col_tipo = df.columns[0]
            col_abiertos = find_column(df, ["abiert", "asign", "abiertos", "cantidad de casos abiertos"])
            col_resueltos = find_column(df, ["resuelt", "cerrad", "cantidad de casos resueltos"])
            col_tardios = find_column(df, ["tard", "vencid", "overdue", "cantidad de casos tardíos"])

            if not all([col_abiertos, col_resueltos, col_tardios]):
                st.error("No se encontraron todas las columnas necesarias (abiertos, resueltos, tardíos). Verifica el archivo.")
                st.stop()

            for c in [col_abiertos, col_resueltos, col_tardios]:
                df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

            resumen = df.groupby(col_tipo, dropna=False)[[col_abiertos, col_resueltos, col_tardios]].sum().reset_index()
            resumen = resumen.rename(columns={
                col_tipo: "Técnico o Categoría",
                col_abiertos: "Casos asignados (abiertos)",
                col_resueltos: "Casos resueltos",
                col_tardios: "Casos tardíos"
            })

            resumen["Eficiencia (%)"] = (resumen["Casos resueltos"] / (resumen["Casos asignados (abiertos)"] + 1e-9)) * 100
            resumen["Eficacia (%)"] = ((resumen["Casos resueltos"] - resumen["Casos tardíos"]) / (resumen["Casos asignados (abiertos)"] + 1e-9)) * 100

            asignados_tot = int(resumen["Casos asignados (abiertos)"].sum())
            resueltos_tot = int(resumen["Casos resueltos"].sum())
            tardios_tot = int(resumen["Casos tardíos"].sum())
            eficiencia_prom = float(resumen["Eficiencia (%)"].mean())
            eficacia_prom = float(resumen["Eficacia (%)"].mean())

            c1, c2, c3, c4 = st.columns(4)
            c1.markdown(f"<div class='metric-card'><div class='metric-value'>{asignados_tot}</div><div class='metric-label'>Asignados (abiertos)</div></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='metric-card'><div class='metric-value'>{resueltos_tot}</div><div class='metric-label'>Resueltos</div></div>", unsafe_allow_html=True)
            c3.markdown(f"<div class='metric-card'><div class='metric-value'>{tardios_tot}</div><div class='metric-label'>Tardíos</div></div>", unsafe_allow_html=True)
            c4.markdown(f"<div class='metric-card'><div class='metric-value'>{eficiencia_prom:.2f}%</div><div class='metric-label'>Eficiencia Prom.</div></div>", unsafe_allow_html=True)
            st.markdown("<hr>", unsafe_allow_html=True)

            st.dataframe(resumen, use_container_width=True)

            fig1 = px.bar(resumen, x="Técnico o Categoría", y=["Casos asignados (abiertos)", "Casos resueltos", "Casos tardíos"],
                          barmode="group", color_discrete_sequence=["#3A86FF", "#06D6A0", "#EF476F"])
            st.plotly_chart(fig1, use_container_width=True)

            fig2 = px.bar(resumen, x="Técnico o Categoría", y=["Eficiencia (%)", "Eficacia (%)"],
                          barmode="group", color_discrete_sequence=["#FFD166", "#118AB2"])
            st.plotly_chart(fig2, use_container_width=True)

            pdf = generar_pdf_tabla(
                resumen[["Técnico o Categoría", "Casos asignados (abiertos)", "Casos resueltos", "Casos tardíos", "Eficiencia (%)", "Eficacia (%)"]],
                {"asignados": asignados_tot, "resueltos": resueltos_tot, "tardios": tardios_tot,
                 "eficiencia_prom": eficiencia_prom, "eficacia_prom": eficacia_prom}
            )
            st.download_button("📄 Descargar Reporte PDF", pdf, file_name="reporte_gia_por_tecnico.pdf")

        except Exception as e:
            st.error(f"❌ Error al procesar: {e}")
