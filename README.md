# Noticias Yucatán – Analizador de PDFs

Aplicación web desarrollada con **Streamlit** para analizar documentos PDF y detectar automáticamente menciones relacionadas con **Yucatán**, personas, lugares y temas específicos mediante búsqueda de palabras clave y OCR.

La herramienta permite subir múltiples PDFs, analizar su contenido y mostrar coincidencias con contexto visual de cada página.

---

# Características

* Carga de **múltiples PDFs**
* Detección automática de texto
* **OCR automático** si el PDF es escaneado
* Búsqueda inteligente con **expresiones regulares**
* Visualización de resultados con **miniaturas de página**
* **Resaltado de palabras clave**
* Resumen final listo para copiar
* Optimizado para **Streamlit Cloud**

---

# Palabras clave detectadas

La aplicación busca menciones relacionadas con:

* Yucatán
* YUC
* yucateco
* Mérida
* Tren Maya
* Gobernador de Yucatán
* Huacho Díaz Mena

Las coincidencias se muestran con contexto dentro del documento.

---

# Tecnologías utilizadas

* Python
* Streamlit
* PyMuPDF
* Tesseract OCR
* Pillow
* Regex

---

# Instalación local

1. Clonar el repositorio

```
git clone https://github.com/TU_USUARIO/noticias-yucatan.git
```

2. Entrar al proyecto

```
cd noticias-yucatan
```

3. Instalar dependencias

```
pip install -r requirements.txt
```

4. Ejecutar la aplicación

```
streamlit run app.py
```

---

# Uso

1. Abrir la aplicación en el navegador
2. Subir uno o varios archivos PDF
3. El sistema analizará automáticamente cada página
4. Se mostrarán las coincidencias encontradas
5. Al final se genera un **resumen con todas las menciones**

---

# Estructura del proyecto

```
noticias-yucatan/
│
├── app.py
├── requirements.txt
├── packages.txt
└── README.md
```

---

# Despliegue en Streamlit Cloud

1. Subir el proyecto a GitHub
2. Ir a:

https://share.streamlit.io

3. Crear una nueva app seleccionando:

* repositorio
* rama `main`
* archivo `app.py`

Streamlit instalará automáticamente las dependencias.

---

# Limitaciones

* El OCR puede ser más lento en PDFs muy grandes
* Documentos escaneados de baja calidad pueden reducir la precisión

---

# Licencia

Proyecto de uso libre para análisis de documentos y monitoreo de medios.
