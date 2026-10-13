import httpx

from app.core.config import settings

DEFAULT_BILL_IMAGE_BUCKET = "bill-images"


class StorageError(Exception):
    pass


def fetch_bill_image_bytes(storage_path: str, bucket: str = DEFAULT_BILL_IMAGE_BUCKET) -> bytes:
    """Fetches an image from Supabase Storage using the service-role key -
    server-side only, never exposed to Web/Mobile clients (those upload
    directly to Storage with their own, more restricted, Supabase client;
    see app/schemas/bill.py's BillCreate docstring). design.md SS1: Supabase
    Storage is the chosen v1 image store."""
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
        raise StorageError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY is not configured.")

    url = f"{settings.SUPABASE_URL}/storage/v1/object/{bucket}/{storage_path}"
    headers = {
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
    }
    try:
        response = httpx.get(url, headers=headers, timeout=30.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise StorageError(str(exc)) from exc
    return response.content
