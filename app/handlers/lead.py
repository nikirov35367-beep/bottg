"""Воронка квалификации: приветствие → цель → бюджет → срок → город → контакт."""
from __future__ import annotations

import html
import logging
import re

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
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
# Telegram разрешает в deep link только латиницу, цифры, _ и -
SOURCE_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


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
async def cmd_start(message: Message, state: FSMContext,
                    command: CommandObject) -> None:
    """Старт воронки. Из ссылки t.me/<bot>?start=КЛЮЧ забираем метку."""
    await state.clear()

    source_key = (command.args or "").strip()
    if source_key and not SOURCE_RE.match(source_key):
        log.warning("Неожиданная метка в ссылке запуска: %r — игнорирую", source_key)
        source_key = ""
    if source_key:
        log.info("Старт по ссылке с меткой %r (tg_id=%s)", source_key,
                 message.from_user.id if message.from_user else "?")
    await state.update_data(source_key=source_key)

    name = message.from_user.full_name if message.from_user else ""
    greeting = GREETING if not name else GREETING.replace(
        "Здравствуйте!", f"Здравствуйте, {html.escape(name.split()[0])}!"
    )
    await message.answer(greeting, reply_markup=start_kb())


@router.callback_query(F.data.in_({"go", "restart"}))
async def on_go(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    source_key = data.get("source_key", "")  # метка переживает «заполнить заново»
    await state.clear()
    await state.update_data(answers={}, source_key=source_key)
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
    source_key: str = data.get("source_key", "")
    user = message.from_user
    points = score(answers)

    lead_id = await db.save_lead(
        tg_id=user.id,
        username=user.username,
        full_name=user.full_name,
        answers=answers,
        phone=phone,
        score=points,
        source_key=source_key,
    )

    await state.set_state(Lead.done)
    await message.answer(FINAL_TEXT, reply_markup=remove_kb())
    await message.answer("Хотите изменить параметры?", reply_markup=restart_kb())

    crm_note = await push_to_bitrix(cfg, user, answers, phone, points, source_key)
    await notify_admins(bot, cfg, lead_id, user, answers, phone, points,
                        crm_note, source_key)


async def push_to_bitrix(cfg, user, answers, phone, points, source_key="") -> str:
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
            source_key=source_key,
        )
        return f"\n\n✅ Битрикс: сделка #{deal_id}, контакт #{contact_id}"
    except Exception as exc:
        log.exception("Не удалось отправить лид в Битрикс")
        return f"\n\n⚠️ <b>Битрикс недоступен</b> — занесите вручную.\n<code>{html.escape(str(exc)[:200])}</code>"


async def notify_admins(bot, cfg, lead_id, user, answers, phone, points,
                        crm_note: str = "", source_key: str = "") -> None:
    if not cfg.admin_ids:
        return

    contact = f"@{user.username}" if user.username else f"id{user.id}"
    tag = f"\n🏷 Метка: <code>{html.escape(source_key)}</code>" if source_key else ""
    card = (
        f"🆕 <b>Заявка #{lead_id}</b> — {temperature(points)} ({points} б.){tag}\n\n"
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
