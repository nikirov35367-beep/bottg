"""Проверка перед деплоем: код собирается, воронка и база работают.

Запускается в GitHub Actions без обращения к Telegram.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiogram import Dispatcher  # noqa: E402
from aiogram.fsm.storage.memory import MemoryStorage  # noqa: E402

from app import db, funnel  # noqa: E402
from app.config import Config  # noqa: E402
from app.handlers import get_router  # noqa: E402
from app.bitrix import Bitrix, build_comment  # noqa: E402
from app.keyboards import phone_kb, start_kb, step_kb  # noqa: E402


def check_funnel() -> None:
    assert funnel.STEPS, "воронка пустая"
    keys = [s.key for s in funnel.STEPS]
    assert len(keys) == len(set(keys)), f"дублируются ключи шагов: {keys}"

    for i, step in enumerate(funnel.STEPS):
        assert step.question.strip(), f"пустой вопрос на шаге {step.key}"
        assert step.options, f"нет вариантов ответа на шаге {step.key}"
        codes = [c for c, _ in step.options]
        assert len(codes) == len(set(codes)), f"дубли вариантов в {step.key}"
        for code, _ in step.options:
            # callback_data Telegram ограничивает 64 байтами
            payload = f"a:{step.key}:{code}".encode()
            assert len(payload) <= 64, f"слишком длинный callback_data: {payload!r}"
            assert funnel.label(step.key, code) != code, f"нет подписи для {code}"
        step_kb(step, i)

    start_kb()
    phone_kb()
    print(f"✓ воронка: {len(funnel.STEPS)} шагов, ключи {keys}")


def check_scoring() -> None:
    hot = funnel.score(
        {"purpose": "invest", "budget": "gt12", "timing": "m1", "region": "sochi"}
    )
    cold = funnel.score({"purpose": "self", "budget": "lt8", "timing": "m6"})
    assert hot > cold, "оценка лидов не различает горячих и холодных"
    print(f"✓ баллы: горячий={hot} ({funnel.temperature(hot)}), "
          f"холодный={cold} ({funnel.temperature(cold)})")


def check_routers() -> None:
    cfg = Config.from_env()
    dp = Dispatcher(storage=MemoryStorage())
    dp["cfg"] = cfg
    dp.include_router(get_router())
    print("✓ роутеры и конфиг собираются")


async def check_db() -> None:
    await db.init()
    answers = {s.key: s.options[0][0] for s in funnel.STEPS}
    lead_id = await db.save_lead(
        tg_id=1,
        username="ci",
        full_name="CI Test",
        answers=answers,
        phone="+70000000000",
        score=funnel.score(answers),
    )
    assert lead_id > 0 and await db.count_leads() > 0
    assert await db.all_leads()
    db.DB_PATH.unlink(missing_ok=True)
    print("✓ база: запись и чтение заявки работают")


async def check_bitrix() -> None:
    """Проверяем формирование запросов к Битриксу, не обращаясь к сети."""
    sent: list[tuple[str, dict]] = []

    crm = Bitrix("https://example.bitrix24.ru/rest/1/key/", deal_title="Бот ТГ")

    async def fake_call(method, payload):
        sent.append((method, payload))
        return 100 + len(sent)

    crm._call = fake_call  # type: ignore[method-assign]

    answers = {s.key: s.options[0][0] for s in funnel.STEPS}
    contact_id, deal_id = await crm.send_lead(
        full_name="Иван Петров", username="ivan", tg_id=7,
        phone="+79990000000", answers=answers, points=funnel.score(answers),
    )
    assert [m for m, _ in sent] == ["crm.contact.add", "crm.deal.add"], sent
    assert contact_id and deal_id

    contact = sent[0][1]["fields"]
    assert contact["NAME"] == "Иван" and contact["LAST_NAME"] == "Петров"
    assert contact["PHONE"][0]["VALUE"] == "+79990000000"

    deal = sent[1][1]["fields"]
    assert deal["TITLE"] == "Бот ТГ", deal["TITLE"]
    assert deal["CONTACT_ID"] == contact_id, "сделка не связана с контактом"
    assert deal["SOURCE_DESCRIPTION"] == "Telegram"

    comment = build_comment(
        full_name="Иван Петров", username="ivan", tg_id=7,
        phone="+79990000000", answers=answers, points=5,
    )
    for step in funnel.STEPS:
        assert step.title in comment, f"в комментарии нет поля {step.title}"
    assert "+79990000000" in comment and "@ivan" in comment
    print("✓ Битрикс: контакт + сделка связаны, все ответы в комментарии")


def main() -> None:
    check_funnel()
    check_scoring()
    check_routers()
    asyncio.run(check_db())
    asyncio.run(check_bitrix())
    print("\nВсё в порядке — можно деплоить.")


if __name__ == "__main__":
    main()
