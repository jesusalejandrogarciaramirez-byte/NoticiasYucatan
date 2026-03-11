# app.py

import streamlit as st
import fitz
import pytesseract
from PIL import Image
import io
import re
import base64
import gc
import threading

# ----------------------------

# CONFIG STREAMLIT CLOUD

# ----------------------------

st.set_page_config(layout="wide", page_title="Noticias Yucatán")
st.set_option('client.showErrorDetails', False)

# ----------------------------

# PALABRAS CLAVE

# ----------------------------

KEYWORDS = {
"Yucatán":[r"\bYucat[aá]n\b"],
"YUC":[r"\bYUC\b"],
"yucateco":[r"\byucateco\b"],
"Mérida":[r"\bM[eé]rida\b"],
"Tren Maya":[r"\bTren Maya\b"],
"Gobernador":[r"\bGobernador de Yucat[aá]n\b"],
"Huacho Díaz Mena":[
r"\bJoaqu[ií]n ?Huacho D[ií]az Mena\b",
r"\bHuacho D[ií]az Mena\b"
]
}

# ----------------------------

# OCR CON TIMEOUT

# ----------------------------

def ocr_with_timeout(img, timeout=20):

```
result={"text":""}

def target():
    try:
        result["text"]=pytesseract.image_to_string(img)
    except:
        result["text"]=""

thread=threading.Thread(target=target)
thread.start()
thread.join(timeout)

if thread.is_alive():
    return ""

return result["text"]
```

# ----------------------------

# MINIATURA

# ----------------------------

def create_thumbnail(page):

```
pix=page.get_pixmap(matrix=fitz.Matrix(0.35,0.35))

img=Image.frombytes(
    "RGB",
    [pix.width,pix.height],
    pix.samples
)

img.thumbnail((200,200))

buffer=io.BytesIO()
img.save(buffer,format="PNG")
buffer.seek(0)

base64_img=base64.b64encode(buffer.getvalue()).decode()

del pix,img,buffer
gc.collect()

return base64_img
```

# ----------------------------

# EXTRAER TEXTO

# ----------------------------

def extract_text(page):

```
text=page.get_text("text")

if len(text.strip())>40:
    return text

# usar OCR si no hay texto
pix=page.get_pixmap(matrix=fitz.Matrix(0.5,0.5),colorspace=fitz.csGRAY)

img=Image.frombytes(
    "L",
    [pix.width,pix.height],
    pix.samples
)

text=ocr_with_timeout(img)

del pix,img
gc.collect()

return text
```

# ----------------------------

# BUSCAR PALABRAS

# ----------------------------

def search_keywords(text):

```
results=[]

for kw,patterns in KEYWORDS.items():

    for pattern in patterns:

        for match in re.finditer(pattern,text,re.IGNORECASE):

            start=max(match.start()-60,0)
            end=min(match.end()+60,len(text))

            phrase=text[start:end]
            phrase=re.sub(r'\s+',' ',phrase)

            highlighted=re.sub(
                pattern,
                r"<span style='color:red;font-weight:bold'>\g<0></span>",
                phrase,
                flags=re.IGNORECASE
            )

            results.append(highlighted)

return results
```

# ----------------------------

# UI

# ----------------------------

st.markdown("<h1 style='text-align:center'>Noticias Yucatán</h1>",unsafe_allow_html=True)
st.markdown("<h3 style='text-align:center;color:gray'>Análisis automático de PDFs</h3>",unsafe_allow_html=True)

st.write("---")

uploaded_files=st.file_uploader(
"Sube tus PDFs",
type=["pdf"],
accept_multiple_files=True
)

summary={}

# ----------------------------

# PROCESAMIENTO

# ----------------------------

if uploaded_files:

```
for file in uploaded_files:

    st.header(file.name)

    summary[file.name]=[]

    try:
        doc=fitz.open(stream=file.read(),filetype="pdf")
    except:
        st.warning("No se pudo abrir el PDF")
        continue

    total=len(doc)

    progress=st.progress(0)

    for i,page in enumerate(doc):

        progress.progress((i+1)/total)

        text=extract_text(page)

        results=search_keywords(text)

        if results:

            thumb=create_thumbnail(page)

            html=""

            for r in results:
                html+=r+"<br><br>"

            st.markdown(f"""

            <div style="display:flex;
                        border:1px solid #ccc;
                        padding:10px;
                        margin-bottom:15px;
                        border-radius:6px;
                        background:#f5f5f5;
                        color:black">

                <img src="data:image/png;base64,{thumb}" width="200"
                style="margin-right:15px">

                <div>
                <h3>Página {i+1}</h3>
                {html}
                </div>

            </div>

            """,unsafe_allow_html=True)

            summary[file.name].append(
                f"Página {i+1}: "+re.sub('<[^<]+?>','',results[0])
            )

        gc.collect()

    progress.progress(1.0)

    if summary[file.name]:
        st.success("Procesamiento terminado con coincidencias")
    else:
        st.info("No se encontraron coincidencias")
```

# ----------------------------

# RESUMEN FINAL

# ----------------------------

final=""

for pdf,entries in summary.items():

```
final+=pdf+"\n"

if entries:
    final+="\n".join(entries)
else:
    final+="Sin coincidencias"

final+="\n\n"
```

if final:
st.text_area(
"Resumen final (copiar)",
final,
height=400
)
