import pandas as pd
import streamlit as st
import plotly.express as px
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from io import BytesIO
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import letter
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.units import inch
import unicodedata
import time as time_module

# CONFIGURACIÓN
st.set_page_config(page_title="GIA - SLA Inteligente", page_icon="🤖", layout="wide")

# Detectar modo TV
try:
    is_tv = "tv" in st.query_params and st.query_params.get("tv") in ("1", "true", "True")
except Exception:
    is_tv = False

# Botón cambio de modo
if not is_tv:
    col_btn1, col_btn2, col_btn3 = st.columns([3, 1, 3])
    with col_btn2:
        if st.button("📺 Modo TV", use_container_width=True, type="primary"):
            st.query_params["tv"] = "1"
            st.rerun()
else:
    col_btn1, col_btn2, col_btn3 = st.columns([3, 1, 3])
    with col_btn2:
        if st.button("📊 Modo Normal", use_container_width=True, type="secondary"):
            st.query_params.clear()
            st.rerun()

# Tema oscuro
st.markdown("""
<style>
:root, body, [data-testid="stAppViewContainer"] { background: #0E1117 !important; color: #FFF !important; }
* { color: #FFF; }
[data-testid="stHeader"], [data-testid="stToolbar"] { visibility: hidden !important; }
footer { visibility: hidden !important; }
.block-container { padding-top: 1.2rem; padding-bottom: 2rem; }
.metric-card {
  background:#1E1E1E; border:1px solid #3A86FF33;
  border-radius:12px; padding:14px; text-align:center;
  box-shadow:0 0 6px rgba(58,134,255,0.25);
}
.metric-value { font-size:22px; font-weight:800; color:white; }
.metric-label { color:#FF9F1C; font-size:12px; }
.clock-card {
  background:#1E1E1E; border:2px solid #06D6A0;
  border-radius:12px; padding:16px; text-align:center;
  box-shadow:0 0 8px rgba(6,214,160,0.3);
}
.clock-value { font-size:28px; font-weight:900; color:#06D6A0; }
.clock-label { color:#FFD166; font-size:14px; font-weight:600; }
hr {border:0; height:1px; background:#333; margin:18px 0;}
</style>
""", unsafe_allow_html=True)

# PARÁMETROS
OFFSET_HOURS = 5.0
WORK_SCHEDULE = {
    0: [(time(7,0), time(17,0))],
    1: [(time(7,0), time(17,0))],
    2: [(time(7,0), time(17,0))],
    3: [(time(7,0), time(17,0))],
    4: [(time(7,0), time(16,0))],
    5: [(time(8,0), time(13,0))],
    6: []
}

SLA_HOURS = {
    "muy alta": 4,
    "alta": 8,
    "media": 16,
    "baja": 32,
    "muy baja": 2/60
}

# FUNCIONES UTILIDAD
def norm(s: str) -> str:
    if pd.isna(s) or s is None:
        return ""
    s = str(s)
    s = "".join(ch for ch in unicodedata.normalize("NFD", s) if unicodedata.category(ch) != "Mn")
    return s.lower().strip()

def to_timestamp(fecha_str, offset_hours=OFFSET_HOURS):
    if pd.isna(fecha_str):
        return pd.NaT
    try:
        dt = pd.to_datetime(fecha_str, errors='coerce', dayfirst=True)
        if pd.isna(dt):
            return pd.NaT
        return dt - timedelta(hours=offset_hours)
    except:
        return pd.NaT

def business_hours_between(start: datetime, end: datetime) -> float:
    if pd.isna(start) or pd.isna(end) or end <= start:
        return 0.0
    
    total_seconds = 0.0
    current = start
    max_days = 400
    
    for _ in range(max_days):
        current_date = current.date()
        weekday = current.weekday()
        
        if weekday not in WORK_SCHEDULE or not WORK_SCHEDULE[weekday]:
            next_day = datetime.combine(current_date + timedelta(days=1), time(0, 0))
            if next_day >= end:
                break
            current = next_day
            continue
        
        for (start_time, end_time) in WORK_SCHEDULE[weekday]:
            block_start = datetime.combine(current_date, start_time)
            block_end = datetime.combine(current_date, end_time)
            
            actual_start = max(current, block_start)
            actual_end = min(end, block_end)
            
            if actual_end > actual_start:
                total_seconds += (actual_end - actual_start).total_seconds()
        
        next_day = datetime.combine(current_date + timedelta(days=1), time(0, 0))
        if next_day >= end:
            break
        current = next_day
    
    return total_seconds / 3600.0

def get_sla_hours(priority: str) -> float:
    if pd.isna(priority):
        return 8.0
    
    priority_norm = norm(priority)
    
    if "muy baja" in priority_norm or "muybaja" in priority_norm:
        return 2/60
    elif "muy alta" in priority_norm or "muyalta" in priority_norm:
        return 4
    elif "alta" in priority_norm:
        return 8
    elif "media" in priority_norm:
        return 16
    elif "baja" in priority_norm:
        return 32
    
    return 8.0

def is_resolved(estado: str) -> bool:
    estado_norm = norm(estado)
    return "resuel" in estado_norm or "cerr" in estado_norm or "solucion" in estado_norm

def procesar_datos(df: pd.DataFrame):
    df["Fecha Apertura (Bogotá)"] = df["Fecha de apertura"].apply(to_timestamp)
    df["Resuelto"] = df["Estados"].apply(is_resolved)
    
    df["Fecha Cierre (Bogotá)"] = df.apply(
        lambda r: to_timestamp(r["Última modificación"]) if r["Resuelto"] else pd.NaT,
        axis=1
    )
    
    def calc_horas(row):
        if pd.isna(row["Fecha Apertura (Bogotá)"]):
            return 0.0
        
        if row["Resuelto"] and pd.notna(row["Fecha Cierre (Bogotá)"]):
            end_date = row["Fecha Cierre (Bogotá)"]
        else:
            end_date = datetime.now()
        
        return business_hours_between(row["Fecha Apertura (Bogotá)"], end_date)
    
    df["Horas Hábiles"] = df.apply(calc_horas, axis=1)
    df["Minutos Hábiles"] = df["Horas Hábiles"] * 60
    
    df["SLA Límite (h)"] = df["Prioridad"].apply(get_sla_hours)
    df["SLA Límite (min)"] = df["SLA Límite (h)"] * 60
    
    def estado_sla(row):
        if not row["Resuelto"]:
            if row["Horas Hábiles"] > row["SLA Límite (h)"]:
                return "⏰ Abierto (Tardío)"
            return "🟢 Abierto"
        else:
            if row["Horas Hábiles"] <= row["SLA Límite (h)"]:
                return "✅ Cumplido"
            return "❌ Tardío"
    
    df["Estado SLA"] = df.apply(estado_sla, axis=1)
    df["Es Tardío"] = df["Estado SLA"].str.contains("Tardío")
    
    return df

def generar_resumen(df: pd.DataFrame, col_tecnico: str) -> pd.DataFrame:
    resumen = df.groupby(col_tecnico).agg(
        Asignados=("ID", "count"),
        Resueltos=("Resuelto", "sum"),
        Tardíos=("Es Tardío", "sum")
    ).reset_index()
    
    def calc_sla_pct(row):
        if row["Resueltos"] == 0:
            return 0.0
        cumplidos = row["Resueltos"] - row["Tardíos"]
        return (cumplidos / row["Resueltos"]) * 100
    
    resumen["SLA (%)"] = resumen.apply(calc_sla_pct, axis=1)
    
    return resumen

def generar_pdf_mejorado(resumen: pd.DataFrame, df_completo: pd.DataFrame, col_tec: str, filtro_tec: str = None):
    buf = BytesIO()
    fecha_bog = datetime.now(ZoneInfo("America/Bogota"))
    fecha_str = fecha_bog.strftime("%d/%m/%Y - %H:%M")
    
    doc = SimpleDocTemplate(buf, pagesize=letter, 
                           topMargin=0.5*inch, bottomMargin=0.5*inch,
                           leftMargin=0.5*inch, rightMargin=0.5*inch)
    
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'Title', parent=styles['Title'],
        fontSize=24, textColor=colors.HexColor("#3A86FF"),
        alignment=TA_CENTER, spaceAfter=12
    )
    
    heading_style = ParagraphStyle(
        'Heading', parent=styles['Heading2'],
        fontSize=14, textColor=colors.HexColor("#3A86FF"),
        spaceAfter=10, spaceBefore=15
    )
    
    story = []
    
    story.append(Paragraph("GIA - REPORTE DE SLA", title_style))
    story.append(Paragraph(f"Generado: {fecha_str} (Bogota)", styles["Normal"]))
    if filtro_tec:
        story.append(Paragraph(f"Tecnico: {filtro_tec}", styles["Normal"]))
    story.append(Spacer(1, 0.2*inch))
    
    total_asignados = int(resumen["Asignados"].sum())
    total_resueltos = int(resumen["Resueltos"].sum())
    total_tardios = int(resumen["Tardíos"].sum())
    sla_promedio = resumen["SLA (%)"].mean() if not resumen.empty else 0.0
    
    metricas_data = [
        ["METRICA", "VALOR"],
        ["Total casos", str(total_asignados)],
        ["Resueltos", str(total_resueltos)],
        ["Tardios", str(total_tardios)],
        ["SLA Promedio", f"{sla_promedio:.2f}%"],
    ]
    
    metricas_table = Table(metricas_data, colWidths=[3.5*inch, 2.5*inch])
    metricas_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#3A86FF")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 11),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('TOPPADDING', (0,0), (-1,-1), 10),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(metricas_table)
    story.append(Spacer(1, 0.3*inch))
    
    story.append(Paragraph("RENDIMIENTO POR TECNICO", heading_style))
    
    tecnico_data = [["Tecnico", "Asignados", "Resueltos", "Tardios", "SLA (%)"]]
    
    for _, row in resumen.sort_values("SLA (%)", ascending=False).iterrows():
        tecnico_data.append([
            str(row[col_tec])[:30],
            str(int(row["Asignados"])),
            str(int(row["Resueltos"])),
            str(int(row["Tardíos"])),
            f"{row['SLA (%)']:.1f}%"
        ])
    
    tecnico_table = Table(tecnico_data, colWidths=[2.2*inch, 0.9*inch, 0.9*inch, 0.9*inch, 1*inch])
    tecnico_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#3A86FF")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(tecnico_table)
    
    doc.build(story)
    return buf.getvalue()

# ==================
# MODO NORMAL
# ==================
if not is_tv:
    st.markdown("<h2 style='color:#3A86FF'>🤖 GIA - Analisis de SLA</h2>", unsafe_allow_html=True)
    st.caption("IPS Goleman - Inteligencia para el Soporte")
    st.markdown("<hr>", unsafe_allow_html=True)
    
    st.subheader("🕐 Sincronizacion Horaria")
    now_bogota = datetime.now(ZoneInfo("America/Bogota"))
    now_servidor = now_bogota + timedelta(hours=OFFSET_HOURS)
    
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        st.markdown(f"""
        <div class='clock-card'>
            <div class='clock-label'>HORA BOGOTA</div>
            <div class='clock-value'>{now_bogota.strftime('%H:%M:%S')}</div>
            <div style='color:#AAA;font-size:11px;'>{now_bogota.strftime('%d/%m/%Y')}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class='clock-card'>
            <div class='clock-label'>HORA SERVIDOR GIA</div>
            <div class='clock-value'>{now_servidor.strftime('%H:%M:%S')}</div>
            <div style='color:#AAA;font-size:11px;'>{now_servidor.strftime('%d/%m/%Y')}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class='clock-card'>
            <div class='clock-label'>DESFASE</div>
            <div class='clock-value'>+{OFFSET_HOURS:.0f}h</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("<hr>", unsafe_allow_html=True)
    
    uploaded = st.file_uploader("📎 Subir reporte de GIA (CSV)", type=["csv"])
    
    if not uploaded:
        st.info("📌 Sube el archivo CSV exportado desde GIA para comenzar el analisis.")
        st.stop()
    
    try:
        df = pd.read_csv(uploaded, sep=";", encoding="utf-8")
    except:
        try:
            df = pd.read_csv(uploaded, sep=",", encoding="utf-8")
        except Exception as e:
            st.error(f"Error al leer el archivo: {str(e)}")
            st.stop()
    
    required_cols = ["ID", "Estados", "Fecha de apertura", "Prioridad", "Asignado a - Técnico"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        st.error(f"❌ Faltan columnas requeridas: {', '.join(missing)}")
        st.stop()
    
    df_procesado = procesar_datos(df)
    
    st.subheader("🔍 Filtros")
    solo_uno = st.checkbox("Consultar un solo tecnico", value=False)
    
    col_tec = "Asignado a - Técnico"
    tec_seleccionado = None
    
    if solo_uno:
        tecnicos = sorted([t for t in df_procesado[col_tec].dropna().unique() if str(t).strip()])
        if tecnicos:
            tec_seleccionado = st.selectbox("👤 Seleccionar tecnico", tecnicos)
            df_filtrado = df_procesado[df_procesado[col_tec] == tec_seleccionado].copy()
        else:
            st.warning("No hay tecnicos en los datos.")
            df_filtrado = df_procesado.copy()
    else:
        df_filtrado = df_procesado.copy()
    
    resumen = generar_resumen(df_filtrado, col_tec)
    
    st.subheader("📊 Metricas Generales")
    c1, c2, c3, c4 = st.columns(4)
    
    total_asignados = int(resumen["Asignados"].sum())
    total_resueltos = int(resumen["Resueltos"].sum())
    total_tardios = int(resumen["Tardíos"].sum())
    sla_promedio = resumen["SLA (%)"].mean() if not resumen.empty else 0.0
    
    c1.markdown(f"<div class='metric-card'><div class='metric-value'>{total_asignados}</div><div class='metric-label'>Casos Asignados</div></div>", unsafe_allow_html=True)
    c2.markdown(f"<div class='metric-card'><div class='metric-value'>{total_resueltos}</div><div class='metric-label'>Casos Resueltos</div></div>", unsafe_allow_html=True)
    c3.markdown(f"<div class='metric-card'><div class='metric-value'>{total_tardios}</div><div class='metric-label'>Casos Tardios</div></div>", unsafe_allow_html=True)
    c4.markdown(f"<div class='metric-card'><div class='metric-value'>{sla_promedio:.1f}%</div><div class='metric-label'>SLA Promedio</div></div>", unsafe_allow_html=True)
    
    st.subheader("📋 Resumen por Tecnico")
    st.dataframe(resumen, use_container_width=True, hide_index=True)
    
    st.subheader("📈 Cumplimiento SLA por Tecnico")
    if not resumen.empty:
        fig = px.bar(
            resumen.sort_values("SLA (%)", ascending=False),
            x=col_tec, y="SLA (%)",
            color="SLA (%)",
            color_continuous_scale=["#EF476F", "#FFD166", "#06D6A0"],
            text_auto=".1f"
        )
        fig.update_layout(template="plotly_dark", height=400)
        st.plotly_chart(fig, use_container_width=True)
    
    st.subheader("🥧 Distribucion de Casos Cerrados")
    cerrados = df_filtrado[df_filtrado["Resuelto"] == True]
    if not cerrados.empty:
        cumplidos = (cerrados["Estado SLA"] == "✅ Cumplido").sum()
        tardios = (cerrados["Estado SLA"] == "❌ Tardío").sum()
        
        fig_pie = px.pie(
            pd.DataFrame({"Estado": ["Cumplido", "Tardio"], "Cantidad": [cumplidos, tardios]}),
            names="Estado", values="Cantidad",
            color="Estado",
            color_discrete_map={"Cumplido": "#06D6A0", "Tardio": "#EF476F"}
        )
        fig_pie.update_layout(template="plotly_dark")
        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("No hay casos cerrados para mostrar.")
    
    st.subheader("📝 Detalle de Casos")
    
    df_display = df_filtrado.copy()
    df_display["Fecha Cierre (Bogotá)"] = df_display["Fecha Cierre (Bogotá)"].apply(
        lambda x: "Sin cerrar" if pd.isna(x) else x
    )
    
    cols_mostrar = ["ID", "Título", "Estados", col_tec, "Prioridad", 
                    "Fecha Apertura (Bogotá)", "Fecha Cierre (Bogotá)",
                    "Minutos Hábiles", "SLA Límite (min)", "Estado SLA"]
    
    def highlight_tardios(row):
        if "Tardío" in str(row["Estado SLA"]):
            return ['background-color: #8B0000; color: white; font-weight: bold'] * len(row)
        return [''] * len(row)
    
    st.dataframe(
        df_display[cols_mostrar].style.apply(highlight_tardios, axis=1),
        use_container_width=True, 
        hide_index=True
    )
    
    st.markdown("<hr>", unsafe_allow_html=True)
    
    st.subheader("📥 Descargar Reporte PDF")
    
    try:
        pdf_data = generar_pdf_mejorado(resumen, df_filtrado, col_tec, tec_seleccionado)
        timestamp = now_bogota.strftime("%Y%m%d_%H%M")
        st.download_button(
            label="📄 Descargar Reporte Completo en PDF",
            data=pdf_data,
            file_name=f"GIA_SLA_Completo_{timestamp}.pdf",
            mime="application/pdf",
            use_container_width=True
        )
    except Exception as e:
        st.error(f"Error al generar PDF: {str(e)}")

# ==================
# MODO TV
# ==================
else:
    uploaded = st.file_uploader("📎 CSV", type=["csv"], key="tv_upload", label_visibility="collapsed")
    if not uploaded:
        st.markdown("<div style='text-align:center;padding:100px;'><h1 style='color:#3A86FF;'>📺 PANEL TV</h1><p style='color:#AAA;'>Esperando archivo...</p></div>", unsafe_allow_html=True)
        st.stop()
    
    df = pd.read_csv(uploaded, sep=";")
    df_procesado = procesar_datos(df)
    resumen = generar_resumen(df_procesado, "Asignado a - Técnico")
    
    if resumen.empty:
        st.warning("Sin datos")
        st.stop()
    
    tecnicos = resumen.sort_values("SLA (%)", ascending=False).reset_index(drop=True)
    total = len(tecnicos)
    
    if 'tv_index' not in st.session_state:
        st.session_state.tv_index = 0
    
    idx = st.session_state.tv_index % (total + 1)
    hora = datetime.now(ZoneInfo("America/Bogota"))
    
    if idx == total:
        st.markdown(f"<h1 style='text-align:center;color:#3A86FF;'>RESUMEN GLOBAL</h1><p style='text-align:center;color:#888;'>{hora.strftime('%d/%m/%Y %H:%M:%S')}</p>", unsafe_allow_html=True)
        
        sla_g = resumen["SLA (%)"].mean()
        color = "#06D6A0" if sla_g >= 90 else "#FFD166" if sla_g >= 70 else "#EF476F"
        
        st.markdown(f"<div style='text-align:center;padding:50px;'><div style='color:{color};font-size:140px;font-weight:900;'>{sla_g:.1f}%</div></div>", unsafe_allow_html=True)
        
        for i, row in tecnicos.iterrows():
            sla = row["SLA (%)"]
            c = "#06D6A0" if sla >= 90 else "#FFD166" if sla >= 70 else "#EF476F"
            st.markdown(f"<div style='background:#1A1A1A;padding:20px;margin:10px;border-left:4px solid {c};'><span style='font-size:24px;'>#{i+1} {row['Asignado a - Técnico']}</span><span style='float:right;color:{c};font-size:28px;font-weight:900;'>{sla:.1f}%</span></div>", unsafe_allow_html=True)
    else:
        tec = tecnicos.iloc[idx]
        sla = tec["SLA (%)"]
        color = "#06D6A0" if sla >= 90 else "#FFD166" if sla >= 70 else "#EF476F"
        
        st.markdown(f"<h1 style='text-align:center;color:#FFF;'>{tec['Asignado a - Técnico']}</h1><p style='text-align:center;color:#888;'>Posicion #{idx+1} de {total}</p>", unsafe_allow_html=True)
        st.markdown(f"<div style='text-align:center;padding:60px;background:#1A1A1A;border:3px solid {color};border-radius:20px;margin:30px;'><div style='color:{color};font-size:180px;font-weight:900;'>{sla:.1f}%</div></div>", unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns(3)
        col1.markdown(f"<div style='text-align:center;padding:30px;background:#1A1A1A;border-radius:10px;'><div style='color:#888;'>Asignados</div><div style='color:#3A86FF;font-size:64px;font-weight:700;'>{int(tec['Asignados'])}</div></div>", unsafe_allow_html=True)
        col2.markdown(f"<div style='text-align:center;padding:30px;background:#1A1A1A;border-radius:10px;'><div style='color:#888;'>Resueltos</div><div style='color:#06D6A0;font-size:64px;font-weight:700;'>{int(tec['Resueltos'])}</div></div>", unsafe_allow_html=True)
        col3.markdown(f"<div style='text-align:center;padding:30px;background:#1A1A1A;border-radius:10px;'><div style='color:#888;'>Tardios</div><div style='color:#EF476F;font-size:64px;font-weight:700;'>{int(tec['Tardíos'])}</div></div>", unsafe_allow_html=True)
    
    time_module.sleep(5)
    st.session_state.tv_index += 1
    st.rerun()
