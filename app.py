import streamlit as st
import fitz
import pytesseract
from PIL import Image, ImageOps, ImageFilter
import io
import re
import base64
import gc

# ----------------------------
# CONFIG STREAMLIT
# ----------------------------

st.set_page_config(layout="wide", page_title="Noticias Yucatán")
st.set_option("client.showErrorDetails", False)

# Si lo necesitas en Windows, descomenta esta línea:
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

DEBUG_MODE = True

# ----------------------------
# CONFIG OCR
# ----------------------------

OCR_DPI = 200
OCR_LANG = "spa+eng"
MIN_CHARS_TEXTO_EMBEDIDO = 40

# ----------------------------
# PALABRAS CLAVE
# ----------------------------

KEYWORDS = {
    "Yucatán": [
        r"\bYucat[aá]n\b"
    ],
    "YUC": [
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
        r"\bTren\s+Maya\b"
    ],
    "Gobernador": [
        r"\bGobernador\s+de\s+Yucat[aá]n\b"
    ],
    "Huacho Díaz Mena": [
        r"\bJoaqu[ií]n\s*Huacho\s*D[ií]az\s*Mena\b",
        r"\bHuacho\s*D[ií]az\s*Mena\b"
    ]
}

# ----------------------------
# FUNCIONES AUXILIARES
# ----------------------------

def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\x00", " ")
    text = text.replace("\r", " ")
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def limpiar_texto_para_busqueda(text: str) -> str:
    """
    Limpieza pensada para búsqueda:
    - une palabras partidas por salto de línea
    - elimina basura típica de OCR
    - conserva letras, números, acentos, ü y ñ
    """
    if not text:
        return ""

    text = text.replace("\x00", " ")
    text = text.replace("-\n", "")
    text = text.replace("\r", "\n")
    text = text.replace("\n", " ")
    text = text.replace("-", " ")

    replacements = {
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "´": "'",
        "`": "'",
        "•": " ",
        "·": " ",
        "…": " ",
        "|": " ",
        "¦": " ",
        "_": " ",
        "/": " ",
        "\\": " ",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"[^0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+", " ", text)
    text = re.sub(r"\s{2,}", " ", text)

    return text.strip()


def normalizar_para_busqueda(text: str) -> str:
    """
    Normaliza solo para búsqueda interna:
    - pasa a minúsculas
    - quita acentos
    - conserva la ñ
    """
    if not text:
        return ""

    text = text.lower().strip()

    reemplazos = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ü": "u",
    }

    for a, b in reemplazos.items():
        text = text.replace(a, b)

    text = re.sub(r"\s+", " ", text)
    return text.strip()


def preprocess_for_ocr(img: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(img)
    gray = ImageOps.autocontrast(gray)
    gray = gray.filter(ImageFilter.SHARPEN)

    # Binarización suave para mejorar OCR
    bw = gray.point(lambda x: 0 if x < 180 else 255, "1")
    return bw.convert("L")


def build_normalized_mapping(original_text: str):
    """
    Crea:
    - normalized_text: versión sin acentos (excepto ñ)
    - index_map: por cada carácter de normalized_text, guarda el índice
      correspondiente en original_text.

    Esto permite buscar sobre texto normalizado y luego recortar
    el snippet desde el texto original.
    """
    normalized_chars = []
    index_map = []

    replacements = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u",
        "Á": "a", "É": "e", "Í": "i", "Ó": "o", "Ú": "u", "Ü": "u",
    }

    for idx, ch in enumerate(original_text):
        ch2 = replacements.get(ch, ch)
        ch2 = ch2.lower()
        normalized_chars.append(ch2)
        index_map.append(idx)

    return "".join(normalized_chars), index_map


# ----------------------------
# OCR SIN TIMEOUT
# ----------------------------

def hacer_ocr(img):
    try:
        texto = pytesseract.image_to_string(
            img,
            lang=OCR_LANG,
            config="--oem 3 --psm 6"
        )
        return texto or "", None
    except Exception as e:
        return "", str(e)


# ----------------------------
# MINIATURA
# ----------------------------

def create_thumbnail(page):
    pix = page.get_pixmap(matrix=fitz.Matrix(0.35, 0.35), alpha=False)

    mode = "RGB" if pix.n < 4 else "RGBA"

    img = Image.frombytes(
        mode,
        [pix.width, pix.height],
        pix.samples
    )

    img.thumbnail((200, 200))

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    base64_img = base64.b64encode(buffer.getvalue()).decode()

    del pix, img, buffer
    gc.collect()

    return base64_img


# ----------------------------
# EXTRAER TEXTO
# ----------------------------

def extract_text(page, page_number=None, debug_expander=None):
    """
    Devuelve un dict con:
    - text_original: texto limpio para mostrar snippets
    - text_search: texto normalizado para búsqueda interna
    - source: EMBEDDED / OCR
    """
    texto_raw = ""

    # 1) Intentar texto embebido
    try:
        texto_raw = page.get_text("text") or ""
    except Exception as e:
        texto_raw = ""
        if DEBUG_MODE and debug_expander:
            debug_expander.write(f"Error extrayendo texto embebido: {e}")

    # 2) Si es poco, intentar bloques
    if len(texto_raw.strip()) < MIN_CHARS_TEXTO_EMBEDIDO:
        try:
            bloques = page.get_text("blocks") or []
            texto_bloques = "\n".join(
                b[4].strip() for b in bloques
                if len(b) >= 5 and str(b[4]).strip()
            )
            if len(texto_bloques.strip()) > len(texto_raw.strip()):
                texto_raw = texto_bloques
        except Exception as e:
            if DEBUG_MODE and debug_expander:
                debug_expander.write(f"No se pudo extraer texto por bloques: {e}")

    texto_original = limpiar_texto_para_busqueda(normalize_text(texto_raw))
    texto_busqueda = normalizar_para_busqueda(texto_original)

    if DEBUG_MODE and debug_expander:
        try:
            text_dict = page.get_text("dict")
            blocks = text_dict.get("blocks", [])
            image_blocks = sum(1 for b in blocks if b.get("type") == 1)
            text_blocks = sum(1 for b in blocks if b.get("type") == 0)

            debug_expander.write(f"Texto embebido limpio: {len(texto_original)} caracteres")
            debug_expander.write(f"Texto búsqueda normalizado: {len(texto_busqueda)} caracteres")
            debug_expander.write(
                f"Bloques totales: {len(blocks)} | "
                f"bloques texto: {text_blocks} | "
                f"bloques imagen: {image_blocks}"
            )
        except Exception as e:
            debug_expander.write(f"No se pudo leer page.get_text('dict'): {e}")

    # 3) Si trae suficiente texto embebido, usarlo
    if len(texto_original) >= MIN_CHARS_TEXTO_EMBEDIDO:
        if DEBUG_MODE and debug_expander:
            debug_expander.write("Se usará texto embebido limpio.")
            if texto_original:
                debug_expander.text_area(
                    f"Preview texto original limpio página {page_number}",
                    texto_original[:2000],
                    height=220
                )
        return {
            "text_original": texto_original,
            "text_search": texto_busqueda,
            "source": "EMBEDDED"
        }

    # 4) Si no, usar OCR
    if DEBUG_MODE and debug_expander:
        debug_expander.write("Se usará OCR.")

    try:
        pix = page.get_pixmap(
            dpi=OCR_DPI,
            colorspace=fitz.csGRAY,
            alpha=False
        )

        img = Image.frombytes(
            "L",
            [pix.width, pix.height],
            pix.samples
        )

        img = preprocess_for_ocr(img)

        text_ocr_raw, ocr_error = hacer_ocr(img)
        text_ocr_original = limpiar_texto_para_busqueda(normalize_text(text_ocr_raw))
        text_ocr_search = normalizar_para_busqueda(text_ocr_original)

        if DEBUG_MODE and debug_expander:
            debug_expander.write(f"OCR limpio caracteres: {len(text_ocr_original)}")
            debug_expander.write(f"Error OCR: {ocr_error}")
            if text_ocr_original:
                debug_expander.text_area(
                    f"Preview OCR original limpio página {page_number}",
                    text_ocr_original[:2000],
                    height=220
                )

        del pix, img
        gc.collect()

        return {
            "text_original": text_ocr_original,
            "text_search": text_ocr_search,
            "source": "OCR"
        }

    except Exception as e:
        if DEBUG_MODE and debug_expander:
            debug_expander.write(f"Fallo OCR en página {page_number}: {e}")
        return {
            "text_original": "",
            "text_search": "",
            "source": "ERROR"
        }


# ----------------------------
# BUSCAR PALABRAS
# ----------------------------

def search_keywords(text_original, text_search):
    """
    Busca sobre texto normalizado para tolerar acentos,
    pero recorta y muestra el snippet desde el texto original.
    """
    results = []
    seen = set()

    if not text_original or not text_search:
        return results

    normalized_original, index_map = build_normalized_mapping(text_original)

    for kw, patterns in KEYWORDS.items():
        for pattern in patterns:
            # Normalizar patrón para búsqueda interna
            pattern_norm = normalizar_para_busqueda(pattern)

            # Ajustes básicos del patrón tras normalizar
            pattern_norm = pattern_norm.replace(r"[aá]", r"[aa]")
            pattern_norm = pattern_norm.replace(r"[eé]", r"[ee]")
            pattern_norm = pattern_norm.replace(r"[ií]", r"[ii]")
            pattern_norm = pattern_norm.replace(r"[oó]", r"[oo]")
            pattern_norm = pattern_norm.replace(r"[uú]", r"[uu]")

            try:
                matches = list(re.finditer(pattern_norm, normalized_original, re.IGNORECASE))
            except re.error:
                continue

            for match in matches:
                start_norm = max(match.start() - 60, 0)
                end_norm = min(match.end() + 60, len(normalized_original))

                start_orig = index_map[start_norm]
                end_orig = index_map[end_norm - 1] + 1 if end_norm > start_norm else index_map[start_norm] + 1

                phrase = text_original[start_orig:end_orig]
                phrase = re.sub(r"\s+", " ", phrase).strip()

                phrase_key = normalizar_para_busqueda(phrase)
                if phrase_key in seen:
                    continue
                seen.add(phrase_key)

                # Resaltar en el snippet visible usando el patrón original
                highlighted = phrase
                try:
                    highlighted = re.sub(
                        pattern,
                        r"<span style='color:red;font-weight:bold'>\g<0></span>",
                        phrase,
                        flags=re.IGNORECASE
                    )
                except re.error:
                    pass

                results.append(highlighted)

    return results


# ----------------------------
# UI
# ----------------------------

st.markdown("<h1 style='text-align:center'>Noticias Yucatán</h1>", unsafe_allow_html=True)
st.markdown("<h3 style='text-align:center;color:gray'>Análisis automático de PDFs</h3>", unsafe_allow_html=True)

st.write("---")

uploaded_files = st.file_uploader(
    "Sube tus PDFs",
    type=["pdf"],
    accept_multiple_files=True
)

summary = {}

# ----------------------------
# PROCESAMIENTO
# ----------------------------

if uploaded_files:
    for file in uploaded_files:
        st.header(file.name)
        summary[file.name] = []

        try:
            doc = fitz.open(stream=file.read(), filetype="pdf")
        except Exception:
            st.warning("No se pudo abrir el PDF")
            continue

        total = len(doc)
        progress = st.progress(0)

        for i, page in enumerate(doc):
            progress.progress((i + 1) / total)

            debug_expander = None
            if DEBUG_MODE:
                debug_expander = st.expander(f"Diagnóstico página {i+1}", expanded=False)

            extracted = extract_text(page, page_number=i + 1, debug_expander=debug_expander)
            text_original = extracted["text_original"]
            text_search = extracted["text_search"]

            results = search_keywords(text_original, text_search)

            if DEBUG_MODE and debug_expander:
                debug_expander.write(f"Fuente usada: {extracted['source']}")
                debug_expander.write(f"Coincidencias encontradas: {len(results)}")

            if results:
                thumb = create_thumbnail(page)

                image_bytes = base64.b64decode(thumb)
                image = Image.open(io.BytesIO(image_bytes))

                col1, col2 = st.columns([1, 3])

                with col1:
                    st.image(image, width=200)

                with col2:
                    st.markdown(f"### Página {i+1}")

                    for r in results:
                        st.markdown(r, unsafe_allow_html=True)

                summary[file.name].append(
                    f"Página {i+1}: " + re.sub("<[^<]+?>", "", results[0])
                )

            gc.collect()

        progress.progress(1.0)

        if summary[file.name]:
            st.success("Procesamiento terminado con coincidencias")
        else:
            st.info("No se encontraron coincidencias")

        doc.close()

# ----------------------------
# RESUMEN FINAL
# ----------------------------

final = ""

for pdf, entries in summary.items():
    final += pdf + "\n"

    if entries:
        final += "\n".join(entries)
    else:
        final += "Sin coincidencias"

    final += "\n\n"

if final:
    st.text_area(
        "Resumen final (copiar)",
        final,
        height=400
    )