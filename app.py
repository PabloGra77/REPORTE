import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet
import tempfile

# ==========================
# CONFIGURACIÓN GENERAL
# ==========================
st.set_page_config(page_title="Panel GIA", page_icon="🤖", layout="wide")

st.markdown("""
<style>
.title {text-align:center;font-size:40px;font-weight:bold;color:#3A86FF;}
.subtitle {text-align:center;color:#FF9F1C;font-size:18px;margin-bottom:30px;}
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
        # Leer archivo
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file, sep=None, engine="python")
        else:
            df = pd.read_excel(uploaded_file)
        df = df.fillna(0)

        # Definir columnas base
        COL_TECNICO = df.columns[0]
        COL_ASIGNADOS = "Casos asignados"
        COL_RESUELTOS = "Cantidad de casos resueltos"
        COL_TARDIOS = "Cantidad de casos tardíos"

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
        tecnicos_excluir = st.multiselect("Selecciona técnicos que quieras excluir (opcional):", tecnicos)
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
        # IDENTIFICAR TÉCNICOS DESTACADOS
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

        eficiencia_prom = round(df_validos["Eficiencia (%)"].mean(), 2)
        sla_prom = round(df_validos["Cumplimiento SLA (%)"].mean(), 2)

        # ==========================
        # GRÁFICOS
        # ==========================
        # 1️⃣ Casos
        fig1 = go.Figure()
        fig1.add_trace(go.Bar(x=df_validos[COL_TECNICO], y=df_validos[COL_ASIGNADOS], name="Asignados"))
        fig1.add_trace(go.Bar(x=df_validos[COL_TECNICO], y=df_validos[COL_RESUELTOS], name="Resueltos"))
        fig1.add_trace(go.Bar(x=df_validos[COL_TECNICO], y=df_validos[COL_TARDIOS], name="Tardíos"))
        fig1.update_layout(template="plotly_dark", title="Casos por Técnico", barmode="group")
        st.plotly_chart(fig1, use_container_width=True)

        # 2️⃣ Rendimiento Global
        fig2 = px.bar(df_validos, x=COL_TECNICO, y="Rendimiento Global", color="Rendimiento Global",
                      text_auto=".2f", color_continuous_scale="Viridis", title="Rendimiento Global por Técnico")
        fig2.update_layout(template="plotly_dark")
        st.plotly_chart(fig2, use_container_width=True)

        # 3️⃣ Eficacia Global
        fig3 = px.scatter(df_validos, x=COL_ASIGNADOS, y="Eficacia Global (%)", size=COL_RESUELTOS,
                          color="Eficacia Global (%)", text=COL_TECNICO, color_continuous_scale="Bluered",
                          title="Eficacia Global por Técnico (Casos asignados vs Eficacia)")
        fig3.update_traces(textposition="top center")
        st.plotly_chart(fig3, use_container_width=True)

        # 4️⃣ Salud del grupo
        tot_asignados = df_validos[COL_ASIGNADOS].sum()
        tot_resueltos = df_validos[COL_RESUELTOS].sum()
        tot_tardios = df_validos[COL_TARDIOS].sum()
        pendientes = max(tot_asignados - tot_resueltos, 0)

        eff_grupo = (tot_resueltos / (tot_asignados + 1e-9)) * 100
        sla_grupo = ((tot_resueltos - tot_tardios) / (tot_resueltos + 1e-9)) * 100
        efc_grupo = ((tot_resueltos - tot_tardios) / (tot_asignados + 1e-9)) * 100
        indice_salud = (eff_grupo + sla_grupo + efc_grupo) / 3

        st.subheader("👥 Salud del Grupo")
        st.metric("Índice de Salud del Grupo", f"{indice_salud:.2f}%")

        # ==========================
        # GENERAR PDF CON GRÁFICOS
        # ==========================
        def generar_pdf():
            buffer = BytesIO()
            fecha = datetime.now().strftime("%Y-%m-%d")
            nombre_pdf = f"reporte_GIA_{fecha}.pdf"

            # Guardar las gráficas como imágenes temporales
            temp_imgs = []
            for fig in [fig1, fig2, fig3]:
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
                fig.write_image(tmp.name, format="png", width=800, height=500, scale=2)
                temp_imgs.append(tmp.name)

            # Crear documento PDF
            doc = SimpleDocTemplate(buffer, pagesize=A4)
            styles = getSampleStyleSheet()
            story = [
                Paragraph("📘 Reporte GIA", styles["Title"]),
                Paragraph(f"Fecha de generación: {fecha}", styles["Normal"]),
                Spacer(1, 12),
                Paragraph("Resumen General", styles["Heading2"]),
            ]

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
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.gray),
            ]))
            story.append(tabla)
            story.append(Spacer(1, 12))

            for path in temp_imgs:
                story.append(Spacer(1, 12))
                story.append(Image(path, width=6.5 * inch, height=4 * inch))

            story.append(Spacer(1, 12))
            story.append(Paragraph("Fin del reporte GIA.", styles["Italic"]))

            doc.build(story)
            pdf = buffer.getvalue()
            buffer.close()
            return nombre_pdf, pdf

        nombre_pdf, pdf = generar_pdf()
        st.download_button(
            label="📄 Descargar Reporte GIA (PDF con gráficos)",
            data=pdf,
            file_name=nombre_pdf,
            mime="application/pdf"
        )

    except Exception as e:
        st.error(f"❌ Error al procesar el archivo: {e}")
else:
    st.info("📄 Sube un archivo Excel o CSV del sistema GIA para comenzar el análisis.")
