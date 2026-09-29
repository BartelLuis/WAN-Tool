from typing import TypeVar

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.database import Base

T = TypeVar("T", bound=Base)


def hole_oder_404(db: Session, model: type[T], obj_id: int) -> T:
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{model.__name__} {obj_id} nicht gefunden")
    return obj
