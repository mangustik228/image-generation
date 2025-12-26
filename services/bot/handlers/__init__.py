from aiogram import Router

from .start import router as start_router
from .parsing import router as parsing_router
from .generation import router as generation_router
from .status import router as status_router
from .publish import router as publish_router


def get_all_routers() -> list[Router]:
    return [
        start_router,
        parsing_router,
        generation_router,
        status_router,
        publish_router,
    ]
