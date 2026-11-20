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

    url = f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/{bucket}/{storage_path}"
    try:
        response = httpx.get(url, headers=_service_headers(), timeout=30.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise StorageError(str(exc)) from exc
    return response.content


def _service_headers() -> dict[str, str]:
    assert settings.SUPABASE_SERVICE_ROLE_KEY is not None
    return {
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
    }


def create_signed_image_url(
    storage_path: str, expires_in: int = 600, bucket: str = DEFAULT_BILL_IMAGE_BUCKET
) -> str:
    """Mints a short-lived URL for viewing one bill image. The bucket stays
    private (CLAUDE.md SS9: bill images can contain sensitive purchase
    data); the API route that calls this has already checked that the
    requester shares the bill's group, so any group member can view the
    receipt - not only the person who uploaded it."""
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
        raise StorageError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY is not configured.")

    base = settings.SUPABASE_URL.rstrip("/")
    url = f"{base}/storage/v1/object/sign/{bucket}/{storage_path}"
    try:
        response = httpx.post(
            url, headers=_service_headers(), json={"expiresIn": expires_in}, timeout=15.0
        )
        response.raise_for_status()
        signed_path = response.json()["signedURL"]
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise StorageError(str(exc)) from exc
    return f"{base}/storage/v1{signed_path}"
