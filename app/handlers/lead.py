"""Воронка квалификации: приветствие → цель → бюджет → срок → город → контакт."""
from __future__ import annotations

import html
import logging
import re

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app import db
from app.bitrix import Bitrix
from app.config import Config
from app.funnel import (
    CONTACT_QUESTION,
    FINAL_TEXT,
    GREETING,
    STEPS,
    label,
    score,
    temperature,
)
from app.keyboards import phone_kb, remove_kb, restart_kb, start_kb, step_kb

log = logging.getLogger(__name__)
router = Router(name="lead")

PHONE_RE = re.compile(r"^\+?[\d\s\-()]{10,18}$")


class Lead(StatesGroup):
    steps = State()
    phone = State()
    done = State()


async def ask_step(message: Message, state: FSMContext, index: int) -> None:
    """Показать вопрос с номером index (редактируя предыдущее сообщение)."""
    step = STEPS[index]
    await state.update_data(index=index)
    await state.set_state(Lead.steps)
    try:
        await message.edit_text(step.question, reply_markup=step_kb(step, index))
    except Exception:  # сообщение нельзя отредактировать — шлём новое
        await message.answer(step.question, reply_markup=step_kb(step, index))


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    name = message.from_user.full_name if message.from_user else ""
    greeting = GREETING if not name else GREETING.replace(
        "Здравствуйте!", f"Здравствуйте, {html.escape(name.split()[0])}!"
    )
    await message.answer(greeting, reply_markup=start_kb())


@router.callback_query(F.data.in_({"go", "restart"}))
async def on_go(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(answers={})
    if callback.message:
        await ask_step(callback.message, state, 0)
    await callback.answer()


@router.callback_query(Lead.steps, F.data.startswith("a:"))
async def on_answer(callback: CallbackQuery, state: FSMContext) -> None:
    _, key, code = (callback.data or "").split(":", 2)
    data = await state.get_data()
    answers: dict[str, str] = dict(data.get("answers", {}))
    answers[key] = code
    await state.update_data(answers=answers)

    index = int(data.get("index", 0)) + 1
    if index < len(STEPS):
        if callback.message:
            await ask_step(callback.message, state, index)
    else:
        await state.set_state(Lead.phone)
        if callback.message:
            await callback.message.edit_text(summary(answers))
            await callback.message.answer(CONTACT_QUESTION, reply_markup=phone_kb())
    await callback.answer()


@router.callback_query(Lead.steps, F.data == "back")
async def on_back(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    index = max(int(data.get("index", 0)) - 1, 0)
    if callback.message:
        await ask_step(callback.message, state, index)
    await callback.answer()


def summary(answers: dict[str, str]) -> str:
    lines = ["<b>Ваш запрос:</b>"]
    for step in STEPS:
        if step.key in answers:
            lines.append(f"• {step.title}: <b>{label(step.key, answers[step.key])}</b>")
    return "\n".join(lines)


@router.message(Lead.phone, F.contact)
async def on_contact(message: Message, state: FSMContext, bot: Bot, cfg: Config) -> None:
    await finish(message, state, bot, cfg, message.contact.phone_number)


@router.message(Lead.phone, F.text, ~F.text.startswith("/"))
async def on_phone_text(message: Message, state: FSMContext, bot: Bot, cfg: Config) -> None:
    text = (message.text or "").strip()
    if not PHONE_RE.match(text):
        await message.answer(
            "Не похоже на номер телефона 🤔\n"
            "Напишите в формате <code>+7 900 123-45-67</code> "
            "или нажмите кнопку ниже.",
            reply_markup=phone_kb(),
        )
        return
    await finish(message, state, bot, cfg, text)


async def finish(message: Message, state: FSMContext, bot: Bot, cfg: Config, phone: str) -> None:
    data = await state.get_data()
    answers: dict[str, str] = data.get("answers", {})
    user = message.from_user
    points = score(answers)

    lead_id = await db.save_lead(
        tg_id=user.id,
        username=user.username,
        full_name=user.full_name,
        answers=answers,
        phone=phone,
        score=points,
    )

    await state.set_state(Lead.done)
    await message.answer(FINAL_TEXT, reply_markup=remove_kb())
    await message.answer("Хотите изменить параметры?", reply_markup=restart_kb())

    crm_note = await push_to_bitrix(cfg, user, answers, phone, points)
    await notify_admins(bot, cfg, lead_id, user, answers, phone, points, crm_note)


async def push_to_bitrix(cfg, user, answers, phone, points) -> str:
    """Создаёт контакт и сделку в Битриксе. Ошибка не должна ронять заявку."""
    if not cfg.bitrix_webhook:
        return ""
    try:
        crm = Bitrix(
            cfg.bitrix_webhook,
            source_id=cfg.bitrix_source_id,
            deal_title=cfg.bitrix_deal_title,
        )
        contact_id, deal_id = await crm.send_lead(
            full_name=user.full_name,
            username=user.username,
            tg_id=user.id,
            phone=phone,
            answers=answers,
            points=points,
        )
        return f"\n\n✅ Битрикс: сделка #{deal_id}, контакт #{contact_id}"
    except Exception as exc:
        log.exception("Не удалось отправить лид в Битрикс")
        return f"\n\n⚠️ <b>Битрикс недоступен</b> — занесите вручную.\n<code>{html.escape(str(exc)[:200])}</code>"


async def notify_admins(bot, cfg, lead_id, user, answers, phone, points,
                        crm_note: str = "") -> None:
    if not cfg.admin_ids:
        return

    contact = f"@{user.username}" if user.username else f"id{user.id}"
    card = (
        f"🆕 <b>Заявка #{lead_id}</b> — {temperature(points)} ({points} б.)\n\n"
        f"👤 {html.escape(user.full_name)} ({contact})\n"
        f"📞 <code>{html.escape(phone)}</code>\n\n"
        + "\n".join(
            f"• {s.title}: <b>{label(s.key, answers[s.key])}</b>"
            for s in STEPS
            if s.key in answers
        )
        + crm_note
    )
    for admin_id in cfg.admin_ids:
        try:
            await bot.send_message(admin_id, card)
        except Exception as exc:  # админ не начал диалог с ботом и т.п.
            log.warning("Не удалось отправить лид админу %s: %s", admin_id, exc)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Я помогаю подобрать недвижимость.\n"
        "/start — заполнить заявку заново\n"
        "/help — эта справка"
    )


@router.message()
async def fallback(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current == Lead.phone.state:
        await message.answer("Пожалуйста, отправьте номер телефона 📱",
                             reply_markup=phone_kb())
    else:
        await message.answer("Наберите /start, чтобы оставить заявку.")
