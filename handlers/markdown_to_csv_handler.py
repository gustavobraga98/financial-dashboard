import csv
import io
import re

from pydantic import BaseModel

class MarkdownToCsvModel(BaseModel):
    """
    Model for converting Markdown files to CSV format.
    """
    markdown: str

def execute(payload: MarkdownToCsvModel) -> str:
    markdown = payload.markdown.strip()

    # Encontrar todas as tabelas com regex
    table_blocks = re.findall(
        r"(?:\|[^\n]*\|\s*\n)+", markdown
    )

    outcome = io.StringIO()
    writer = csv.writer(outcome)

    for block in table_blocks:
        lines = block.strip().split("\n")

        # Remove linhas separadoras (com ---, pode ter espaços)
        content_lines = [
            line for line in lines if not re.match(r"\|\s*-{3,}", line)
        ]

        if not content_lines:
            continue

        # Processar a primeira linha como cabeçalho
        header_cols = [col.strip() for col in content_lines[0].strip('|').split('|')]
        writer.writerow(header_cols)
        expected_len = len(header_cols)

        for line in content_lines[1:]:
            cols = [col.strip() for col in line.strip('|').split('|')]
            # Ajusta o número de colunas com base no cabeçalho
            if len(cols) < expected_len:
                cols.extend([''] * (expected_len - len(cols)))
            elif len(cols) > expected_len:
                cols = cols[:expected_len]
            writer.writerow(cols)

    return outcome.getvalue()
