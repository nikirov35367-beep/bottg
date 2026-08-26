# Бот квалификации клиентов — недвижимость

Telegram-бот на aiogram 3. Приветствие → 4 вопроса на кнопках → сбор телефона →
заявка падает в SQLite и приходит карточкой админу в Telegram.

## Воронка

1. **Цель покупки** — Инвестиции / Для себя
2. **Бюджет** — до 8 млн ₽ / до 12 млн ₽ / 12+ млн ₽
3. **Срок покупки** — в этом месяце / 2–3 месяца / полгода
4. **Локация** — Крым / Сочи / Алтай / Архыз / Зарубежная
5. **Контакт** — кнопка «отправить номер» или ввод вручную

На каждом шаге есть кнопка «Назад». Лид получает балл 3–11 и метку
🔥 горячий / 🌤 тёплый / ❄️ холодный.

## Установка на сервер

```bash
# на сервере
git clone <repo> tgbot && cd tgbot     # или залейте папку через scp
sudo bash deploy/install.sh
sudo nano /opt/tgbot/.env              # вписать BOT_TOKEN и ADMIN_IDS
sudo systemctl restart tgbot
```

Если заливаете архивом со своей машины:

```bash
scp -r tgbot user@server:/tmp/tgbot
ssh user@server 'cd /tmp/tgbot && sudo bash deploy/install.sh'
```

Проверка и логи:

```bash
systemctl status tgbot
journalctl -u tgbot -f
```

## Локальный запуск

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # вписать токен
python bot.py
```

## Команды

| Команда | Кто | Что делает |
|---|---|---|
| `/start` | все | Начать/перезаполнить заявку |
| `/help` | все | Справка |
| `/stats` | админ | Сколько всего заявок |
| `/export` | админ | CSV со всеми заявками (открывается в Excel) |

## Как менять вопросы

Всё в одном файле — **`app/funnel.py`**: тексты приветствия и финала,
список шагов `STEPS` (вопрос + варианты кнопок), баллы `SCORE`.
Логику в `app/handlers/lead.py` трогать не нужно — шаги подставляются
автоматически, включая нумерацию и кнопку «Назад».

Добавили шаг с новым `key`? Допишите одноимённую колонку в `SCHEMA`
и в `INSERT` внутри `app/db.py`.

## Структура

```
bot.py                 запуск, диспетчер
app/config.py          чтение .env
app/funnel.py          ← вопросы, тексты, баллы
app/keyboards.py       кнопки
app/db.py              SQLite (data/leads.db)
app/handlers/lead.py   логика воронки (FSM)
app/handlers/admin.py  /stats, /export
deploy/                systemd-юнит и install.sh
```

## Заметки

- Состояние диалога хранится в памяти: после `systemctl restart` клиент,
  не дошедший до конца, начнёт заново. Если это важно — подключите
  `RedisStorage` в `bot.py`.
- База лежит в `data/leads.db` рядом с проектом. Бэкап — просто копия файла.
- Админ должен хотя бы раз написать боту `/start`, иначе Telegram не даст
  отправить ему уведомление.
