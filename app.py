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
    if pd.isna(priority):
        return 8.0
    
    priority_norm = norm(priority)
    
    # Orden de verificación: de más específico a menos específico
    if "muy baja" in priority_norm or "muybaja" in priority_norm:
        return 2/60  # 2 minutos
    elif "muy alta" in priority_norm or "muyalta" in priority_norm:
        return 4
    elif "alta" in priority_norm:
        return 8
    elif "media" in priority_norm:
        return 16
    elif "baja" in priority_norm:
        return 32
    
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
    
    # Para casos resueltos, usar "Última modificación" como fecha de cierre real
    # Esto es cuando el técnico cerró el caso
    df["Fecha Cierre (Bogotá)"] = df.apply(
        lambda r: to_timestamp(r["Última modificación"]) if r["Resuelto"] else pd.NaT,
        axis=1
    )
    
    # IMPORTANTE: Para el cálculo de SLA, usar la fecha de cierre real
    # no la fecha límite teórica
    
    # Calcular horas hábiles transcurridas
    def calc_horas(row):
        if pd.isna(row["Fecha Apertura (Bogotá)"]):
            return 0.0
        
        # Para casos resueltos, usar fecha de cierre. Para abiertos, usar ahora
        if row["Resuelto"] and pd.notna(row["Fecha Cierre (Bogotá)"]):
            end_date = row["Fecha Cierre (Bogotá)"]
        else:
            end_date = datetime.now()
        
        return business_hours_between(row["Fecha Apertura (Bogotá)"], end_date)
    
    df["Horas Hábiles"] = df.apply(calc_horas, axis=1)
    
    # Agregar columna de minutos para facilitar lectura (especialmente para SLA muy cortos)
    df["Minutos Hábiles"] = df["Horas Hábiles"] * 60
    
    # Límite SLA según prioridad
    df["SLA Límite (h)"] = df["Prioridad"].apply(get_sla_hours)
    df["SLA Límite (min)"] = df["SLA Límite (h)"] * 60
    
    # Estado del SLA - CORREGIDO para detectar correctamente tardíos
    def estado_sla(row):
        if not row["Resuelto"]:
            # Caso abierto: verificar si ya superó el SLA
            if row["Horas Hábiles"] > row["SLA Límite (h)"]:
                return "⏰ Abierto (Tardío)"
            return "🟢 Abierto"
        else:
            # Caso cerrado: comparar tiempo real vs límite
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
    st.caption("IPS Goleman - Inteligencia para el Soporte")
    st.markdown("<hr>", unsafe_allow_html=True)
    
    # RELOJES
    st.subheader("🕐 Sincronización Horaria")
    now_bogota = datetime.now(ZoneInfo("America/Bogota"))
    now_servidor = now_bogota + timedelta(hours=OFFSET_HOURS)
    
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        st.markdown(f"""
        <div class='clock-card'>
            <div class='clock-label'>🇨🇴 HORA BOGOTÁ</div>
            <div class='clock-value'>{now_bogota.strftime('%H:%M:%S')}</div>
            <div style='color:#AAA;font-size:11px;'>{now_bogota.strftime('%d/%m/%Y')}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class='clock-card'>
            <div class='clock-label'>🖥️ HORA SERVIDOR GIA</div>
            <div class='clock-value'>{now_servidor.strftime('%H:%M:%S')}</div>
            <div style='color:#AAA;font-size:11px;'>{now_servidor.strftime('%d/%m/%Y')}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class='clock-card'>
            <div class='clock-label'>⚙️ DESFASE</div>
            <div class='clock-value'>+{OFFSET_HOURS:.0f}h</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("<hr>", unsafe_allow_html=True)
    
    # SUBIR ARCHIVO
    uploaded = st.file_uploader("📎 Subir reporte de GIA (CSV)", type=["csv"])
    
    if not uploaded:
        st.info("📌 Sube el archivo CSV exportado desde GIA para comenzar el análisis.")
        st.stop()
    
    # Leer CSV con separador correcto
    try:
        df = pd.read_csv(uploaded, sep=";", encoding="utf-8")
    except:
        try:
            df = pd.read_csv(uploaded, sep=",", encoding="utf-8")
        except Exception as e:
            st.error(f"Error al leer el archivo: {str(e)}")
            st.stop()
    
    # Verificar columnas necesarias
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
    solo_uno = st.checkbox("Consultar un solo técnico", value=False)
    
    col_tec = "Asignado a - Técnico"
    tec_seleccionado = None
    
    if solo_uno:
        tecnicos = sorted([t for t in df_procesado[col_tec].dropna().unique() if str(t).strip()])
        if tecnicos:
            tec_seleccionado = st.selectbox("👤 Seleccionar técnico", tecnicos)
            df_filtrado = df_procesado[df_procesado[col_tec] == tec_seleccionado].copy()
        else:
            st.warning("No hay técnicos en los datos.")
            df_filtrado = df_procesado.copy()
    else:
        df_filtrado = df_procesado.copy()
    
    # GENERAR RESUMEN
    resumen = generar_resumen(df_filtrado, col_tec)
    
    # KPIs
    st.subheader("📊 Métricas Generales")
    c1, c2, c3, c4 = st.columns(4)
    
    total_asignados = int(resumen["Asignados"].sum())
    total_resueltos = int(resumen["Resueltos"].sum())
    total_tardios = int(resumen["Tardíos"].sum())
    sla_promedio = resumen["SLA (%)"].mean() if not resumen.empty else 0.0
    
    c1.markdown(f"<div class='metric-card'><div class='metric-value'>{total_asignados}</div><div class='metric-label'>Casos Asignados</div></div>", unsafe_allow_html=True)
    c2.markdown(f"<div class='metric-card'><div class='metric-value'>{total_resueltos}</div><div class='metric-label'>Casos Resueltos</div></div>", unsafe_allow_html=True)
    c3.markdown(f"<div class='metric-card'><div class='metric-value'>{total_tardios}</div><div class='metric-label'>Casos Tardíos</div></div>", unsafe_allow_html=True)
    c4.markdown(f"<div class='metric-card'><div class='metric-value'>{sla_promedio:.1f}%</div><div class='metric-label'>SLA Promedio</div></div>", unsafe_allow_html=True)
    
    # TABLA RESUMEN
    st.subheader("📋 Resumen por Técnico")
    st.dataframe(resumen, use_container_width=True, hide_index=True)
    
    # GRÁFICO BARRAS
    st.subheader("📈 Cumplimiento SLA por Técnico")
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
    
    # GRÁFICO PIE
    st.subheader("🥧 Distribución de Casos Cerrados")
    cerrados = df_filtrado[df_filtrado["Resuelto"] == True]
    if not cerrados.empty:
        cumplidos = (cerrados["Estado SLA"] == "✅ Cumplido").sum()
        tardios = (cerrados["Estado SLA"] == "❌ Tardío").sum()
        
        fig_pie = px.pie(
            pd.DataFrame({"Estado": ["Cumplido", "Tardío"], "Cantidad": [cumplidos, tardios]}),
            names="Estado", values="Cantidad",
            color="Estado",
            color_discrete_map={"Cumplido": "#06D6A0", "Tardío": "#EF476F"}
        )
        fig_pie.update_layout(template="plotly_dark")
        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("No hay casos cerrados para mostrar.")
    
    # DETALLE DE CASOS
    st.subheader("📝 Detalle de Casos")
    
    # Preparar DataFrame para mostrar
    df_display = df_filtrado.copy()
    df_display["Fecha Cierre (Bogotá)"] = df_display["Fecha Cierre (Bogotá)"].apply(
        lambda x: "Sin cerrar" if pd.isna(x) else x
    )
    
    cols_mostrar = ["ID", "Título", "Estados", col_tec, "Prioridad", 
                    "Fecha Apertura (Bogotá)", "Fecha Cierre (Bogotá)",
                    "Minutos Hábiles", "SLA Límite (min)", "Estado SLA"]
    
    # Función para colorear filas tardías
    def highlight_tardios(row):
        if "Tardío" in str(row["Estado SLA"]):
            return ['background-color: #8B0000; color: white; font-weight: bold'] * len(row)
        return [''] * len(row)
    
    st.dataframe(
        df_display[cols_mostrar].style.apply(highlight_tardios, axis=1),
        use_container_width=True, 
        hide_index=True
    )
    
    # DESCARGAR PDF
    st.subheader("📥 Descargar Reporte")
    pdf_data = generar_pdf(resumen, col_tec, tec_seleccionado)
    timestamp = now_bogota.strftime("%Y%m%d_%H%M")
    st.download_button(
        label="📄 Descargar PDF",
        data=pdf_data,
        file_name=f"GIA_SLA_{timestamp}.pdf",
        mime="application/pdf"
    )

# =========================
# MODO TV
# =========================
else:
    st.markdown("<h1 style='text-align:center;color:#3A86FF;'>📺 GIA | Panel de Rendimiento</h1>", unsafe_allow_html=True)
    st.caption("IPS Goleman - Visualizacion en Tiempo Real")
    st.markdown("<hr>", unsafe_allow_html=True)
    
    uploaded = st.file_uploader("📎 Subir reporte CSV", type=["csv"])
    if not uploaded:
        st.info("Esperando archivo...")
        st.stop()
    
    df = pd.read_csv(uploaded, sep=";")
    df_procesado = procesar_datos(df)
    resumen = generar_resumen(df_procesado, "Asignado a - Técnico")
    
    fig = px.bar(
        resumen.sort_values("SLA (%)", ascending=True),
        x="SLA (%)", y="Asignado a - Técnico",
        orientation="h",
        color="SLA (%)",
        color_continuous_scale=["#EF476F", "#FFD166", "#06D6A0"],
        text_auto=".1f"
    )
    fig.update_layout(template="plotly_dark", height=600,
                     title_font=dict(size=26, color="#3A86FF"),
                     font=dict(size=16))
    st.plotly_chart(fig, use_container_width=True)
    
    sla_global = resumen["SLA (%)"].mean()
    hora = datetime.now(ZoneInfo("America/Bogota")).strftime("%H:%M:%S")
    st.markdown(f"<h2 style='text-align:center;color:#06D6A0;'>SLA Global: {sla_global:.1f}%</h2>", unsafe_allow_html=True)
    st.markdown(f"<p style='text-align:center;color:#AAA;'>Actualizado: {hora}</p>", unsafe_allow_html=True)
