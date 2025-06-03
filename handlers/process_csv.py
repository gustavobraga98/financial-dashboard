from pydantic import BaseModel
import pandas as pd
from io import StringIO

class ProcessCSVModel(BaseModel):
    csv_content: str
    separator: str = ','  # Default separator is comma

def execute(payload: ProcessCSVModel):
    df = pd.read_csv(StringIO(payload.csv_content), sep=payload.separator, header = None)
    df[2] = (df[2].str.replace(".", "", regex=False).str.replace(",", ".", regex=False).astype(float))
    return df