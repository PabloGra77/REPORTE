import pandas as pd
import streamlit as st
import plotly.express as px
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from io import BytesIO
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.enums import TA_CENTER
import unicodedata

# =====================================================
# CONFIGURACIÓN GENERAL
# =====================================================
st.set_page_config(page_title="GIA - SLA Inteligente", page_icon="🤖", layout="wide")

# Detectar modo TV
query_params = st.query_params
is_tv = "tv" in query_params and query_params["tv"] in ("1", "true", "True")

# =====================================================
# ESTILO GLOBAL (MODO OSCURO FIJO)
# =====================================================
st.markdown("""
<style>
body {background:#0E1117 !important; color:white !important;}
[data-testid="stHeader"], [data-testid="stToolbar"], footer {visibility: hidden !important;}
.metric-card {
  background:#1E1E1E; border:1px solid #3A86FF33;
  border-radius:12px; padding:14px; text-align:center;
  box-shadow:0 0 6px rgba(58,134,255,0.25);
}
.metric-value { font-size:22px; font-weight:800; color:white; }
.metric-label { color:#FF9F1C; font-size:12px; }
hr {border:0; height:1px; background:#333; margin:18px 0;}
</style>
""", unsafe_allow_html=True)

# =====================================================
# HORARIO Y PARÁMETROS
# =====================================================
WORK_SCHEDULE = {
    0:[(time(7,0), time(17,0))],
    1:[(time(7,0), time(17,0))],
    2:[(time(7,0), time(17,0))],
    3:[(time(7,0), time(17,0))],
    4:[(time(7,0), time(16,0))],
    5:[(time(8,0), time(13,0))],
    6:[]
}
PRIORITY_SLA_HOURS = {"muy alta":4,"alta":8,"media":16,"baja":32}

def norm(s): return "".join(ch for ch in unicodedata.normalize("NFD", str(s)) if unicodedata.category(ch)!="Mn").lower().strip()
def to_ts(s): return pd.to_datetime(s, errors="coerce", dayfirst=True, utc=False)
def horas_habiles(start,end):
    if pd.isna(start) or pd.isna(end) or end<=start: return 0
    total=0; cur=start
    for _ in range(370):
        day=cur.date()
        for h_ini,h_fin in WORK_SCHEDULE[cur.weekday()]:
            seg_ini=datetime.combine(day,h_ini)
            seg_fin=datetime.combine(day,h_fin)
            t_ini=max(cur,seg_ini); t_fin=min(end,seg_fin)
            if t_fin>t_ini: total+=(t_fin-t_ini).total_seconds()
        nxt=datetime.combine(day,time(23,59,59))+timedelta(seconds=1)
        if nxt>=end: break
        cur=nxt
    return total/3600
def sla_limit(p):
    for k,v in PRIORITY_SLA_HOURS.items():
        if k in norm(p): return v
    return 8

# =====================================================
# PANELES
# =====================================================

if not is_tv:
    # -------------------------------------------------
    # PANEL PRINCIPAL - ANÁLISIS
    # -------------------------------------------------
    st.markdown("<h2 style='color:#3A86FF'>🤖 GIA — Análisis de SLA</h2>", unsafe_allow_html=True)
    st.caption("IPS Goleman | Inteligencia para el Soporte")

    offset = st.number_input("Diferencia horaria Servidor vs Bogotá (h)", value=5.0, step=0.5)
    now_bog = datetime.now(ZoneInfo("America/Bogota"))
    server_time = now_bog + timedelta(hours=offset)

    col1,col2 = st.columns(2)
    col1.markdown(f"<div class='metric-card'><div class='metric-value'>{now_bog.strftime('%Y-%m-%d %H:%M:%S')}</div><div class='metric-label'>Hora Bogotá</div></div>", unsafe_allow_html=True)
    col2.markdown(f"<div class='metric-card'><div class='metric-value'>{server_time.strftime('%Y-%m-%d %H:%M:%S')}</div><div class='metric-label'>Hora Servidor (estimada)</div></div>", unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)

    uploaded = st.file_uploader("📎 Subir reporte exportado desde GLPI (Detallado de casos)", type=["csv","xlsx"])
    if not uploaded:
        st.info("Sube tu archivo de casos GLPI para generar el análisis SLA.")
        st.stop()
    df = pd.read_csv(uploaded) if uploaded.name.endswith(".csv") else pd.read_excel(uploaded)
    df.columns=[c.strip() for c in df.columns]

    # Columnas automáticas
    def pick(posibles):
        for c in df.columns:
            if any(p in norm(c) for p in posibles): return c
        return None
    col_crea=pick(["apertura","creacion"])
    col_cierre=pick(["cierre","resol"])
    col_prior=pick(["prioridad"])
    col_tec=pick(["asignado","tecn"])
    col_estado=pick(["estado"])

    df["_crea"]=df[col_crea].apply(to_ts)
    df["_cierre"]=df[col_cierre].apply(to_ts) if col_cierre else pd.NaT
    df["_crea"]-=timedelta(hours=offset)
    df["_cierre"]-=timedelta(hours=offset)
    df["Horas"]=df.apply(lambda r:horas_habiles(r["_crea"],r["_cierre"]) if pd.notna(r["_cierre"]) else 0,axis=1)
    df["SLA(h)"]=df[col_prior].apply(sla_limit)
    df["Estado SLA"]=df.apply(lambda r:"Abierto" if pd.isna(r["_cierre"]) else ("Cumplido" if r["Horas"]<=r["SLA(h)"] else "Tardío"),axis=1)

    # Resumen
    resumen=df.groupby(col_tec).agg(Asignados=(col_crea,"count"),
                                    Resueltos=("_cierre","count"),
                                    Tardíos=("Estado SLA",lambda x:(x=="Tardío").sum())).reset_index()
    resumen["SLA(%)"]=((resumen["Resueltos"]-resumen["Tardíos"])/(resumen["Asignados"]+1e-9))*100

    st.subheader("📊 Resultados por técnico")
    st.dataframe(resumen,use_container_width=True)

    st.subheader("📈 Gráfico SLA por técnico")
    fig=px.bar(resumen.sort_values("SLA(%)",ascending=False),x=col_tec,y="SLA(%)",
               color="SLA(%)",color_continuous_scale=["#EF476F","#FFD166","#06D6A0"],
               text_auto=".2f",title="Cumplimiento SLA (%) por Técnico")
    st.plotly_chart(fig,use_container_width=True)

    cumplidos=int((df["Estado SLA"]=="Cumplido").sum())
    tardios=int((df["Estado SLA"]=="Tardío").sum())
    if cumplidos+tardios>0:
        pie=px.pie(pd.DataFrame({"Estado":["Cumplido","Tardío"],"Cantidad":[cumplidos,tardios]}),
                   names="Estado",values="Cantidad",
                   color="Estado",color_discrete_map={"Cumplido":"#06D6A0","Tardío":"#EF476F"},
                   title="Distribución de Casos Cerrados")
        st.plotly_chart(pie,use_container_width=True)
    else:
        st.warning("No hay casos cerrados para mostrar distribución.")

    # PDF
    st.subheader("📄 Reporte PDF")
    from io import BytesIO
    def pdf(resumen):
        buf=BytesIO()
        fecha=datetime.now(ZoneInfo("America/Bogota")).strftime("%d/%m/%Y – %H:%M (hora local Bogotá)")
        doc=SimpleDocTemplate(buf,pagesize=A4)
        s=getSampleStyleSheet()
        t=ParagraphStyle('t',parent=s['Title'],alignment=TA_CENTER,textColor=colors.HexColor("#3A86FF"))
        story=[Paragraph("GIA – Reporte de SLA",t),Paragraph(f"Generado el {fecha}",s['Normal']),Spacer(1,12)]
        data=[["Técnico","Asignados","Resueltos","Tardíos","SLA(%)"]]+resumen[[col_tec,"Asignados","Resueltos","Tardíos","SLA(%)"]].round(2).values.tolist()
        tbl=Table(data,colWidths=[120,70,70,70,70])
        tbl.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor("#3A86FF")),
                                 ('TEXTCOLOR',(0,0),(-1,0),colors.white),
                                 ('ALIGN',(0,0),(-1,-1),'CENTER'),
                                 ('GRID',(0,0),(-1,-1),0.3,colors.gray)]))
        story.append(tbl); doc.build(story)
        pdf_bytes=buf.getvalue(); buf.close(); return pdf_bytes
    pdf_bytes=pdf(resumen)
    fecha_btn=datetime.now(ZoneInfo("America/Bogota")).strftime("%d-%m-%Y_%H%M")
    st.download_button(f"📥 Descargar reporte PDF de SLA (generado el {fecha_btn})",pdf_bytes,file_name=f"GIA_SLA_{fecha_btn}.pdf")

else:
    # -------------------------------------------------
    # PANEL TV (URL ?tv=1)
    # -------------------------------------------------
    st.markdown("""
    <style>
    body {background: radial-gradient(circle at top left, #0E1117, #010409);}
    h1,h2,h3,p,div,span {color:white !important;}
    </style>
    """, unsafe_allow_html=True)

    st.markdown("<h1 style='text-align:center;color:#3A86FF;'>📺 GIA | Rendimiento del Equipo</h1>", unsafe_allow_html=True)
    st.caption("IPS Goleman | Inteligencia para el Soporte")

    # Cargar archivo previo (o pedirlo)
    uploaded = st.file_uploader("📎 Subir reporte exportado desde GLPI (Detallado de casos)", type=["csv","xlsx"])
    if not uploaded:
        st.info("Sube el reporte para visualizar el panel público.")
        st.stop()

    df = pd.read_csv(uploaded) if uploaded.name.endswith(".csv") else pd.read_excel(uploaded)
    df.columns=[c.strip() for c in df.columns]

    col_crea=next(c for c in df.columns if "apertura" in norm(c) or "creacion" in norm(c))
    col_cierre=next((c for c in df.columns if "cierre" in norm(c) or "resol" in norm(c)),None)
    col_prior=next(c for c in df.columns if "prior" in norm(c))
    col_tec=next(c for c in df.columns if "asignado" in norm(c) or "tecn" in norm(c))

    df["_crea"]=df[col_crea].apply(to_ts)
    df["_cierre"]=df[col_cierre].apply(to_ts) if col_cierre else pd.NaT
    df["Horas"]=df.apply(lambda r:horas_habiles(r["_crea"],r["_cierre"]) if pd.notna(r["_cierre"]) else 0,axis=1)
    df["SLA(h)"]=df[col_prior].apply(sla_limit)
    df["Estado SLA"]=df.apply(lambda r:"Abierto" if pd.isna(r["_cierre"]) else ("Cumplido" if r["Horas"]<=r["SLA(h)"] else "Tardío"),axis=1)
    resumen=df.groupby(col_tec).agg(Asignados=(col_crea,"count"),
                                    Resueltos=("_cierre","count"),
                                    Tardíos=("Estado SLA",lambda x:(x=="Tardío").sum())).reset_index()
    resumen["SLA(%)"]=((resumen["Resueltos"]-resumen["Tardíos"])/(resumen["Asignados"]+1e-9))*100

    # Ranking técnico
    fig = px.bar(resumen.sort_values("SLA(%)",ascending=True),
                 x="SLA(%)", y=col_tec, orientation="h",
                 color="SLA(%)", text_auto=".1f",
                 color_continuous_scale=["#EF476F","#FFD166","#06D6A0"],
                 title="Cumplimiento SLA por Técnico")
    fig.update_layout(template="plotly_dark", height=600,
                      title_font=dict(size=28,color="#3A86FF"),
                      font=dict(size=18,color="white"),margin=dict(l=120,r=40,t=80,b=40))
    st.plotly_chart(fig,use_container_width=True)

    # Indicador global
    prom = resumen["SLA(%)"].mean()
    st.markdown(f"<h2 style='text-align:center;color:#06D6A0;'>Promedio Global SLA: {prom:.2f}%</h2>", unsafe_allow_html=True)
    hora=datetime.now(ZoneInfo("America/Bogota")).strftime("%d/%m/%Y – %H:%M:%S")
    st.markdown(f"<p style='text-align:center;color:#999;'>Actualizado: {hora} (Bogotá)</p>", unsafe_allow_html=True)

    # Auto refrescar cada 30s
    st_autorefresh = st.experimental_rerun  # Para refrescar manual si se desea
