"""
Telegram-бот для приёма номеров Билайн в аренду.
Требования: pip install pyTelegramBotAPI

Запуск: python beeline_bot.py
"""

import telebot
from telebot import types
import re
from datetime import datetime

# ─────────────────────────────────────────────
#  НАСТРОЙКИ — замените на свои значения
# ─────────────────────────────────────────────
BOT_TOKEN = "8651903694:AAEcjjOQ__H757ufXxD-M25ZelY3a5nOxcE"          # токен от @BotFather

# Telegram ID администраторов (int).
# Чтобы узнать свой ID, напишите боту @userinfobot
ADMIN_IDS = [8189622055, 8064942862]         # ← вставьте сюда свои реальные ID

# ─────────────────────────────────────────────
#  Инициализация бота
# ─────────────────────────────────────────────
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ─────────────────────────────────────────────
#  Хранилище данных (in-memory)
#  В продакшне замените на базу данных (SQLite / PostgreSQL и т.д.)
# ─────────────────────────────────────────────
# {user_id: {"username": str, "name": str, "numbers": [...], "chat_open": bool}}
users: dict[int, dict] = {}

# Активные «подключения» админа к пользователю
# {admin_id: user_id}  — к какому пользователю подключён каждый админ
admin_sessions: dict[int, int] = {}

# Принятые номера
# [{"user_id": int, "number": str, "timestamp": str, "name": str}]
submitted_numbers: list[dict] = []

# ─────────────────────────────────────────────
#  Вспомогательные функции
# ─────────────────────────────────────────────

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def is_valid_phone(text: str) -> bool:
    """Проверяет, похож ли текст на российский номер телефона."""
    cleaned = re.sub(r"[\s\-\(\)]", "", text)
    return bool(re.match(r"^(\+7|7|8)\d{10}$", cleaned))


def format_phone(text: str) -> str:
    """Нормализует номер к формату +7XXXXXXXXXX."""
    cleaned = re.sub(r"[\s\-\(\)]", "", text)
    if cleaned.startswith("8"):
        cleaned = "+7" + cleaned[1:]
    elif cleaned.startswith("7"):
        cleaned = "+" + cleaned
    return cleaned


def user_display(user_id: int) -> str:
    u = users.get(user_id, {})
    name = u.get("name", "Неизвестно")
    username = u.get("username", "")
    uname_str = f" (@{username})" if username else ""
    return f"{name}{uname_str} [ID: {user_id}]"


def notify_admins(text: str, exclude: int = None):
    """Отправляет сообщение всем администраторам."""
    for admin_id in ADMIN_IDS:
        if admin_id == exclude:
            continue
        try:
            bot.send_message(admin_id, text)
        except Exception:
            pass


# ─────────────────────────────────────────────
#  /start
# ─────────────────────────────────────────────
@bot.message_handler(commands=["start"])
def cmd_start(message: types.Message):
    uid = message.from_user.id

    # Сохраняем пользователя
    users[uid] = {
        "name": message.from_user.full_name,
        "username": message.from_user.username or "",
        "numbers": users.get(uid, {}).get("numbers", []),
        "chat_open": True,
    }

    if is_admin(uid):
        # Для администратора — отдельное приветствие
        bot.send_message(
            uid,
            "👑 <b>Панель администратора</b>\n\n"
            "Доступные команды:\n"
            "• /numbers — список принятых номеров\n"
            "• /users — список пользователей\n"
            "• /connect &lt;user_id&gt; — подключиться к чату пользователя\n"
            "• /disconnect — отключиться от текущего чата\n"
            "• /session — кто сейчас подключён"
        )
    else:
        bot.send_message(
            uid,
            "👋 <b>Здравствуйте!</b>\n\n"
            "Если вы хотите сдать свой номер <b>Билайн</b> в аренду, "
            "то присылайте номер в сообщении ниже.\n\n"
            "💰 <b>ЦЕНА АРЕНДЫ 1 ЧАС — 10$</b>"
        )


# ─────────────────────────────────────────────
#  Команды администратора
# ─────────────────────────────────────────────

@bot.message_handler(commands=["numbers"])
def cmd_numbers(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    if not submitted_numbers:
        bot.send_message(message.from_user.id, "📭 Номеров пока нет.")
        return

    lines = ["📋 <b>Принятые номера:</b>\n"]
    for i, entry in enumerate(submitted_numbers, 1):
        lines.append(
            f"{i}. <code>{entry['number']}</code>\n"
            f"   👤 {entry['name']} (ID: {entry['user_id']})\n"
            f"   🕐 {entry['timestamp']}"
        )
    bot.send_message(message.from_user.id, "\n".join(lines))


@bot.message_handler(commands=["users"])
def cmd_users(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    if not users:
        bot.send_message(message.from_user.id, "👤 Пользователей пока нет.")
        return

    lines = ["👥 <b>Список пользователей:</b>\n"]
    for uid, data in users.items():
        if is_admin(uid):
            continue
        uname = f"@{data['username']}" if data["username"] else "нет username"
        nums = len(data.get("numbers", []))
        lines.append(
            f"• <b>{data['name']}</b> ({uname})\n"
            f"  ID: <code>{uid}</code> | Номеров: {nums}"
        )
    bot.send_message(message.from_user.id, "\n".join(lines))


@bot.message_handler(commands=["connect"])
def cmd_connect(message: types.Message):
    """Подключиться к чату пользователя: /connect <user_id>"""
    admin_id = message.from_user.id
    if not is_admin(admin_id):
        return

    parts = message.text.split()
    if len(parts) < 2:
        bot.send_message(admin_id, "❌ Укажите ID пользователя: /connect &lt;user_id&gt;")
        return

    try:
        target_id = int(parts[1])
    except ValueError:
        bot.send_message(admin_id, "❌ ID должен быть числом.")
        return

    if is_admin(target_id):
        bot.send_message(admin_id, "❌ Нельзя подключиться к другому администратору.")
        return

    if target_id not in users:
        bot.send_message(admin_id, "❌ Пользователь с таким ID не найден.")
        return

    # Если уже был подключён к кому-то — уведомить того
    if admin_id in admin_sessions:
        old_uid = admin_sessions[admin_id]
        try:
            bot.send_message(
                old_uid,
                "ℹ️ Менеджер отключился от вашего чата."
            )
        except Exception:
            pass

    admin_sessions[admin_id] = target_id

    # Уведомить пользователя
    try:
        bot.send_message(
            target_id,
            "✅ К вашему чату подключился менеджер. Вы можете задать вопрос."
        )
    except Exception:
        pass

    bot.send_message(
        admin_id,
        f"✅ Вы подключились к чату:\n{user_display(target_id)}\n\n"
        "Теперь все ваши сообщения будут пересылаться пользователю.\n"
        "Чтобы отключиться — /disconnect"
    )


@bot.message_handler(commands=["disconnect"])
def cmd_disconnect(message: types.Message):
    admin_id = message.from_user.id
    if not is_admin(admin_id):
        return

    if admin_id not in admin_sessions:
        bot.send_message(admin_id, "ℹ️ Вы ни к кому не подключены.")
        return

    target_id = admin_sessions.pop(admin_id)
    try:
        bot.send_message(
            target_id,
            "ℹ️ Менеджер завершил чат. Если появятся вопросы — напишите снова."
        )
    except Exception:
        pass

    bot.send_message(admin_id, f"🔌 Вы отключились от пользователя {user_display(target_id)}.")


@bot.message_handler(commands=["session"])
def cmd_session(message: types.Message):
    admin_id = message.from_user.id
    if not is_admin(admin_id):
        return

    if admin_id not in admin_sessions:
        bot.send_message(admin_id, "ℹ️ Активного подключения нет.")
    else:
        uid = admin_sessions[admin_id]
        bot.send_message(admin_id, f"🔗 Сейчас подключены к: {user_display(uid)}")


# ─────────────────────────────────────────────
#  Обработка обычных сообщений
# ─────────────────────────────────────────────

@bot.message_handler(func=lambda m: True, content_types=["text"])
def handle_text(message: types.Message):
    uid = message.from_user.id
    text = message.text.strip()

    # ── Администратор пишет сообщение ──
    if is_admin(uid):
        # Пересылка в активную сессию
        if uid in admin_sessions:
            target_id = admin_sessions[uid]
            try:
                bot.send_message(
                    target_id,
                    f"💼 <b>Менеджер:</b> {text}"
                )
                bot.send_message(uid, "✉️ Сообщение доставлено.")
            except Exception as e:
                bot.send_message(uid, f"❌ Не удалось отправить: {e}")
        else:
            bot.send_message(
                uid,
                "ℹ️ Вы не подключены ни к одному пользователю.\n"
                "Используйте /connect &lt;user_id&gt; чтобы подключиться."
            )
        return

    # ── Обычный пользователь ──

    # Убедимся, что пользователь зарегистрирован
    if uid not in users:
        users[uid] = {
            "name": message.from_user.full_name,
            "username": message.from_user.username or "",
            "numbers": [],
            "chat_open": True,
        }

    # Проверяем, является ли сообщение номером телефона
    if is_valid_phone(text):
        phone = format_phone(text)

        # Сохраняем номер
        entry = {
            "user_id": uid,
            "number": phone,
            "name": message.from_user.full_name,
            "timestamp": datetime.now().strftime("%d.%m.%Y %H:%M"),
        }
        submitted_numbers.append(entry)
        users[uid].setdefault("numbers", []).append(phone)

        # Ответ пользователю
        bot.send_message(
            uid,
            f"✅ <code>{phone}</code>\n\n"
            "Номер принят в обработку, ожидайте — "
            "к чату подключится наш менеджер."
        )

        # Уведомление администраторам
        notify_admins(
            f"📥 <b>Новый номер!</b>\n\n"
            f"Номер: <code>{phone}</code>\n"
            f"От: {user_display(uid)}\n"
            f"Время: {entry['timestamp']}\n\n"
            f"Подключиться: /connect {uid}"
        )

    else:
        # Обычное текстовое сообщение — пересылаем администраторам
        # и проверяем, подключён ли кто-то к этому пользователю
        connected_admin = None
        for a_id, u_id in admin_sessions.items():
            if u_id == uid:
                connected_admin = a_id
                break

        if connected_admin:
            # Пересылаем подключённому админу
            try:
                uname = f"@{users[uid]['username']}" if users[uid].get("username") else ""
                bot.send_message(
                    connected_admin,
                    f"👤 <b>{users[uid]['name']}</b> {uname} (ID: {uid}):\n{text}"
                )
            except Exception:
                pass
        else:
            # Никто не подключён — уведомляем всех админов
            uname = f"@{users[uid].get('username', '')}"
            notify_admins(
                f"💬 <b>Сообщение от пользователя</b>\n"
                f"От: {user_display(uid)}\n"
                f"Текст: {text}\n\n"
                f"Подключиться: /connect {uid}"
            )
            bot.send_message(
                uid,
                "📨 Ваше сообщение получено. Менеджер ответит вам в ближайшее время."
            )


# ─────────────────────────────────────────────
#  Запуск
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("🤖 Бот запущен. Нажмите Ctrl+C для остановки.")
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
