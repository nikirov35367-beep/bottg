"""Описание воронки квалификации.

Всё, что можно захотеть поменять (тексты, кнопки, порядок шагов),
лежит здесь. Логика в handlers/lead.py трогать не нужно.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Step:
    key: str  # ключ поля в базе
    title: str  # короткое название для карточки лида
    question: str  # текст вопроса
    # варианты ответа: (код, подпись на кнопке)
    options: list[tuple[str, str]] = field(default_factory=list)
    columns: int = 1  # сколько кнопок в ряду


# Имя клиента подставляется автоматически вместо «Здравствуйте!»
GREETING = (
    "👋 Здравствуйте! Помогу подобрать объект недвижимости под вашу задачу.\n\n"
    "Ответьте на 4 коротких вопроса — это займёт меньше минуты, "
    "и я пришлю подходящие варианты."
)
STEPS: list[Step] = [
    Step(
        key="purpose",
        title="Цель покупки",
        question="1/4 — Какая у вас цель покупки?",
        options=[
            ("invest", "📈 Инвестиции"),
            ("self", "🏡 Для себя"),
        ],
    ),
    Step(
        key="budget",
        title="Бюджет",
        question="2/4 — На какой бюджет ориентируетесь?",
        options=[
            ("lt8", "до 8 млн ₽"),
            ("lt12", "до 12 млн ₽"),
            ("gt12", "12+ млн ₽"),
        ],
    ),
    Step(
        key="timing",
        title="Срок покупки",
        question="3/4 — Когда планируете выйти на сделку?",
        options=[
            ("m1", "В этом месяце"),
            ("m3", "Через 2–3 месяца"),
            ("m6", "В течение полугода"),
        ],
    ),
    Step(
        key="region",
        title="Локация",
        question="4/4 — Какая локация вам интересна?",
        options=[
            ("crimea", "Крым"),
            ("sochi", "Сочи"),
            ("altai", "Алтай"),
            ("arkhyz", "Архыз"),
            ("abroad", "Зарубежная"),
        ],
        columns=2,
    ),
]

CONTACT_QUESTION = (
    "Отлично, спасибо! 🙌\n\n"
    "Оставьте телефон — менеджер свяжется и пришлёт подборку.\n"
    "Нажмите кнопку ниже или впишите номер вручную."
)

FINAL_TEXT = (
    "Готово! ✅\n\n"
    "Ваша заявка принята. Менеджер свяжется с вами в ближайшее рабочее время "
    "и пришлёт подборку объектов под ваш запрос.\n\n"
    "Если хотите изменить параметры — наберите /start."
)

# Балльная оценка: чем выше, тем «горячее» лид.
SCORE = {
    "purpose": {"invest": 2, "self": 1},
    "budget": {"lt8": 1, "lt12": 2, "gt12": 3},
    "timing": {"m1": 3, "m3": 2, "m6": 1},
    "region": {},
}


def label(step_key: str, code: str) -> str:
    """Человеческая подпись по коду ответа."""
    for step in STEPS:
        if step.key == step_key:
            for value, text in step.options:
                if value == code:
                    return text
    return code


def score(answers: dict[str, str]) -> int:
    return sum(SCORE.get(k, {}).get(v, 0) for k, v in answers.items())


def temperature(points: int) -> str:
    if points >= 7:
        return "🔥 горячий"
    if points >= 5:
        return "🌤 тёплый"
    return "❄️ холодный"
