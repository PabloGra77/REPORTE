import pandas as pd
import streamlit as st
import plotly.express as px
from io import BytesIO

# ==========================
# CONFIGURACIÓN GENERAL
# ==========================
st.set_page_config(page_title="Panel GIA", page_icon="🤖", layout="wide")

# Encabezado
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
para generar automáticamente los reportes y estadísticas de rendimiento técnico.  
Incluye cálculos de eficiencia, cumplimiento de SLA y comparativos visuales por técnico.  
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
        # Detectar tipo de archivo
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file, sep=None, engine="python")
        else:
            df = pd.read_excel(uploaded_file)

        df = df.fillna(0)

        # Ignorar columnas no relevantes
        columnas_ignorar = [
            "Cantidad de casos cerrados",
            "Cantidad de encuestas de satisfacción abiertas",
            "Cantidad de encuestas de satisfacción respuestas",
            "Satisfacción promedio"
        ]
        columnas_existentes = [col for col in df.columns if col not in columnas_ignorar]

        # Asegurar que la primera columna sea texto (técnico)
        df.iloc[:, 0] = df.iloc[:, 0].astype(str).str.strip()

        # Convertir columnas relevantes a numéricas
        for col in columnas_existentes[1:]:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        # === CÁLCULOS ===
        df["Eficiencia (%)"] = (
            df["Cantidad de casos resueltos"] /
            (df["Cantidad de casos abiertos"] + df["Cantidad de casos resueltos"] + 1e-9)
        ) * 100

        df["Cumplimiento SLA (%)"] = (
            (df["Cantidad de casos resueltos"] - df["Cantidad de casos tardíos"]) /
            (df["Cantidad de casos resueltos"] + 1e-9)
        ) * 100

        # ==========================
        # TABLA Y RESUMEN
        # ==========================
        st.subheader("📋 Tabla de resultados")
        st.dataframe(df, use_container_width=True)

        eficiencia_prom = round(df["Eficiencia (%)"].mean(), 2)
        sla_prom = round(df["Cumplimiento SLA (%)"].mean(), 2)
        mejor_tecnico = df.iloc[df["Eficiencia (%)"].idxmax(), 0]
        peor_tecnico = df.iloc[df["Eficiencia (%)"].idxmin(), 0]

        st.markdown(f"""
        ### 📊 Resumen General
        - 🧩 **Eficiencia promedio:** {eficiencia_prom}%
        - ⏱️ **Cumplimiento SLA promedio:** {sla_prom}%
        - 🥇 **Mejor técnico:** {mejor_tecnico}
        - 🧰 **Técnico con menor eficiencia:** {peor_tecnico}
        """)

        # ==========================
        # GRÁFICOS INTERACTIVOS 3D
        # ==========================
        st.subheader("📊 Comparativo de Casos por Técnico (3D Interactivo)")
        fig1 = px.bar_3d(
            df,
            x=df.columns[0],
            y="Cantidad de casos resueltos",
            z="Cantidad de casos abiertos",
            color="Cantidad de casos tardíos",
            title="Comparativo de Casos - Plataforma GIA",
            labels={df.columns[0]: "Técnico"},
            color_continuous_scale="Bluered"
        )
        fig1.update_traces(marker=dict(line=dict(width=0.5, color='DarkSlateGrey')))
        st.plotly_chart(fig1, use_container_width=True)

        st.subheader("💪 Eficiencia por Técnico (%) - Interactivo")
        fig2 = px.bar(
            df,
            x=df.columns[0],
            y="Eficiencia (%)",
            text_auto=".2f",
            color="Eficiencia (%)",
            color_continuous_scale="Viridis",
            title="Eficiencia Operativa - GIA"
        )
        fig2.update_traces(marker_line_width=1.2)
        st.plotly_chart(fig2, use_container_width=True)

        st.subheader("⏱️ Cumplimiento SLA por Técnico (%) - Interactivo")
        fig3 = px.bar(
            df,
            x=df.columns[0],
            y="Cumplimiento SLA (%)",
            text_auto=".2f",
            color="Cumplimiento SLA (%)",
            color_continuous_scale="Oranges",
            title="Cumplimiento de SLA - GIA"
        )
        fig3.update_traces(marker_line_width=1.2)
        st.plotly_chart(fig3, use_container_width=True)

        # ==========================
        # DESCARGA RESULTADOS
        # ==========================
        output = BytesIO()
        df.to_excel(output, index=False, engine='openpyxl')
        st.download_button(
            label="⬇️ Descargar reporte Excel con estadísticas GIA",
            data=output.getvalue(),
            file_name="reporte_estadistico_GIA.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        st.error(f"❌ Error al procesar el archivo: {e}")

else:
    st.info("📄 Sube un archivo Excel o CSV del sistema GIA para comenzar el análisis.")
