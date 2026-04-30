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


def format_status_result(result: StatusCheckResult, show_current: bool = False) -> str:
    """Форматирует результат проверки статусов."""
    lines = [
        "📊 *Статистика обработки:*",
        "",
        "*Batch Jobs:*",
        f"├ Всего: {result.total_jobs}",
        f"├ ✅ Успешно: {result.jobs_succeeded}",
        f"├ ⏳ В очереди: {result.jobs_pending}",
        f"├ 🔄 Выполняются: {result.jobs_running}",
        f"├ ❌ Ошибки: {result.jobs_failed}",
        f"└ 🚫 Отменены: {result.jobs_cancelled}",
        "",
        f"⏳ Изображений в очереди/выполняются: *{result.images_pending}* шт.",
    ]

    if show_current and (
        result.current_images_succeeded > 0 or result.current_images_failed > 0
    ):
        lines.append("")
        lines.append("*Обработано сейчас:*")
        lines.append(f"├ ✅ Успешно: {result.current_images_succeeded}")
        lines.append(f"└ ❌ С ошибками: {result.current_images_failed}")

    if result.errors_grouped:
        lines.append("")
        lines.append("*Группировка ошибок:*")
        for error, count in sorted(result.errors_grouped.items(), key=lambda x: -x[1])[
            :10
        ]:
            error_short = error[:80] + "..." if len(error) > 80 else error
            error_short = (
                error_short.replace("_", "\\_")
                .replace("*", "\\*")
                .replace("`", "\\`")
                .replace("[", "\\[")
            )
            lines.append(f"• {error_short}: {count}")

    return "\n".join(lines)
