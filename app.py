import streamlit as st
import streamlit.components.v1 as components
import fitz
import pytesseract
from PIL import Image, ImageOps, ImageFilter
import re
import gc
import hashlib
import base64
import os

# ----------------------------
# CONFIG STREAMLIT
# ----------------------------

st.set_page_config(layout="wide", page_title="Noticias Yucatán")
st.set_option("client.showErrorDetails", False)

# Si lo necesitas en Windows, descomenta esta línea:
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

DEBUG_MODE = False

# ----------------------------
# CONFIG OCR / RENDER
# ----------------------------

OCR_DPI = 120
OCR_LANG = "spa+eng"
MIN_CHARS_TEXTO_EMBEDIDO = 40

DISPLAY_DPI = 100
DISPLAY_WIDTH = 220

# ----------------------------
# PALABRAS CLAVE
# ----------------------------

KEYWORDS = {
    "Yucatán": [
        r"\bYucat[aá]n\b",r"\bYUC\b"
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
    "Gobernador": [
        r"\bGobernador\s+de\s+Yucat[aá]n\b"
    ],
    "Puerto Progreso": [
        r"\bPuerto+\s+Progresp\b"
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
    text = text.replace("\r", "\n")
    text = text.replace("\t", " ")
    text = re.sub(r"[ \f\v]+", " ", text)

    return text.strip()


def limpiar_texto_para_busqueda(text: str) -> str:
    """
    Limpieza estricta:
    1) une palabras partidas por guión + salto de línea
    2) elimina guiones restantes
    3) deja solo letras, números, espacios, vocales con acento y ñ
    """
    if not text:
        return ""

    text = text.replace("\x00", " ")
    text = text.replace("\r", "\n")

    prev = None
    while prev != text:
        prev = text
        text = re.sub(
            r"([A-Za-zÁÉÍÓÚáéíóúÑñ])\-\s*\n\s*([A-Za-zÁÉÍÓÚáéíóúÑñ])",
            r"\1\2",
            text
        )

    text = text.replace("\n", " ")
    text = text.replace("-", "")
    text = re.sub(r"[^0-9A-Za-zÁÉÍÓÚáéíóúÑñ ]+", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalizar_para_busqueda(text: str) -> str:
    """
    Normaliza solo para búsqueda interna:
    - minúsculas
    - quita acentos
    - conserva ñ
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
        "Á": "a",
        "É": "e",
        "Í": "i",
        "Ó": "o",
        "Ú": "u",
    }

    for a, b in reemplazos.items():
        text = text.replace(a, b)

    text = re.sub(r"\s+", " ", text)
    return text.strip()


def preprocess_for_ocr(img: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(img)
    gray = ImageOps.autocontrast(gray)
    gray = gray.filter(ImageFilter.SHARPEN)
    bw = gray.point(lambda x: 0 if x < 180 else 255, "1")
    return bw.convert("L")


def build_normalized_mapping(original_text: str):
    normalized_chars = []
    index_map = []

    replacements = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
        "Á": "a", "É": "e", "Í": "i", "Ó": "o", "Ú": "u",
    }

    for idx, ch in enumerate(original_text):
        ch2 = replacements.get(ch, ch)
        ch2 = ch2.lower()
        normalized_chars.append(ch2)
        index_map.append(idx)

    return "".join(normalized_chars), index_map


def make_unique_page_key(file_name: str, page_number: int) -> str:
    raw = f"{file_name}__{page_number}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def bytes_to_data_url(png_bytes: bytes) -> str:
    b64 = base64.b64encode(png_bytes).decode("utf-8")
    return f"data:image/png;base64,{b64}"


def inferir_periodico_desde_archivo(nombre_archivo: str) -> str:
    base = os.path.splitext(os.path.basename(nombre_archivo))[0]
    return base.strip()


def render_image_actions(png_bytes: bytes, unique_key: str, width_px: int, file_name: str, page_number: int):
    data_url = bytes_to_data_url(png_bytes)
    download_name = f"{os.path.splitext(file_name)[0]}_pagina_{page_number}.png"

    html = f"""
    <div style="display:flex; flex-direction:column; gap:8px;">
        <div style="display:flex; gap:8px; flex-wrap:wrap;">
            <button
                onclick="copyImage_{unique_key}()"
                style="
                    padding:8px 12px;
                    border:1px solid #CCC;
                    border-radius:8px;
                    background:#F8F8F8;
                    color:#111;
                    font-size:14px;
                    cursor:pointer;
                "
            >
                Copiar imagen al portapapeles
            </button>

            <a
                href="{data_url}"
                download="{download_name}"
                style="
                    text-decoration:none;
                    padding:8px 12px;
                    border:1px solid #CCC;
                    border-radius:8px;
                    background:#F8F8F8;
                    color:#111;
                    font-size:14px;
                    display:inline-block;
                "
            >
                Descargar PNG
            </a>
        </div>

        <img
            src="{data_url}"
            style="
                width:{width_px}px;
                height:auto;
                border:1px solid #DDD;
                border-radius:8px;
                display:block;
            "
        />

        <div id="msg_{unique_key}" style="font-size:12px; color:#666;"></div>
        <div style="font-size:12px; color:#666;">Puedes dar clic derecho en la imagen para guardar manualmente.</div>
    </div>

    <script>
    async function copyImage_{unique_key}() {{
        const msg = document.getElementById("msg_{unique_key}");
        try {{
            const response = await fetch("{data_url}");
            const blob = await response.blob();

            await navigator.clipboard.write([
                new ClipboardItem({{
                    [blob.type]: blob
                }})
            ]);

            msg.innerText = "Imagen copiada al portapapeles.";
        }} catch (err) {{
            msg.innerText = "No se pudo copiar automáticamente desde este navegador.";
        }}
    }}
    </script>
    """
    components.html(html, height=width_px + 120)


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
# RENDER DE PÁGINA
# ----------------------------

def render_page_png_bytes(page, dpi=DISPLAY_DPI) -> bytes:
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    return pix.tobytes("png")


# ----------------------------
# EXTRAER TEXTO
# ----------------------------

def extract_text(page, page_number=None, debug_expander=None):
    texto_raw = ""

    try:
        texto_raw = page.get_text("text") or ""
    except Exception as e:
        texto_raw = ""
        if DEBUG_MODE and debug_expander:
            debug_expander.write(f"Error extrayendo texto embebido: {e}")

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

    if len(texto_original) >= MIN_CHARS_TEXTO_EMBEDIDO:
        if DEBUG_MODE and debug_expander and texto_original:
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
    results = []
    seen = set()

    if not text_original or not text_search:
        return results

    normalized_original, index_map = build_normalized_mapping(text_original)

    for kw, patterns in KEYWORDS.items():
        for pattern in patterns:
            pattern_norm = normalizar_para_busqueda(pattern)

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
# UI CSS
# ----------------------------

st.markdown("""
<style>
.small-preview-card {
    border: 1px solid #DDD;
    border-radius: 10px;
    padding: 10px;
    margin-bottom: 14px;
    background: #FFF;
}
.small-preview-title {
    font-size: 15px;
    font-weight: 600;
    margin-bottom: 8px;
}
.small-preview-meta {
    font-size: 12px;
    color: #666;
    margin-bottom: 8px;
}
.periodico-h5 {
    margin-top: 0.3rem;
    margin-bottom: 0.7rem;
    font-size: 1.05rem;
    font-weight: 600;
}
</style>
""", unsafe_allow_html=True)

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
            pdf_bytes = file.read()
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception:
            st.warning("No se pudo abrir el PDF")
            continue

        total = len(doc)
        progress = st.progress(0)
        periodico = inferir_periodico_desde_archivo(file.name)

        for i, page in enumerate(doc):
            page_number = i + 1
            progress.progress((i + 1) / total)

            debug_expander = None
            if DEBUG_MODE:
                debug_expander = st.expander(f"Diagnóstico página {page_number}", expanded=False)

            extracted = extract_text(page, page_number=page_number, debug_expander=debug_expander)
            text_original = extracted["text_original"]
            text_search = extracted["text_search"]

            results = search_keywords(text_original, text_search)

            if DEBUG_MODE and debug_expander:
                debug_expander.write(f"Fuente usada: {extracted['source']}")
                debug_expander.write(f"Coincidencias encontradas: {len(results)}")

            if results:
                page_png_bytes = render_page_png_bytes(page, dpi=DISPLAY_DPI)
                unique_key = make_unique_page_key(file.name, page_number)

                col1, col2 = st.columns([1, 3])

                with col1:
                    st.markdown(
                        f"""
                        <div class="small-preview-card">
                            <div class="small-preview-title">Página {page_number}</div>
                            <div class="small-preview-meta">Copia al portapapeles o guarda la imagen manualmente</div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

                    render_image_actions(
                        png_bytes=page_png_bytes,
                        unique_key=unique_key,
                        width_px=DISPLAY_WIDTH,
                        file_name=file.name,
                        page_number=page_number
                    )

                with col2:
                    st.markdown(f"### Página {page_number}")
                    st.markdown(f"<h5 class='periodico-h5'>{periodico}</h5>", unsafe_allow_html=True)

                    for r in results:
                        st.markdown(r, unsafe_allow_html=True)

                    st.caption(f"Fuente de texto usada: {extracted['source']}")

                summary[file.name].append(
                    f"Página {page_number}: " + re.sub("<[^<]+?>", "", results[0])
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