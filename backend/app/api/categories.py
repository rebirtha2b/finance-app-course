"""Category CRUD.

The tree is deliberately limited to two levels (parent -> leaf). Deeper trees
make every rollup query recursive for no practical benefit.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_session
from app.models import Budget, Category, CategoryKind, RecurringRule, Transaction
from app.schemas.core import (
    CategoryCreate,
    CategoryOut,
    CategoryTreeOut,
    CategoryUpdate,
)

router = APIRouter(prefix="/api/categories", tags=["categories"])


def _validate_parent(session: Session, parent_id: int | None, kind: CategoryKind) -> None:
    if parent_id is None:
        return
    parent = session.get(Category, parent_id)
    if parent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Parent category not found")
    if parent.parent_id is not None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Categories are limited to two levels; the chosen parent is already a child.",
        )
    if parent.kind != kind:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "A category must have the same kind (income/expense) as its parent.",
        )


@router.get("", response_model=list[CategoryOut])
def list_categories(
    kind: CategoryKind | None = None,
    include_archived: bool = False,
    session: Session = Depends(get_session),
) -> list[Category]:
    stmt = select(Category).order_by(Category.name)
    if kind is not None:
        stmt = stmt.where(Category.kind == kind)
    if not include_archived:
        stmt = stmt.where(Category.archived.is_(False))
    return list(session.scalars(stmt))


@router.get("/tree", response_model=list[CategoryTreeOut])
def category_tree(
    kind: CategoryKind | None = None,
    include_archived: bool = False,
    session: Session = Depends(get_session),
) -> list[CategoryTreeOut]:
    """Top-level categories with their children nested — what pickers need."""
    stmt = (
        select(Category)
        .where(Category.parent_id.is_(None))
        .options(selectinload(Category.children))
        .order_by(Category.name)
    )
    if kind is not None:
        stmt = stmt.where(Category.kind == kind)
    if not include_archived:
        stmt = stmt.where(Category.archived.is_(False))

    result = []
    for parent in session.scalars(stmt):
        children = [
            c for c in parent.children if include_archived or not c.archived
        ]
        result.append(
            CategoryTreeOut(
                **CategoryOut.model_validate(parent).model_dump(),
                children=sorted(
                    (CategoryOut.model_validate(c) for c in children),
                    key=lambda c: c.name,
                ),
            )
        )
    return result


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: CategoryCreate, session: Session = Depends(get_session)
) -> Category:
    _validate_parent(session, payload.parent_id, payload.kind)
    duplicate = session.scalar(
        select(Category).where(
            Category.name == payload.name, Category.parent_id == payload.parent_id
        )
    )
    if duplicate:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A category with that name already exists here"
        )
    category = Category(**payload.model_dump())
    session.add(category)
    session.commit()
    return category


def _get_or_404(session: Session, category_id: int) -> Category:
    category = session.get(Category, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    return category


@router.patch("/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: int, payload: CategoryUpdate, session: Session = Depends(get_session)
) -> Category:
    category = _get_or_404(session, category_id)
    data = payload.model_dump(exclude_unset=True)

    if "parent_id" in data:
        new_parent = data["parent_id"]
        if new_parent == category.id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "A category cannot be its own parent"
            )
        # Moving a parent that has children under another parent would create a
        # third level via its subtree.
        if new_parent is not None and category.children:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "This category has children; move or delete them before nesting it.",
            )
        _validate_parent(session, new_parent, category.kind)

    for field, value in data.items():
        setattr(category, field, value)
    session.commit()
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: int, session: Session = Depends(get_session)) -> None:
    category = _get_or_404(session, category_id)

    if category.children:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Delete or move the child categories first"
        )

    for model, label in (
        (Transaction, "transactions"),
        (RecurringRule, "recurring rules"),
        (Budget, "budgets"),
    ):
        used = session.scalar(
            select(model.id).where(model.category_id == category_id).limit(1)
        )
        if used:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Category is used by existing {label}; archive it instead of deleting.",
            )

    session.delete(category)
    session.commit()
