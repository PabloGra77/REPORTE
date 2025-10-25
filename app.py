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
# CONFIGURACIÓN GLOBAL
# ==========================
st.set_page_config(page_title="Panel GIA", page_icon="🤖", layout="wide")

# ============
# ESTILO CSS GIA
# ============
st.markdown("""
<style>
body {
    background-color:#0E1117;
    color:white;
}
.banner {
    background: linear-gradient(90deg, #3A86FF, #FF9F1C);
    padding: 18px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: flex-start;
    box-shadow: 0 0 20px rgba(255,159,28,0.3);
    margin-bottom: 25px;
}
.banner img {
    height: 70px;
    margin-right: 15px;
}
.banner-text {
    font-size: 32px;
    font-weight: bold;
    color: white;
}
.banner-sub {
    font-size: 16px;
    color: #F8F9FA;
}
.metric-card {
    background-color:#1E1E1E;
    padding:15px;
    border-radius:15px;
    text-align:center;
    border:1px solid #3A86FF33;
    box-shadow:0 0 8px rgba(58,134,255,0.3);
}
.metric-value {
    font-size:26px;
    font-weight:bold;
    color:#FFFFFF;
}
.metric-label {
    color:#FF9F1C;
    font-size:14px;
}
hr {border:0;height:1px;background:#333;margin:25px 0;}
</style>
""", unsafe_allow_html=True)

# ============
# ENCABEZADO GIA
# ============
st.markdown("""
<div class="banner">
    <img src="https://raw.githubusercontent.com/PabloGra77/INFORME/main/logo_gia.png" alt="Logo GIA">
    <div>
        <div class="banner-text">🤖 GIA - Panel de Estadísticas</div>
        <div class="banner-sub">IPS Goleman | Inteligencia para el Soporte</div>
    </div>
</div>
""", unsafe_allow_html=True)

# ==========================
# CARGA DEL ARCHIVO
# ==========================
uploaded_file = st.file_uploader("📁 Cargar archivo Excel o CSV", type=["xlsx", "csv"])

if uploaded_file:
    try:
        # Cargar datos
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file, sep=None, engine="python")
        else:
            df = pd.read_excel(uploaded_file)
        df = df.fillna(0)

        # Identificar columnas base
        COL_TECNICO = df.columns[0]
        if "Cantidad de casos abiertos" in df.columns:
            df["Casos asignados"] = df["Cantidad de casos abiertos"]

        df.iloc[:, 0] = df.iloc[:, 0].astype(str).str.strip()
        df = df[~df.iloc[:, 0].isin(["", "0", "nan", "None"])].reset_index(drop=True)

        for c in ["Casos asignados", "Cantidad de casos resueltos", "Cantidad de casos tardíos"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

        # ==========================
        # FILTRO DE TÉCNICOS
        # ==========================
        st.markdown("### 🧹 Filtrar Técnicos")
        tecnicos = sorted(df[COL_TECNICO].unique())
        excluir = st.multiselect("Selecciona técnicos para excluir:", tecnicos)
        if excluir:
            df = df[~df[COL_TECNICO].isin(excluir)]

        # ==========================
        # CÁLCULOS
        # ==========================
        df["Eficiencia (%)"] = (df["Cantidad de casos resueltos"] / (df["Casos asignados"] + 1e-9)) * 100
        df["Cumplimiento SLA (%)"] = ((df["Cantidad de casos resueltos"] - df["Cantidad de casos tardíos"]) /
                                      (df["Cantidad de casos resueltos"] + 1e-9)) * 100
        df["Eficacia Global (%)"] = ((df["Cantidad de casos resueltos"] - df["Cantidad de casos tardíos"]) /
                                     (df["Casos asignados"] + 1e-9)) * 100
        df_validos = df.copy()
        max_asignados = df_validos["Casos asignados"].max() if len(df_validos) else 1
        df_validos["Rendimiento Global"] = (
            ((df_validos["Eficiencia (%)"] + df_validos["Cumplimiento SLA (%)"]) / 2)
            * ((1 + (df_validos["Casos asignados"] / max_asignados)) / 2)
        )

        # ==========================
        # TÉCNICOS DESTACADOS
        # ==========================
        mejor = df_validos.loc[df_validos["Rendimiento Global"].idxmax(), COL_TECNICO]
        mas_solicitado = df_validos.loc[df_validos["Casos asignados"].idxmax(), COL_TECNICO]
        mas_eficaz = df_validos.loc[df_validos["Eficacia Global (%)"].idxmax(), COL_TECNICO]
        peor = df_validos.loc[df_validos["Rendimiento Global"].idxmin(), COL_TECNICO]

        # ==========================
        # TARJETAS DE RESUMEN
        # ==========================
        eficiencia_prom = round(df_validos["Eficiencia (%)"].mean(), 2)
        sla_prom = round(df_validos["Cumplimiento SLA (%)"].mean(), 2)

        st.markdown("## 📊 Resumen General")
        col1, col2, col3, col4 = st.columns(4)
        col1.markdown(f"""
        <div class='metric-card'>
            <div class='metric-value'>{eficiencia_prom}%</div>
            <div class='metric-label'>Eficiencia Promedio</div>
        </div>""", unsafe_allow_html=True)
        col2.markdown(f"""
        <div class='metric-card'>
            <div class='metric-value'>{sla_prom}%</div>
            <div class='metric-label'>Cumplimiento SLA</div>
        </div>""", unsafe_allow_html=True)
        col3.markdown(f"""
        <div class='metric-card'>
            <div class='metric-value'>{mas_solicitado}</div>
            <div class='metric-label'>Técnico más solicitado</div>
        </div>""", unsafe_allow_html=True)
        col4.markdown(f"""
        <div class='metric-card'>
            <div class='metric-value'>{mejor}</div>
            <div class='metric-label'>Mejor Técnico</div>
        </div>""", unsafe_allow_html=True)

        st.markdown("<hr>", unsafe_allow_html=True)

        # ==========================
        # GRÁFICOS
        # ==========================
        fig1 = go.Figure()
        fig1.add_trace(go.Bar(x=df_validos[COL_TECNICO], y=df_validos["Casos asignados"], name="Asignados"))
        fig1.add_trace(go.Bar(x=df_validos[COL_TECNICO], y=df_validos["Cantidad de casos resueltos"], name="Resueltos"))
        fig1.add_trace(go.Bar(x=df_validos[COL_TECNICO], y=df_validos["Cantidad de casos tardíos"], name="Tardíos"))
        fig1.update_layout(template="plotly_dark", title="📦 Casos por Técnico", barmode="group")
        st.plotly_chart(fig1, use_container_width=True)

        fig2 = px.bar(df_validos, x=COL_TECNICO, y="Rendimiento Global", color="Rendimiento Global",
                      text_auto=".2f", color_continuous_scale="Viridis", title="⚙️ Rendimiento Global por Técnico")
        fig2.update_layout(template="plotly_dark")
        st.plotly_chart(fig2, use_container_width=True)

        fig3 = px.scatter(df_validos, x="Casos asignados", y="Eficacia Global (%)", size="Cantidad de casos resueltos",
                          color="Eficacia Global (%)", text=COL_TECNICO, color_continuous_scale="Bluered",
                          title="🎯 Eficacia Global (Casos asignados vs Eficacia)")
        fig3.update_traces(textposition="top center")
        st.plotly_chart(fig3, use_container_width=True)

        # ==========================
        # SALUD DEL GRUPO
        # ==========================
        tot_asignados = df_validos["Casos asignados"].sum()
        tot_resueltos = df_validos["Cantidad de casos resueltos"].sum()
        tot_tardios = df_validos["Cantidad de casos tardíos"].sum()

        eff_grupo = (tot_resueltos / (tot_asignados + 1e-9)) * 100
        sla_grupo = ((tot_resueltos - tot_tardios) / (tot_resueltos + 1e-9)) * 100
        efc_grupo = ((tot_resueltos - tot_tardios) / (tot_asignados + 1e-9)) * 100
        indice_salud = (eff_grupo + sla_grupo + efc_grupo) / 3

        st.markdown("## 👥 Salud del Grupo")
        fig4 = go.Figure(go.Indicator(
            mode="gauge+number",
            value=indice_salud,
            title={'text': "Salud del Grupo (%)", 'font': {'size': 22, 'color': "#FFFFFF"}},
            gauge={
                'axis': {'range': [0, 100], 'tickcolor': "#FFFFFF"},
                'bar': {'color': "#3A86FF"},
                'steps': [
                    {'range': [0, 50], 'color': "#ef476f"},
                    {'range': [50, 75], 'color': "#ffd166"},
                    {'range': [75, 100], 'color': "#06d6a0"}
                ],
                'threshold': {'line': {'color': "white", 'width': 3}, 'value': indice_salud}
            }
        ))
        fig4.update_layout(template="plotly_dark", height=350)
        st.plotly_chart(fig4, use_container_width=True)

        # ==========================
        # PDF CON GRÁFICOS
        # ==========================
        def generar_pdf():
            buffer = BytesIO()
            fecha = datetime.now().strftime("%Y-%m-%d")
            nombre_pdf = f"reporte_GIA_{fecha}.pdf"
            temp_imgs = []
            for fig in [fig1, fig2, fig3, fig4]:
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
                fig.write_image(tmp.name, format="png", width=800, height=500, scale=2)
                temp_imgs.append(tmp.name)

            doc = SimpleDocTemplate(buffer, pagesize=A4)
            styles = getSampleStyleSheet()
            story = [Paragraph("📘 Reporte GIA", styles["Title"]),
                     Paragraph(f"Fecha: {fecha}", styles["Normal"]),
                     Spacer(1, 12)]
            for path in temp_imgs:
                story.append(Image(path, width=6.2*inch, height=3.8*inch))
                story.append(Spacer(1, 8))
            doc.build(story)
            pdf = buffer.getvalue()
            buffer.close()
            return nombre_pdf, pdf

        nombre_pdf, pdf = generar_pdf()
        st.download_button("📄 Descargar Reporte GIA (PDF)", pdf, nombre_pdf, "application/pdf")

    except Exception as e:
        st.error(f"❌ Error: {e}")
else:
    st.info("📄 Sube tu archivo Excel o CSV del sistema GIA para comenzar.")
