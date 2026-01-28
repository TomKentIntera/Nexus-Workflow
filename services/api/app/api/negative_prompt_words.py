from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_session
from ..models import NegativePromptWord

router = APIRouter(prefix="/negative-prompt-words", tags=["negative-prompt-words"])


@router.get("", response_model=list[str])
def get_negative_prompt_words(session: Session = Depends(get_session)) -> list[str]:
    """
    Returns the current list of negative prompt words.
    
    These words are appended to the base negative prompt during image generation.
    """
    words = session.execute(
        select(NegativePromptWord.word).order_by(NegativePromptWord.word.asc())
    ).scalars().all()
    return [str(w) for w in words]


@router.post("", response_model=list[str], status_code=status.HTTP_201_CREATED)
def add_negative_prompt_words(
    words: list[str], session: Session = Depends(get_session)
) -> list[str]:
    """
    Idempotently add words to the negative prompt list.
    
    Returns the full list after update.
    """
    if not words:
        raise HTTPException(status_code=400, detail="No words provided")
    
    # Normalize: strip whitespace and filter empty strings
    incoming = [w.strip() for w in words if w.strip()]
    if not incoming:
        raise HTTPException(status_code=400, detail="No valid words provided after normalization")
    
    existing = set(
        session.execute(
            select(NegativePromptWord.word).where(NegativePromptWord.word.in_(incoming))
        ).scalars().all()
    )
    to_add = [w for w in incoming if w not in existing]
    for w in to_add:
        session.add(NegativePromptWord(word=w))
    
    session.commit()
    all_words = session.execute(
        select(NegativePromptWord.word).order_by(NegativePromptWord.word.asc())
    ).scalars().all()
    return [str(w) for w in all_words]


@router.delete("/{word}", response_model=list[str])
def delete_negative_prompt_word(word: str, session: Session = Depends(get_session)) -> list[str]:
    """
    Delete a negative prompt word by exact match.
    
    Returns the full list after deletion.
    """
    word = (word or "").strip()
    if not word:
        raise HTTPException(status_code=400, detail="Word is required")
    
    row = session.execute(
        select(NegativePromptWord).where(NegativePromptWord.word == word)
    ).scalar_one_or_none()
    if row:
        session.delete(row)
        session.commit()
    
    all_words = session.execute(
        select(NegativePromptWord.word).order_by(NegativePromptWord.word.asc())
    ).scalars().all()
    return [str(w) for w in all_words]

