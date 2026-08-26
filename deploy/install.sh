#!/usr/bin/env bash
# Установка бота на сервер (Ubuntu/Debian). Запускать из папки проекта: sudo bash deploy/install.sh
set -euo pipefail

APP_DIR=/opt/tgbot
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Ставлю python3-venv"
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip

echo "==> Копирую проект в $APP_DIR"
mkdir -p "$APP_DIR"
rsync -a --exclude venv --exclude data --exclude .git "$SRC_DIR/" "$APP_DIR/"

echo "==> Создаю виртуальное окружение"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install -q --upgrade pip
"$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
  echo "!! Впишите BOT_TOKEN и ADMIN_IDS в $APP_DIR/.env, затем: systemctl restart tgbot"
fi

echo "==> Ставлю systemd-сервис"
cp "$APP_DIR/deploy/tgbot.service" /etc/systemd/system/tgbot.service
systemctl daemon-reload
systemctl enable tgbot

if grep -q '^BOT_TOKEN=123456' "$APP_DIR/.env"; then
  echo "==> Сервис включён, но не запущен: сначала заполните .env"
else
  systemctl restart tgbot
  sleep 2
  systemctl --no-pager status tgbot | head -20
fi

echo
echo "Готово. Логи:   journalctl -u tgbot -f"
echo "Перезапуск:     systemctl restart tgbot"
