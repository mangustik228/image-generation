from services.batch import StatusCheckResult
from services.parser.schemas import ParseStats


def format_stats(stats: ParseStats, added_count: int) -> str:
    lines = [
        "📊 *Результаты парсинга:*",
        f"├ Каталогов: {stats.catalogs_parsed}/{stats.catalogs_total}",
        f"├ Товаров: {stats.products_parsed}/{stats.products_total}",
        f"├ Изображений: {stats.images_total}",
        f"└ Добавлено в таблицу: {added_count}",
    ]
    if stats.catalogs_failed or stats.products_failed:
        lines.append(
            f"\n⚠️ Ошибки: каталогов={stats.catalogs_failed}, товаров={stats.products_failed}"
        )
    return "\n".join(lines)


def format_status_result(result: StatusCheckResult) -> str:
    """Форматирует результат проверки статусов."""
    total_active = result.jobs_pending + result.jobs_running

    if total_active == 0:
        return "✅ Нет активных заданий в очереди"

    lines = [
        "📊 *Статус обработки:*",
        f"⏳ Изображений в очереди/выполняются: *{result.total_images}* шт.",
        "",
        f"├ Batch jobs в очереди: {result.jobs_pending}",
        f"└ Batch jobs выполняются: {result.jobs_running}",
    ]

    return "\n".join(lines)
