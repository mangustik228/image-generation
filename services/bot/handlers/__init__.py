from aiogram import Router

from .generation import router as generation_router
from .help import router as help_router
from .inline import router as inline_router
from .parsing import router as parsing_router
from .prompt import router as prompt_router
from .publish import router as publish_router
from .start import router as start_router
from .status import router as status_router


def get_all_routers() -> list[Router]:
    return [
        start_router,
        parsing_router,
        generation_router,
        status_router,
        publish_router,
        prompt_router,
        inline_router,
        help_router,
    ]
