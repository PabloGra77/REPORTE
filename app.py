if uploaded_file:
    try:
        # Detectar tipo de archivo
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file, sep=None, engine="python")
        else:
            df = pd.read_excel(uploaded_file)

        df = df.fillna(0)

        # === LIMPIEZA DE DATOS ===
        # Asegurar que la primera columna (técnico) sea texto
        df.iloc[:, 0] = df.iloc[:, 0].astype(str).str.strip()

        # Convertir el resto a numérico
        for col in df.columns[1:]:
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

        # Mostrar tabla
        st.subheader("📋 Tabla de resultados")
        st.dataframe(df, use_container_width=True)

        # === GRÁFICOS ===
        st.subheader("📊 Comparativo de Casos por Técnico")
        fig1, ax1 = plt.subplots(figsize=(10, 5))
        df.plot(
            x=df.columns[0],
            y=["Cantidad de casos abiertos", "Cantidad de casos resueltos", "Cantidad de casos tardíos"],
            kind="bar", ax=ax1
        )
        plt.title("Comparativo de Casos - Plataforma GIA")
        plt.ylabel("Cantidad de Casos")
        plt.grid(True, linestyle="--", alpha=0.5)
        st.pyplot(fig1)

        # === GRÁFICO DE EFICIENCIA ===
        st.subheader("💪 Eficiencia por Técnico (%)")
        fig2, ax2 = plt.subplots(figsize=(8, 5))
        tecnicos = df.iloc[:, 0].astype(str)
        eficiencias = df["Eficiencia (%)"].astype(float)
        ax2.bar(tecnicos, eficiencias, color="#3A86FF")
        plt.title("Eficiencia Operativa - GIA")
        plt.ylabel("Eficiencia (%)")
        plt.xticks(rotation=45, ha="right")
        plt.grid(axis="y", linestyle="--", alpha=0.5)
        st.pyplot(fig2)

        # === GRÁFICO DE SLA ===
        st.subheader("⏱️ Cumplimiento SLA por Técnico (%)")
        fig3, ax3 = plt.subplots(figsize=(8, 5))
        sla = df["Cumplimiento SLA (%)"].astype(float)
        ax3.bar(tecnicos, sla, color="#FF9F1C")
        plt.title("Cumplimiento de SLA - GIA")
        plt.ylabel("Cumplimiento SLA (%)")
        plt.xticks(rotation=45, ha="right")
        plt.grid(axis="y", linestyle="--", alpha=0.5)
        st.pyplot(fig3)

        # === DESCARGA ===
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
