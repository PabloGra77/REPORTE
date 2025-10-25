import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st

st.set_page_config(page_title="📊 Reporte GIA", layout="wide")

st.title("🤖 Panel de Estadísticas GIA")
st.markdown("""
Sube tu archivo **Excel (.xlsx)** exportado del sistema **GIA** para generar automáticamente los reportes y estadísticas de rendimiento técnico.  
Incluye cálculos de eficiencia, cumplimiento de SLA y comparativos visuales por técnico.
""")

uploaded_file = st.file_uploader("📁 Cargar archivo Excel (.xlsx)", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    df = df.fillna(0)

    # Cálculos de métricas
    df["Eficiencia (%)"] = (df["Cantidad de casos resueltos"] /
                           (df["Cantidad de casos abiertos"] + df["Cantidad de casos resueltos"] + 1e-9)) * 100
    df["Cumplimiento SLA (%)"] = ((df["Cantidad de casos resueltos"] - df["Cantidad de casos tardíos"]) /
                                 (df["Cantidad de casos resueltos"] + 1e-9)) * 100

    # Mostrar tabla
    st.subheader("📋 Tabla de resultados")
    st.dataframe(df)

    # Gráfico 1: Casos
    st.subheader("📊 Comparativo de Casos por Técnico")
    fig, ax = plt.subplots(figsize=(10, 5))
    df.plot(x=df.columns[0],
            y=["Cantidad de casos abiertos", "Cantidad de casos resueltos", "Cantidad de casos tardíos"],
            kind="bar", ax=ax)
    plt.ylabel("Cantidad de Casos")
    plt.title("Comparativo de Casos - Plataforma GIA")
    plt.grid(True, linestyle="--", alpha=0.4)
    st.pyplot(fig)

    # Gráfico 2: Eficiencia
    st.subheader("💪 Eficiencia por Técnico (%)")
    fig2, ax2 = plt.subplots(figsize=(8, 5))
    ax2.bar(df[df.columns[0]], df["Eficiencia (%)"], color="#3A86FF")
    plt.ylabel("Eficiencia (%)")
    plt.title("Eficiencia Operativa - Plataforma GIA")
    plt.grid(axis="y", linestyle="--", alpha=0.4)
    st.pyplot(fig2)

    # Gráfico 3: Cumplimiento SLA
    st.subheader("⏱️ Cumplimiento SLA por Técnico (%)")
    fig3, ax3 = plt.subplots(figsize=(8, 5))
    ax3.bar(df[df.columns[0]], df["Cumplimiento SLA (%)"], color="#FF9F1C")
    plt.ylabel("Cumplimiento SLA (%)")
    plt.title("Cumplimiento de SLA - Plataforma GIA")
    plt.grid(axis="y", linestyle="--", alpha=0.4)
    st.pyplot(fig3)

    # Botón de descarga
    st.download_button(
        label="⬇️ Descargar reporte Excel con estadísticas GIA",
        data=df.to_excel(index=False, engine="openpyxl"),
        file_name="reporte_estadistico_GIA.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

else:
    st.info("📄 Sube un archivo Excel de GIA para comenzar el análisis.")

