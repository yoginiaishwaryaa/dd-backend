from pydantic import BaseModel


# Generic message response schema
class Message(BaseModel):
    message: str
