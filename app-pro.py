import streamlit as st
import fitz
import pytesseract
from PIL import Image, ImageOps, ImageFilter
import io
import re
import base64
import gc
import threading
import unicodedata

# ----------------------------
# CONFIGURACIÓN
# ----------------------------
st.set_page_config(layout="wide", page_title="Noticias Yucatán")

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

DEBUG_MODE = True
OCR_TIMEOUT = 40
OCR_ZOOM = 2.5

KEYWORDS = {
    "Yucatán": [
        r"\bYucat[aá]n\b",
        r"\bYUC\b"
    ],
    "yucateco": [
        r"\byucateco\b",
        r"\byucateca\b",
        r"\byucatecos\b",
        r"\byucatecas\b"
    ],
    "Mérida": [
        r"\bM[eé]rida\b"
    ],
    "Tren Maya": [
        r"\bTren\s*Maya\b"
    ],
    "Gobernador de Yucatán": [
        r"\bGobernador\s+de\s+Yucat[aá]n\b"
    ],
    "Huacho Díaz Mena": [
        r"\bJoaqu[ií]n\s*[\"“”']?\s*Huacho\s*[\"“”']?\s*D[ií]az\s+Mena\b",
        r"\bHuacho\s+D[ií]az\s+Mena\b",
        r"\bD[ií]az\s+Mena\b"
    ]
}

FLEXIBLE_KEYWORDS = {
    "Yucatán": [
        r"\bYucatan\b",
        r"\bYUC\b"
    ],
    "yucateco": [
        r"\byucateco\b",
        r"\byucateca\b",
        r"\byucatecos\b",
        r"\byucatecas\b"
    ],
    "Mérida": [
        r"\bMerida\b"
    ],
    "Tren Maya": [
        r"\bTren\s*Maya\b",
        r"\bTrenMaya\b"
    ],
    "Gobernador de Yucatán": [
        r"\bGobernador\s+de\s+Yucatan\b"
    ],
    "Huacho Díaz Mena": [
        r"\bJoaquin\s*[\"“”']?\s*Huacho\s*[\"“”']?\s*Diaz\s+Mena\b",
        r"\bHuacho\s+Diaz\s+Mena\b",
        r"\bDiaz\s+Mena\b"
    ]
}

# ----------------------------
# UI
# ----------------------------
st.markdown("<h1 style='text-align:center;'>Noticias Yucatán</h1>", unsafe_allow_html=True)
st.markdown("<h3 style='text-align:center; color:gray;'>Análisis de PDFs con OCR simplificado</h3>", unsafe_allow_html=True)
st.write("---")

# ----------------------------
# FUNCIONES
# ----------------------------
def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\x00", " ")
    text = text.replace("\n", " ")
    text = text.replace("\r", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def strip_accents(text: str) -> str:
    if not text:
        return ""
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )

def preprocess_for_ocr(img: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(img)
    gray = ImageOps.autocontrast(gray)
    gray = gray.filter(ImageFilter.MedianFilter(size=3))
    gray = gray.filter(ImageFilter.SHARPEN)
    bw = gray.point(lambda x: 0 if x < 180 else 255, "1")
    return bw.convert("L")

def render_page_to_image(page, zoom=2.5):
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    mode = "RGB" if pix.n < 4 else "RGBA"
    img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
    return pix, img

def ocr_worker(img: Image.Image, lang: str, config: str, result: dict):
    try:
        result["text"] = pytesseract.image_to_string(img, lang=lang, config=config)
    except Exception as e:
        result["error"] = str(e)
        result["text"] = ""

def ocr_with_timeout(img: Image.Image, timeout_sec=40, psm=6):
    result = {"text": "", "error": None}
    config = f"--oem 3 --psm {psm}"

    thread = threading.Thread(
        target=ocr_worker,
        args=(img, "spa", config, result),
        daemon=True
    )
    thread.start()
    thread.join(timeout=timeout_sec)

    if thread.is_alive():
        return "", f"Timeout OCR > {timeout_sec}s con psm={psm}"

    return normalize_text(result["text"]), result["error"]

def crop_left_right(img: Image.Image):
    w, h = img.size
    left = img.crop((0, 0, w // 2, h))
    right = img.crop((w // 2, 0, w, h))
    return left, right

def detect_scanned_like_page(page):
    try:
        text = normalize_text(page.get_text("text"))
        text_dict = page.get_text("dict")
        blocks = text_dict.get("blocks", [])
        text_blocks = sum(1 for b in blocks if b.get("type") == 0)
        image_blocks = sum(1 for b in blocks if b.get("type") == 1)

        scanned_like = (len(text) < 100 and image_blocks >= 1) or (text_blocks == 0 and image_blocks > 0)

        return {
            "embedded_chars": len(text),
            "text_blocks": text_blocks,
            "image_blocks": image_blocks,
            "scanned_like": scanned_like
        }
    except Exception as e:
        return {
            "embedded_chars": 0,
            "text_blocks": 0,
            "image_blocks": 0,
            "scanned_like": True,
            "error": str(e)
        }

def text_is_good_enough(text: str, min_chars=800):
    return len(normalize_text(text)) >= min_chars

def extract_best_text_from_page(page, page_number, debug_expander=None):
    diagnosis = detect_scanned_like_page(page)

    embedded_text = ""
    try:
        embedded_text = normalize_text(page.get_text("text"))
    except Exception as e:
        if DEBUG_MODE and debug_expander:
            debug_expander.write(f"Error leyendo texto embebido: {e}")

    if DEBUG_MODE and debug_expander:
        debug_expander.write(f"Texto embebido: {len(embedded_text)} caracteres")
        debug_expander.write(
            f"Bloques texto: {diagnosis.get('text_blocks', 0)} | "
            f"bloques imagen: {diagnosis.get('image_blocks', 0)} | "
            f"escaneado probable: {diagnosis.get('scanned_like', False)}"
        )

    # 1) Si trae buen texto embebido, usar ese y salir
    if text_is_good_enough(embedded_text, min_chars=300):
        if DEBUG_MODE and debug_expander:
            debug_expander.write("Se usó texto embebido.")
            debug_expander.text_area(
                f"Preview texto final página {page_number}",
                embedded_text[:2500],
                height=220
            )
        return embedded_text, "texto_embebido"

    # 2) OCR secuencial con fallback
    try:
        pix, page_img = render_page_to_image(page, zoom=OCR_ZOOM)
        page_img = preprocess_for_ocr(page_img)

        # Intento A: página completa psm 11
        text_a, err_a = ocr_with_timeout(page_img, timeout_sec=OCR_TIMEOUT, psm=11)
        if DEBUG_MODE and debug_expander:
            debug_expander.write(f"Intento OCR A: página completa psm=11 -> chars={len(text_a)} error={err_a}")

        if text_is_good_enough(text_a):
            if DEBUG_MODE and debug_expander:
                debug_expander.write("Se eligió OCR A y se detienen más intentos.")
                debug_expander.text_area(
                    f"Preview texto final página {page_number}",
                    text_a[:2500],
                    height=220
                )
            del pix, page_img
            gc.collect()
            return text_a, "ocr_pagina_completa_psm11"

        # Intento B: página completa psm 6
        text_b, err_b = ocr_with_timeout(page_img, timeout_sec=OCR_TIMEOUT, psm=6)
        if DEBUG_MODE and debug_expander:
            debug_expander.write(f"Intento OCR B: página completa psm=6 -> chars={len(text_b)} error={err_b}")

        if text_is_good_enough(text_b):
            if DEBUG_MODE and debug_expander:
                debug_expander.write("Se eligió OCR B y se detienen más intentos.")
                debug_expander.text_area(
                    f"Preview texto final página {page_number}",
                    text_b[:2500],
                    height=220
                )
            del pix, page_img
            gc.collect()
            return text_b, "ocr_pagina_completa_psm6"

        # Intento C: mitades con psm 11
        left_img, right_img = crop_left_right(page_img)
        text_left, err_left = ocr_with_timeout(left_img, timeout_sec=OCR_TIMEOUT, psm=11)
        text_right, err_right = ocr_with_timeout(right_img, timeout_sec=OCR_TIMEOUT, psm=11)
        text_c = normalize_text(text_left + " " + text_right)

        if DEBUG_MODE and debug_expander:
            debug_expander.write(
                f"Intento OCR C: mitades psm=11 -> "
                f"izq={len(text_left)} der={len(text_right)} total={len(text_c)}"
            )

        if text_is_good_enough(text_c):
            if DEBUG_MODE and debug_expander:
                debug_expander.write("Se eligió OCR C y se detienen más intentos.")
                debug_expander.text_area(
                    f"Preview texto final página {page_number}",
                    text_c[:2500],
                    height=220
                )
            del pix, page_img, left_img, right_img
            gc.collect()
            return text_c, "ocr_mitades_psm11"

        # 3) Si ninguno pasó el umbral, elegir el mejor por longitud
        candidates = [
            ("ocr_pagina_completa_psm11", text_a),
            ("ocr_pagina_completa_psm6", text_b),
            ("ocr_mitades_psm11", text_c),
        ]
        best_method, best_text = max(candidates, key=lambda x: len(x[1]))

        if DEBUG_MODE and debug_expander:
            debug_expander.write(f"Ningún intento pasó el umbral. Se elige el mejor por longitud: {best_method} ({len(best_text)} chars)")
            if best_text:
                debug_expander.text_area(
                    f"Preview texto final página {page_number}",
                    best_text[:2500],
                    height=220
                )

        del pix, page_img, left_img, right_img
        gc.collect()
        return best_text, best_method

    except Exception as e:
        if DEBUG_MODE and debug_expander:
            debug_expander.write(f"Fallo OCR: {e}")
        return "", "ocr_error"

def find_keyword_matches(text: str, patterns_dict: dict, accent_insensitive=False):
    phrases_dict = {kw: [] for kw in patterns_dict}
    if not text:
        return phrases_dict

    base_text = normalize_text(text)
    search_text = strip_accents(base_text) if accent_insensitive else base_text

    for kw, patterns in patterns_dict.items():
        seen_phrases = set()

        for pattern in patterns:
            try:
                for match in re.finditer(pattern, search_text, flags=re.IGNORECASE):
                    start_idx = max(match.start() - 80, 0)
                    end_idx = min(match.end() + 80, len(search_text))
                    phrase = normalize_text(base_text[start_idx:end_idx])

                    if not phrase:
                        continue

                    # deduplicación por contexto
                    phrase_key = strip_accents(phrase.lower())
                    if phrase_key in seen_phrases:
                        continue
                    seen_phrases.add(phrase_key)

                    if not accent_insensitive:
                        highlighted = re.sub(pattern, r"__\g<0>__", phrase, flags=re.IGNORECASE)
                    else:
                        highlighted = phrase

                    phrases_dict[kw].append(highlighted)
            except re.error:
                continue

    return phrases_dict

def merge_phrase_dicts(main_dict, flexible_dict):
    merged = {k: [] for k in main_dict.keys()}

    for k in merged.keys():
        seen = set()

        for phrase in main_dict.get(k, []):
            key = strip_accents(phrase.lower())
            if key not in seen:
                seen.add(key)
                merged[k].append(phrase)

        for phrase in flexible_dict.get(k, []):
            key = strip_accents(phrase.lower())
            if key not in seen:
                seen.add(key)
                merged[k].append(phrase)

    return merged

def build_thumbnail(page):
    pix_thumb = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5), alpha=False)
    mode = "RGB" if pix_thumb.n < 4 else "RGBA"
    img_thumb = Image.frombytes(mode, [pix_thumb.width, pix_thumb.height], pix_thumb.samples)

    thumbnail = img_thumb.copy()
    thumbnail.thumbnail((200, 200))

    img_buffer = io.BytesIO()
    thumbnail.save(img_buffer, format="PNG")
    img_buffer.seek(0)
    img_base64 = base64.b64encode(img_buffer.getvalue()).decode()

    return pix_thumb, img_thumb, thumbnail, img_buffer, img_base64

def render_page_result(page_number, img_base64, phrases_dict):
    html_phrases = ""
    for kw in phrases_dict:
        for ph in phrases_dict[kw]:
            ph_html = re.sub(r"__(.*?)__", r"<span style='color:red; font-weight:bold;'>\1</span>", ph)
            html_phrases += f"<b>{kw}:</b> {ph_html}<br><br>"

    html_code = f"""
    <div style="display:flex; align-items:flex-start; border:1px solid #ccc; padding:10px; margin-bottom:15px;
                border-radius:5px; background-color:#f5f5f5; color:black;">
        <div style="flex:0 0 auto; margin-right:15px;">
            <img src="data:image/png;base64,{img_base64}" width="200"/>
        </div>
        <div style="flex:1;">
            <h2><b>Página {page_number}</b></h2>
            {html_phrases}
        </div>
    </div>
    """
    st.markdown(html_code, unsafe_allow_html=True)

# ----------------------------
# UPLOAD
# ----------------------------
uploaded_files = st.file_uploader(
    "Arrastra tus PDFs aquí o selecciona desde tu equipo",
    type=["pdf"],
    accept_multiple_files=True
)

pdf_results_summary = {}

# ----------------------------
# PROCESAMIENTO
# ----------------------------
if uploaded_files:
    for pdf_file in uploaded_files:
        st.header(f"Archivo: {pdf_file.name}")
        pdf_results_summary[pdf_file.name] = []
        found_any = False

        try:
            pdf_bytes = pdf_file.read()
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            st.warning(f"No se pudo abrir el PDF {pdf_file.name}: {e}")
            continue

        total_pages = len(doc)
        st.write(f"Procesando {total_pages} páginas...")
        progress_bar = st.progress(0)

        for page_number, page in enumerate(doc, start=1):
            progress_bar.progress(page_number / total_pages)

            debug_expander = st.expander(f"Diagnóstico página {page_number}", expanded=False) if DEBUG_MODE else None

            text_final, extraction_method = extract_best_text_from_page(page, page_number, debug_expander)

            if DEBUG_MODE and debug_expander:
                debug_expander.write(f"Método final elegido: {extraction_method}")
                debug_expander.write(f"Longitud final: {len(text_final)} caracteres")

            matches_main = find_keyword_matches(text_final, KEYWORDS, accent_insensitive=False)
            matches_flexible = find_keyword_matches(text_final, FLEXIBLE_KEYWORDS, accent_insensitive=True)
            phrases_dict = merge_phrase_dicts(matches_main, matches_flexible)

            page_has_matches = any(len(v) > 0 for v in phrases_dict.values())

            if DEBUG_MODE and debug_expander:
                total_hits = sum(len(v) for v in phrases_dict.values())
                debug_expander.write(f"Coincidencias encontradas: {total_hits}")
                for kw, vals in phrases_dict.items():
                    if vals:
                        debug_expander.write(f"{kw}: {len(vals)}")

            try:
                pix_thumb, img_thumb, thumbnail, img_buffer, img_base64 = build_thumbnail(page)
            except Exception as e:
                st.warning(f"No se pudo generar miniatura en página {page_number}: {e}")
                continue

            if page_has_matches:
                for kw in phrases_dict:
                    for phrase in phrases_dict[kw]:
                        pdf_results_summary[pdf_file.name].append(f"**Página {page_number}** [{kw}]: {phrase}")
                        found_any = True

                render_page_result(page_number, img_base64, phrases_dict)

            del pix_thumb, img_thumb, thumbnail, img_buffer
            gc.collect()

        progress_bar.progress(1.0)

        if found_any:
            st.markdown(
                "<div style='border:1px solid #2196F3; padding:8px; color:#2196F3; border-radius:5px;'>Procesamiento completado con coincidencias.</div>",
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                "<div style='border:1px solid #2196F3; padding:8px; color:#2196F3; border-radius:5px;'>Sin coincidencias encontradas en todo el PDF.</div>",
                unsafe_allow_html=True
            )
            pdf_results_summary[pdf_file.name].append("Sin coincidencias")

        doc.close()

# ----------------------------
# RESUMEN
# ----------------------------
resumen_texto_final = ""
for pdf_name, entries in pdf_results_summary.items():
    resumen_texto_final += f"{pdf_name}\n"
    resumen_texto_final += "\n".join(entries) + "\n\n"

if resumen_texto_final:
    st.text_area(
        "Resumen final de todos los PDFs (Ctrl+C para copiar)",
        resumen_texto_final,
        height=400
    )