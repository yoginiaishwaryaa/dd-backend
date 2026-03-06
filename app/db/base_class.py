from sqlalchemy.orm import as_declarative
from sqlalchemy import MetaData


@as_declarative()
class Base:
    __tablename__: str
    metadata: MetaData

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
