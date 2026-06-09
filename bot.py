"""
Commit Club — Telegram MVP Bot v10
Логика: все действия через кнопки меню → режим ожидания → следующее сообщение обрабатывается
"""

import asyncio
import os
import logging
from datetime import time as dtime

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
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

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
GROUP_ID  = int(os.environ.get("GROUP_ID", "0"))
ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()]

# ── СОСТОЯНИЯ ─────────────────────────────────────────────────────────────────
# { user_id: "report" | "setgoal" | "setname" | "callout" | "reg_goal" }
USER_STATE: dict[int, str] = {}

RANK_EMOJI = {"E": "⬛", "D": "🟫", "C": "🟦", "B": "🟩", "A": "🟨", "S": "🟥"}
CALLOUT_CODE: dict = {"code": ""}

# ── КНОПКИ ────────────────────────────────────────────────────────────────────
MAIN_MENU = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📝 Отчёт"), KeyboardButton("👤 Профиль")],
        [KeyboardButton("🎯 Изменить цель"), KeyboardButton("✏️ Изменить имя")],
        [KeyboardButton("📞 Отметиться на созвоне")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

# ── HELPERS ───────────────────────────────────────────────────────────────────

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
        f"⚡ {p['xp']} XP\n"
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
        USER_STATE.pop(user_id, None)
        await update.message.reply_text(
            f"Ты уже в системе, *{existing['display_name']}* 👊\n\n"
            f"Твой ранг: {rank_badge(existing['rank'])}\n"
            "Используй меню ниже 👇",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=MAIN_MENU,
        )
        return

    # Имя из Telegram-профиля
    first = (user.first_name or "").strip()
    last  = (user.last_name or "").strip()
    display_name = f"{first} {last}".strip() if last else first
    if not display_name:
        display_name = user.username or "Игрок"

    ctx.user_data["reg_name"] = display_name
    USER_STATE[user_id] = "reg_goal"

    await update.message.reply_text(
        "⚡ *Система обнаружила тебя.*\n\n"
        "Ты попал в *Commit Club* — закрытый клуб людей, которые не просто мечтают, а делают каждый день.\n\n"
        "Здесь нет мотивационных постов. Нет теории. Только одно правило:\n\n"
        "*Каждый день — одно действие к своей цели. И отчёт боту.*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardRemove(),
    )

    await asyncio.sleep(3)

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

    await asyncio.sleep(3)

    await update.message.reply_text(
        "Готов? Напиши свою цель на 60 дней — одним предложением. Чем конкретнее — тем лучше.\n\n"
        "_Например: «Зарабатывать 100к в месяц.» или «Убрать 10 кг.» или «Запустить свой проект»_",
        parse_mode=ParseMode.MARKDOWN,
    )

# ── ГЛАВНЫЙ ОБРАБОТЧИК СООБЩЕНИЙ ─────────────────────────────────────────────

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg  = update.message
    user = update.effective_user
    user_id = user.id

    # Игнорируем группы
    if msg.chat.type in ("group", "supergroup", "channel"):
        return

    text = (msg.text or msg.caption or "").strip()

    # ── Регистрация: ждём цель ────────────────────────────────────────────
    if USER_STATE.get(user_id) == "reg_goal":
        if not text:
            await msg.reply_text("Напиши цель — одним предложением 👇")
            return
        goal = text
        name = ctx.user_data.get("reg_name", user.first_name or "Игрок")
        USER_STATE.pop(user_id)
        db.register_user(user_id, user.username or "", name, goal, False)

        await msg.reply_text(
            f"🎮 *Игрок {name} — добро пожаловать в систему.*\n\n"
            f"🎯 Цель: _{goal}_\n"
            f"Начальный ранг: {rank_badge('E')}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=MAIN_MENU,
        )
        await msg.reply_text(
            "Что дальше:\n\n"
            "• Каждый день нажимай *📝 Отчёт* и пиши что сделал\n"
            "• Чем дольше стрик — тем больше XP и бонусы\n"
            "• Бот объявит о твоём прогрессе в группу\n\n"
            "Первый квест — *сегодня* 👇",
            parse_mode=ParseMode.MARKDOWN,
        )
        if GROUP_ID:
            try:
                await ctx.bot.send_message(
                    GROUP_ID,
                    f"🆕 *{name}* вступил в Commit Club!\n"
                    f"🎯 Цель: _{goal}_\n\n"
                    "Поприветствуем нового игрока 👊",
                    parse_mode=ParseMode.MARKDOWN,
                )
            except Exception as e:
                logger.warning(f"New member group post failed: {e}")
        return

    # ── Проверяем что пользователь зарегистрирован ────────────────────────
    db_user = db.get_user(user_id)
    if not db_user:
        await msg.reply_text(
            "Ты не в системе. Напиши /start — займёт 30 секунд.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    # ── Обработка кнопок меню ─────────────────────────────────────────────
    if text == "📝 Отчёт":
        USER_STATE[user_id] = "report"
        await msg.reply_text(
            "Напиши что сделал сегодня — текстом или отправь фото с подписью.\n"
            "Одно предложение — уже достаточно 👇"
        )
        return

    if text == "👤 Профиль":
        p = db.get_user_profile(user_id)
        await msg.reply_text(profile_text(p), parse_mode=ParseMode.MARKDOWN)
        return

    if text == "🎯 Изменить цель":
        USER_STATE[user_id] = "setgoal"
        await msg.reply_text(
            f"Текущая цель: _{db_user['goal']}_\n\n"
            "Напиши новую цель 👇",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if text == "✏️ Изменить имя":
        USER_STATE[user_id] = "setname"
        await msg.reply_text(
            f"Текущее имя: *{db_user['display_name']}*\n\n"
            "Напиши новое имя 👇",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if text == "📞 Отметиться на созвоне":
        USER_STATE[user_id] = "callout"
        await msg.reply_text(
            "Напиши код созвона 👇\n"
            "_Код объявляется во время звонка_",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # ── Обработка ввода после кнопки ─────────────────────────────────────
    state = USER_STATE.get(user_id)

    if state == "report":
        has_photo = bool(msg.photo)
        if not text and not has_photo:
            return
        USER_STATE.pop(user_id)
        result = db.submit_report(user_id, text, has_photo)

        if "error" in result:
            if result["error"] == "already_reported":
                await msg.reply_text(
                    "Квест сегодня уже выполнен ✅\n"
                    "Возвращайся завтра — стрик продолжается 🔥",
                    reply_markup=MAIN_MENU,
                )
            return

        reasons_str = "  |  ".join(result["reasons"])
        await msg.reply_text(
            f"✅ *Квест выполнен!* {reasons_str}\n"
            f"⚡ {result['total_xp']} XP  |  🔥 Стрик: {result['streak']} дн.\n"
            f"_{xp_to_next(result['total_xp'], result['rank'])}_\n\n"
            "Так держать — ты на шаг ближе к своей цели 💪",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=MAIN_MENU,
        )

        if result.get("rank_up"):
            await msg.reply_text(
                f"🆙 *РАНГ ПОВЫШЕН!*\n\n"
                f"{RANK_EMOJI.get(result['old_rank'], '⬛')} {result['old_rank']}  →  "
                f"{RANK_EMOJI.get(result['rank'], '⬛')} {result['rank']}\n\n"
                "Система фиксирует твой рост. Не останавливайся.",
                parse_mode=ParseMode.MARKDOWN,
            )

        if GROUP_ID:
            report_display = text if text else "📷 фото"
            group_text = (
                f"✅ *{result['display_name']}* {report_display}  ➕{result['xp_earned']} XP\n"
                f"🎯 {result['goal']}  |  🔥 {result['streak']} дн. / {result['days_joined']} дн."
            )
            try:
                await ctx.bot.send_message(GROUP_ID, group_text, parse_mode=ParseMode.MARKDOWN)
            except Exception as e:
                logger.warning(f"Group post failed: {e}")

        if result.get("streak_bonus") and GROUP_ID:
            try:
                await ctx.bot.send_message(
                    GROUP_ID,
                    f"🔥🔥🔥 *{result['display_name']}* держит стрик 7 дней подряд!\n"
                    "Это уже не случайность. Это характер.",
                    parse_mode=ParseMode.MARKDOWN,
                )
            except Exception as e:
                logger.warning(f"Streak group post failed: {e}")
        return

    if state == "setgoal":
        if not text:
            await msg.reply_text("Напиши новую цель 👇")
            return
        if len(text) > 200:
            await msg.reply_text("Слишком длинно — максимум 200 символов.")
            return
        old_goal = db_user["goal"]
        USER_STATE.pop(user_id)
        db.update_user_goal(user_id, text)
        await msg.reply_text(
            f"✅ Цель обновлена\n\n"
            f"Было: _{old_goal}_\n"
            f"Стало: _{text}_",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=MAIN_MENU,
        )
        if GROUP_ID:
            try:
                await ctx.bot.send_message(
                    GROUP_ID,
                    f"🔄 *{db_user['display_name']}* сменил цель.\n\n"
                    f"Новая цель: _{text}_",
                    parse_mode=ParseMode.MARKDOWN,
                )
            except Exception as e:
                logger.warning(f"Goal change group post failed: {e}")
        return

    if state == "setname":
        if not text:
            await msg.reply_text("Напиши новое имя 👇")
            return
        if len(text) > 32:
            await msg.reply_text("Слишком длинно — максимум 32 символа.")
            return
        USER_STATE.pop(user_id)
        db.update_user_name(user_id, text)
        await msg.reply_text(
            f"✅ Имя обновлено: *{text}*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=MAIN_MENU,
        )
        return

    if state == "callout":
        if not text:
            await msg.reply_text("Напиши код созвона 👇")
            return
        USER_STATE.pop(user_id)
        if not CALLOUT_CODE["code"]:
            await msg.reply_text(
                "Сегодня созвона нет или код ещё не установлен.",
                reply_markup=MAIN_MENU,
            )
            return
        result = db.mark_callout(user_id, text, CALLOUT_CODE["code"])
        if "error" in result:
            errors = {
                "wrong_code": "Неверный код. Будь внимательнее на созвоне 👀",
                "already_marked": "Ты уже отмечен на сегодняшнем созвоне ✅",
            }
            await msg.reply_text(
                errors.get(result["error"], "Ошибка"),
                reply_markup=MAIN_MENU,
            )
            return
        await msg.reply_text(
            f"✅ Присутствие зафиксировано!\n"
            f"+{result['xp_earned']} XP  |  Итого: {result['total_xp']} XP",
            reply_markup=MAIN_MENU,
        )
        return

    # ── Неизвестное сообщение — показываем меню ───────────────────────────
    await msg.reply_text(
        "Используй меню ниже 👇",
        reply_markup=MAIN_MENU,
    )


# ── ADMIN КОМАНДЫ ─────────────────────────────────────────────────────────────

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def cmd_setcallout(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = ctx.args
    if not args:
        await update.message.reply_text("Укажи код: /setcallout КОД")
        return
    CALLOUT_CODE["code"] = args[0].upper()
    await update.message.reply_text(
        f"✅ Код созвона: *{CALLOUT_CODE['code']}*",
        parse_mode=ParseMode.MARKDOWN,
    )

async def cmd_remind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await _send_personal_reminders(ctx)
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

async def cmd_profile(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    p = db.get_user_profile(user_id)
    if not p:
        await update.message.reply_text("Ты ещё не в системе. Напиши /start")
        return
    await update.message.reply_text(profile_text(p), parse_mode=ParseMode.MARKDOWN)

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

async def _send_personal_reminders(ctx: ContextTypes.DEFAULT_TYPE):
    users = db.get_users_without_report()
    for u in users:
        try:
            await ctx.bot.send_message(
                u["user_id"],
                f"⚡ {u['display_name']}, квест ещё не закрыт.\n"
                f"Стрик 🔥{u['streak']} дн. — не дай ему сгореть.",
            )
        except Exception as e:
            logger.warning(f"Personal reminder failed for {u['user_id']}: {e}")

async def _send_group_reminder(ctx: ContextTypes.DEFAULT_TYPE):
    if not GROUP_ID:
        return
    users = db.get_users_without_report()
    if not users:
        return
    names = "".join(f"• {u['display_name']}\n" for u in users)
    try:
        await ctx.bot.send_message(
            GROUP_ID,
            f"⏰ *Ещё не выполнили квест сегодня:*\n\n{names}\n"
            "До конца дня — 4 часа. Ещё можно.",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        logger.warning(f"Group reminder failed: {e}")

async def job_midday_reminder(ctx: ContextTypes.DEFAULT_TYPE):
    await _send_personal_reminders(ctx)

async def job_evening_reminder(ctx: ContextTypes.DEFAULT_TYPE):
    await _send_group_reminder(ctx)

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

async def job_weekly_leaderboard(ctx: ContextTypes.DEFAULT_TYPE):
    if not GROUP_ID:
        return
    board = db.get_weekly_leaderboard()
    if not board:
        return
    medals = ["🥇", "🥈", "🥉"] + ["▪️"] * 10
    lines = ["🏆 *Рейтинг клуба — итоги недели*\n"]
    for i, row in enumerate(board):
        lines.append(f"{medals[i]} *{row['display_name']}* — {row['xp']} XP  🔥{row['streak']}")
    lines.append("\nВы огонь. Продолжаем 💪")
    try:
        await ctx.bot.send_message(
            GROUP_ID,
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        logger.warning(f"Weekly leaderboard post failed: {e}")


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    if not BOT_TOKEN:
        raise RuntimeError("Set BOT_TOKEN environment variable")

    db.init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",       cmd_start))
    app.add_handler(CommandHandler("profile",     cmd_profile))
    app.add_handler(CommandHandler("setcallout",  cmd_setcallout))
    app.add_handler(CommandHandler("remind",      cmd_remind))
    app.add_handler(CommandHandler("leaderboard", cmd_leaderboard))
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_message))

    jq = app.job_queue
    # KG = UTC+6
    # 14:00 KG = 08:00 UTC — личное напоминание в личку
    # 20:00 KG = 14:00 UTC — напоминание в группу с именами
    # 22:00 KG = 16:00 UTC — рейтинг дня в группу
    # суббота 12:00 KG = 06:00 UTC — недельный рейтинг по XP
    jq.run_daily(job_midday_reminder,    time=dtime(8,  0), name="midday_reminder")
    jq.run_daily(job_evening_reminder,   time=dtime(14, 0), name="evening_reminder")
    jq.run_daily(job_daily_leaderboard,  time=dtime(16, 0), name="leaderboard")
    jq.run_daily(job_weekly_leaderboard, time=dtime(6,  0), days=(5,), name="weekly_leaderboard")

    logger.info("Bot started. Polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
