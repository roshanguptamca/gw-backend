from pypdf import PdfReader
from docx import Document as DocxDocument
import pytesseract
from PIL import Image


def extract_pdf(path):
    reader = PdfReader(path)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text


def extract_docx(path):
    doc = DocxDocument(path)
    return "\n".join(p.text for p in doc.paragraphs)


def extract_image(path):
    return pytesseract.image_to_string(Image.open(path))
