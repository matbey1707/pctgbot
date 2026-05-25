"""
Телеграм-бот шпаргалка для школы.
Открывает Web App, в котором можно добавлять, просматривать,
искать и удалять шпаргалки по предметам.
"""

import json
import logging
import os
import sqlite3
from contextlib import closing
from pathlib import Path

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
    WebAppInfo,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "PUT_YOUR_TOKEN_HERE")
WEBAPP_URL = os.environ.get(
    "WEBAPP_URL",
    "https://example.com/cheatsheet.html",
)

DB_PATH = Path(__file__).parent / "cheatsheets.db"


def init_db() -> None:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cheatsheets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                subject TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def save_cheatsheet(user_id: int, subject: str, title: str, content: str) -> int:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.execute(
            "INSERT INTO cheatsheets (user_id, subject, title, content) VALUES (?, ?, ?, ?)",
            (user_id, subject, title, content),
        )
        conn.commit()
        return cur.lastrowid


def delete_cheatsheet(user_id: int, sheet_id: int) -> bool:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.execute(
            "DELETE FROM cheatsheets WHERE id = ? AND user_id = ?",
            (sheet_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0


def list_cheatsheets(user_id: int) -> list[dict]:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, subject, title, content, created_at "
            "FROM cheatsheets WHERE user_id = ? ORDER BY subject, created_at DESC",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton(
                    "📚 Открыть шпаргалки",
                    web_app=WebAppInfo(url=WEBAPP_URL),
                )
            ],
            [KeyboardButton("📋 Список"), KeyboardButton("ℹ️ Помощь")],
        ],
        resize_keyboard=True,
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    text = (
        f"Привет, {user.first_name}! 👋\n\n"
        "Я — твоя школьная шпаргалка 📚\n"
        "Со мной ты можешь:\n"
        "• Добавлять заметки и формулы по предметам\n"
        "• Искать шпаргалки по теме\n"
        "• Быстро открывать нужную информацию\n\n"
        "Нажми кнопку «Открыть шпаргалки», чтобы начать!"
    )
    await update.message.reply_text(text, reply_markup=main_keyboard())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "📖 Как пользоваться ботом:\n\n"
        "/start — начать работу\n"
        "/open — открыть веб-приложение\n"
        "/list — список твоих шпаргалок\n"
        "/help — эта подсказка\n\n"
        "Внутри веб-приложения можно:\n"
        "➕ Добавлять шпаргалки\n"
        "🔍 Искать по тексту\n"
        "📁 Фильтровать по предмету\n"
        "🗑️ Удалять старое\n"
    )
    await update.message.reply_text(text, reply_markup=main_keyboard())


async def open_webapp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🚀 Открыть",
                    web_app=WebAppInfo(url=WEBAPP_URL),
                )
            ]
        ]
    )
    await update.message.reply_text(
        "Открываю шпаргалки 📚",
        reply_markup=keyboard,
    )


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sheets = list_cheatsheets(update.effective_user.id)
    if not sheets:
        await update.message.reply_text(
            "У тебя пока нет шпаргалок 😢\n"
            "Открой веб-приложение и добавь первую!",
            reply_markup=main_keyboard(),
        )
        return

    by_subject: dict[str, list[dict]] = {}
    for s in sheets:
        by_subject.setdefault(s["subject"], []).append(s)

    lines = [f"📚 Всего шпаргалок: {len(sheets)}\n"]
    for subject, items in by_subject.items():
        lines.append(f"\n📁 *{subject}* ({len(items)})")
        for it in items[:5]:
            lines.append(f"  • {it['title']}")
        if len(items) > 5:
            lines.append(f"  …и ещё {len(items) - 5}")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )


async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Принимает данные от Web App, отправленные через tg.sendData()."""
    try:
        payload = json.loads(update.effective_message.web_app_data.data)
    except (ValueError, AttributeError):
        await update.message.reply_text("⚠️ Не удалось прочитать данные из приложения.")
        return

    action = payload.get("action")
    user_id = update.effective_user.id

    if action == "add":
        sheet_id = save_cheatsheet(
            user_id=user_id,
            subject=payload.get("subject", "Без предмета"),
            title=payload.get("title", "Без названия"),
            content=payload.get("content", ""),
        )
        await update.message.reply_text(
            f"✅ Шпаргалка #{sheet_id} сохранена!",
            reply_markup=main_keyboard(),
        )
    elif action == "delete":
        ok = delete_cheatsheet(user_id, int(payload.get("id", 0)))
        msg = "🗑️ Удалено." if ok else "⚠️ Не найдено."
        await update.message.reply_text(msg, reply_markup=main_keyboard())
    elif action == "sync":
        sheets = list_cheatsheets(user_id)
        await update.message.reply_text(
            f"🔄 Синхронизировано: {len(sheets)} записей",
            reply_markup=main_keyboard(),
        )
    else:
        await update.message.reply_text(
            "🤔 Неизвестное действие из приложения.",
            reply_markup=main_keyboard(),
        )


async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""
    if text.startswith("📋"):
        await list_command(update, context)
    elif text.startswith("ℹ️"):
        await help_command(update, context)
    else:
        await update.message.reply_text(
            "Используй кнопки внизу или команды (/help).",
            reply_markup=main_keyboard(),
        )


def main() -> None:
    if BOT_TOKEN == "PUT_YOUR_TOKEN_HERE":
        raise SystemExit(
            "Установи переменную окружения BOT_TOKEN с токеном от @BotFather"
        )

    init_db()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("open", open_webapp))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))

    logger.info("Бот запущен. Web App URL: %s", WEBAPP_URL)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
