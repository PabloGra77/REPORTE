import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
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
Los gráficos usan **efecto 3D visual interactivo** con profundidad y sombras ✨
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
        # GRÁFICOS INTERACTIVOS 3D (efecto visual)
        # ==========================
        st.subheader("📊 Comparativo de Casos por Técnico (Efecto 3D)")

        fig1 = go.Figure()
        fig1.add_trace(go.Bar(
            x=df[df.columns[0]],
            y=df["Cantidad de casos abiertos"],
            name="Casos Abiertos",
            marker=dict(color="rgba(58,134,255,0.8)", line=dict(color="rgba(58,134,255,1.0)", width=2)),
        ))
        fig1.add_trace(go.Bar(
            x=df[df.columns[0]],
            y=df["Cantidad de casos resueltos"],
            name="Casos Resueltos",
            marker=dict(color="rgba(255,159,28,0.8)", line=dict(color="rgba(255,159,28,1.0)", width=2)),
        ))
        fig1.add_trace(go.Bar(
            x=df[df.columns[0]],
            y=df["Cantidad de casos tardíos"],
            name="Casos Tardíos",
            marker=dict(color="rgba(255,70,70,0.8)", line=dict(color="rgba(255,70,70,1.0)", width=2)),
        ))

        fig1.update_layout(
            barmode='group',
            title="Comparativo de Casos - Plataforma GIA (Efecto 3D)",
            xaxis_title="Técnico",
            yaxis_title="Cantidad de Casos",
            template="plotly_dark",
            scene_camera=dict(eye=dict(x=1.3, y=1.2, z=0.7)),
            bargap=0.2,
            plot_bgcolor="rgba(20,20,30,1)",
            paper_bgcolor="rgba(10,10,15,1)",
        )

        st.plotly_chart(fig1, use_container_width=True)

        # --- Eficiencia ---
        st.subheader("💪 Eficiencia por Técnico (%) - Interactivo")
        fig2 = px.bar(
            df,
            x=df.columns[0],
            y="Eficiencia (%)",
            text_auto=".2f",
            color="Eficiencia (%)",
            color_continuous_scale="Blues",
            title="Eficiencia Operativa - GIA"
        )
        fig2.update_traces(marker_line_width=1.3)
        fig2.update_layout(template="plotly_dark", bargap=0.3)
        st.plotly_chart(fig2, use_container_width=True)

        # --- Cumplimiento SLA ---
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
        fig3.update_traces(marker_line_width=1.3)
        fig3.update_layout(template="plotly_dark", bargap=0.3)
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
