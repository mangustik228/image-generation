from dataclasses import dataclass, field


@dataclass
class ParseResult:
    model: str
    image_url: str
    position: int
    category: str
    page_url: str
    order_number: str = ""


@dataclass
class ParseStats:
    catalogs_total: int = 0
    catalogs_parsed: int = 0
    catalogs_failed: int = 0
    products_total: int = 0
    products_parsed: int = 0
    products_failed: int = 0
    images_total: int = 0
    errors: list[str] = field(default_factory=list)
