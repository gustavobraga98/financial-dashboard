from pydantic import BaseModel

class NewTransactionRegisteredDataModel(BaseModel):
    sucess: bool
    message: str