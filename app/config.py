"""Конфигурация бота: читается из переменных окружения (.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: tuple[int, ...]
    log_level: str
    bitrix_webhook: str
    bitrix_source_id: str
    bitrix_deal_title: str

    @classmethod
    def from_env(cls) -> "Config":
        token = os.getenv("BOT_TOKEN", "").strip()
        if not token:
            raise RuntimeError(
                "BOT_TOKEN не задан. Скопируйте .env.example в .env и впишите токен от @BotFather."
            )
        raw_admins = os.getenv("ADMIN_IDS", "").replace(" ", "")
        admins = tuple(int(x) for x in raw_admins.split(",") if x)
        return cls(
            bot_token=token,
            admin_ids=admins,
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            bitrix_webhook=os.getenv("BITRIX_WEBHOOK", "").strip(),
            bitrix_source_id=os.getenv("BITRIX_SOURCE_ID", "RC_GENERATOR").strip() or "RC_GENERATOR",
            bitrix_deal_title=os.getenv("BITRIX_DEAL_TITLE", "Бот ТГ").strip(),
        )
