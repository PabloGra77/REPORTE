import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
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

        # Definir columnas
        COL_TECNICO   = df.columns[0]
        COL_ASIGNADOS = "Casos asignados"
        COL_RESUELTOS = "Cantidad de casos resueltos"
        COL_TARDIOS   = "Cantidad de casos tardíos"

        if "Cantidad de casos abiertos" in df.columns:
            df[COL_ASIGNADOS] = df["Cantidad de casos abiertos"]

        # Limpiar técnicos vacíos
        df.iloc[:, 0] = df.iloc[:, 0].astype(str).str.strip()
        df = df[~df.iloc[:, 0].isin(["", "0", "nan", "None"])].reset_index(drop=True)

        # Convertir columnas numéricas
        for c in [COL_ASIGNADOS, COL_RESUELTOS, COL_TARDIOS]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

        # ==========================
        # CÁLCULOS DE MÉTRICAS
        # ==========================
        df["Eficiencia (%)"] = (df[COL_RESUELTOS] / (df[COL_ASIGNADOS] + 1e-9)) * 100
        df["Cumplimiento SLA (%)"] = ((df[COL_RESUELTOS] - df[COL_TARDIOS]) / (df[COL_RESUELTOS] + 1e-9)) * 100
        df["Eficacia Global (%)"] = ((df[COL_RESUELTOS] - df[COL_TARDIOS]) / (df[COL_ASIGNADOS] + 1e-9)) * 100

        # Limpiar técnicos inactivos
        df_validos = df[(df[COL_ASIGNADOS] > 0) | (df[COL_RESUELTOS] > 0)].copy()

        # Rendimiento Global ponderado
        max_asignados = df_validos[COL_ASIGNADOS].max()
        df_validos["Rendimiento Global"] = (
            ((df_validos["Eficiencia (%)"] + df_validos["Cumplimiento SLA (%)"]) / 2)
            * ((1 + (df_validos[COL_ASIGNADOS] / max_asignados)) / 2)
        )

        # ==========================
        # IDENTIFICAR TÉCNICOS DESTACADOS
        # ==========================
        if len(df_validos) > 0:
            mejor_tecnico = df_validos.iloc[df_validos["Rendimiento Global"].idxmax(), 0]
            tecnico_mas_solicitado = df_validos.iloc[df_validos[COL_ASIGNADOS].idxmax(), 0]
            peor_tecnico = df_validos.iloc[df_validos["Rendimiento Global"].idxmin(), 0]
        else:
            mejor_tecnico = tecnico_mas_solicitado = peor_tecnico = "—"

        eficiencia_prom = round(df_validos["Eficiencia (%)"].mean(), 2)
        sla_prom = round(df_validos["Cumplimiento SLA (%)"].mean(), 2)

        # ==========================
        # TABLA DE RESULTADOS
        # ==========================
        st.subheader("📋 Tabla de resultados")
        st.dataframe(df_validos, use_container_width=True)

        # ==========================
        # RESUMEN GENERAL
        # ==========================
        st.markdown(f"""
        ### 📊 Resumen General
        - 🧩 **Eficiencia promedio:** {eficiencia_prom}%
        - ⏱️ **Cumplimiento SLA promedio:** {sla_prom}%
        - 👥 **Técnico más solicitado:** {tecnico_mas_solicitado}
        - 🥇 **Mejor técnico (Rendimiento Global):** {mejor_tecnico}
        - 🧰 **Técnico con menor rendimiento:** {peor_tecnico}
        """)

        # ==========================
        # COMPARATIVA ENTRE TÉCNICOS CLAVE
        # ==========================
        if tecnico_mas_solicitado != "—" and mejor_tecnico != "—":
            comp_df = df_validos[df_validos[COL_TECNICO].isin([tecnico_mas_solicitado, mejor_tecnico])]
            st.subheader("⚖️ Comparativa entre el técnico más solicitado y el de mejor rendimiento")
            st.dataframe(comp_df[[COL_TECNICO, COL_ASIGNADOS, COL_RESUELTOS, "Eficiencia (%)", "Cumplimiento SLA (%)", "Eficacia Global (%)", "Rendimiento Global"]])

        # ==========================
        # GRÁFICO 1 - Casos
        # ==========================
        st.subheader("📊 Comparativo de Casos por Técnico")
        fig1 = go.Figure()
        fig1.add_trace(go.Bar(
            x=df_validos[COL_TECNICO], y=df_validos[COL_ASIGNADOS],
            name="Casos Asignados", marker=dict(color="rgba(58,134,255,0.8)")
        ))
        fig1.add_trace(go.Bar(
            x=df_validos[COL_TECNICO], y=df_validos[COL_RESUELTOS],
            name="Casos Resueltos", marker=dict(color="rgba(255,159,28,0.8)")
        ))
        fig1.add_trace(go.Bar(
            x=df_validos[COL_TECNICO], y=df_validos[COL_TARDIOS],
            name="Casos Tardíos", marker=dict(color="rgba(255,70,70,0.8)")
        ))
        fig1.update_layout(
            barmode='group',
            title="Comparativo de Casos Asignados / Resueltos / Tardíos",
            template="plotly_dark",
            xaxis_title="Técnico",
            yaxis_title="Cantidad de Casos"
        )
        st.plotly_chart(fig1, use_container_width=True)

        # ==========================
        # GRÁFICO 2 - Rendimiento Global
        # ==========================
        st.subheader("🏆 Rendimiento Global por Técnico (ponderado)")
        fig2 = px.bar(
            df_validos.sort_values("Rendimiento Global", ascending=False),
            x=COL_TECNICO, y="Rendimiento Global",
            text_auto=".2f", color="Rendimiento Global",
            color_continuous_scale="Viridis"
        )
        fig2.update_layout(template="plotly_dark", bargap=0.3)
        st.plotly_chart(fig2, use_container_width=True)

        # ==========================
        # GRÁFICO 3 - Eficacia Global (nuevo)
        # ==========================
        st.subheader("💥 Eficacia Global por Técnico (Casos resueltos y a tiempo)")
        fig3 = px.scatter(
            df_validos,
            x=COL_ASIGNADOS,
            y="Eficacia Global (%)",
            size=COL_RESUELTOS,
            color="Eficacia Global (%)",
            text=COL_TECNICO,  # 🔹 muestra el nombre
            hover_name=COL_TECNICO,
            color_continuous_scale="Bluered",
            title="Eficacia del Técnico según el volumen de casos asignados",
        )
        fig3.update_traces(
            textposition="top center",
            marker=dict(line=dict(width=1, color="DarkSlateGrey"), opacity=0.8)
        )

        # Línea de promedio de eficacia
        prom_eficacia = df_validos["Eficacia Global (%)"].mean()
        fig3.add_hline(
            y=prom_eficacia,
            line_dash="dot",
            line_color="white",
            annotation_text=f"Promedio global: {prom_eficacia:.2f}%",
            annotation_position="bottom right",
            annotation_font_size=12
        )

        fig3.update_layout(
            template="plotly_dark",
            xaxis_title="Casos Asignados (Volumen de trabajo)",
            yaxis_title="Eficacia Global (%)",
            font=dict(size=12),
            height=600
        )
        st.plotly_chart(fig3, use_container_width=True)

        # ==========================
        # DESCARGA RESULTADOS
        # ==========================
        output = BytesIO()
        df_validos.to_excel(output, index=False, engine='openpyxl')
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
