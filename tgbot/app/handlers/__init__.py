from aiogram import Router

from app.handlers import admin, lead


def get_router() -> Router:
    """Порядок важен: lead с общим fallback идёт последним."""
    root = Router(name="root")
    root.include_router(admin.router)
    root.include_router(lead.router)
    return root
