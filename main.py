from fastapi import FastAPI, UploadFile, File, Form, HTTPException
import pandas as pd
from io import StringIO
from typing import Optional
from handlers import pdf_to_markdown, markdown_to_csv, process_csv
import uvicorn

app = FastAPI()

@app.post("/process_file/")
async def process_file(
    file: UploadFile = File(...),
    separator: Optional[str] = Form(",")  # <--- Aceita como parte do formulário
):
    contents = await file.read()

    if file.content_type == "application/pdf":
        markdown = pdf_to_markdown.execute(
            pdf_to_markdown.ProcessPdfModel(pdf_binary=contents)
        )
        csv = markdown_to_csv.execute(
            markdown_to_csv.MarkdownToCsvModel(markdown=markdown)
        )
        df = pd.read_csv(StringIO(csv), sep=separator)

    elif file.content_type in ["text/csv", "application/vnd.ms-excel", "text/plain"]:
        df = process_csv.execute(
            process_csv.ProcessCSVModel(csv_content=contents.decode("utf-8"), separator=separator)
        )

    else:
        raise HTTPException(status_code=400, detail="File type not supported")
    
    

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
