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
        if st.button("📺 Modo TV", use_container_width=True, type="primary", key="btn_mode_tv"):
            st.query_params["tv"] = "1"
            st.rerun()
else:
    col_btn1, col_btn2, col_btn3 = st.columns([3, 1, 3])
    with col_btn2:
        if st.button("📊 Modo Normal", use_container_width=True, type="secondary", key="btn_mode_normal"):
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

/* Estilos para Inputs y Selectbox */
/* Contenedor principal del Selectbox - Forzamos fondo oscuro */
div[data-baseweb="select"] > div, 
div[data-testid="stSelectbox"] > div > div > div {
    background-color: #1E1E1E !important;
    border-color: #3A86FF !important;
    color: white !important;
}

/* Texto del valor seleccionado y cualquier texto dentro */
div[data-baseweb="select"] span, 
div[data-baseweb="select"] div {
    color: white !important;
}

/* Menú desplegable (la lista de opciones) */
div[data-baseweb="menu"], 
div[data-baseweb="popover"] {
    background-color: #1E1E1E !important;
    border: 1px solid #3A86FF !important;
}

/* Opciones individuales dentro del menú */
li[role="option"] {
    background-color: #1E1E1E !important;
    color: white !important;
}

/* Opción seleccionada o hover */
li[role="option"]:hover, 
li[role="option"][aria-selected="true"] {
    background-color: #3A86FF !important;
    color: white !important;
}

/* Placeholder y texto en general dentro del select */
div[data-testid="stSelectbox"] div[class*="singleValue"], 
div[data-testid="stSelectbox"] div[class*="placeholder"],
div[data-testid="stSelectbox"] label {
    color: white !important;
}

/* Asegurar que el SVG del icono de flecha sea blanco */
div[data-baseweb="select"] svg {
    fill: white !important;
}
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

def find_col(df: pd.DataFrame, target: str):
    target_norm = norm(target)
    for c in df.columns:
        if norm(c) == target_norm:
            return c
    for c in df.columns:
        if target_norm in norm(c):
            return c
    return None

def parse_duration_to_hours(val) -> float:
    if pd.isna(val):
        return None
    try:
        if isinstance(val, (int, float)):
            return float(val) / 3600.0
        s = str(val).strip().lower()
        
        # Formato: "1 hora 30 minutos" o "3h 15m"
        if "h" in s or "m" in s or "s" in s:
            total_hours = 0.0
            s = s.replace("horas", "h").replace("hora", "h")
            s = s.replace("minutos", "m").replace("minuto", "m")
            s = s.replace("segundos", "s").replace("segundo", "s")
            
            # Extraer horas
            if "h" in s:
                parts = s.split("h")
                try:
                    total_hours += float(parts[0].strip())
                    s = parts[1]
                except:
                    pass
            # Extraer minutos
            if "m" in s:
                parts = s.split("m")
                try:
                    total_hours += float(parts[0].strip()) / 60.0
                    s = parts[1]
                except:
                    pass
            # Extraer segundos
            if "s" in s:
                parts = s.split("s")
                try:
                    total_hours += float(parts[0].strip()) / 3600.0
                except:
                    pass
            return total_hours

        if 'd' in s and ':' in s:
            try:
                parts = s.split('d')
                days = int(parts[0].strip())
                hms = parts[1].strip()
                h, m, sec = [int(x) for x in hms.split(':')]
                return days*24 + h + m/60.0 + sec/3600.0
            except:
                pass
        if ':' in s:
            p = s.split(':')
            if len(p) == 3:
                h, m, sec = [int(x) for x in p]
                return h + m/60.0 + sec/3600.0
            elif len(p) == 2:
                m, sec = [int(x) for x in p]
                return m/60.0 + sec/3600.0
        v = float(s)
        return v / 3600.0
    except:
        return None

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

def procesar_datos(df: pd.DataFrame, offset_hours: float = OFFSET_HOURS):
    col_fecha_cre = find_col(df, "Fecha de creación") or find_col(df, "Fecha de apertura")
    # Prioridad: Fecha de Solución > Fecha de Cierre > Última modificación
    col_fecha_cie = find_col(df, "Fecha de solución") or find_col(df, "Solution date") or find_col(df, "Fecha de cierre") or find_col(df, "Closing date") or find_col(df, "Última modificación")
    
    # En este reporte, 'Tiempo en resolver' contiene la FECHA LÍMITE (Vencimiento), no la duración
    col_fecha_venc = find_col(df, "Fecha de vencimiento") or find_col(df, "Tiempo límite") or find_col(df, "Due date") or find_col(df, "Tiempo en resolver") or find_col(df, "tiempo en resolver")
    
    col_excedido = find_col(df, "Tarde") or find_col(df, "Tiempo de solución excedido") or find_col(df, "TTR excedido") or find_col(df, "SLA excedido") or find_col(df, "Excedido")
    
    # Columna de duración real (si existe, para cálculos de horas)
    col_duracion_real = find_col(df, "Duración real") or find_col(df, "Tiempo real")

    df["Fecha Apertura (Bogotá)"] = df[col_fecha_cre].apply(lambda s: to_timestamp(s, offset_hours)) if col_fecha_cre else pd.NaT
    df["Resuelto"] = df["Estados"].apply(is_resolved)

    df["Fecha Cierre (Bogotá)"] = df.apply(
        lambda r: to_timestamp(r[col_fecha_cie], offset_hours) if r["Resuelto"] and col_fecha_cie else pd.NaT,
        axis=1
    )
    
    df["Fecha Vencimiento (Bogotá)"] = df[col_fecha_venc].apply(lambda s: to_timestamp(s, offset_hours)) if col_fecha_venc else pd.NaT

    def calc_horas(row):
        if pd.isna(row["Fecha Apertura (Bogotá)"]):
            return 0.0
        if row["Resuelto"]:
            # 1. Si existe columna explícita de duración real
            if col_duracion_real and pd.notna(row[col_duracion_real]):
                h = parse_duration_to_hours(row[col_duracion_real])
                if h is not None:
                    return float(h)
            
            # 2. Calcular horas hábiles entre Apertura y Cierre
            if pd.notna(row["Fecha Cierre (Bogotá)"]):
                return business_hours_between(row["Fecha Apertura (Bogotá)"], row["Fecha Cierre (Bogotá)"])
        
        # Para casos abiertos
        end_date = datetime.now(ZoneInfo("America/Bogota")).replace(tzinfo=None)
        start_date = row["Fecha Apertura (Bogotá)"]
        if pd.notna(start_date) and start_date.tzinfo is not None:
            start_date = start_date.replace(tzinfo=None)
            
        return business_hours_between(start_date, end_date)

    df["Horas Hábiles"] = df.apply(calc_horas, axis=1)
    df["Minutos Hábiles"] = df["Horas Hábiles"] * 60

    df["SLA Límite (h)"] = df["Prioridad"].apply(get_sla_hours)
    df["SLA Límite (min)"] = df["SLA Límite (h)"] * 60

    def estado_sla(row):
        is_late = False
        
        # 0. REGLA DE ORO (Usuario): Si NO hay fecha de vencimiento ("Tiempo en resolver"), SIEMPRE es A TIEMPO.
        if pd.isna(row.get("Fecha Vencimiento (Bogotá)")):
            is_late = False

        # 1. Si hay fecha, verificamos columna explícita de GLPI "Excedido"
        elif col_excedido and pd.notna(row[col_excedido]):
            val = str(row[col_excedido]).lower().strip()
            if val in ["si", "yes", "1", "true", "excedido"]:
                is_late = True
            else:
                # Si columna Excedido dice NO, verificamos fecha por si acaso (o confiamos en la columna)
                # GLPI manda: si Excedido es NO, es NO. Pero mantendremos chequeo de fecha por consistencia si usuario quiere.
                # Para ser consistentes con GLPI, si existe columna Excedido, deberíamos confiar en ella.
                # Sin embargo, la lógica de fecha es la prueba definitiva.
                pass
        
        # 2. Si no hay columna "Excedido" (o no dice nada), verificamos fechas manualmente
        # (Ya sabemos que existe Fecha Vencimiento porque pasamos el paso 0)
        if not is_late and pd.notna(row.get("Fecha Vencimiento (Bogotá)")):
            limit = row["Fecha Vencimiento (Bogotá)"]
            if row["Resuelto"]:
                # Si se cerró después de la fecha límite
                if pd.notna(row["Fecha Cierre (Bogotá)"]) and row["Fecha Cierre (Bogotá)"] > limit:
                    is_late = True
            else:
                # Si sigue abierto y ya pasó la fecha límite
                now_bog = datetime.now(ZoneInfo("America/Bogota")).replace(tzinfo=None)
                if now_bog > limit:
                    is_late = True

        if not row["Resuelto"]:
            return "⏰ Abierto (Tardío)" if is_late else "🟢 Abierto"
        else:
            return "❌ Tardío" if is_late else "✅ Cumplido"

    df["Estado SLA"] = df.apply(estado_sla, axis=1)
    df["Es Tardío"] = df["Estado SLA"].str.contains("Tardío")
    
    # Marcador específico para tardíos resueltos (para concordar con GLPI)
    df["Es Tardío Resuelto"] = df.apply(lambda r: r["Resuelto"] and r["Es Tardío"], axis=1)

    return df

def generar_resumen(df: pd.DataFrame, col_tecnico: str) -> pd.DataFrame:
    resumen = df.groupby(col_tecnico).agg(
        Asignados=("ID", "count"),
        Resueltos=("Resuelto", "sum"),
        Tardíos=("Es Tardío Resuelto", "sum") # Contamos solo los resueltos tardíos para el reporte
    ).reset_index()
    
    def calc_sla_pct(row):
        if row["Resueltos"] == 0:
            return 0.0
        # SLA basado en resueltos: (Resueltos - Tardíos Resueltos) / Resueltos
        cumplidos = row["Resueltos"] - row["Tardíos"]
        return (cumplidos / row["Resueltos"]) * 100
    
    resumen["SLA (%)"] = resumen.apply(calc_sla_pct, axis=1)
    
    return resumen

def generar_pdf_mejorado(resumen: pd.DataFrame, df_completo: pd.DataFrame, col_tec: str, filtro_tec: str = None, offset_hours: float = OFFSET_HOURS):
    buf = BytesIO()
    fecha_bog = datetime.now(ZoneInfo("America/Bogota"))
    fecha_str = fecha_bog.strftime("%d/%m/%Y - %H:%M")
    
    doc = SimpleDocTemplate(buf, pagesize=letter, 
                           topMargin=0.4*inch, bottomMargin=0.4*inch,
                           leftMargin=0.5*inch, rightMargin=0.5*inch)
    
    styles = getSampleStyleSheet()
    
    # Estilos personalizados
    title_style = ParagraphStyle('Title', parent=styles['Title'],
        fontSize=28, textColor=colors.HexColor("#3A86FF"),
        alignment=TA_CENTER, spaceAfter=6, fontName='Helvetica-Bold')
    
    subtitle_style = ParagraphStyle('Subtitle', parent=styles['Normal'],
        fontSize=11, textColor=colors.grey, alignment=TA_CENTER, spaceAfter=14)
    
    heading1_style = ParagraphStyle('Heading1', parent=styles['Heading1'],
        fontSize=16, textColor=colors.HexColor("#3A86FF"),
        spaceAfter=10, spaceBefore=16, fontName='Helvetica-Bold')
    
    heading2_style = ParagraphStyle('Heading2', parent=styles['Heading2'],
        fontSize=13, textColor=colors.HexColor("#5FA8FF"),
        spaceAfter=8, spaceBefore=12, fontName='Helvetica-Bold')
    
    normal_style = ParagraphStyle('Normal', parent=styles['Normal'],
        fontSize=9, textColor=colors.black)
    
    story = []
    
    # ==================
    # PORTADA
    # ==================
    story.append(Paragraph("GIA - INFORME DETALLADO DE SLA", title_style))
    story.append(Paragraph("IPS Goleman | Sistema de Gestion de Incidencias y Soporte Tecnico", subtitle_style))
    story.append(Spacer(1, 0.12*inch))
    
    # Información general del reporte
    info_data = [
        ["Fecha y hora de generacion:", fecha_str],
        ["Zona horaria:", "Bogota, Colombia (COT, UTC-5)"],
        ["Desfase del servidor:", f"+{offset_hours:.0f} horas"],
        ["Total de registros procesados:", str(len(df_completo))],
        ["Periodo analizado:", "Completo"],
    ]
    if filtro_tec:
        info_data.append(["Filtro aplicado:", f"Tecnico: {filtro_tec}"])
    
    info_table = Table(info_data, colWidths=[2.2*inch, 4*inch])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (0,-1), colors.HexColor("#E8E8E8")),
        ('ALIGN', (0,0), (0,-1), 'RIGHT'),
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('TOPPADDING', (0,0), (-1,-1), 7),
        ('BOTTOMPADDING', (0,0), (-1,-1), 7),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 0.2*inch))
    
    # ==================
    # RESUMEN EJECUTIVO
    # ==================
    story.append(Paragraph("1. RESUMEN EJECUTIVO", heading1_style))
    
    total_asignados = int(resumen["Asignados"].sum())
    total_resueltos = int(resumen["Resueltos"].sum())
    total_tardios = int(resumen["Tardíos"].sum())
    sla_promedio = resumen["SLA (%)"].mean() if not resumen.empty else 0.0
    tasa_resol = (total_resueltos/total_asignados*100 if total_asignados > 0 else 0)
    cumplidos = total_resueltos - total_tardios
    abiertos = total_asignados - total_resueltos
    
    # Determinar estado general
    if sla_promedio >= 90:
        estado_general = "EXCELENTE"
        color_estado = colors.HexColor("#06D6A0")
    elif sla_promedio >= 75:
        estado_general = "BUENO"
        color_estado = colors.HexColor("#FFD166")
    elif sla_promedio >= 60:
        estado_general = "ACEPTABLE"
        color_estado = colors.HexColor("#FF9F1C")
    else:
        estado_general = "CRITICO"
        color_estado = colors.HexColor("#EF476F")
    
    resumen_ejecutivo = f"""
    <b>Estado General del SLA: {estado_general} ({sla_promedio:.1f}%)</b><br/>
    <br/>
    Durante el periodo analizado se gestionaron <b>{total_asignados} casos</b> en total. 
    De estos, <b>{total_resueltos} casos fueron resueltos</b> ({tasa_resol:.1f}% de resolucion), 
    mientras que <b>{abiertos} casos permanecen abiertos</b>.<br/>
    <br/>
    Del total de casos resueltos, <b>{cumplidos} cumplieron con el SLA</b> establecido 
    ({(cumplidos/total_resueltos*100 if total_resueltos>0 else 0):.1f}%), y <b>{total_tardios} casos 
    se resolvieron fuera del tiempo esperado</b> ({(total_tardios/total_resueltos*100 if total_resueltos>0 else 0):.1f}%).
    """
    
    story.append(Paragraph(resumen_ejecutivo, normal_style))
    story.append(Spacer(1, 0.15*inch))
    
    # Tabla de métricas principales
    metricas_data = [
        ["INDICADOR", "VALOR", "PORCENTAJE"],
        ["Total de casos asignados", str(total_asignados), "100%"],
        ["Casos resueltos", str(total_resueltos), f"{tasa_resol:.1f}%"],
        ["Casos abiertos", str(abiertos), f"{(abiertos/total_asignados*100 if total_asignados>0 else 0):.1f}%"],
        ["Casos cumplidos (dentro SLA)", str(cumplidos), f"{(cumplidos/total_resueltos*100 if total_resueltos>0 else 0):.1f}%"],
        ["Casos tardios (fuera SLA)", str(total_tardios), f"{(total_tardios/total_resueltos*100 if total_resueltos>0 else 0):.1f}%"],
        ["SLA PROMEDIO GLOBAL", f"{sla_promedio:.2f}%", estado_general],
    ]
    
    metricas_table = Table(metricas_data, colWidths=[2.5*inch, 1.3*inch, 1.3*inch])
    metricas_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#3A86FF")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('BACKGROUND', (0,6), (-1,6), color_estado),
        ('TEXTCOLOR', (0,6), (-1,6), colors.white),
        ('FONTNAME', (0,6), (-1,6), 'Helvetica-Bold'),
        ('FONTSIZE', (0,6), (-1,6), 11),
    ]))
    story.append(metricas_table)
    
    # ==================
    # DESGLOSE POR TÉCNICO
    # ==================
    story.append(PageBreak())
    story.append(Paragraph("2. DESGLOSE DETALLADO POR TECNICO", heading1_style))
    
    if filtro_tec:
        tecnicos_data = resumen[resumen[col_tec] == filtro_tec].copy()
    else:
        tecnicos_data = resumen.copy()
        
    tecnicos_data = tecnicos_data.sort_values("SLA (%)", ascending=False)
    
    table_data = [["TECNICO", "ASIGNADOS", "RESUELTOS", "TARDIOS", "SLA (%)"]]
    
    for _, row in tecnicos_data.iterrows():
        sla_val = row["SLA (%)"]
        if sla_val >= 90: color_sla = colors.HexColor("#06D6A0") # Verde
        elif sla_val >= 70: color_sla = colors.HexColor("#FFD166") # Amarillo
        else: color_sla = colors.HexColor("#EF476F") # Rojo
        
        table_data.append([
            str(row[col_tec]),
            str(int(row["Asignados"])),
            str(int(row["Resueltos"])),
            str(int(row["Tardíos"])),
            f"{sla_val:.1f}%"
        ])
        
    t_tec = Table(table_data, colWidths=[3*inch, 1*inch, 1*inch, 1*inch, 1*inch])
    t_tec.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E1E1E")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('ALIGN', (1,0), (-1,-1), 'CENTER'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.whitesmoke, colors.white]),
    ]))
    
    story.append(t_tec)
    
    # ==================
    # LISTADO DE CASOS TARDÍOS
    # ==================
    story.append(Paragraph("3. LISTADO DE CASOS FUERA DE SLA (TARDIOS)", heading1_style))
    
    tardios_df = df_completo[df_completo["Es Tardío"] == True].copy()
    if filtro_tec:
        tardios_df = tardios_df[tardios_df[col_tec] == filtro_tec]
        
    if not tardios_df.empty:
        story.append(Paragraph(f"Se encontraron {len(tardios_df)} casos fuera del SLA en el periodo.", normal_style))
        story.append(Spacer(1, 0.1*inch))
        
        casos_data = [["ID", "TECNICO", "FECHA APERTURA", "FECHA CIERRE", "ESTADO"]]
        
        for _, row in tardios_df.head(100).iterrows(): # Limitamos a 100 para no explotar el PDF
            f_ap = row["Fecha Apertura (Bogotá)"].strftime("%d/%m %H:%M") if pd.notna(row["Fecha Apertura (Bogotá)"]) else "-"
            f_ci = row["Fecha Cierre (Bogotá)"].strftime("%d/%m %H:%M") if pd.notna(row["Fecha Cierre (Bogotá)"]) else "Abierto"
            
            casos_data.append([
                str(row["ID"]),
                str(row[col_tec])[:20], # Truncar nombre largo
                f_ap,
                f_ci,
                "TARDIO"
            ])
            
        t_casos = Table(casos_data, colWidths=[0.8*inch, 2*inch, 1.2*inch, 1.2*inch, 1.2*inch])
        t_casos.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#EF476F")),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('FONTSIZE', (0,0), (-1,-1), 8),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ]))
        story.append(t_casos)
        
        if len(tardios_df) > 100:
            story.append(Paragraph(f"... y {len(tardios_df)-100} casos más no listados.", normal_style))
    else:
        story.append(Paragraph("¡Felicitaciones! No se encontraron casos tardíos en este reporte.", normal_style))

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()


# INTERFAZ PRINCIPAL
if not is_tv:
    st.markdown("<h1 style='text-align: center; color: #3A86FF;'>📊 Tablero de Control SLA - IPS Goleman</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #888;'>Analisis inteligente de tiempos de respuesta y solucion</p>", unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader("📂 Cargar archivo CSV de GLPI", type=["csv"])
    
    if not uploaded_file:
        st.info("👆 Por favor sube el archivo CSV exportado de GLPI para comenzar.")
        st.stop()
        
    try:
        df = pd.read_csv(uploaded_file, sep=";")
    except:
        try:
            df = pd.read_csv(uploaded_file, sep=",")
        except:
            st.error("Error leyendo el archivo. Asegurate que sea un CSV valido (separado por ; o ,).")
            st.stop()
            
    df_procesado = procesar_datos(df, OFFSET_HOURS)
    
    st.sidebar.header("⚙️ Configuracion")
    offset_ui = st.sidebar.slider("Ajuste Horario (Horas)", 0, 10, int(OFFSET_HOURS))
    now_bogota = datetime.now(ZoneInfo("America/Bogota"))
    st.sidebar.markdown(f"**Hora actual:** {now_bogota.strftime('%H:%M:%S')}")
    
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
    c1, c2, c3, c4, c5 = st.columns(5)
    
    total_casos = len(df_filtrado)
    total_asignados = int(resumen["Asignados"].sum())
    total_resueltos = int(resumen["Resueltos"].sum())
    total_tardios = int(resumen["Tardíos"].sum())
    sla_promedio = resumen["SLA (%)"].mean() if not resumen.empty else 0.0
    
    c1.markdown(f"<div class='metric-card'><div class='metric-value'>{total_casos}</div><div class='metric-label'>Total Casos</div></div>", unsafe_allow_html=True)
    c2.markdown(f"<div class='metric-card'><div class='metric-value'>{total_asignados}</div><div class='metric-label'>Casos Asignados</div></div>", unsafe_allow_html=True)
    c3.markdown(f"<div class='metric-card'><div class='metric-value'>{total_resueltos}</div><div class='metric-label'>Casos Resueltos</div></div>", unsafe_allow_html=True)
    c4.markdown(f"<div class='metric-card'><div class='metric-value'>{total_tardios}</div><div class='metric-label'>Casos Tardios</div></div>", unsafe_allow_html=True)
    c5.markdown(f"<div class='metric-card'><div class='metric-value'>{sla_promedio:.1f}%</div><div class='metric-label'>SLA Promedio</div></div>", unsafe_allow_html=True)
    
    st.subheader("📋 Resumen por Tecnico")
    
    st.dataframe(
        resumen,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Asignados": st.column_config.NumberColumn("Asignados", format="%d"),
            "Resueltos": st.column_config.NumberColumn("Resueltos", format="%d"),
            "Tardíos": st.column_config.NumberColumn("Tardíos", format="%d"),
            "SLA (%)": st.column_config.NumberColumn("SLA (%)", format="%.1f%%"),
        }
    )
    
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
    dias_semana = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]
    df_display["Cierre (día y hora)"] = df_filtrado["Fecha Cierre (Bogotá)"].apply(
        lambda x: "Sin cerrar" if pd.isna(x) else f"{dias_semana[x.weekday()]} {x.strftime('%d/%m/%Y %H:%M')}"
    )
    
    cols_mostrar = ["ID", "Título", "Estados", col_tec, "Prioridad", 
                    "Fecha Apertura (Bogotá)", "Fecha Cierre (Bogotá)", "Cierre (día y hora)",
                    "Estado SLA"]
    
    def highlight_tardios(row):
        if "Tardío" in str(row["Estado SLA"]):
            return ['background-color: #8B0000; color: white; font-weight: bold'] * len(row)
        return [''] * len(row)
    
    fmt_fecha = lambda x: x.strftime("%d/%m/%Y %H:%M") if not pd.isna(x) else "-"
    format_map = {
        "Fecha Apertura (Bogotá)": fmt_fecha,
        "Fecha Cierre (Bogotá)": (lambda x: x if isinstance(x, str) else (x.strftime("%d/%m/%Y %H:%M") if not pd.isna(x) else "-")),
    }
    styled = df_display[cols_mostrar].style.format(format_map, na_rep="-").apply(highlight_tardios, axis=1)
    st.dataframe(styled, use_container_width=True, hide_index=True)
    
    st.markdown("<hr>", unsafe_allow_html=True)
    
    st.subheader("📥 Descargar Reporte PDF")
    
    try:
        pdf_data = generar_pdf_mejorado(resumen, df_filtrado, col_tec, tec_seleccionado, offset_ui)
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
    # Botón flotante para pantalla completa (Versión Mejorada JS)
    st.markdown("""
    <style>
    .fullscreen-btn {
        position: fixed;
        bottom: 20px;
        right: 20px;
        z-index: 2147483647; /* Max Z-Index */
        background-color: rgba(58, 134, 255, 0.3);
        border: 2px solid #3A86FF;
        color: white;
        padding: 12px;
        border-radius: 50%;
        cursor: pointer;
        width: 60px;
        height: 60px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 30px;
        transition: all 0.3s ease;
        backdrop-filter: blur(4px);
        box-shadow: 0 4px 15px rgba(0,0,0,0.5);
    }
    .fullscreen-btn:hover {
        background-color: #3A86FF;
        transform: scale(1.1);
        box-shadow: 0 0 20px rgba(58, 134, 255, 0.6);
    }
    </style>
    
    <button onclick="toggleFullScreen()" class="fullscreen-btn" title="Pantalla Completa">⛶</button>
    
    <script>
    window.toggleFullScreen = function() {
        var doc = window.document;
        var docEl = doc.documentElement;

        var requestFullScreen = docEl.requestFullscreen || docEl.mozRequestFullScreen || docEl.webkitRequestFullScreen || docEl.msRequestFullscreen;
        var cancelFullScreen = doc.exitFullscreen || doc.mozCancelFullScreen || doc.webkitExitFullscreen || doc.msExitFullscreen;

        if(!doc.fullscreenElement && !doc.mozFullScreenElement && !doc.webkitFullscreenElement && !doc.msFullscreenElement) {
            if (requestFullScreen) {
                requestFullScreen.call(docEl);
            }
        } else {
            if (cancelFullScreen) {
                cancelFullScreen.call(doc);
            }
        }
    };
    </script>
    """, unsafe_allow_html=True)

    uploaded = st.file_uploader("📎 CSV", type=["csv"], key="tv_upload", label_visibility="collapsed")
    if not uploaded:
        st.markdown("<div style='text-align:center;padding:100px;'><h1 style='color:#3A86FF;'>📺 PANEL TV</h1><p style='color:#AAA;'>Esperando archivo...</p></div>", unsafe_allow_html=True)
        st.stop()
    
    df = pd.read_csv(uploaded, sep=";")
    df_procesado = procesar_datos(df, OFFSET_HOURS)
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
    
    # Usar un placeholder para actualizar el contenido dinámicamente
    content_placeholder = st.empty()
    
    with content_placeholder.container():
        if idx == total:
            # VISTA GLOBAL
            st.markdown(f"<h1 style='text-align:center;color:#3A86FF;'>RESUMEN GLOBAL</h1><p style='text-align:center;color:#888;'>{hora.strftime('%d/%m/%Y %H:%M:%S')}</p>", unsafe_allow_html=True)
            
            sla_g = resumen["SLA (%)"].mean()
            color = "#06D6A0" if sla_g >= 90 else "#FFD166" if sla_g >= 70 else "#EF476F"
            
            st.markdown(f"<div style='text-align:center;padding:50px;'><div style='color:{color};font-size:140px;font-weight:900;'>{sla_g:.1f}%</div></div>", unsafe_allow_html=True)
            
            for i, row in tecnicos.iterrows():
                sla = row["SLA (%)"]
                c = "#06D6A0" if sla >= 90 else "#FFD166" if sla >= 70 else "#EF476F"
                medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"#{i+1}"
                st.markdown(f"<div style='background:#1A1A1A;padding:20px;margin:10px;border-left:4px solid {c};'><span style='font-size:24px;'>{medal} {row['Asignado a - Técnico']}</span><span style='float:right;color:{c};font-size:28px;font-weight:900;'>{sla:.1f}%</span></div>", unsafe_allow_html=True)
        else:
            # VISTA INDIVIDUAL
            tec = tecnicos.iloc[idx]
            sla = tec["SLA (%)"]
            color = "#06D6A0" if sla >= 90 else "#FFD166" if sla >= 70 else "#EF476F"
            
            st.markdown(f"<h1 style='text-align:center;color:#FFF;font-size:48px;'>{tec['Asignado a - Técnico']}</h1><p style='text-align:center;color:#888;font-size:18px;'>Posicion #{idx+1} de {total} | {hora.strftime('%H:%M:%S')}</p>", unsafe_allow_html=True)
            st.markdown(f"<div style='text-align:center;padding:60px;background:#1A1A1A;border:3px solid {color};border-radius:20px;margin:30px;'><div style='color:#888;font-size:28px;margin-bottom:20px;'>CUMPLIMIENTO SLA</div><div style='color:{color};font-size:180px;font-weight:900;line-height:1;'>{sla:.1f}%</div></div>", unsafe_allow_html=True)
            
            col1, col2, col3 = st.columns(3)
            col1.markdown(f"<div style='text-align:center;padding:35px;background:#1A1A1A;border-radius:10px;border-top:4px solid #3A86FF;'><div style='color:#888;font-size:16px;margin-bottom:15px;'>ASIGNADOS</div><div style='color:#3A86FF;font-size:64px;font-weight:700;'>{int(tec['Asignados'])}</div></div>", unsafe_allow_html=True)
            col2.markdown(f"<div style='text-align:center;padding:35px;background:#1A1A1A;border-radius:10px;border-top:4px solid #06D6A0;'><div style='color:#888;font-size:16px;margin-bottom:15px;'>RESUELTOS</div><div style='color:#06D6A0;font-size:64px;font-weight:700;'>{int(tec['Resueltos'])}</div></div>", unsafe_allow_html=True)
            col3.markdown(f"<div style='text-align:center;padding:35px;background:#1A1A1A;border-radius:10px;border-top:4px solid #EF476F;'><div style='color:#888;font-size:16px;margin-bottom:15px;'>TARDÍOS</div><div style='color:#EF476F;font-size:64px;font-weight:700;'>{int(tec['Tardíos'])}</div></div>", unsafe_allow_html=True)
    
    time_module.sleep(5)
    st.session_state.tv_index += 1
    st.rerun()
