from pydantic import BaseModel

class NewCategoryRegisteredDataModel(BaseModel):
    sucess: bool
    message: str