"""
Commit Club — Telegram MVP Bot v2
"""

import os
import logging
from datetime import time as dtime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode

import database as db

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN  = os.environ.get("BOT_TOKEN", "")
GROUP_ID   = int(os.environ.get("GROUP_ID", "0"))
ADMIN_IDS  = [int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()]

REG_STATE: dict[int, dict] = {}
CALLOUT_CODE: dict = {"code": ""}

RANK_EMOJI = {"E": "⬛", "D": "🟫", "C": "🟦", "B": "🟩", "A": "🟨", "S": "🟥"}

def rank_badge(rank: str) -> str:
    return f"{RANK_EMOJI.get(rank, '⬛')} Ранг {rank}"

def xp_to_next(xp: int, rank: str) -> str:
    thresholds = {"E": 100, "D": 300, "C": 700, "B": 1500, "A": 3000, "S": None}
    nxt = thresholds.get(rank)
    if nxt is None:
        return "Ранг S — ты на вершине"
    return f"До следующего ранга: {nxt - xp} XP"

def profile_text(p: dict) -> str:
    done = "✅ выполнен" if p["reported_today"] else "⏳ ещё не сдан"
    return (
        f"👤 *{p['display_name']}*\n"
        f"🎯 Цель: _{p['goal']}_\n\n"
        f"{rank_badge(p['rank'])}\n"
        f"⚡ {p['xp']} XP  |  🔮 {p['aura']} Aura\n"
        f"🔥 Стрик: {p['streak']} дн.  |  Рекорд: {p['best_streak']} дн.\n"
        f"📋 Всего отчётов: {p['total_reports']}\n\n"
        f"Квест сегодня: {done}\n"
        f"_{xp_to_next(p['xp'], p['rank'])}_"
    )


# ── /start ────────────────────────────────────────────────────────────────────

WELCOME_TEXT = """\
⚡ *Система обнаружила тебя.*

Ты попал в *Commit Club* — закрытый клуб людей, которые не просто мечтают, а делают каждый день.

Здесь нет мотивационных постов. Нет теории. Только одно правило:

*Каждый день — одно действие к своей цели. И отчёт боту.*

━━━━━━━━━━━━━━━
⚙️ *Как это работает:*

1️⃣ Ты ставишь одну цель на 60 дней
2️⃣ Каждый день пишешь боту что сделал — текстом или фото
3️⃣ Получаешь XP и Aura, растёшь в ранге
4️⃣ Бот объявляет о твоих результатах в общей группе

🔥 Пропустил день — стрик (сколько дней подряд выполняешь квест) сгорает.
📈 Держишь стрик — получаешь бонусы и поднимаешься в рейтинге.

*Никто не заставляет тебя платить. Никаких скрытых условий.*
Это просто система, которая не даёт тебе забить на себя и свою цель.

━━━━━━━━━━━━━━━
Готов? Напиши свою цель на 60 дней — одним предложением. Чем конкретнее - тем лучше.

_Например: «Зарабатывать 100к в месяц.» или «Убрать 10 кг.» или «Запустить свой проект»_\
"""

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    existing = db.get_user(user_id)
    if existing:
        await update.message.reply_text(
            f"Ты уже в системе, *{existing['display_name']}* 👊\n\n"
            f"Твой ранг: {rank_badge(existing['rank'])}\n"
            "Используй /profile чтобы посмотреть прогресс.\n"
            "Или сразу отправь сегодняшний отчёт — текстом или фото.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    REG_STATE[user_id] = {"step": "goal"}
    await update.message.reply_text(
        WELCOME_TEXT,
        parse_mode=ParseMode.MARKDOWN,
    )


# ── /profile ──────────────────────────────────────────────────────────────────

async def cmd_profile(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    p = db.get_user_profile(user_id)
    if not p:
        await update.message.reply_text(
            "Ты ещё не в системе. Напиши /start — займёт 30 секунд."
        )
        return
    await update.message.reply_text(profile_text(p), parse_mode=ParseMode.MARKDOWN)


# ── /report ───────────────────────────────────────────────────────────────────

async def cmd_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📝 Просто напиши что сделал сегодня — текстом или фото с подписью.\n"
        "Одно предложение — уже достаточно."
    )


# ── HANDLE TEXT / PHOTO ───────────────────────────────────────────────────────

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    msg = update.message

    # ── Registration flow ──────────────────────────────────────────────────
    if user_id in REG_STATE:
        state = REG_STATE[user_id]
        text = (msg.text or "").strip()

        if state["step"] == "goal":
            if not text:
                await msg.reply_text("Напиши цель — одним предложением 👇")
                return
            state["goal"] = text
            state["step"] = "name"
            tg_name = user.username or user.first_name or "Hunter"
            await msg.reply_text(
                f"Цель принята: _{text}_\n\n"
                "Теперь выбери никнейм — под ним тебя будут видеть в группе.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        f"Использовать @{tg_name}",
                        callback_data=f"reg_name:{tg_name}"
                    ),
                    InlineKeyboardButton(
                        "Ввести своё",
                        callback_data="reg_name:custom"
                    ),
                ]])
            )
            return

        if state["step"] == "name_custom":
            if not text:
                await msg.reply_text("Напиши никнейм 👇")
                return
            state["name"] = text
            await _finish_registration(update, ctx, user_id, user.username or "")
            return

        return

    # ── Report flow ────────────────────────────────────────────────────────
    existing = db.get_user(user_id)
    if not existing:
        await msg.reply_text(
            "Ты не в системе. Напиши /start — займёт 30 секунд."
        )
        return

    has_photo = bool(msg.photo)
    text = msg.caption or msg.text or ""

    if not text and not has_photo:
        return

    result = db.submit_report(user_id, text, has_photo)

    if "error" in result:
        if result["error"] == "already_reported":
            await msg.reply_text(
                "Квест сегодня уже выполнен ✅\n"
                "Возвращайся завтра — стрик продолжается 🔥"
            )
        return

    # ── Личка: ответ участнику ─────────────────────────────────────────────
    reasons_str = "  |  ".join(result["reasons"])
    await msg.reply_text(
        f"✅ *Квест выполнен!*\n\n"
        f"{reasons_str}\n\n"
        f"{rank_badge(result['rank'])}\n"
        f"⚡ {result['total_xp']} XP  |  🔮 {result['aura']} Aura\n"
        f"🔥 Стрик: {result['streak']} дн.\n\n"
        f"_{xp_to_next(result['total_xp'], result['rank'])}_",
        parse_mode=ParseMode.MARKDOWN,
    )

    if result.get("rank_up"):
        await msg.reply_text(
            f"🆙 *РАНГ ПОВЫШЕН!*\n\n"
            f"{RANK_EMOJI.get(result['old_rank'], '⬛')} {result['old_rank']}  →  "
            f"{RANK_EMOJI.get(result['rank'], '⬛')} {result['rank']}\n\n"
            "Система фиксирует твой рост. Не останавливайся.",
            parse_mode=ParseMode.MARKDOWN,
        )

    # ── Группа: публичный анонс ────────────────────────────────────────────
    if GROUP_ID:
        streak_fire = "🔥" * min(result["streak"], 5)
        group_text = (
            f"⚡ *{result['display_name']}* закрыл квест!\n"
            f"🎯 _{result['goal']}_\n\n"
            f"{rank_badge(result['rank'])}  |  +{result['xp_earned']} XP\n"
            f"Стрик: {streak_fire} {result['streak']} дн."
        )
        try:
            await ctx.bot.send_message(GROUP_ID, group_text, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.warning(f"Group post failed: {e}")

    if result.get("streak_bonus"):
        if GROUP_ID:
            try:
                await ctx.bot.send_message(
                    GROUP_ID,
                    f"🔥🔥🔥 *{result['display_name']}* держит стрик 7 дней подряд!\n"
                    "Это уже не случайность. Это характер.",
                    parse_mode=ParseMode.MARKDOWN,
                )
            except Exception as e:
                logger.warning(f"Streak group post failed: {e}")


# ── REGISTRATION CALLBACKS ────────────────────────────────────────────────────

async def _finish_registration(update, ctx, user_id, tg_username):
    state = REG_STATE.pop(user_id)
    msg = update.message or update.callback_query.message

    db.register_user(user_id, tg_username, state["name"], state["goal"], False)

    await msg.reply_text(
        f"🎮 *Охотник {state['name']} — добро пожаловать в систему.*\n\n"
        f"🎯 Цель: _{state['goal']}_\n"
        f"Начальный ранг: {rank_badge('E')}\n\n"
        "━━━━━━━━━━━━━━━\n"
        "Что дальше:\n"
        "• Каждый день пиши мне что сделал — текстом или фото\n"
        "• Чем дольше стрик — тем больше XP и бонусы\n"
        "• Бот объявит о твоём прогрессе в группу\n\n"
        "Первый квест — *сегодня.* Пора действовать.\n"
        "Задание: Поставь таймер на 10 минут и сделай первый шаг к своей цели не отвлекаясь до конца 10 минут. Как сделаешь, напиши мне что именно ты сделал. 👇",
        parse_mode=ParseMode.MARKDOWN,
    )

    if GROUP_ID:
        try:
            await ctx.bot.send_message(
                GROUP_ID,
                f"🆕 *{state['name']}* вступил в Commit Club!\n"
                f"🎯 Цель: _{state['goal']}_\n"
                f"Поприветствуем нового охотника 👊",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            logger.warning(f"New member group post failed: {e}")


async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data.startswith("reg_name:"):
        value = data.split(":", 1)[1]

        if value == "custom":
            if user_id not in REG_STATE:
                return
            REG_STATE[user_id]["step"] = "name_custom"
            await query.edit_message_text(
                "Напиши свой никнейм — под ним тебя будут видеть в группе 👇"
            )
            return

        if user_id not in REG_STATE:
            return
        REG_STATE[user_id]["name"] = value
        REG_STATE[user_id]["step"] = "done"
        await query.edit_message_text(
            f"Никнейм: *{value}*",
            parse_mode=ParseMode.MARKDOWN,
        )
        await _finish_registration(update, ctx, user_id, query.from_user.username or "")


# ── /callout ──────────────────────────────────────────────────────────────────

async def cmd_callout(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = ctx.args
    if not args:
        await update.message.reply_text(
            "Укажи код созвона: /callout КОД\n"
            "Код объявляется во время звонка."
        )
        return
    code = args[0].upper()
    if not CALLOUT_CODE["code"]:
        await update.message.reply_text(
            "Сегодня созвона нет или код ещё не установлен."
        )
        return
    result = db.mark_callout(user_id, code, CALLOUT_CODE["code"])
    if "error" in result:
        errors = {
            "wrong_code": "Неверный код. Будь внимательнее на созвоне 👀",
            "already_marked": "Ты уже отмечен на сегодняшнем созвоне ✅",
            "not_registered": "Сначала зарегистрируйся — /start",
        }
        await update.message.reply_text(errors.get(result["error"], "Ошибка"))
        return
    await update.message.reply_text(
        f"✅ Присутствие на созвоне зафиксировано!\n"
        f"+{result['xp_earned']} XP  |  Итого: {result['total_xp']} XP"
    )


# ── ADMIN ─────────────────────────────────────────────────────────────────────

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def cmd_set_callout(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = ctx.args
    if not args:
        await update.message.reply_text("Укажи код: /setcallout КОД")
        return
    CALLOUT_CODE["code"] = args[0].upper()
    await update.message.reply_text(
        f"✅ Код созвона: *{CALLOUT_CODE['code']}*\n"
        "Скажи участникам написать /callout {код} во время звонка.",
        parse_mode=ParseMode.MARKDOWN,
    )

async def cmd_remind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await _send_reminders(ctx)
    await update.message.reply_text("Напоминания отправлены.")

async def cmd_leaderboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    board = db.get_daily_leaderboard()
    if not board:
        await update.message.reply_text("Сегодня ещё никто не сдал квест.")
        return
    await update.message.reply_text(
        _leaderboard_text(board),
        parse_mode=ParseMode.MARKDOWN,
    )


# ── SCHEDULED ─────────────────────────────────────────────────────────────────

def _leaderboard_text(board: list) -> str:
    medals = ["🥇", "🥈", "🥉"] + ["▪️"] * 10
    lines = ["📊 *Итоги дня — рейтинг Commit Club*\n"]
    for i, row in enumerate(board):
        lines.append(
            f"{medals[i]} *{row['display_name']}*  "
            f"{rank_badge(row['rank'])}  "
            f"+{row['xp_earned']} XP  🔥{row['streak']}"
        )
    lines.append("\nЗавтра снова. Не тормози.")
    return "\n".join(lines)

async def _send_reminders(ctx: ContextTypes.DEFAULT_TYPE):
    users = db.get_users_without_report()
    for u in users:
        try:
            await ctx.bot.send_message(
                u["user_id"],
                "⏰ *Квест ещё не закрыт.*\n\n"
                "Стрик под угрозой. Осталось меньше 2 часов.\n\n"
                "Напиши одно предложение — что сделал сегодня.\n"
                "Этого достаточно.",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            logger.warning(f"Reminder failed for {u['user_id']}: {e}")

async def job_evening_reminder(ctx: ContextTypes.DEFAULT_TYPE):
    await _send_reminders(ctx)

async def job_daily_leaderboard(ctx: ContextTypes.DEFAULT_TYPE):
    if not GROUP_ID:
        return
    board = db.get_daily_leaderboard()
    if not board:
        return
    try:
        await ctx.bot.send_message(
            GROUP_ID,
            _leaderboard_text(board),
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        logger.warning(f"Leaderboard post failed: {e}")


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    if not BOT_TOKEN:
        raise RuntimeError("Set BOT_TOKEN environment variable")

    db.init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("profile", cmd_profile))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("callout", cmd_callout))
    app.add_handler(CommandHandler("setcallout", cmd_set_callout))
    app.add_handler(CommandHandler("remind", cmd_remind))
    app.add_handler(CommandHandler("leaderboard", cmd_leaderboard))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_message))

    jq = app.job_queue
    # KG = UTC+6: 20:00 KG = 14:00 UTC, 22:00 KG = 16:00 UTC
    jq.run_daily(job_evening_reminder, time=dtime(14, 0), name="reminder")
    jq.run_daily(job_daily_leaderboard, time=dtime(16, 0), name="leaderboard")

    logger.info("Bot started. Polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
import database as db

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── CONFIG ────────────────────────────────────────────────────────────────────
BOT_TOKEN  = os.environ.get("BOT_TOKEN", "")
GROUP_ID   = int(os.environ.get("GROUP_ID", "0"))
ADMIN_IDS  = [int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()]

# Хранилище временного состояния регистрации (в памяти — ок для MVP)
# { user_id: {"step": "goal"|"name"|"anon", "goal": str, "name": str} }
REG_STATE: dict[int, dict] = {}

# Текущий код для созвона (меняется командой /setcallout)
CALLOUT_CODE: dict = {"code": ""}

# ── RANK DISPLAY ──────────────────────────────────────────────────────────────
RANK_EMOJI = {"E": "⬛", "D": "🟫", "C": "🟦", "B": "🟩", "A": "🟨", "S": "🟥"}

def rank_badge(rank: str) -> str:
    return f"{RANK_EMOJI.get(rank, '⬛')} {rank}"

def xp_to_next(xp: int, rank: str) -> str:
    thresholds = {"E": 100, "D": 300, "C": 700, "B": 1500, "A": 3000, "S": None}
    nxt = thresholds.get(rank)
    if nxt is None:
        return "MAX — ты Легенда"
    return f"{nxt - xp} XP до ранга выше"

def profile_text(p: dict) -> str:
    done = "✅" if p["reported_today"] else "⏳"
    return (
        f"*{p['display_name']}*\n"
        f"🎯 Цель: {p['goal']}\n\n"
        f"{rank_badge(p['rank'])}  |  {p['xp']} XP  |  ⚡ {p['aura']} Aura\n"
        f"🔥 Стрик: {p['streak']} дн.  |  Лучший: {p['best_streak']} дн.\n"
        f"📋 Отчётов всего: {p['total_reports']}\n"
        f"Сегодня: {done}\n\n"
        f"_{xp_to_next(p['xp'], p['rank'])}_"
    )

# ── /start ────────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    existing = db.get_user(user_id)
    if existing:
        await update.message.reply_text(
            f"Ты уже в клубе, {existing['display_name']} 💪\n"
            "Используй /profile чтобы посмотреть прогресс.\n"
            "Или просто отправь отчёт — текстом или фото."
        )
        return

    REG_STATE[user_id] = {"step": "goal"}
    await update.message.reply_text(
        "⚡ *Добро пожаловать в Commit Club*\n\n"
        "Одна цель. Каждый день. Видимый рост.\n\n"
        "Напиши свою цель на 60 дней — одним предложением.\n"
        "_Например: «Зарабатывать 100к в месяц» или «Убрать 10 кг»_",
        parse_mode=ParseMode.MARKDOWN,
    )

# ── /profile ──────────────────────────────────────────────────────────────────
async def cmd_profile(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    p = db.get_user_profile(user_id)
    if not p:
        await update.message.reply_text("Ты не зарегистрирован. Напиши /start")
        return
    await update.message.reply_text(profile_text(p), parse_mode=ParseMode.MARKDOWN)

# ── /report ───────────────────────────────────────────────────────────────────
async def cmd_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📝 Отправь отчёт — текстом или фото с подписью.\n"
        "Напиши что сделал сегодня для своей цели."
    )

# ── HANDLE TEXT / PHOTO ───────────────────────────────────────────────────────
async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    msg = update.message

    # ── Registration flow ──
    if user_id in REG_STATE:
        state = REG_STATE[user_id]
        text = (msg.text or "").strip()

        if state["step"] == "goal":
            if not text:
                await msg.reply_text("Напиши цель текстом 👇")
                return
            state["goal"] = text
            state["step"] = "name"
            tg_name = user.username or user.first_name or "участник"
            await msg.reply_text(
                f"Цель сохранена: _{text}_\n\n"
                "Как тебя называть в клубе?\n"
                f"Нажми *Использовать @{tg_name}* или напиши своё имя/никнейм.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        f"Использовать @{tg_name}",
                        callback_data=f"reg_name:{tg_name}"
                    )
                ]])
            )
            return

        if state["step"] == "name":
            if not text:
                await msg.reply_text("Напиши имя 👇")
                return
            state["name"] = text
            state["step"] = "anon"
            await msg.reply_text(
                "Когда ты сдаёшь отчёт — бот постит это в общую группу.\n"
                "Как постить твоё имя?",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Публично 📣", callback_data="reg_anon:no"),
                    InlineKeyboardButton("Анонимно 🕶", callback_data="reg_anon:yes"),
                ]])
            )
            return

        return  # waiting for callback

    # ── Report flow ──
    existing = db.get_user(user_id)
    if not existing:
        await msg.reply_text("Сначала зарегистрируйся — /start")
        return

    has_photo = bool(msg.photo)
    text = msg.caption or msg.text or ""

    if not text and not has_photo:
        return  # ignore empty messages

    result = db.submit_report(user_id, text, has_photo)

    if "error" in result:
        if result["error"] == "already_reported":
            await msg.reply_text("Ты уже сдал отчёт сегодня ✅ Возвращайся завтра!")
        return

    # ── Reply to user ──
    reasons_str = "  ".join(result["reasons"])
    await msg.reply_text(
        f"✅ *Отчёт принят!*\n\n"
        f"{reasons_str}\n\n"
        f"{rank_badge(result['rank'])}  |  {result['total_xp']} XP  |  ⚡ {result['aura']} Aura\n"
        f"🔥 Стрик: {result['streak']} дн.",
        parse_mode=ParseMode.MARKDOWN,
    )

    if result.get("rank_up"):
        await msg.reply_text(
            f"🎉 *РАНГ ПОВЫШЕН!*\n{result['old_rank']} → {result['rank']}\n\nТы растёшь.",
            parse_mode=ParseMode.MARKDOWN,
        )

    # ── Post to group ──
    if GROUP_ID:
        name = "Анонимный участник" if result["is_anon"] else result["display_name"]
        goal_str = f"_{result['goal']}_" if not result["is_anon"] else ""
        group_text = (
            f"⚡ *{name}* выполнил квест сегодня!\n"
            f"{goal_str}\n"
            f"{rank_badge(result['rank'])}  +{result['xp_earned']} XP  |  Стрик 🔥{result['streak']}"
        ).strip()
        try:
            await ctx.bot.send_message(GROUP_ID, group_text, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.warning(f"Could not post to group: {e}")

    if result.get("streak_bonus"):
        if GROUP_ID:
            name = "Анонимный участник" if result["is_anon"] else result["display_name"]
            try:
                await ctx.bot.send_message(
                    GROUP_ID,
                    f"🔥🔥🔥 *{name}* держит стрик 7 дней подряд! Железная воля.",
                    parse_mode=ParseMode.MARKDOWN,
                )
            except Exception as e:
                logger.warning(f"Group streak post failed: {e}")

# ── CALLBACKS (registration) ──────────────────────────────────────────────────
async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data.startswith("reg_name:"):
        name = data.split(":", 1)[1]
        if user_id not in REG_STATE:
            return
        REG_STATE[user_id]["name"] = name
        REG_STATE[user_id]["step"] = "anon"
        await query.edit_message_text(
            f"Имя: *{name}*\n\nКак постить твоё имя в группу?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Публично 📣", callback_data="reg_anon:no"),
                InlineKeyboardButton("Анонимно 🕶", callback_data="reg_anon:yes"),
            ]])
        )

    elif data.startswith("reg_anon:"):
        is_anon = data.split(":", 1)[1] == "yes"
        if user_id not in REG_STATE:
            return
        state = REG_STATE.pop(user_id)
        tg_username = query.from_user.username or ""
        db.register_user(user_id, tg_username, state["name"], state["goal"], is_anon)

        anon_str = "анонимно 🕶" if is_anon else "публично 📣"
        await query.edit_message_text(
            f"🎯 *Добро пожаловать в клуб, {state['name']}!*\n\n"
            f"Цель: _{state['goal']}_\n"
            f"В группе ты будешь {anon_str}\n\n"
            f"Начальный ранг: {rank_badge('E')}\n\n"
            "Каждый день пиши мне свой отчёт — текстом или фото.\n"
            "Бот начислит XP и объявит об этом в группе.\n\n"
            "💪 Первый квест уже сегодня!",
            parse_mode=ParseMode.MARKDOWN,
        )

# ── /callout ──────────────────────────────────────────────────────────────────
async def cmd_callout(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = ctx.args
    if not args:
        await update.message.reply_text(
            "Укажи код: /callout КОД\n"
            "Код дня объявляется на созвоне."
        )
        return
    code = args[0].upper()
    if not CALLOUT_CODE["code"]:
        await update.message.reply_text("Сегодня созвона нет или код ещё не установлен.")
        return
    result = db.mark_callout(user_id, code, CALLOUT_CODE["code"])
    if "error" in result:
        errors = {
            "wrong_code": "Неверный код. Внимательнее слушай созвон 👀",
            "already_marked": "Ты уже отмечен на сегодняшнем созвоне ✅",
            "not_registered": "Сначала зарегистрируйся — /start",
        }
        await update.message.reply_text(errors.get(result["error"], "Ошибка"))
        return
    await update.message.reply_text(
        f"✅ Присутствие на созвоне отмечено!\n"
        f"+{result['xp_earned']} XP → итого {result['total_xp']} XP"
    )

# ── ADMIN COMMANDS ────────────────────────────────────────────────────────────
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def cmd_set_callout(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = ctx.args
    if not args:
        await update.message.reply_text("Укажи код: /setcallout КОД")
        return
    CALLOUT_CODE["code"] = args[0].upper()
    await update.message.reply_text(
        f"✅ Код созвона установлен: *{CALLOUT_CODE['code']}*\n"
        "Скажи участникам написать /callout {код} во время или после звонка.",
        parse_mode=ParseMode.MARKDOWN,
    )

async def cmd_remind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await _send_reminders(ctx)
    await update.message.reply_text("Напоминания отправлены.")

async def cmd_leaderboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    board = db.get_daily_leaderboard()
    if not board:
        await update.message.reply_text("Сегодня ещё никто не сдал отчёт.")
        return
    await update.message.reply_text(
        _leaderboard_text(board),
        parse_mode=ParseMode.MARKDOWN,
    )

# ── SCHEDULED JOBS ────────────────────────────────────────────────────────────
def _leaderboard_text(board: list) -> str:
    medals = ["🥇", "🥈", "🥉"] + ["▫️"] * 10
    lines = ["📊 *Рейтинг дня*\n"]
    for i, row in enumerate(board):
        name = "Аноним" if row["is_anon"] else row["display_name"]
        lines.append(
            f"{medals[i]} {name}  {rank_badge(row['rank'])}  "
            f"+{row['xp_earned']} XP  🔥{row['streak']}"
        )
    return "\n".join(lines)

async def _send_reminders(ctx: ContextTypes.DEFAULT_TYPE):
    users = db.get_users_without_report()
    for u in users:
        try:
            await ctx.bot.send_message(
                u["user_id"],
                "⏰ Ты ещё не сдал отчёт сегодня!\n"
                "🔥 Стрик под угрозой. Осталось 2 часа.\n\n"
                "Напиши что сделал — одно предложение, и дело сделано.",
            )
        except Exception as e:
            logger.warning(f"Reminder failed for {u['user_id']}: {e}")

async def job_evening_reminder(ctx: ContextTypes.DEFAULT_TYPE):
    await _send_reminders(ctx)

async def job_daily_leaderboard(ctx: ContextTypes.DEFAULT_TYPE):
    if not GROUP_ID:
        return
    board = db.get_daily_leaderboard()
    if not board:
        return
    try:
        await ctx.bot.send_message(
            GROUP_ID,
            _leaderboard_text(board),
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        logger.warning(f"Leaderboard post failed: {e}")

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    if not BOT_TOKEN:
        raise RuntimeError("Set BOT_TOKEN environment variable")

    db.init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("profile", cmd_profile))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("callout", cmd_callout))
    app.add_handler(CommandHandler("setcallout", cmd_set_callout))
    app.add_handler(CommandHandler("remind", cmd_remind))
    app.add_handler(CommandHandler("leaderboard", cmd_leaderboard))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_message))

    # Scheduled jobs (UTC times — adjust offset for your timezone)
    # KG = UTC+6: 20:00 KG = 14:00 UTC, 22:00 KG = 16:00 UTC
    jq = app.job_queue
    jq.run_daily(job_evening_reminder, time=dtime(14, 0), name="reminder")
    jq.run_daily(job_daily_leaderboard, time=dtime(16, 0), name="leaderboard")

    logger.info("Bot started. Polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
