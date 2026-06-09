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

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
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

    # Имя берём из Telegram-профиля: имя + фамилия, или только имя, или username
    first = (user.first_name or "").strip()
    last = (user.last_name or "").strip()
    display_name = f"{first} {last}".strip() if last else first
    if not display_name:
        display_name = user.username or "Игрок"

    REG_STATE[user_id] = {"step": "goal", "name": display_name}

    await update.message.reply_text(
        "⚡ *Система обнаружила тебя.*\n\n"
        "Ты попал в *Commit Club* — закрытый клуб людей, которые не просто мечтают, а делают каждый день.\n\n"
        "Здесь нет мотивационных постов. Нет теории. Только одно правило:\n\n"
        "*Каждый день — одно действие к своей цели. И отчёт боту.*",
        parse_mode=ParseMode.MARKDOWN,
    )

    await update.message.reply_text(
        "⚙️ *Как это работает:*\n\n"
        "1️⃣ Ты ставишь одну цель на 60 дней\n"
        "2️⃣ Каждый день пишешь боту что сделал — текстом или фото\n"
        "3️⃣ Получаешь XP и Aura, растёшь в ранге\n"
        "4️⃣ Бот объявляет о твоих результатах в общей группе\n\n"
        "🔥 Пропустил день — стрик _(сколько дней подряд выполняешь квест)_ сгорает.\n"
        "📈 Держишь стрик — получаешь бонусы и поднимаешься в рейтинге.\n\n"
        "Никто не заставляет тебя платить. Никаких скрытых условий.\n"
        "Это просто система, которая не даёт тебе забить на себя и свою цель.",
        parse_mode=ParseMode.MARKDOWN,
    )

    await update.message.reply_text(
        "Готов? Напиши свою цель на 60 дней — одним предложением. Чем конкретнее — тем лучше.\n\n"
        "_Например: «Зарабатывать 100к в месяц.» или «Убрать 10 кг.» или «Запустить свой проект»_",
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


# ── /setname ──────────────────────────────────────────────────────────────────

async def cmd_setname(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not db.get_user(user_id):
        await update.message.reply_text("Ты ещё не в системе. Напиши /start")
        return
    new_name = " ".join(ctx.args).strip() if ctx.args else ""
    if not new_name:
        await update.message.reply_text(
            "Укажи новое имя: `/setname Новое имя`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    if len(new_name) > 32:
        await update.message.reply_text("Имя слишком длинное — максимум 32 символа.")
        return
    db.update_user_name(user_id, new_name)
    await update.message.reply_text(
        f"✅ Имя обновлено: *{new_name}*",
        parse_mode=ParseMode.MARKDOWN,
    )


# ── /setgoal ──────────────────────────────────────────────────────────────────

async def cmd_setgoal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    if not user:
        await update.message.reply_text("Ты ещё не в системе. Напиши /start")
        return
    new_goal = " ".join(ctx.args).strip() if ctx.args else ""
    if not new_goal:
        await update.message.reply_text(
            "Укажи новую цель: `/setgoal Моя новая цель`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    if len(new_goal) > 200:
        await update.message.reply_text("Цель слишком длинная — максимум 200 символов.")
        return
    old_goal = user["goal"]
    db.update_user_goal(user_id, new_goal)
    await update.message.reply_text(
        f"✅ Цель обновлена:\n\n"
        f"Было: _{old_goal}_\n"
        f"Стало: _{new_goal}_",
        parse_mode=ParseMode.MARKDOWN,
    )
    if GROUP_ID:
        name = user["display_name"]
        try:
            await ctx.bot.send_message(
                GROUP_ID,
                f"🔄 *{name}* сменил цель.\n\n"
                f"Новая цель: _{new_goal}_",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            logger.warning(f"Goal change group post failed: {e}")


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
        f"🎮 *Игрок {state['name']} — добро пожаловать в систему.*\n\n"
        f"🎯 Цель: _{state['goal']}_\n"
        f"Начальный ранг: {rank_badge('E')}",
        parse_mode=ParseMode.MARKDOWN,
    )

    await msg.reply_text(
        "Что дальше:\n\n"
        "• Каждый день пиши мне что сделал — текстом или фото\n"
        "• Чем дольше стрик — тем больше XP и бонусы\n"
        "• Бот объявит о твоём прогрессе в группу\n\n"
        "Первый квест — *сегодня.*\n"
        "Напиши что уже сделал или что сделаешь прямо сейчас 👇",
        parse_mode=ParseMode.MARKDOWN,
    )

    if GROUP_ID:
        try:
            await ctx.bot.send_message(
                GROUP_ID,
                f"🆕 *{state['name']}* вступил в Commit Club!\n"
                f"🎯 Цель: _{state['goal']}_\n\n"
                f"Поприветствуем нового игрока 👊",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            logger.warning(f"New member group post failed: {e}")


async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    # Placeholder — nickname step removed, no inline buttons in registration anymore
    await update.callback_query.answer()


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
    app.add_handler(CommandHandler("setname", cmd_setname))
    app.add_handler(CommandHandler("setgoal", cmd_setgoal))
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
