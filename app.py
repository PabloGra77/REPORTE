import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st

st.set_page_config(page_title="📊 Reporte GLPI", layout="wide")

st.title("📈 Panel de Estadísticas GLPI")
st.markdown("Sube tu archivo Excel con las columnas de GLPI para generar el informe automáticamente.")

uploaded_file = st.file_uploader("📁 Cargar archivo Excel (.xlsx)", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    df = df.fillna(0)

    # Calcular métricas
    df["Eficiencia (%)"] = (df["Cantidad de casos resueltos"] /
                           (df["Cantidad de casos abiertos"] + df["Cantidad de casos resueltos"] + 1e-9)) * 100
    df["Cumplimiento SLA (%)"] = ((df["Cantidad de casos resueltos"] - df["Cantidad de casos tardíos"]) /
                                 (df["Cantidad de casos resueltos"] + 1e-9)) * 100

    st.subheader("📋 Tabla de resultados")
    st.dataframe(df)

    # Gráfico 1
    st.subheader("📊 Comparativo de Casos por Técnico")
    fig, ax = plt.subplots(figsize=(10, 5))
    df.plot(x=df.columns[0], y=["Cantidad de casos abiertos", "Cantidad de casos resueltos", "Cantidad de casos tardíos"],
            kind="bar", ax=ax)
    plt.ylabel("Cantidad de Casos")
    plt.grid(True, linestyle="--", alpha=0.4)
    st.pyplot(fig)

    # Gráfico 2
    st.subheader("💪 Eficiencia por Técnico (%)")
    fig2, ax2 = plt.subplots(figsize=(8, 5))
    ax2.bar(df[df.columns[0]], df["Eficiencia (%)"], color="royalblue")
    plt.ylabel("Eficiencia (%)")
    plt.grid(axis="y", linestyle="--", alpha=0.4)
    st.pyplot(fig2)

    # Gráfico 3
    st.subheader("⏱️ Cumplimiento SLA por Técnico (%)")
    fig3, ax3 = plt.subplots(figsize=(8, 5))
    ax3.bar(df[df.columns[0]], df["Cumplimiento SLA (%)"], color="orange")
    plt.ylabel("Cumplimiento SLA (%)")
    plt.grid(axis="y", linestyle="--", alpha=0.4)
    st.pyplot(fig3)

    # Descargar resultados
    st.download_button(
        label="⬇️ Descargar reporte Excel con estadísticas",
        data=df.to_excel(index=False, engine="openpyxl"),
        file_name="reporte_estadistico_resultado.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
else:
    st.info("Sube un archivo Excel para comenzar 📄")
