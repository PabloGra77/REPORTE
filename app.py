import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
from datetime import datetime
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
)
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
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
body {background-color:#0E1117; color:white;}
.banner {
    background: linear-gradient(90deg, #3A86FF, #FF9F1C);
    padding: 18px; border-radius: 12px;
    display: flex; align-items: center; justify-content: flex-start;
    box-shadow: 0 0 20px rgba(255,159,28,0.3); margin-bottom: 25px;
}
.banner-text { font-size: 32px; font-weight: bold; color: white; }
.banner-sub { font-size: 16px; color: #F8F9FA; }
.metric-card {
    background-color:#1E1E1E; padding:16px; border-radius:14px; text-align:center;
    border:1px solid #3A86FF33; box-shadow:0 0 8px rgba(58,134,255,0.25);
}
.metric-value { font-size:22px; font-weight:800; color:#FFFFFF; }
.metric-label { color:#FF9F1C; font-size:13px; }
.badge { display:inline-block; padding:2px 8px; border-radius:999px; background:#23262F; border:1px solid #3A86FF55; font-size:12px; }
hr {border:0;height:1px;background:#333;margin:20px 0;}
.small { font-size:13px; color:#DADADA; }
</style>
""", unsafe_allow_html=True)

# ============
# ENCABEZADO
# ============
st.markdown("""
<div class="banner">
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
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file, sep=None, engine="python")
        else:
            df = pd.read_excel(uploaded_file)
        df = df.fillna(0)

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
        # CÁLCULOS POR TÉCNICO
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
        # TOTALES & MÉTRICAS DE GRUPO
        # ==========================
        tot_asignados = df_validos["Casos asignados"].sum()
        tot_resueltos = df_validos["Cantidad de casos resueltos"].sum()
        tot_tardios  = df_validos["Cantidad de casos tardíos"].sum()
        pendientes   = max(tot_asignados - tot_resueltos, 0)
        n_tecnicos   = df_validos[COL_TECNICO].nunique()

        eficiencia_prom = round(df_validos["Eficiencia (%)"].mean(), 2)
        sla_prom        = round(df_validos["Cumplimiento SLA (%)"].mean(), 2)
        eficacia_prom   = round(df_validos["Eficacia Global (%)"].mean(), 2)

        eff_grupo = (tot_resueltos / (tot_asignados + 1e-9)) * 100
        sla_grupo = ((tot_resueltos - tot_tardios) / (tot_resueltos + 1e-9)) * 100
        efc_grupo = ((tot_resueltos - tot_tardios) / (tot_asignados + 1e-9)) * 100
        indice_salud = round((eff_grupo + sla_grupo + efc_grupo) / 3, 2)

        # ==========================
        # DESTACADOS
        # ==========================
        mejor          = df_validos.loc[df_validos["Rendimiento Global"].idxmax(), COL_TECNICO] if len(df_validos) else "—"
        mas_solicitado = df_validos.loc[df_validos["Casos asignados"].idxmax(), COL_TECNICO]    if len(df_validos) else "—"
        mas_eficaz     = df_validos.loc[df_validos["Eficacia Global (%)"].idxmax(), COL_TECNICO] if len(df_validos) else "—"
        mas_eficaz_val = round(df_validos["Eficacia Global (%)"].max(), 2) if len(df_validos) else 0.0
        peor           = df_validos.loc[df_validos["Rendimiento Global"].idxmin(), COL_TECNICO] if len(df_validos) else "—"

        # ==========================
        # RESUMEN GENERAL (AMPLIADO)
        # ==========================
        st.markdown("## <span class='badge'>📊 Resumen General</span>", unsafe_allow_html=True)

        c1,c2,c3,c4 = st.columns(4)
        c1.markdown(f"<div class='metric-card'><div class='metric-value'>{eficiencia_prom:.2f}%</div><div class='metric-label'>Eficiencia Promedio</div></div>", unsafe_allow_html=True)
        c2.markdown(f"<div class='metric-card'><div class='metric-value'>{sla_prom:.2f}%</div><div class='metric-label'>Cumplimiento SLA Promedio</div></div>", unsafe_allow_html=True)
        c3.markdown(f"<div class='metric-card'><div class='metric-value'>{eficacia_prom:.2f}%</div><div class='metric-label'>Eficacia Promedio</div></div>", unsafe_allow_html=True)
        c4.markdown(f"<div class='metric-card'><div class='metric-value'>{indice_salud:.2f}%</div><div class='metric-label'>Salud del Grupo</div></div>", unsafe_allow_html=True)

        c5,c6,c7,c8 = st.columns(4)
        c5.markdown(f"<div class='metric-card'><div class='metric-value'>{mas_solicitado}</div><div class='metric-label'>Técnico más solicitado</div></div>", unsafe_allow_html=True)
        c6.markdown(f"<div class='metric-card'><div class='metric-value'>{mejor}</div><div class='metric-label'>Mejor Técnico (Rend. Global)</div></div>", unsafe_allow_html=True)
        c7.markdown(f"<div class='metric-card'><div class='metric-value'>{mas_eficaz}</div><div class='metric-label'>Técnico más eficaz ({mas_eficaz_val:.2f}%)</div></div>", unsafe_allow_html=True)
        c8.markdown(f"<div class='metric-card'><div class='metric-value'>{peor}</div><div class='metric-label'>Técnico con menor rendimiento</div></div>", unsafe_allow_html=True)

        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown(f"**📦 Totales** — Asignados: **{int(tot_asignados)}**, Resueltos: **{int(tot_resueltos)}**, Tardíos: **{int(tot_tardios)}**, Pendientes: **{int(pendientes)}** · Técnicos: **{n_tecnicos}**")
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

        fig2 = px.bar(
            df_validos, x=COL_TECNICO, y="Rendimiento Global",
            color="Rendimiento Global", text_auto=".2f",
            color_continuous_scale="Viridis", title="⚙️ Rendimiento Global por Técnico"
        )
        fig2.update_layout(template="plotly_dark")
        st.plotly_chart(fig2, use_container_width=True)

        fig3 = px.scatter(
            df_validos, x="Casos asignados", y="Eficacia Global (%)",
            size="Cantidad de casos resueltos", color="Eficacia Global (%)",
            text=COL_TECNICO, color_continuous_scale="Bluered",
            title="🎯 Eficacia Global (Casos asignados vs Eficacia)"
        )
        fig3.update_traces(textposition="top center")
        st.plotly_chart(fig3, use_container_width=True)

        # ==========================
        # SALUD DEL GRUPO (Gauge)
        # ==========================
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
        # PDF PROFESIONAL
        # ==========================
        def generar_pdf():
            buffer = BytesIO()
            fecha = datetime.now().strftime("%Y-%m-%d")
            nombre_pdf = f"reporte_GIA_{fecha}.pdf"

            temp_imgs = []
            for fig in [fig1, fig2, fig3, fig4]:
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
                fig.write_image(tmp.name, format="png", width=850, height=500, scale=2)
                temp_imgs.append(tmp.name)

            styles = getSampleStyleSheet()
            style_title = ParagraphStyle(
                'TitleCenter', parent=styles['Title'], alignment=TA_CENTER,
                textColor=colors.HexColor("#3A86FF"), fontSize=20
            )
            style_subtitle = ParagraphStyle(
                'Subtitle', parent=styles['Normal'], alignment=TA_CENTER,
                textColor=colors.HexColor("#FF9F1C"), fontSize=12
            )
            style_section = ParagraphStyle(
                'Section', parent=styles['Heading2'], textColor=colors.HexColor("#3A86FF")
            )
            style_text = ParagraphStyle(
                'BodyText', parent=styles['Normal'], alignment=TA_LEFT, fontSize=11, leading=15
            )

            doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=40, bottomMargin=30)
            story = []

            story.append(Paragraph("📘 Reporte GIA", style_title))
            story.append(Paragraph(f"Fecha del informe: {fecha}", style_subtitle))
            story.append(Spacer(1, 12))

            data_metrics = [
                ["Eficiencia Promedio", f"{eficiencia_prom:.2f} %"],
                ["Cumplimiento SLA Promedio", f"{sla_prom:.2f} %"],
                ["Eficacia Promedio", f"{eficacia_prom:.2f} %"],
                ["Salud del Grupo", f"{indice_salud:.2f} %"],
            ]
            t = Table(data_metrics, colWidths=[3.2*inch, 1.3*inch])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#3A86FF")),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor("#AAAAAA")),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.lightgrey])
            ]))
            story.append(t)
            story.append(Spacer(1, 15))

            story.append(Paragraph("👷 Técnicos Destacados", style_section))
            story.append(Spacer(1, 8))
            story.append(Paragraph(f"• <b>Técnico más solicitado:</b> {mas_solicitado}", style_text))
            story.append(Paragraph(f"• <b>Mejor técnico (Rendimiento Global):</b> {mejor}", style_text))
            story.append(Paragraph(f"• <b>Técnico más eficaz:</b> {mas_eficaz} ({mas_eficaz_val:.2f} %)", style_text))
            story.append(Paragraph(f"• <b>Técnico con menor rendimiento:</b> {peor}", style_text))
            story.append(Spacer(1, 10))

            story.append(Paragraph("📦 Totales del periodo", style_section))
            story.append(Spacer(1, 6))
            story.append(Paragraph(
                f"Asignados: <b>{int(tot_asignados)}</b> · "
                f"Resueltos: <b>{int(tot_resueltos)}</b> · "
                f"Tardíos: <b>{int(tot_tardios)}</b> · "
                f"Pendientes: <b>{int(pendientes)}</b> · "
                f"Técnicos: <b>{n_tecnicos}</b>", style_text
            ))
            story.append(Spacer(1, 18))

            titulos_graficos = [
                "📊 Casos por Técnico",
                "⚙️ Rendimiento Global por Técnico",
                "🎯 Eficacia Global",
                "👥 Salud del Grupo"
            ]

            for i, path in enumerate(temp_imgs):
                story.append(Paragraph(titulos_graficos[i], style_section))
                story.append(Spacer(1, 6))
                story.append(Image(path, width=6.3*inch, height=3.5*inch))
                story.append(Spacer(1, 12))

            doc.build(story)
            pdf = buffer.getvalue()
            buffer.close()
            return nombre_pdf, pdf

        nombre_pdf, pdf = generar_pdf()
        st.download_button("📄 Descargar Reporte GIA (PDF)", pdf, nombre_pdf, "application/pdf")

    except Exception as e:
