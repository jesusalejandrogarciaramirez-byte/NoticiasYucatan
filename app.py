import streamlit as st
import fitz
import pytesseract
from PIL import Image, ImageOps, ImageFilter
import io
import re
import base64
import gc
import threading

# ----------------------------
# CONFIG STREAMLIT
# ----------------------------

st.set_page_config(layout="wide", page_title="Noticias Yucatán")
st.set_option("client.showErrorDetails", False)

# Si lo necesitas en Windows, descomenta esta línea:
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

DEBUG_MODE = True

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
    text = text.replace("\n", " ")
    text = text.replace("\r", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def preprocess_for_ocr(img: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(img)
    gray = ImageOps.autocontrast(gray)
    gray = gray.filter(ImageFilter.SHARPEN)
    bw = gray.point(lambda x: 0 if x < 180 else 255, "1")
    return bw.convert("L")


# ----------------------------
# OCR CON TIMEOUT
# ----------------------------

def ocr_with_timeout(img, timeout=30):
    result = {"text": "", "error": None}

    def target():
        try:
            result["text"] = pytesseract.image_to_string(
                img,
                lang="spa",
                config="--oem 3 --psm 6"
            )
        except Exception as e:
            result["error"] = str(e)
            result["text"] = ""

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout)

    if thread.is_alive():
        return "", f"Timeout OCR > {timeout}s"

    return result["text"], result["error"]


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
    try:
        text = page.get_text("text")
    except Exception as e:
        text = ""
        if DEBUG_MODE and debug_expander:
            debug_expander.write(f"Error extrayendo texto embebido: {e}")

    text = normalize_text(text)

    if DEBUG_MODE and debug_expander:
        try:
            text_dict = page.get_text("dict")
            blocks = text_dict.get("blocks", [])
            image_blocks = sum(1 for b in blocks if b.get("type") == 1)
            text_blocks = sum(1 for b in blocks if b.get("type") == 0)

            debug_expander.write(f"Texto embebido: {len(text)} caracteres")
            debug_expander.write(
                f"Bloques totales: {len(blocks)} | "
                f"bloques texto: {text_blocks} | "
                f"bloques imagen: {image_blocks}"
            )
        except Exception as e:
            debug_expander.write(f"No se pudo leer page.get_text('dict'): {e}")

    # Si trae suficiente texto embebido, usarlo
    if len(text) > 40:
        if DEBUG_MODE and debug_expander:
            debug_expander.write("Se usará texto embebido.")
            if text:
                debug_expander.text_area(
                    f"Preview texto embebido página {page_number}",
                    text[:2000],
                    height=220
                )
        return text

    # Si no, usar OCR simple con escala 1 + preproceso
    if DEBUG_MODE and debug_expander:
        debug_expander.write("Se usará OCR.")

    try:
        zoom = 1
        pix = page.get_pixmap(
            matrix=fitz.Matrix(zoom, zoom),
            colorspace=fitz.csGRAY,
            alpha=False
        )

        img = Image.frombytes(
            "L",
            [pix.width, pix.height],
            pix.samples
        )

        img = preprocess_for_ocr(img)

        text_ocr, ocr_error = ocr_with_timeout(img, timeout=30)
        text_ocr = normalize_text(text_ocr)

        if DEBUG_MODE and debug_expander:
            debug_expander.write(f"OCR caracteres: {len(text_ocr)}")
            debug_expander.write(f"Error OCR: {ocr_error}")
            if text_ocr:
                debug_expander.text_area(
                    f"Preview OCR página {page_number}",
                    text_ocr[:2000],
                    height=220
                )

        del pix, img
        gc.collect()

        return text_ocr

    except Exception as e:
        if DEBUG_MODE and debug_expander:
            debug_expander.write(f"Fallo OCR en página {page_number}: {e}")
        return ""


# ----------------------------
# BUSCAR PALABRAS
# ----------------------------

def search_keywords(text):
    results = []
    seen = set()

    if not text:
        return results

    for kw, patterns in KEYWORDS.items():
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                start = max(match.start() - 60, 0)
                end = min(match.end() + 60, len(text))

                phrase = text[start:end]
                phrase = re.sub(r"\s+", " ", phrase).strip()

                phrase_key = phrase.lower()
                if phrase_key in seen:
                    continue
                seen.add(phrase_key)

                highlighted = re.sub(
                    pattern,
                    r"<span style='color:red;font-weight:bold'>\g<0></span>",
                    phrase,
                    flags=re.IGNORECASE
                )

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

            text = extract_text(page, page_number=i + 1, debug_expander=debug_expander)
            results = search_keywords(text)

            if DEBUG_MODE and debug_expander:
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