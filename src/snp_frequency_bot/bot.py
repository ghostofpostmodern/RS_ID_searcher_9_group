import asyncio
import logging
import os
import re
from typing import Any, Dict

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    FSInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)

from .config import settings
from .logging_config import setup_logging
from .cache_manager import cache_manager
from . import ncbi_client
from .snp_analyzer import summarize_snp
from .plot_generator import generate_plots
from .extended_summary import build_extended_summary
from .pdf_builder import build_pdf_report

# Разрешаем rs/RS, префикс rs + цифры
RSID_REGEX = re.compile(r"^rs\d+$", re.IGNORECASE)

REPORTS_DIR = "reports"  # будет /app/reports внутри контейнера

EXAMPLE_RSIDS = [
    "rs1801133",  # MTHFR
    "rs429358",   # APOE
    "rs7412",     # APOE
    "rs1695",     # GSTP1
    "rs7903146",  # TCF7L2
]


async def handle_start(message: Message) -> None:
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Пример rs1801133",
                    callback_data="example:rs1801133",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Пример rs429358",
                    callback_data="example:rs429358",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Пример rs7412",
                    callback_data="example:rs7412",
                )
            ],
        ]
    )

    text = (
        "Привет! Я бот для анализа частот генетических вариантов по rsID.\n\n"
        "Основная команда:\n"
        "  /get rs12345 — получить данные по указанному rsID\n\n"
        "Формат rsID:\n"
        "  • префикс 'rs' (регистр неважен)\n"
        "  • затем только цифры\n"
        "Пример: /get rs1801133\n\n"
        "Для демонстрации можете нажать на одну из кнопок с примерами ниже."
    )

    await message.answer(text, reply_markup=keyboard)


async def handle_help(message: Message) -> None:
    text = (
        "/start — краткое приветствие и инструкция\n"
        "/help — подробная справка по использованию бота\n"
        "/get <rsid> — получить данные по rsID\n"
        "    Формат: /get rs12345 (префикс rs + цифры)\n"
        "    Пример: /get rs1801133\n\n"
        "/history — показать ваши запросы за последние 24 часа\n"
        "/about — информация о боте\n"
        "/stop — остановить взаимодействие с ботом (бот больше не будет отвечать до новых команд)"
    )
    await message.answer(text)


async def handle_about(message: Message) -> None:
    text = (
        "SNP Frequency Bot\n\n"
        "Источник данных:\n"
        " • NCBI dbSNP API (https://api.ncbi.nlm.nih.gov/variation/v0/refsnp/)\n\n"
        "Что делает бот:\n"
        " • Получает популяционные частоты аллелей по rsID\n"
        " • По упрощённой модели Харди–Вайнберга рассчитывает частоты генотипов\n"
        " • Строит графики распределения частот\n\n"
        "Ограничения:\n"
        f" • Не более {settings.max_requests_per_hour} запросов в час на пользователя\n"
        " • Данные зависят от актуальности и полноты баз NCBI\n"
        " • Возможны различия между исследованиями/популяциями\n\n"
        "Дисклеймер:\n"
        " • Бот не предназначен для постановки диагнозов или назначения лечения\n"
        " • Информация носит исключительно ознакомительный и образовательный характер\n"
        " • По вопросам интерпретации результатов обращайтесь к врачу/генетику."
    )
    await message.answer(text)


async def handle_history(message: Message) -> None:
    history = await cache_manager.get_history(message.from_user.id)
    if not history:
        await message.answer("За последние 24 часа вы не делали запросов.")
        return
    lines = [f"{i + 1}. {rsid}" for i, rsid in enumerate(history)]
    await message.answer("Ваши запросы за последние 24 часа:\n" + "\n".join(lines))


async def _process_rsid(message: Message, rsid: str) -> None:
    # Нормализуем rsid (регистр)
    rsid = rsid.strip().lower()

    # --- rate limiting на пользователя ---
    allowed, remaining = await cache_manager.register_request_and_check_limit(
        user_id=message.from_user.id,
        limit=settings.max_requests_per_hour,
    )
    if not allowed:
        await message.answer(
            f"Вы превысили лимит {settings.max_requests_per_hour} запросов в час.\n"
            "Попробуйте позже."
        )
        return

    logging.info(
        "Processing rsid=%s user_id=%s remaining=%s",
        rsid,
        message.from_user.id,
        remaining,
    )

    await message.answer(f"Запрашиваю данные для {rsid}...")

    # --- 1. Пробуем использовать кэш ---
    cached = await cache_manager.get_snp_result(rsid)
    if cached:
        logging.info("Cache hit for %s", rsid)
        await cache_manager.add_history_entry(message.from_user.id, rsid)
        await _send_result(message, cached)
        return

    # --- 2. Запрос к NCBI ---
    try:
        raw = await ncbi_client.fetch_snp(rsid)
    except ncbi_client.SnpNotFoundError:
        await message.answer(f"Вариант {rsid} не найден в NCBI dbSNP.")
        return
    except ncbi_client.NcbiUnavailableError as e:
        logging.exception("NCBI unavailable: %s", e)
        await message.answer("NCBI API сейчас недоступен. Попробуйте позже.")
        return
    except ncbi_client.NcbiError as e:
        logging.exception("NCBI error: %s", e)
        await message.answer("Ошибка при обращении к NCBI API.")
        return

    # --- 3. Базовый summary + графики ---
    summary = summarize_snp(rsid, raw)
    images = generate_plots(summary)

    # --- 4. Расширенная аналитика ---
    extended_summary = build_extended_summary(rsid, raw, summary)

    # --- 5. Генерация PDF-отчёта ---
    os.makedirs(REPORTS_DIR, exist_ok=True)
    pdf_path = os.path.join(REPORTS_DIR, f"{rsid}.pdf")
    build_pdf_report(rsid, extended_summary, images, pdf_path)

    # --- 6. Собираем payload для кэша ---
    payload: Dict[str, Any] = {
        "rsid": rsid,
        "populations": [p.to_dict() for p in summary.populations],
        "extended_summary": extended_summary,
        "images": images,
        "pdf": pdf_path,
    }

    # --- 7. Кэш + история ---
    await cache_manager.set_snp_result(rsid, payload)
    await cache_manager.add_history_entry(message.from_user.id, rsid)

    # --- 8. Отправка результата ---
    await _send_result(message, payload)


async def _send_result(message: Message, payload: Dict[str, Any]) -> None:
    rsid = payload.get("rsid", "-")
    pops = payload.get("populations") or []
    extended = payload.get("extended_summary") or {}

    if not pops:
        await message.answer(f"Не удалось извлечь частоты для {rsid}.")
        return

    lines: list[str] = [f"РЕЗУЛЬТАТЫ ДЛЯ {rsid}", ""]

    # --- Блок: общая информация, если есть extended_summary ---
    basic = extended.get("basic_info") or {}
    if basic:
        genes_list = basic.get("genes") or []
        genes = ", ".join(genes_list) if genes_list else "-"
        lines.append("🔬 Общая информация:")
        lines.append(f"  Ген(ы): {genes}")
        lines.append(f"  Тип варианта: {basic.get('variant_type', '-')}")
        chrom = basic.get("chrom", "-")
        pos38 = basic.get("pos38", "-")
        if chrom != "-" or pos38 != "-":
            lines.append(f"  Локус (GRCh38): chr{chrom}:{pos38}")
        hgvs_c = basic.get("hgvs_c", "-")
        hgvs_p = basic.get("hgvs_p", "-")
        if hgvs_c not in ("", "-"):
            lines.append(f"  HGVS (c.): {hgvs_c}")
        if hgvs_p not in ("", "-"):
            lines.append(f"  HGVS (p.): {hgvs_p}")
        region = basic.get("region")
        if region and region != "-":
            lines.append(f"  Регион: {region}")
        lines.append("")

    # --- Блок: популяционные частоты ---
    lines.append("📊 Популяционные частоты:")
    lines.append("")

    # extended-популяции индексируем по имени (study/name)
    ext_pops: Dict[str, Dict[str, Any]] = {}
    for ep in extended.get("populations", []):
        if isinstance(ep, dict) and "name" in ep:
            ext_pops[ep["name"]] = ep

    for p in pops:
        study = p.get("study", "unknown")
        lines.append(f"Исследование / популяция: {study}")
        lines.append(
            f"  Референсный аллель: {p.get('ref_allele')} "
            f"(частота: {p.get('freq_ref'):.6f})"
        )
        lines.append(
            f"  Альтернативный аллель: {p.get('alt_allele')} "
            f"(частота: {p.get('freq_alt'):.6f})"
        )

        gf = p.get("genotype_freqs")
        if isinstance(gf, dict):
            lines.append("  Ожидаемые частоты генотипов (Hardy–Вайнберг):")
            lines.append(f"    0/0: {gf.get('hom_ref'):.6f}")
            lines.append(f"    0/1: {gf.get('het'):.6f}")
            lines.append(f"    1/1: {gf.get('hom_alt'):.6f}")

        # Дополнительная инфа из extended_summary (MAF, N, категория)
        ext = ext_pops.get(study)
        if ext:
            maf = ext.get("maf")
            if maf is not None:
                lines.append(
                    f"  MAF: {maf:.6f} "
                    f"(категория: {ext.get('category', '-')})"
                )
            sample_n = ext.get("sample_n")
            if sample_n:
                lines.append(f"  Размер выборки (N): {sample_n}")

        lines.append("")

    # --- Блок: предупреждения (если есть) ---
    warnings = extended.get("warnings") or []
    if warnings:
        lines.append("⚠ Предупреждения:")
        for w in warnings:
            lines.append(f"  - {w}")
        lines.append("")

    # --- Отправка текста чанками (ограничение Telegram ~4096 символов) ---
    max_len = 3500  # небольшой запас
    chunk_lines: list[str] = []
    current_len = 0

    for line in lines:
        add_len = len(line) + 1  # +1 за '\n'
        if current_len + add_len > max_len and chunk_lines:
            await message.answer("\n".join(chunk_lines))
            chunk_lines = []
            current_len = 0
        chunk_lines.append(line)
        current_len += add_len

    if chunk_lines:
        await message.answer("\n".join(chunk_lines))

    # --- Отправляем картинки ---
    images = payload.get("images") or []
    for img_path in images:
        if img_path and os.path.exists(img_path):
            await message.answer_photo(FSInputFile(img_path))

    # --- Отправляем PDF, если есть ---
    pdf_path = payload.get("pdf")
    if pdf_path and os.path.exists(pdf_path):
        await message.answer_document(
            FSInputFile(pdf_path),
            caption=f"PDF-отчёт по {rsid}",
        )


async def handle_get(message: Message) -> None:
    parts = (message.text or "").strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /get rs12345")
        return

    rsid = parts[1].strip()
    if not RSID_REGEX.match(rsid):
        await message.answer("Неверный формат rsID. Пример: rs7755898")
        return

    await _process_rsid(message, rsid)


async def handle_stop(message: Message) -> None:
    text = (
        "Останавливаю взаимодействие.\n"
        "Бот не будет отправлять новые ответы, пока вы не введёте команду снова "
        "(/start, /get и т.п.)."
    )
    await message.answer(text)


async def handle_example_callback(callback: CallbackQuery) -> None:
    data = callback.data or ""
    if not data.startswith("example:"):
        return

    rsid = data.split(":", 1)[1].strip().lower()

    # закрываем "часики" у кнопки
    await callback.answer()

    if callback.message:
        await _process_rsid(callback.message, rsid)


async def main() -> None:
    setup_logging()
    if not settings.telegram_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    bot = Bot(token=settings.telegram_token)
    dp = Dispatcher()

    dp.message.register(handle_start, Command("start"))
    dp.message.register(handle_help, Command("help"))
    dp.message.register(handle_about, Command("about"))
    dp.message.register(handle_history, Command("history"))
    dp.message.register(handle_get, Command("get"))
    dp.message.register(handle_stop, Command("stop"))
    # plain-rsid хендлер убран по ТЗ — всё только через /get
    dp.callback_query.register(handle_example_callback, F.data.startswith("example:"))

    logging.info("Bot starting...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
