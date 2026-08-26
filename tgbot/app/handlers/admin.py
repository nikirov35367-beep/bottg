"""Админские команды: /stats и /export."""
from __future__ import annotations

import csv
import io

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message

from app import db
from app.config import Config
from app.funnel import label

router = Router(name="admin")

HEADERS = [
    "id", "created_at", "Имя", "Username", "TG ID", "Цель",
    "Бюджет", "Срок", "Локация", "Телефон", "Баллы",
]
FIELD_KEYS = {5: "purpose", 6: "budget", 7: "timing", 8: "region"}


def is_admin(message: Message, cfg: Config) -> bool:
    return bool(message.from_user and message.from_user.id in cfg.admin_ids)


@router.message(Command("stats"))
async def cmd_stats(message: Message, cfg: Config) -> None:
    if not is_admin(message, cfg):
        return
    total = await db.count_leads()
    await message.answer(f"📊 Всего заявок: <b>{total}</b>\n\n/export — выгрузка в CSV")


@router.message(Command("export"))
async def cmd_export(message: Message, cfg: Config) -> None:
    if not is_admin(message, cfg):
        return
    rows = await db.all_leads()
    if not rows:
        await message.answer("Заявок пока нет.")
        return

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(HEADERS)
    for row in rows:
        row = list(row)
        for idx, key in FIELD_KEYS.items():
            if row[idx]:
                row[idx] = label(key, row[idx])
        writer.writerow(row)

    data = buf.getvalue().encode("utf-8-sig")  # BOM — чтобы Excel не ломал кириллицу
    await message.answer_document(
        BufferedInputFile(data, filename="leads.csv"),
        caption=f"Выгрузка: {len(rows)} заявок",
    )
