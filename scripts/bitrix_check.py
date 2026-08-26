"""Проверка интеграции с Битрикс24.

Запуск на сервере:
    /opt/tgbot/venv/bin/python scripts/bitrix_check.py            # показать источники
    /opt/tgbot/venv/bin/python scripts/bitrix_check.py --test     # создать тестовую сделку

Первый режим ничего не меняет в CRM — только читает справочник источников,
чтобы вы могли вписать нужный BITRIX_SOURCE_ID в .env.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.bitrix import Bitrix, BitrixError  # noqa: E402
from app.config import Config  # noqa: E402


async def show_sources(crm: Bitrix) -> None:
    rows = await crm._call("crm.status.list", {"filter": {"ENTITY_ID": "SOURCE"}})
    print("Источники в вашем Битриксе (STATUS_ID → название):\n")
    for row in rows:
        mark = "  ← сейчас в .env" if row["STATUS_ID"] == crm.source_id else ""
        print(f"  {row['STATUS_ID']:<20} {row['NAME']}{mark}")
    print(
        "\nЕсли среди них есть «Telegram» — впишите его STATUS_ID в BITRIX_SOURCE_ID.\n"
        "Если нет — заведите источник в CRM → Настройки → Справочники → Источники,\n"
        "либо оставьте OTHER: название «Telegram» всё равно уйдёт в поле\n"
        "«Дополнительно об источнике»."
    )


async def send_test(crm: Bitrix) -> None:
    answers = {
        "purpose": "invest",
        "budget": "gt12",
        "timing": "m1",
        "region": "sochi",
    }
    contact_id, deal_id = await crm.send_lead(
        full_name="Тестовый Клиент",
        username="test_user",
        tg_id=1,
        phone="+79990000000",
        answers=answers,
        points=8,
    )
    print(f"Создано: контакт #{contact_id}, сделка #{deal_id}")
    print("Проверьте карточку в CRM и удалите её, если всё верно.")


async def main() -> None:
    cfg = Config.from_env()
    if not cfg.bitrix_webhook:
        sys.exit("BITRIX_WEBHOOK не задан в .env")

    crm = Bitrix(
        cfg.bitrix_webhook,
        source_id=cfg.bitrix_source_id,
        deal_title=cfg.bitrix_deal_title,
    )
    try:
        if "--test" in sys.argv:
            await send_test(crm)
        else:
            await show_sources(crm)
    except BitrixError as exc:
        sys.exit(f"Ошибка Битрикса: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
