from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.user import UserOut

router = APIRouter()


@router.get("/me", response_model=UserOut)
def read_current_user(current_user: User = Depends(get_current_user)):
    """Sanity-check endpoint: proves a client's Supabase token round-trips
    through auth and resolves to a real local User row."""
    return current_user
