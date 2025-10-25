import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st
from io import BytesIO

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
        # Detectar formato
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file, sep=None, engine="python")
        else:
            df = pd.read_excel(uploaded_file)

        df = df.fillna(0)

        # Convertir columnas numéricas
        for col in df.columns[1:]:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        # Cálculos de métricas
        df["Eficiencia (%)"] = (df["Cantidad de casos resueltos"] /
                               (df["Cantidad de casos abiertos"] + df["Cantidad de casos resueltos"] + 1e-9)) * 100

        df["Cumplimiento SLA (%)"] = ((df["Cantidad de casos resueltos"] - df["Cantidad de casos tardíos"]) /
                                     (df["Cantidad de casos resueltos"] + 1e-9)) * 100

        # Mostrar tabla
        st.subheader("📋 Tabla de resultados")
        st.dataframe(df, use_container_width=True)

        # ==========================
        # GRÁFICOS
        # ==========================
        # Gráfico 1 - Comparativo de casos
        st.subheader("📊 Comparativo de Casos por Técnico")
        fig1, ax1 = plt.subplots(figsize=(10, 5))
        df.plot(x=df.columns[0],
                y=["Cantidad de casos abiertos", "Cantidad de casos resueltos", "Cantidad de casos tardíos"],
                kind="bar", ax=ax1)
        plt.title("Comparativo de Casos - Plataforma GIA")
        plt.ylabel("Cantidad de Casos")
        plt.grid(True, linestyle="--", alpha=0.5)
        st.pyplot(fig1)

        # Gráfico 2 - Eficiencia
        st.subheader("💪 Eficiencia por Técnico (%)")
        fig2, ax2 = plt.subplots(figsize=(8, 5))
        ax2.bar(df[df.columns[0]], df["Eficiencia (%)"], color="#3A86FF")
        plt.title("Eficiencia Operativa - GIA")
        plt.ylabel("Eficiencia (%)")
        plt.grid(axis="y", linestyle="--", alpha=0.5)
        st.pyplot(fig2)

        # Gráfico 3 - Cumplimiento SLA
        st.subheader("⏱️ Cumplimiento SLA por Técnico (%)")
        fig3, ax3 = plt.subplots(figsize=(8, 5))
        ax3.bar(df[df.columns[0]], df["Cumplimiento SLA (%)"], color="#FF9F1C")
        plt.title("Cumplimiento de SLA - GIA")
        plt.ylabel("Cumplimiento SLA (%)")
        plt.grid(axis="y", linestyle="--", alpha=0.5)
        st.pyplot(fig3)

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
