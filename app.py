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

# =========================
# CONFIGURACIÓN GLOBAL
# =========================
st.set_page_config(page_title="GIA - SLA Inteligente", page_icon="🤖", layout="wide")

# Detectar modo TV
try:
    is_tv = "tv" in st.query_params and st.query_params.get("tv") in ("1", "true", "True")
except Exception:
    is_tv = False

# Botón para cambiar de modo (antes de cualquier contenido)
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
a { color: #5FA8FF !important; }
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
.stDownloadButton button {
  background:#3A86FF !important; color:white !important; border:none !important;
}
.stDownloadButton button:hover { background:#5FA8FF !important; }
hr {border:0; height:1px; background:#333; margin:18px 0;}
</style>
""", unsafe_allow_html=True)

# =========================
# PARÁMETROS DE NEGOCIO
# =========================
OFFSET_HOURS = 5.0  # Servidor tiene +5h respecto a Bogotá

# Horario laboral (0=Lunes...6=Domingo)
WORK_SCHEDULE = {
    0: [(time(7,0), time(17,0))],   # Lunes
    1: [(time(7,0), time(17,0))],   # Martes
    2: [(time(7,0), time(17,0))],   # Miércoles
    3: [(time(7,0), time(17,0))],   # Jueves
    4: [(time(7,0), time(16,0))],   # Viernes
    5: [(time(8,0), time(13,0))],   # Sábado
    6: []                            # Domingo
}

# SLA por prioridad (en HORAS hábiles)
SLA_HOURS = {
    "muy alta": 4,           # 4 horas
    "alta": 8,               # 8 horas (1 día)
    "media": 16,             # 2 días hábiles
    "baja": 32,              # 4 días hábiles
    "muy baja": 2/60         # 2 minutos
}

# =========================
# UTILIDADES
# =========================
def norm(s: str) -> str:
    """Normaliza texto: sin acentos, minúsculas, sin espacios extra"""
    if pd.isna(s) or s is None:
        return ""
    s = str(s)
    s = "".join(ch for ch in unicodedata.normalize("NFD", s) if unicodedata.category(ch) != "Mn")
    return s.lower().strip()

def to_timestamp(fecha_str, offset_hours=OFFSET_HOURS):
    """Convierte string a datetime y ajusta a hora Bogotá"""
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
    """Calcula horas hábiles entre dos fechas según WORK_SCHEDULE"""
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
    """Retorna las horas SLA según la prioridad"""
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
    """Determina si un caso está resuelto según su estado"""
    estado_norm = norm(estado)
    return "resuel" in estado_norm or "cerr" in estado_norm or "solucion" in estado_norm

# =========================
# PROCESAMIENTO PRINCIPAL
# =========================
def procesar_datos(df: pd.DataFrame):
    """Procesa el DataFrame y calcula todas las métricas SLA"""
    
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
    """Genera resumen por técnico"""
    
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
    """Genera reporte PDF completo con todas las estadísticas"""
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
    
    subtitle_style = ParagraphStyle(
        'Subtitle', parent=styles['Normal'],
        fontSize=11, textColor=colors.grey,
        alignment=TA_CENTER, spaceAfter=20
    )
    
    heading_style = ParagraphStyle(
        'Heading', parent=styles['Heading2'],
        fontSize=14, textColor=colors.HexColor("#3A86FF"),
        spaceAfter=10, spaceBefore=15
    )
    
    story = []
    
    # PORTADA
    story.append(Paragraph("GIA - REPORTE DE SLA", title_style))
    story.append(Paragraph("IPS Goleman | Inteligencia para el Soporte", subtitle_style))
    story.append(Spacer(1, 0.2*inch))
    
    # Info del reporte
    info_data = [
        ["Fecha de generacion:", fecha_str],
        ["Zona horaria:", "Bogota (COT, UTC-5)"],
        ["Desfase servidor:", f"+{OFFSET_HOURS:.0f} horas"],
    ]
    
    if filtro_tec:
        info_data.append(["Tecnico filtrado:", filtro_tec])
    
    info_table = Table(info_data, colWidths=[2*inch, 4*inch])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (0,-1), colors.HexColor("#E8E8E8")),
        ('ALIGN', (0,0), (0,-1), 'RIGHT'),
        ('ALIGN', (1,0), (1,-1), 'LEFT'),
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 10),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 0.3*inch))
    
    # METRICAS GLOBALES
    story.append(Paragraph("METRICAS GLOBALES", heading_style))
    
    total_asignados = int(resumen["Asignados"].sum())
    total_resueltos = int(resumen["Resueltos"].sum())
    total_tardios = int(resumen["Tardíos"].sum())
    sla_promedio = resumen["SLA (%)"].mean() if not resumen.empty else 0.0
    tasa_resol = (total_resueltos/total_asignados*100 if total_asignados > 0 else 0)
    
    if sla_promedio >= 90:
        sla_color = colors.HexColor("#06D6A0")
    elif sla_promedio >= 70:
        sla_color = colors.HexColor("#FFD166")
    else:
        sla_color = colors.HexColor("#EF476F")
    
    metricas_data = [
        ["METRICA", "VALOR"],
        ["Total de casos asignados", str(total_asignados)],
        ["Casos resueltos", str(total_resueltos)],
        ["Casos tardios", str(total_tardios)],
        ["SLA Promedio", f"{sla_promedio:.2f}%"],
        ["Tasa de resolucion", f"{tasa_resol:.1f}%"],
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
        ('BACKGROUND', (0,4), (-1,4), sla_color),
        ('TEXTCOLOR', (0,4), (-1,4), colors.white),
        ('FONTNAME', (0,4), (-1,4), 'Helvetica-Bold'),
    ]))
    story.append(metricas_table)
    story.append(Spacer(1, 0.3*inch))
    
    # RENDIMIENTO POR TECNICO
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
    
    table_style = [
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#3A86FF")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
    ]
    
    for i, (_, row) in enumerate(resumen.sort_values("SLA (%)", ascending=False).iterrows(), start=1):
        sla_val = row["SLA (%)"]
        if sla_val >= 90:
            bg_color = colors.HexColor("#D5F5E3")
        elif sla_val >= 70:
            bg_color = colors.HexColor("#FFF4CC")
        else:
            bg_color = colors.HexColor("#FADBD8")
        table_style.append(('BACKGROUND', (0,i), (-1,i), bg_color))
    
    tecnico_table.setStyle(TableStyle(table_style))
    story.append(tecnico_table)
    
    # NUEVA PAGINA: DETALLE DE CASOS
    story.append(PageBreak())
    story.append(Paragraph("DETALLE DE CASOS", heading_style))
    story.append(Spacer(1, 0.1*inch))
    
    df_pdf = df_completo.copy()
    if len(df_pdf) > 50:
        story.append(Paragraph(
            f"<i>Mostrando los primeros 50 casos de {len(df_pdf)} totales</i>",
            styles['Normal']
        ))
        df_pdf = df_pdf.head(50)
    
    casos_data = [["ID", "Titulo", "Tecnico", "Prior.", "Min.", "Limite", "Estado"]]
    
    for _, row in df_pdf.iterrows():
        titulo = str(row["Título"])[:25] + "..." if len(str(row["Título"])) > 25 else str(row["Título"])
        tecnico = str(row[col_tec])[:18] + "..." if len(str(row[col_tec])) > 18 else str(row[col_tec])
        prior = str(row["Prioridad"])[:8]
        estado = "OK" if "Cumplido" in str(row["Estado SLA"]) else "X" if "Tardío" in str(row["Estado SLA"]) else "..."
        
        casos_data.append([
            str(row["ID"]),
            titulo,
            tecnico,
            prior,
            f"{row['Minutos Hábiles']:.1f}",
            f"{row['SLA Límite (min)']:.1f}",
            estado
        ])
    
    casos_table = Table(casos_data, colWidths=[0.4*inch, 1.5*inch, 1.4*inch, 0.6*inch, 0.5*inch, 0.6*inch, 0.5*inch])
    
    casos_style = [
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#3A86FF")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.3, colors.grey),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]
    
    for i, (_, row) in enumerate(df_pdf.iterrows(), start=1):
        if "Tardío" in str(row["Estado SLA"]):
            casos_style.append(('BACKGROUND', (0,i), (-1,i), colors.HexColor("#EF476F")))
            casos_style.append(('TEXTCOLOR', (0,i), (-1,i), colors.white))
    
    casos_table.setStyle(TableStyle(casos_style))
    story.append(casos_table)
    
    story.append(Spacer(1, 0.3*inch))
    footer_style = ParagraphStyle('footer', parent=styles['Normal'], 
                                  fontSize=8, textColor=colors.grey, alignment=TA_CENTER)
    story.append(Paragraph(f"<i>Reporte generado por GIA | {fecha_str}</i>", footer_style))
    
    doc.build(story)
    return buf.getvalue()

# =========================
# INTERFAZ PRINCIPAL
# =========================
if not is_tv:
    st.markdown("<h2 style='color:#3A86FF'>🤖 GIA - Analisis de SLA</h2>", unsafe_allow_html=True)
    st.caption("IPS Goleman - Inteligencia para el Soporte")
    st.markdown("<hr>", unsafe_allow_html=True)
    
    # RELOJES
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
    
    # SUBIR ARCHIVO
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
        st.info(f"Columnas encontradas: {', '.join(df.columns)}")
        st.stop()
    
    # PROCESAR DATOS
    df_procesado = procesar_datos(df)
    
    # FILTROS
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
    
    # GENERAR RESUMEN
    resumen = generar_resumen(df_filtrado, col_tec)
    
    # KPIs
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
    
    # TABLA RESUMEN
    st.subheader("📋 Resumen por Tecnico")
    st.dataframe(resumen, use_container_width=True, hide_index=True)
    
    # GRAFICO BARRAS
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
    
    # GRAFICO PIE
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
    
    # DETALLE DE CASOS
    st.subheader("📝 Detalle de Casos")
    
    df_display = df_filtrado.copy()
    df_display["Fecha Cierre (Bogotá)"] = df_display["Fecha Cierre (Bogotá)"].apply(
        lambda x: "Sin cerrar" if pd.isna(x) else x
    )
    
    cols_mostrar = ["ID", "Título", "Estados", col_tec, "Prioridad", 
                    "Fecha Apertura (Bogotá)", "Fecha Cierre (Bogotá)",
                    "Minutos Hábiles", "SLA Límite (min)", "Estado SLA"]
    
    # Funcion para colorear filas tardias
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
    
    # DESCARGAR PDF
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
        st.info("Por favor reporta este error al administrador.")

# MODO TV
else:
    st.markdown("<h1 style='text-align:center;color:#3A86FF;'>📺 GIA | PANEL DE RENDIMIENTO EN VIVO</h1>", unsafe_allow_html=True)
    st.caption("IPS Goleman - Dashboard en Tiempo Real")
    st.markdown("<hr>", unsafe_allow_html=True)
    
    # JavaScript para auto-refresh cada 30 segundos
    st.markdown("""
    <script>
        setTimeout(function(){
            window.location.reload();
        }, 30000);
    </script>
    """, unsafe_allow_html=True)
    
    uploaded = st.file_uploader("📎 Subir reporte CSV", type=["csv"], key="tv_upload")
    if not uploaded:
        st.info("⏳ Esperando archivo para iniciar el dashboard...")
        st.stop()
    
    df = pd.read_csv(uploaded, sep=";")
    df_procesado = procesar_datos(df)
    resumen = generar_resumen(df_procesado, "Asignado a - Técnico")
    
    if resumen.empty:
        st.warning("No hay datos para mostrar")
        st.stop()
    
    # HORA Y MÉTRICAS GLOBALES
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col1:
        hora = datetime.now(ZoneInfo("America/Bogota")).strftime("%H:%M:%S")
        fecha = datetime.now(ZoneInfo("America/Bogota")).strftime("%d/%m/%Y")
        st.markdown(f"""
        <div style='background:#1E1E1E;border:2px solid #06D6A0;border-radius:15px;padding:25px;text-align:center;'>
            <div style='color:#FFD166;font-size:16px;font-weight:600;'>🕐 HORA ACTUAL</div>
            <div style='color:#06D6A0;font-size:38px;font-weight:900;margin:10px 0;'>{hora}</div>
            <div style='color:#AAA;font-size:14px;'>{fecha}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        sla_global = resumen["SLA (%)"].mean()
        total_casos = int(resumen["Asignados"].sum())
        total_resueltos = int(resumen["Resueltos"].sum())
        
        color_sla = "#06D6A0" if sla_global >= 90 else "#FFD166" if sla_global >= 70 else "#EF476F"
        
        st.markdown(f"""
        <div style='background:#1E1E1E;border:3px solid {color_sla};border-radius:15px;padding:25px;text-align:center;'>
            <div style='color:#3A86FF;font-size:18px;font-weight:700;'>📊 SLA GLOBAL DEL EQUIPO</div>
            <div style='color:{color_sla};font-size:65px;font-weight:900;margin:15px 0;text-shadow:0 0 20px {color_sla};'>
                {sla_global:.1f}%
            </div>
            <div style='color:#AAA;font-size:14px;'>{total_resueltos} resueltos de {total_casos} casos</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        mejor_tecnico = resumen.sort_values("SLA (%)", ascending=False).iloc[0]
        st.markdown(f"""
        <div style='background:#1E1E1E;border:2px solid #FFD166;border-radius:15px;padding:25px;text-align:center;'>
            <div style='color:#FFD166;font-size:16px;font-weight:600;'>🏆 MVP DEL DÍA</div>
            <div style='color:white;font-size:16px;font-weight:700;margin:10px 0;'>{str(mejor_tecnico['Asignado a - Técnico'])[:20]}</div>
            <div style='color:#06D6A0;font-size:32px;font-weight:900;'>{mejor_tecnico['SLA (%)']:.1f}%</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("<hr style='margin:30px 0;'>", unsafe_allow_html=True)
    
    # RANKING TOP 3 - PODIO
    st.markdown("<h2 style='text-align:center;color:#3A86FF;margin-bottom:30px;'>🏆 PODIO DE TECNICOS</h2>", unsafe_allow_html=True)
    
    top3 = resumen.sort_values("SLA (%)", ascending=False).head(3)
    
    if len(top3) >= 3:
        col_2do, col_1ro, col_3ro = st.columns([1, 1, 1])
        
        # PRIMER LUGAR (centro)
        with col_1ro:
            primero = top3.iloc[0]
            st.markdown(f"""
            <div style='background:linear-gradient(135deg, #FFD700 0%, #FFA500 100%);
                        border-radius:20px;padding:30px;text-align:center;
                        box-shadow:0 0 30px rgba(255,215,0,0.5);transform:scale(1.1);'>
                <div style='font-size:50px;margin-bottom:10px;'>🥇</div>
                <div style='color:#000;font-size:20px;font-weight:900;margin:15px 0;'>
                    {str(primero['Asignado a - Técnico'])[:25]}
                </div>
                <div style='color:#000;font-size:48px;font-weight:900;text-shadow:2px 2px 4px rgba(0,0,0,0.3);'>
                    {primero['SLA (%)']:.1f}%
                </div>
                <div style='color:#000;font-size:14px;margin-top:10px;'>
                    {int(primero['Resueltos'])} casos resueltos
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        # SEGUNDO LUGAR (izquierda)
        with col_2do:
            segundo = top3.iloc[1]
            st.markdown(f"""
            <div style='background:linear-gradient(135deg, #C0C0C0 0%, #A8A8A8 100%);
                        border-radius:20px;padding:25px;text-align:center;margin-top:40px;
                        box-shadow:0 0 20px rgba(192,192,192,0.4);'>
                <div style='font-size:40px;margin-bottom:10px;'>🥈</div>
                <div style='color:#000;font-size:16px;font-weight:800;margin:10px 0;'>
                    {str(segundo['Asignado a - Técnico'])[:25]}
                </div>
                <div style='color:#000;font-size:38px;font-weight:900;'>
                    {segundo['SLA (%)']:.1f}%
                </div>
                <div style='color:#000;font-size:12px;margin-top:8px;'>
                    {int(segundo['Resueltos'])} casos resueltos
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        # TERCER LUGAR (derecha)
        with col_3ro:
            tercero = top3.iloc[2]
            st.markdown(f"""
            <div style='background:linear-gradient(135deg, #CD7F32 0%, #B87333 100%);
                        border-radius:20px;padding:25px;text-align:center;margin-top:40px;
                        box-shadow:0 0 20px rgba(205,127,50,0.4);'>
                <div style='font-size:40px;margin-bottom:10px;'>🥉</div>
                <div style='color:#FFF;font-size:16px;font-weight:800;margin:10px 0;'>
                    {str(tercero['Asignado a - Técnico'])[:25]}
                </div>
                <div style='color:#FFF;font-size:38px;font-weight:900;'>
                    {tercero['SLA (%)']:.1f}%
                </div>
                <div style='color:#FFF;font-size:12px;margin-top:8px;'>
                    {int(tercero['Resueltos'])} casos resueltos
                </div>
            </div>
            """, unsafe_allow_html=True)
    
    st.markdown("<hr style='margin:40px 0;'>", unsafe_allow_html=True)
    
    # TABLA RANKING COMPLETO
    st.markdown("<h2 style='text-align:center;color:#3A86FF;margin-bottom:25px;'>📊 RANKING COMPLETO</h2>", unsafe_allow_html=True)
    
    # Crear tabla HTML personalizada
    ranking_html = """
    <style>
        .ranking-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 18px;
            background: #1E1E1E;
            border-radius: 15px;
            overflow: hidden;
        }
        .ranking-table thead {
            background: linear-gradient(135deg, #3A86FF 0%, #5FA8FF 100%);
            color: white;
        }
        .ranking-table th {
            padding: 20px;
            text-align: center;
            font-weight: 800;
            font-size: 16px;
        }
        .ranking-table td {
            padding: 18px;
            text-align: center;
            border-bottom: 1px solid #333;
        }
        .ranking-table tr:hover {
            background: #2A2A2A;
        }
        .rank-num {
            font-size: 24px;
            font-weight: 900;
            color: #FFD166;
        }
        .sla-excellent { color: #06D6A0; font-weight: 900; font-size: 22px; }
        .sla-good { color: #FFD166; font-weight: 900; font-size: 22px; }
        .sla-poor { color: #EF476F; font-weight: 900; font-size: 22px; }
    </style>
    <table class="ranking-table">
        <thead>
            <tr>
                <th>🏅 PUESTO</th>
                <th>👤 TÉCNICO</th>
                <th>📋 ASIGNADOS</th>
                <th>✅ RESUELTOS</th>
                <th>❌ TARDÍOS</th>
                <th>📊 SLA %</th>
            </tr>
        </thead>
        <tbody>
    """
    
    for idx, (_, row) in enumerate(resumen.sort_values("SLA (%)", ascending=False).iterrows(), 1):
        sla_val = row["SLA (%)"]
        if sla_val >= 90:
            sla_class = "sla-excellent"
        elif sla_val >= 70:
            sla_class = "sla-good"
        else:
            sla_class = "sla-poor"
        
        ranking_html += f"""
        <tr>
            <td><span class="rank-num">#{idx}</span></td>
            <td style="text-align:left;font-weight:700;color:white;">{row['Asignado a - Técnico']}</td>
            <td style="color:#AAA;font-weight:600;">{int(row['Asignados'])}</td>
            <td style="color:#06D6A0;font-weight:700;">{int(row['Resueltos'])}</td>
            <td style="color:#EF476F;font-weight:700;">{int(row['Tardíos'])}</td>
            <td><span class="{sla_class}">{sla_val:.1f}%</span></td>
        </tr>
        """
    
    ranking_html += """
        </tbody>
    </table>
    """
    
    st.markdown(ranking_html, unsafe_allow_html=True)
    
    # Pie de página con actualización automática
    st.markdown("<hr style='margin:30px 0;'>", unsafe_allow_html=True)
    st.markdown(f"""
    <div style='text-align:center;color:#AAA;font-size:14px;'>
        <p>🔄 Panel actualizado: {datetime.now(ZoneInfo('America/Bogota')).strftime('%H:%M:%S')}</p>
        <p style='font-size:12px;'>Dashboard se actualiza automáticamente cada 30 segundos</p>
    </div>
    """, unsafe_allow_html=True)
