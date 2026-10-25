from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db import get_db
from app.models import Category
from app.schemas import CategoryResponse

router = APIRouter(prefix="/meta", tags=["meta"])

# get all available grievance categories
@router.get("/categories", response_model=List[CategoryResponse])
def get_categories(db: Session = Depends(get_db)):
    categories = db.execute(select(Category).order_by(Category.name.asc())).scalars().all()
    return categories

