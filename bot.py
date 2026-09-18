import os
import sqlite3
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes,
    ConversationHandler, filters
)

TOKEN = os.environ["BOT_TOKEN"]
DB = "dating.db"

logging.basicConfig(level=logging.INFO)

NAME, AGE, CITY, PHOTO, BIO = range(5)

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            age INTEGER NOT NULL,
            city TEXT NOT NULL,
            photo_id TEXT NOT NULL,
            bio TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS likes (
            from_id INTEGER,
            to_id INTEGER,
            UNIQUE(from_id, to_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS blocks (
            from_id INTEGER,
            to_id INTEGER,
            UNIQUE(from_id, to_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            from_id INTEGER,
            to_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    conn = db()
    user = conn.execute("SELECT id FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()

    if user:
        await menu(update)
        return ConversationHandler.END

    kb = [[KeyboardButton("Мне 18+ лет")]]
    await update.message.reply_text(
        "❤️ Добро пожаловать в «Знакомства Морозово»!\n\n"
        "Бот предназначен только для пользователей 18+.\n"
        "Нажимая кнопку, ты подтверждаешь, что тебе уже исполнилось 18 лет.",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
    )
    return NAME

async def name_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text != "Мне 18+ лет":
        await update.message.reply_text("Для продолжения нужно подтвердить, что тебе 18+.")
        return NAME
    await update.message.reply_text("Как тебя зовут?")
    return AGE

async def age_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text.strip()[:50]
    await update.message.reply_text("Сколько тебе лет? (18–99)")
    return CITY

async def city_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        age = int(update.message.text)
    except ValueError:
        await update.message.reply_text("Напиши возраст числом, например: 23")
        return CITY
    if not 18 <= age <= 99:
        await update.message.reply_text("Возраст должен быть от 18 до 99 лет.")
        return CITY
    context.user_data["age"] = age
    kb = [["Морозово", "Всеволожск"], ["Другой"]]
    await update.message.reply_text(
        "Где ты находишься?",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
    )
    return PHOTO

async def photo_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = update.message.text.strip()
    if city not in {"Морозово", "Всеволожск"}:
        city = city[:40]
    context.user_data["city"] = city
    await update.message.reply_text("Отправь свою фотографию одним сообщением.")
    return BIO

async def bio_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("Пожалуйста, отправь именно фотографию.")
        return BIO
    context.user_data["photo_id"] = update.message.photo[-1].file_id
    await update.message.reply_text("Напиши пару слов о себе.")
    return ConversationHandler.END

async def save_bio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # This handler is installed separately for users finishing registration.
    data = context.user_data
    if not all(k in data for k in ("name", "age", "city", "photo_id")):
        return
    bio = update.message.text.strip()[:500]
    conn = db()
    conn.execute("""
        INSERT OR REPLACE INTO users(id,name,age,city,photo_id,bio)
        VALUES(?,?,?,?,?,?)
    """, (
        update.effective_user.id, data["name"], data["age"],
        data["city"], data["photo_id"], bio
    ))
    conn.commit()
    conn.close()
    context.user_data.clear()
    await menu(update)

async def menu(update):
    kb = [
        ["❤️ Смотреть анкеты", "📝 Моя анкета"],
        ["✏️ Изменить анкету", "🚫 Заблокированные"]
    ]
    await update.message.reply_text(
        "Главное меню:",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    conn = db()
    u = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()
    if not u:
        await update.message.reply_text("Сначала создай анкету: /start")
        return
    await update.message.reply_photo(
        u["photo_id"],
        caption=f"👤 {u['name']}, {u['age']}\n📍 {u['city']}\n\n{u['bio']}"
    )

async def browse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    conn = db()
    candidate = conn.execute("""
        SELECT * FROM users
        WHERE id != ?
        AND id NOT IN (SELECT to_id FROM blocks WHERE from_id=?)
        AND id NOT IN (SELECT from_id FROM blocks WHERE to_id=?)
        AND id NOT IN (SELECT to_id FROM likes WHERE from_id=?)
        ORDER BY RANDOM() LIMIT 1
    """, (uid, uid, uid, uid)).fetchone()
    conn.close()

    if not candidate:
        await update.message.reply_text("Пока новых анкет нет. Попробуй позже.")
        return

    context.user_data["candidate"] = candidate["id"]
    kb = [["❤️ Нравится", "❌ Пропустить"], ["🚫 Заблокировать", "🛡 Пожаловаться"]]
    await update.message.reply_photo(
        candidate["photo_id"],
        caption=f"👤 {candidate['name']}, {candidate['age']}\n"
                f"📍 {candidate['city']}\n\n{candidate['bio']}",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )

async def action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    cid = context.user_data.get("candidate")
    if not cid:
        await browse(update, context)
        return

    text = update.message.text
    conn = db()

    if text == "❤️ Нравится":
        conn.execute("INSERT OR IGNORE INTO likes(from_id,to_id) VALUES(?,?)", (uid,cid))
        mutual = conn.execute(
            "SELECT 1 FROM likes WHERE from_id=? AND to_id=?",
            (cid, uid)
        ).fetchone()
        conn.commit()
        candidate = conn.execute("SELECT * FROM users WHERE id=?", (cid,)).fetchone()
        conn.close()

        if mutual:
            await update.message.reply_text(
                f"💕 У вас взаимная симпатия с {candidate['name']}!\n"
                f"Открой профиль пользователя в Telegram, чтобы написать."
            )
        else:
            await update.message.reply_text("❤️ Лайк отправлен!")
        await browse(update, context)
        return

    if text == "🚫 Заблокировать":
        conn.execute("INSERT OR IGNORE INTO blocks(from_id,to_id) VALUES(?,?)",(uid,cid))
        conn.commit()
        conn.close()
        await update.message.reply_text("Пользователь заблокирован.")
        await browse(update, context)
        return

    if text == "🛡 Пожаловаться":
        conn.execute("INSERT INTO reports(from_id,to_id) VALUES(?,?)",(uid,cid))
        conn.commit()
        conn.close()
        await update.message.reply_text("Жалоба отправлена администрации.")
        await browse(update, context)
        return

    if text == "❌ Пропустить":
        conn.close()
        await browse(update, context)
        return

    conn.close()

async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    if text == "❤️ Смотреть анкеты":
        await browse(update, context)
    elif text == "📝 Моя анкета":
        await profile(update, context)
    elif text == "🚫 Заблокированные":
        await update.message.reply_text("Функция списка заблокированных будет добавлена в следующей версии.")
    elif text == "✏️ Изменить анкету":
        await update.message.reply_text("Для изменения анкеты пока используй /start после удаления бота из чата.")

def main():
    init_db()
    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name_step)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, age_step)],
            CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, city_step)],
            PHOTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, photo_step)],
            BIO: [
                MessageHandler(filters.PHOTO, photo_step),
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_bio),
            ],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, action))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))
    app.run_polling()

if __name__ == "__main__":
    main()