import re
import pandas as pd
import streamlit as st
import plotly.express as px
from datetime import datetime
from io import BytesIO
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4

# ==============================
# CONFIG
# ==============================
st.set_page_config(page_title="GIA - Admin & Estadísticas", page_icon="🤖", layout="wide")
MAP_FILE = "asignaciones.csv"  # reglas Tipo → Técnico

# ==============================
# HELPERS
# ==============================
def load_mappings():
    try:
        df = pd.read_csv(MAP_FILE)
        if set(df.columns) != {"tipo_patron", "tecnico"}:
            raise ValueError
        return df
    except Exception:
        return pd.DataFrame(columns=["tipo_patron", "tecnico"])

def save_mappings(df):
    df.to_csv(MAP_FILE, index=False)

def clean_headers_and_read(uploaded):
    """Lee CSV/Excel robustamente, limpia encabezados, dupes y separador."""
    if uploaded.name.lower().endswith(".csv"):
        df = pd.read_csv(uploaded, sep=None, engine="python", on_bad_lines="skip", header=0)
    else:
        df = pd.read_excel(uploaded, header=0)

    # Forzar texto y unicidad de columnas
    cols = []
    seen = {}
    for c in df.columns.astype(str):
        c2 = (c or "").strip()
        if c2 == "":
            c2 = "columna_sin_nombre"
        if c2 in seen:
            seen[c2] += 1
            c2 = f"{c2}_{seen[c2]}"
        else:
            seen[c2] = 0
        cols.append(c2)
    df.columns = cols
    df = df.loc[:, ~df.columns.duplicated()].copy()
    df.columns = [c.lower() for c in df.columns]
    return df

def find_column(df, candidates):
    """Encuentra la primera columna cuyo nombre contenga cualquiera de los candidatos."""
    for c in df.columns:
        for key in candidates:
            if key in c:
                return c
    return None

def estado_buckets(estado_val):
    """Clasifica estado → abierto/resuelto/tardío (booleanos)."""
    if not isinstance(estado_val, str):
        estado_val = str(estado_val or "")
    s = estado_val.strip().lower()

    abiertos = {"abierto", "abiertos", "nuevo", "nueva", "en curso", "asignado", "pendiente", "en espera", "procesando", "planificado"}
    resueltos = {"resuelto", "cerrado", "solucionado", "finalizado", "completado"}
    tardios_keys = {"tard", "vencid", "late", "overdue", "fuera de plazo"}

    is_abierto = any(k in s for k in abiertos) and not any(k in s for k in resueltos)
    is_resuelto = any(k in s for k in resueltos)
    # tardío lo determinaremos con columna específica si existe; aquí solo heurística por estado:
    is_tardio = any(k in s for k in tardios_keys)
    return is_abierto, is_resuelto, is_tardio

def assign_tecnico_from_tipo(tipo_val, mappings_df):
    """Asigna técnico por patrones (regex/substring) definidos en admin."""
    txt = str(tipo_val or "").strip().lower()
    if mappings_df.empty or txt == "":
        return "— sin asignación —"
    for _, row in mappings_df.iterrows():
        patron = str(row["tipo_patron"] or "").strip()
        tecnico = str(row["tecnico"] or "").strip()
        if patron == "" or tecnico == "":
            continue
        # Coincidencia flexible: regex o substring (case-insensitive)
        try:
            if re.search(patron, txt, flags=re.IGNORECASE):
                return tecnico
        except re.error:
            if patron.lower() in txt:
                return tecnico
    return "— sin asignación —"

def generar_pdf_tabla(df_resumen, kpis):
    buffer = BytesIO()
    fecha = datetime.now().strftime("%Y-%m-%d")
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    title = ParagraphStyle('title', parent=styles['Title'], alignment=TA_CENTER, textColor=colors.HexColor("#3A86FF"))

    story = []
    story.append(Paragraph(f"Reporte GIA - Estadísticas por Técnico ({fecha})", title))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        f"Casos asignados (abiertos): {kpis['asignados']} | "
        f"Resueltos: {kpis['resueltos']} | "
        f"Tardíos: {kpis['tardios']} | "
        f"Eficiencia prom: {kpis['eficiencia_prom']:.2f}% | "
        f"Eficacia prom: {kpis['eficacia_prom']:.2f}%",
        styles["Normal"]
    ))
    story.append(Spacer(1, 10))

    data = [df_resumen.columns.tolist()] + df_resumen.values.tolist()
    tabla = Table(data, colWidths=[130, 90, 90, 90, 90, 90])
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#3A86FF")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.gray),
    ]))
    story.append(tabla)
    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf

# ==============================
# ESTILO
# ==============================
st.markdown("""
<style>
body {background-color:#0E1117; color:white;}
.badge { display:inline-block; padding:4px 10px; border-radius:999px; background:#23262F; border:1px solid #3A86FF55; font-size:12px; }
.metric-card { background:#1E1E1E; border:1px solid #3A86FF33; border-radius:12px; padding:14px; text-align:center; box-shadow:0 0 6px rgba(58,134,255,0.25); }
.metric-value { font-size:22px; font-weight:800; }
.metric-label { color:#FF9F1C; font-size:12px; }
hr {border:0; height:1px; background:#333; margin:18px 0;}
</style>
""", unsafe_allow_html=True)

st.markdown("<h2 style='color:#3A86FF'>🤖 GIA — Admin & Estadísticas por Técnico</h2>", unsafe_allow_html=True)
st.markdown("<div class='badge'>IPS Goleman | Inteligencia para el Soporte</div>", unsafe_allow_html=True)
st.markdown("<hr>", unsafe_allow_html=True)

panel = st.sidebar.radio("Selecciona panel", ["🛠️ Panel de Administración", "📊 Panel de Estadísticas"])

# ==============================
# PANEL ADMIN
# ==============================
if panel == "🛠️ Panel de Administración":
    st.subheader("🛠️ Reglas de asignación: Tipo de caso → Técnico")
    st.caption("Agrega patrones (palabras clave o expresiones regulares) que identifiquen el **tipo de caso** y el **técnico** al que debe asignarse.")

    maps_df = load_mappings()
    if not maps_df.empty:
        st.dataframe(maps_df, use_container_width=True)
    else:
        st.info("Aún no hay reglas. Crea la primera abajo.")

    with st.form("frm_mappings"):
        col1, col2 = st.columns(2)
        tipo_patron = col1.text_input("Patrón de tipo de caso (palabra o regex)", placeholder="p.ej. soporte|hardware|software|red|correo")
        tecnico = col2.text_input("Técnico asignado", placeholder="p.ej. Pablo Granados")
        submitted = st.form_submit_button("➕ Agregar regla")
    if submitted:
        if tipo_patron.strip() and tecnico.strip():
            maps_df = pd.concat([maps_df, pd.DataFrame([{"tipo_patron": tipo_patron.strip(), "tecnico": tecnico.strip()}])], ignore_index=True)
            save_mappings(maps_df)
            st.success("✅ Regla agregada.")
        else:
            st.warning("Completa ambos campos.")

    if not maps_df.empty:
        st.markdown("---")
        st.subheader("🧹 Limpiar / Editar")
        if st.button("🗑️ Borrar todas las reglas"):
            save_mappings(pd.DataFrame(columns=["tipo_patron", "tecnico"]))
            st.warning("Se eliminaron todas las reglas.")

# ==============================
# PANEL ESTADÍSTICO
# ==============================
if panel == "📊 Panel de Estadísticas":
    st.subheader("📊 Generar estadísticas desde reporte GLPI (detalle de casos)")
    st.caption("Sube el archivo exportado de GLPI (CSV o XLSX). La app asignará cada caso al técnico según tus reglas del Panel de Administración.")

    up = st.file_uploader("📁 Subir reporte GLPI (detalle de tickets)", type=["csv", "xlsx"])
    if up is None:
        st.info("Sube un archivo para continuar.")
    else:
        try:
            df = clean_headers_and_read(up)

            # Detectar columnas clave del reporte GLPI
            col_tipo   = find_column(df, ["tipo", "categor", "category"])
            col_estado = find_column(df, ["estado", "status"])
            col_tardio = find_column(df, ["tard", "vencid", "overdue", "sla"])

            if col_tipo is None:
                st.error("No encontré una columna de **Tipo** en el reporte (busqué: tipo, categoría, category). Exporta el reporte detallado con esa columna.")
                st.stop()
            if col_estado is None:
                st.error("No encontré una columna de **Estado** (busqué: estado, status). Exporta el reporte detallado con estados.")
                st.stop()

            # Cargar reglas admin
            maps_df = load_mappings()
            if maps_df.empty:
                st.warning("No hay reglas de asignación aún. Ve al Panel de Administración y agrega al menos una (Tipo → Técnico).")
                st.stop()

            # Asignar técnico por tipo
            df["__Tecnico__"] = df[col_tipo].apply(lambda v: assign_tecnico_from_tipo(v, maps_df))

            # Construir flags
            abiertos = []
            resueltos = []
            tardios_flag = []
            for _, row in df.iterrows():
                ab, re, ta = estado_buckets(row[col_estado])
                # Si hay columna específica de tardío/SLA vencido, úsala antes que la heurística
                if col_tardio:
                    val = str(row[col_tardio]).strip().lower()
                    ta = any(k in val for k in ["tard", "vencid", "overdue", "fuera de plazo"])
                abiertos.append(1 if ab else 0)
                resueltos.append(1 if re else 0)
                tardios_flag.append(1 if ta else 0)

            df["__abiertos__"]  = abiertos
            df["__resueltos__"] = resueltos
            df["__tardios__"]   = tardios_flag

            # Agregación por técnico asignado desde admin
            resumen = df.groupby("__Tecnico__", dropna=False)[["__abiertos__", "__resueltos__", "__tardios__"]].sum().reset_index()
            resumen = resumen.rename(columns={
                "__Tecnico__": "Técnico",
                "__abiertos__": "Casos asignados (abiertos)",
                "__resueltos__": "Casos resueltos",
                "__tardios__": "Casos tardíos"
            })

            # KPIs
            resumen["Eficiencia (%)"] = (resumen["Casos resueltos"] / (resumen["Casos asignados (abiertos)"] + 1e-9)) * 100
            resumen["Eficacia (%)"]   = ((resumen["Casos resueltos"] - resumen["Casos tardíos"]) / (resumen["Casos asignados (abiertos)"] + 1e-9)) * 100

            asignados_tot = int(resumen["Casos asignados (abiertos)"].sum())
            resueltos_tot = int(resumen["Casos resueltos"].sum())
            tardios_tot   = int(resumen["Casos tardíos"].sum())
            eficiencia_prom = float(resumen["Eficiencia (%)"].mean())
            eficacia_prom   = float(resumen["Eficacia (%)"].mean())

            # Métricas
            c1, c2, c3, c4 = st.columns(4)
            c1.markdown(f"<div class='metric-card'><div class='metric-value'>{asignados_tot}</div><div class='metric-label'>Asignados (abiertos)</div></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='metric-card'><div class='metric-value'>{resueltos_tot}</div><div class='metric-label'>Resueltos</div></div>", unsafe_allow_html=True)
            c3.markdown(f"<div class='metric-card'><div class='metric-value'>{tardios_tot}</div><div class='metric-label'>Tardíos</div></div>", unsafe_allow_html=True)
            c4.markdown(f"<div class='metric-card'><div class='metric-value'>{eficiencia_prom:.2f}%</div><div class='metric-label'>Eficiencia Prom.</div></div>", unsafe_allow_html=True)
            st.markdown("<hr>", unsafe_allow_html=True)

            # Tabla
            st.dataframe(resumen, use_container_width=True)

            # Gráficos
            st.markdown("### 📊 Casos por técnico")
            fig1 = px.bar(
                resumen,
                x="Técnico",
                y=["Casos asignados (abiertos)", "Casos resueltos", "Casos tardíos"],
                barmode="group",
                color_discrete_sequence=["#3A86FF", "#06D6A0", "#EF476F"]
            )
            st.plotly_chart(fig1, use_container_width=True)

            st.markdown("### 🎯 Eficiencia y eficacia por técnico")
            fig2 = px.bar(
                resumen,
                x="Técnico",
                y=["Eficiencia (%)", "Eficacia (%)"],
                barmode="group",
                color_discrete_sequence=["#FFD166", "#118AB2"]
            )
            st.plotly_chart(fig2, use_container_width=True)

            # PDF
            pdf = generar_pdf_tabla(
                resumen[["Técnico", "Casos asignados (abiertos)", "Casos resueltos", "Casos tardíos", "Eficiencia (%)", "Eficacia (%)"]],
                {
                    "asignados": asignados_tot,
                    "resueltos": resueltos_tot,
                    "tardios": tardios_tot,
                    "eficiencia_prom": eficiencia_prom,
                    "eficacia_prom": eficacia_prom
                }
            )
            st.download_button("📄 Descargar Reporte PDF", pdf, file_name="reporte_gia_por_tecnico.pdf")

        except Exception as e:
            st.error(f"❌ Error al procesar: {e}")
