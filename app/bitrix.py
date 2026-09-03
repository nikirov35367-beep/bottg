"""Отправка заявки в Битрикс24 через входящий вебхук.

Создаём контакт, затем сделку и связываем их (CONTACT_ID).
Все ответы из воронки складываем в комментарий сделки.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any

import aiohttp

from app.funnel import STEPS, label, temperature

log = logging.getLogger(__name__)

TIMEOUT = aiohttp.ClientTimeout(total=15)


class BitrixError(RuntimeError):
    pass


class Bitrix:
    def __init__(self, webhook: str, *, source_id: str = "RC_GENERATOR",
                 deal_title: str = "Бот ТГ") -> None:
        self.webhook = webhook.rstrip("/") + "/"
        self.source_id = source_id
        self.deal_title = deal_title

    async def _call(self, method: str, payload: dict[str, Any]) -> Any:
        url = f"{self.webhook}{method}.json"
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            async with session.post(url, json=payload) as resp:
                text = await resp.text()
                if resp.status != 200:
                    raise BitrixError(f"{method}: HTTP {resp.status} — {text[:300]}")
                try:
                    data = await resp.json(content_type=None)
                except Exception as exc:
                    raise BitrixError(f"{method}: не JSON — {text[:300]}") from exc
        if "error" in data:
            raise BitrixError(
                f"{method}: {data.get('error')} — {data.get('error_description')}"
            )
        return data.get("result")

    async def add_contact(self, *, full_name: str, phone: str,
                          username: str | None) -> int:
        parts = plain(full_name).split(maxsplit=1)
        fields: dict[str, Any] = {
            "NAME": parts[0] if parts else "Клиент",
            "OPENED": "Y",
            "TYPE_ID": "CLIENT",
            "SOURCE_ID": self.source_id,
            "PHONE": [{"VALUE": phone, "VALUE_TYPE": "MOBILE"}],
        }
        if len(parts) > 1:
            fields["LAST_NAME"] = parts[1]
        if username:
            fields["IM"] = [{"VALUE": f"@{username}", "VALUE_TYPE": "TELEGRAM"}]
        return int(await self._call("crm.contact.add", {"fields": fields}))

    async def add_deal(self, *, contact_id: int, comment: str,
                       source_key: str = "") -> int:
        title = self.deal_title
        if source_key:
            title = f"{title} — {plain(source_key)}"
        fields = {
            "TITLE": title,
            "CONTACT_ID": contact_id,
            "SOURCE_ID": self.source_id,
            "SOURCE_DESCRIPTION": plain(f"Telegram / {source_key}") if source_key
                                  else "Telegram",
            "OPENED": "Y",
            "COMMENTS": comment,
        }
        return int(await self._call("crm.deal.add", {"fields": fields}))

    async def send_lead(self, *, full_name: str, username: str | None, tg_id: int,
                        phone: str, answers: dict[str, str], points: int,
                        source_key: str = "") -> tuple[int, int]:
        comment = build_comment(
            full_name=full_name, username=username, tg_id=tg_id,
            phone=phone, answers=answers, points=points, source_key=source_key,
        )
        contact_id = await self.add_contact(
            full_name=full_name, phone=phone, username=username
        )
        deal_id = await self.add_deal(
            contact_id=contact_id, comment=comment, source_key=source_key
        )
        log.info("Битрикс: контакт %s, сделка %s", contact_id, deal_id)
        return contact_id, deal_id


def plain(text: str) -> str:
    """Убираем эмодзи и прочие 4-байтные символы.

    База Битрикса обычно в кодировке utf8 (не utf8mb4): встретив эмодзи,
    портал обрезает строку по этому месту — комментарий приходит пустым.
    Поэтому в CRM отправляем текст без эмодзи, в Telegram они остаются.
    """
    cleaned = "".join(
        ch for ch in text
        if ord(ch) <= 0xFFFF and unicodedata.category(ch) != "So"
    )
    # схлопываем пробелы, оставшиеся на месте вырезанных символов
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return "\n".join(line.strip() for line in cleaned.split("\n"))


def build_comment(*, full_name: str, username: str | None, tg_id: int,
                  phone: str, answers: dict[str, str], points: int,
                  source_key: str = "") -> str:
    """Всё, что собрал бот — в комментарий сделки.

    Ключевое слово из ссылки запуска (t.me/bot?start=КЛЮЧ) идёт
    первой строкой — заголовком комментария.
    """
    header = f"Заявка из Telegram-бота: {source_key}" if source_key \
        else "Заявка из Telegram-бота"
    lines = [header, ""]
    for step in STEPS:
        if step.key in answers:
            lines.append(f"{step.title}: {label(step.key, answers[step.key])}")
    lines += [
        "",
        f"Телефон: {phone}",
        f"Имя в Telegram: {full_name}",
        f"Username: @{username}" if username else "Username: не указан",
        f"Telegram ID: {tg_id}",
        f"Оценка: {points} б. — {temperature(points)}",
    ]
    return plain("\n".join(lines))
