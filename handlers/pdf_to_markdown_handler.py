import tempfile
from docling.document_converter import DocumentConverter
from pydantic import BaseModel

class ProcessPdfModel(BaseModel):
    """
    Model for processing PDF files.
    """
    pdf_binary: bytes


def execute(payload: ProcessPdfModel) -> str:
    converter = DocumentConverter()

    # Write PDF binary to a temporary file
    with tempfile.NamedTemporaryFile(delete=True, suffix=".pdf") as temp_pdf:
        temp_pdf.write(payload.pdf_binary)
        temp_pdf.flush()  # Ensure all data is written to disk

        # Convert the temporary PDF file to a DoclingDocument object
        doc = converter.convert(temp_pdf.name).document

    # Export the document to Markdown
    markdown_text = doc.export_to_markdown()

    return markdown_text
