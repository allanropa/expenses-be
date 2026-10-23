from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth_context, require_csrf
from app.api.ledger_schemas import CategoryCreate, CategoryResponse
from app.db.session import get_db
from app.models.ledger import Category

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("", response_model=list[CategoryResponse])
def list_categories(archived: bool = Query(False), context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    return db.query(Category).filter(Category.user_id == context.user.id, Category.is_archived.is_(archived)).order_by(Category.name).all()


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: CategoryCreate,
    context: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    category = Category(user_id=context.user.id, name=payload.name.strip(), kind=payload.kind)
    db.add(category)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Ya existe una categoría con ese nombre") from None
    db.refresh(category)
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_category(
    category_id: int,
    context: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    category = db.query(Category).filter(Category.id == category_id, Category.user_id == context.user.id).one_or_none()
    if category is None:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")
    category.is_archived = True
    db.commit()


@router.post("/{category_id}/unarchive", response_model=CategoryResponse)
def unarchive_category(category_id: int, context: AuthContext = Depends(require_csrf), db: Session = Depends(get_db)):
    category = db.query(Category).filter(Category.id == category_id, Category.user_id == context.user.id).one_or_none()
    if category is None:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")
    category.is_archived = False
    db.commit()
    db.refresh(category)
    return category
