"""Клавиатуры бота."""
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from app.funnel import Step


def start_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, начнём", callback_data="go")]
        ]
    )


def step_kb(step: Step, index: int) -> InlineKeyboardMarkup:
    """Кнопки вариантов ответа + кнопка «назад» со второго шага."""
    rows: list[list[InlineKeyboardButton]] = []
    buttons = [
        InlineKeyboardButton(text=text, callback_data=f"a:{step.key}:{code}")
        for code, text in step.options
    ]
    for i in range(0, len(buttons), step.columns):
        rows.append(buttons[i : i + step.columns])
    if index > 0:
        rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Отправить мой номер", request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def remove_kb() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def restart_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Заполнить заново", callback_data="restart")]
        ]
    )
