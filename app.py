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

# =========================
# CONFIGURACIÓN GLOBAL
# =========================
st.set_page_config(page_title="GIA - SLA Inteligente", page_icon="🤖", layout="wide")

# Detectar modo TV
try:
    is_tv = "tv" in st.query_params and st.query_params.get("tv") in ("1", "true", "True")
except Exception:
    is_tv = False

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
    "muy alta": 4,      # 4 horas
    "alta": 8,          # 8 horas (1 día)
    "media": 16,        # 2 días hábiles
    "baja": 32          # 4 días hábiles
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
        # Intenta parsear con diferentes formatos
        dt = pd.to_datetime(fecha_str, errors='coerce', dayfirst=True)
        if pd.isna(dt):
            return pd.NaT
        # Restar offset para llevar a hora Bogotá
        return dt - timedelta(hours=offset_hours)
    except:
        return pd.NaT

def business_hours_between(start: datetime, end: datetime) -> float:
    """Calcula horas hábiles entre dos fechas según WORK_SCHEDULE"""
    if pd.isna(start) or pd.isna(end) or end <= start:
        return 0.0
    
    total_seconds = 0.0
    current = start
    max_days = 400  # Límite de seguridad
    
    for _ in range(max_days):
        current_date = current.date()
        weekday = current.weekday()
        
        # Si no hay horario laboral ese día, saltar al siguiente
        if weekday not in WORK_SCHEDULE or not WORK_SCHEDULE[weekday]:
            next_day = datetime.combine(current_date + timedelta(days=1), time(0, 0))
            if next_day >= end:
                break
            current = next_day
            continue
        
        # Procesar cada bloque horario del día
        for (start_time, end_time) in WORK_SCHEDULE[weekday]:
            block_start = datetime.combine(current_date, start_time)
            block_end = datetime.combine(current_date, end_time)
            
            # Intersección del bloque con el rango [current, end]
            actual_start = max(current, block_start)
            actual_end = min(end, block_end)
            
            if actual_end > actual_start:
                total_seconds += (actual_end - actual_start).total_seconds()
        
        # Avanzar al siguiente día
        next_day = datetime.combine(current_date + timedelta(days=1), time(0, 0))
        if next_day >= end:
            break
        current = next_day
    
    return total_seconds / 3600.0  # Convertir a horas

def get_sla_hours(priority: str) -> float:
    """Retorna las horas SLA según la prioridad"""
    priority_norm = norm(priority)
    for key, hours in SLA_HOURS.items():
        if key in priority_norm:
            return hours
    return 8.0  # Por defecto: 8 horas

def is_resolved(estado: str) -> bool:
    """Determina si un caso está resuelto según su estado"""
    estado_norm = norm(estado)
    return "resuel" in estado_norm or "cerr" in estado_norm or "solucion" in estado_norm

# =========================
# PROCESAMIENTO PRINCIPAL
# =========================
def procesar_datos(df: pd.DataFrame):
    """Procesa el DataFrame y calcula todas las métricas SLA"""
    
    # Convertir fechas a Bogotá
    df["Fecha Apertura (Bogotá)"] = df["Fecha de apertura"].apply(to_timestamp)
    
    # Determinar si está resuelto
    df["Resuelto"] = df["Estados"].apply(is_resolved)
    
    # Para casos resueltos, usar "Última modificación" como fecha de cierre
    df["Fecha Cierre (Bogotá)"] = df.apply(
        lambda r: to_timestamp(r["Última modificación"]) if r["Resuelto"] else pd.NaT,
        axis=1
    )
    
    # Calcular horas hábiles transcurridas
    def calc_horas(row):
        if pd.isna(row["Fecha Apertura (Bogotá)"]):
            return 0.0
        
        end_date = row["Fecha Cierre (Bogotá)"] if row["Resuelto"] else datetime.now()
        return business_hours_between(row["Fecha Apertura (Bogotá)"], end_date)
    
    df["Horas Hábiles"] = df.apply(calc_horas, axis=1)
    
    # Límite SLA según prioridad
    df["SLA Límite (h)"] = df["Prioridad"].apply(get_sla_hours)
    
    # Estado del SLA
    def estado_sla(row):
        if not row["Resuelto"]:
            # Caso abierto: verificar si ya superó el SLA
            if row["Horas Hábiles"] > row["SLA Límite (h)"]:
                return "⏰ Abierto (Tardío)"
            return "🟢 Abierto"
        else:
            # Caso cerrado
            if row["Horas Hábiles"] <= row["SLA Límite (h)"]:
                return "✅ Cumplido"
            return "❌ Tardío"
    
    df["Estado SLA"] = df.apply(estado_sla, axis=1)
    
    # Clasificación para análisis
    df["Es Tardío"] = df["Estado SLA"].str.contains("Tardío")
    
    return df

def generar_resumen(df: pd.DataFrame, col_tecnico: str) -> pd.DataFrame:
    """Genera resumen por técnico"""
    
    resumen = df.groupby(col_tecnico).agg(
        Asignados=("ID", "count"),
        Resueltos=("Resuelto", "sum"),
        Tardíos=("Es Tardío", "sum")
    ).reset_index()
    
    # Calcular SLA% correctamente
    # SLA% = (Resueltos que cumplieron SLA / Total Resueltos) * 100
    def calc_sla_pct(row):
        if row["Resueltos"] == 0:
            return 0.0
        cumplidos = row["Resueltos"] - row["Tardíos"]
        return (cumplidos / row["Resueltos"]) * 100
    
    resumen["SLA (%)"] = resumen.apply(calc_sla_pct, axis=1)
    
    return resumen

def generar_pdf(resumen: pd.DataFrame, col_tec: str, filtro_tec: str = None):
    """Genera reporte PDF"""
    buf = BytesIO()
    fecha = datetime.now(ZoneInfo("America/Bogota")).strftime("%d/%m/%Y – %H:%M")
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=30, bottomMargin=20)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('t', parent=styles['Title'], alignment=TA_CENTER, 
                                 textColor=colors.HexColor("#3A86FF"))
    
    story = []
    story.append(Paragraph("GIA – Reporte de SLA", title_style))
    story.append(Paragraph(f"Generado: {fecha} (Bogotá)", styles["Normal"]))
    if filtro_tec:
        story.append(Paragraph(f"Técnico: <b>{filtro_tec}</b>", styles["Normal"]))
    story.append(Spacer(1, 12))
    
    # Tabla
    data = [["Técnico", "Asignados", "Resueltos", "Tardíos", "SLA (%)"]]
    for _, row in resumen.iterrows():
        data.append([
            str(row[col_tec]),
            int(row["Asignados"]),
            int(row["Resueltos"]),
            int(row["Tardíos"]),
            f"{row['SLA (%)']:.1f}%"
        ])
    
    tabla = Table(data, colWidths=[120, 70, 70, 70, 70])
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#3A86FF")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey)
    ]))
    story.append(tabla)
    
    doc.build(story)
    return buf.getvalue()

# =========================
# INTERFAZ PRINCIPAL
# =========================
if not is_tv:
    st.markdown("<h2 style='color:#3A86FF'>🤖 GIA — Análisis de SLA</h2>", unsafe_allow_html=True)
    st.caption("IPS Goleman | Inteligencia para
