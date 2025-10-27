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
import unicodedata

# ==============================
# CONFIG
# ==============================
st.set_page_config(page_title="GIA - Comparador GLPI por Categoría", page_icon="🤖", layout="wide")
THEME = """
<style>
body {background:#0E1117; color:white;}
.badge { display:inline-block; padding:4px 10px; border-radius:999px; background:#23262F; border:1px solid #3A86FF55; font-size:12px; }
.metric-card { background:#1E1E1E; border:1px solid #3A86FF33; border-radius:12px; padding:14px; text-align:center; box-shadow:0 0 6px rgba(58,134,255,0.25); }
.metric-value { font-size:22px; font-weight:800; }
.metric-label { color:#FF9F1C; font-size:12px; }
hr {border:0; height:1px; background:#333; margin:18px 0;}
</style>
"""
st.markdown(THEME, unsafe_allow_html=True)
st.markdown("<h2 style='color:#3A86FF'>🤖 GIA — Comparador de Reportes GLPI por Categoría</h2>", unsafe_allow_html=True)
st.markdown("<div class='badge'>IPS Goleman | Inteligencia para el Soporte</div>", unsafe_allow_html=True)
st.markdown("<hr>", unsafe_allow_html=True)

# ==============================
# HELPERS
# ==============================
def strip_accents(s: str) -> str:
    if s is None:
        return ""
    s = str(s)
    return "".join(ch for ch in unicodedata.normalize("NFD", s) if unicodedata.category(ch) != "Mn")

def norm_txt(s: str) -> str:
    s = strip_accents(s).lower().strip()
    # normalizar espacios y separadores raros
    s = " ".join(s.split())
    return s

def read_csv_forgiving(file):
    # detecta separador/encodings, soporta csv sin encabezado
    for enc in ("utf-8", "latin-1", "utf-16"):
        try:
            df = pd.read_csv(file, sep=None, engine="python", on_bad_lines="skip", encoding=enc)
            break
        except Exception:
            df = None
    if df is None:
        # sin encabezado
        for enc in ("utf-8", "latin-1", "utf-16"):
            try:
                df = pd.read_csv(file, header=None, sep=None, engine="python", on_bad_lines="skip", encoding=enc)
                break
            except Exception:
                df = None
    if df is None:
        raise ValueError("No se pudo leer el CSV (encoding/separador).")
    # si parece no tener encabezado, nombrear columnas
    if any(str(c).startswith("Unnamed") for c in df.columns) or df.columns.dtype != "O":
        df.columns = [f"Columna_{i+1}" for i in range(df.shape[1])]
    return df

def read_any(upload):
    name = upload.name.lower()
    if name.endswith(".csv"):
        return read_csv_forgiving(upload)
    else:
        # Excel
        df = pd.read_excel(upload, header=None)
        # si la primera fila luce encabezado (texto), promuévelo
        if df.iloc[0].apply(lambda x: isinstance(x, str)).mean() > 0.6:
            df.columns = df.iloc[0].astype(str).tolist()
            df = df.iloc[1:].reset_index(drop=True)
        else:
            df.columns = [f"Columna_{i+1}" for i in range(df.shape[1])]
        return df

def pick_col(df, keywords, required=False, fallback_first=False, label=""):
    # busca la primera columna cuyo nombre contenga alguna palabra clave
    cols = [c for c in df.columns if any(k in norm_txt(c) for k in keywords)]
    if cols:
        return cols[0]
    if fallback_first:
        return df.columns[0]
    if required:
        raise ValueError(f"No se encontró columna requerida: {label or keywords}")
    return None

def generar_pdf_tabla(df_resumen, kpis):
    buffer = BytesIO()
    fecha = datetime.now().strftime("%Y-%m-%d")
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    title = ParagraphStyle('title', parent=styles['Title'], alignment=TA_CENTER, textColor=colors.HexColor("#3A86FF"))
    story = []
    story.append(Paragraph(f"Reporte GIA - Comparación de Casos ({fecha})", title))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        f"Asignados: {kpis['asignados']} | Resueltos: {kpis['resueltos']} | Tardíos: {kpis['tardios']} | "
        f"Eficiencia Prom: {kpis['eficiencia_prom']:.2f}% | Eficacia Prom: {kpis['eficacia_prom']:.2f}%",
        styles["Normal"]
    ))
    story.append(Spacer(1, 10))
    data = [list(df_resumen.columns)] + df_resumen.values.tolist()
    tabla = Table(data, colWidths=[140, 90, 90, 90, 90, 90])
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#3A86FF")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('GRID', (0,0), (-1,-1), 0.3, colors.gray),
    ]))
    story.append(tabla)
    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf

# ==============================
# UI: SUBIDA DE ARCHIVOS
# ==============================
c1, c2 = st.columns(2)
detalle_file = c1.file_uploader("📄 Archivo DETALLE (glpi 6): contiene Categoría y 'Asignado a - Técnico'", type=["csv","xlsx"])
resumen_file = c2.file_uploader("📄 Archivo RESUMEN (glpi 7): contiene Categoría (columna A) + abiertos/resueltos/tardíos", type=["csv","xlsx"])

if not (detalle_file and resumen_file):
    st.info("Sube ambos archivos para generar la comparación.")
    st.stop()

try:
    df_det = read_any(detalle_file)
    df_res = read_any(resumen_file)

    # --- DETECTAR COLUMNAS ---
    # En detalle: categoría (nombre del caso)
    col_categoria_det = pick_col(
        df_det,
        keywords=["categor", "category", "asunto", "titulo", "título", "tipo", "caso", "nombre"],
        required=True, label="Categoría (detalle)"
    )

    # En detalle: técnico (Asignado a - Técnico)
    col_tecnico = pick_col(
        df_det,
        keywords=["asignado a - tecnico", "asignado a - técnico", "tecnico", "técnico", "asignado a", "assigned to"],
        required=False
    )
    if col_tecnico is None:
        # fallback: la mejor coincidencia que contenga "tecn" o "asign"
        cand = [c for c in df_det.columns if ("tecn" in norm_txt(c) or "asign" in norm_txt(c))]
        if not cand:
            raise ValueError("No se encontró columna del técnico en el DETALLE (ej: 'Asignado a - Técnico').")
        col_tecnico = cand[0]

    # En resumen: categoría = COLUMNA A (tomar primera columna sí o sí)
    col_categoria_res = df_res.columns[0]

    # En resumen: abiertos/resueltos/tardíos
    col_abiertos = pick_col(df_res, ["abiert","asign","abiertos","cantidad de casos abiertos"], required=True, label="Abiertos/Asignados")
    col_resueltos = pick_col(df_res, ["resuelt","cerrad","cantidad de casos resueltos"], required=True, label="Resueltos")
    col_tardios = pick_col(df_res, ["tard","vencid","overdue","cantidad de casos tardios","cantidad de casos tardíos"], required=True, label="Tardíos")

    # --- LIMPIAR Y NORMALIZAR CLAVES DE CRUCE ---
    det = df_det[[col_categoria_det, col_tecnico]].copy()
    res = df_res[[col_categoria_res, col_abiertos, col_resueltos, col_tardios]].copy()

    # normalizar texto de categorías (quitar acentos / mayúsculas / espacios)
    det["_cat_norm_"] = det[col_categoria_det].apply(norm_txt)
    res["_cat_norm_"] = res[col_categoria_res].apply(norm_txt)

    # convertir numéricos
    for c in [col_abiertos, col_resueltos, col_tardios]:
        res[c] = pd.to_numeric(res[c], errors="coerce").fillna(0).astype(int)

    # --- RESOLVER MÚLTIPLES TÉCNICOS POR CATEGORÍA ---
    # si una categoría aparece ligado a varios técnicos en el detalle, usamos el más frecuente (modo)
    modo_tecnico = (
        det.groupby("_cat_norm_")[col_tecnico]
           .agg(lambda s: s.mode().iloc[0] if not s.mode().empty else s.iloc[0])
           .reset_index()
    )

    # --- CRUCE ---
    merged = res.merge(modo_tecnico, on="_cat_norm_", how="left")

    # métricas de match
    no_match = merged[col_tecnico].isna().sum()
    st.markdown(f"**Categorías del resumen sin técnico en el detalle:** {no_match}")

    merged[col_tecnico] = merged[col_tecnico].fillna("— sin técnico —")

    # --- RESUMEN POR TÉCNICO ---
    resumen = (
        merged.groupby(col_tecnico)[[col_abiertos, col_resueltos, col_tardios]]
              .sum()
              .reset_index()
              .rename(columns={
                  col_tecnico: "Técnico",
                  col_abiertos: "Casos asignados (abiertos)",
                  col_resueltos: "Casos resueltos",
                  col_tardios: "Casos tardíos"
              })
    )

    # KPIs derivados
    resumen["Eficiencia (%)"] = (resumen["Casos resueltos"] / (resumen["Casos asignados (abiertos)"] + 1e-9)) * 100
    resumen["Eficacia (%)"]   = ((resumen["Casos resueltos"] - resumen["Casos tardíos"]) / (resumen["Casos asignados (abiertos)"] + 1e-9)) * 100

    asignados_tot = int(resumen["Casos asignados (abiertos)"].sum())
    resueltos_tot = int(resumen["Casos resueltos"].sum())
    tardios_tot   = int(resumen["Casos tardíos"].sum())
    eficiencia_prom = float(resumen["Eficiencia (%)"].mean())
    eficacia_prom   = float(resumen["Eficacia (%)"].mean())

    # ==============================
    # UI: METRICAS + TABLA + GRAFICOS
    # ==============================
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f"<div class='metric-card'><div class='metric-value'>{asignados_tot}</div><div class='metric-label'>Asignados</div></div>", unsafe_allow_html=True)
    c2.markdown(f"<div class='metric-card'><div class='metric-value'>{resueltos_tot}</div><div class='metric-label'>Resueltos</div></div>", unsafe_allow_html=True)
    c3.markdown(f"<div class='metric-card'><div class='metric-value'>{tardios_tot}</div><div class='metric-label'>Tardíos</div></div>", unsafe_allow_html=True)
    c4.markdown(f"<div class='metric-card'><div class='metric-value'>{eficiencia_prom:.2f}%</div><div class='metric-label'>Eficiencia Prom.</div></div>", unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)
    st.dataframe(resumen, use_container_width=True)

    fig1 = px.bar(resumen, x="Técnico", y=["Casos asignados (abiertos)", "Casos resueltos", "Casos tardíos"],
                  barmode="group", color_discrete_sequence=["#3A86FF", "#06D6A0", "#EF476F"],
                  title="Casos por Técnico")
    st.plotly_chart(fig1, use_container_width=True)

    fig2 = px.bar(resumen, x="Técnico", y=["Eficiencia (%)", "Eficacia (%)"],
                  barmode="group", color_discrete_sequence=["#FFD166", "#118AB2"],
                  title="Eficiencia y Eficacia por Técnico")
    st.plotly_chart(fig2, use_container_width=True)

    # PDF
    pdf = generar_pdf_tabla(
        resumen[["Técnico", "Casos asignados (abiertos)", "Casos resueltos", "Casos tardíos", "Eficiencia (%)", "Eficacia (%)"]],
        {"asignados": asignados_tot, "resueltos": resueltos_tot, "tardios": tardios_tot,
         "eficiencia_prom": eficiencia_prom, "eficacia_prom": eficacia_prom}
    )
    st.download_button("📄 Descargar Reporte PDF", pdf, file_name="reporte_gia_comparativo.pdf")

except Exception as e:
    st.error(f"❌ Error al procesar: {e}")
