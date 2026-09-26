import logging
from datetime import datetime, timezone

from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import db
import scheduler as reminder_scheduler
from config import BOT_TOKEN, REMINDER_CHECK_INTERVAL_SECONDS, ADMIN_TELEGRAM_ID

from handlers.start import start, help_command
from handlers.elder import mycode, summary
from handlers.caregiver import link, listmeds, removemed
from handlers.medication import (
    addmed_start, got_name, got_dose, got_times, days_choice, weekday_toggle, cancel,
    NAME, DOSE, TIMES, DAYS_CUSTOM,
)
from handlers.callbacks import role_selected, timezone_selected, reminder_response, remove_medication
from handlers.registration import handle_registration_text
from handlers.status import status
from handlers.ask import ask_start, got_question, cancel_ask, ASKING
from handlers.common import (
    ELDER_SUMMARY_BTN, ELDER_CODE_BTN, ASK_QUESTION_BTN,
    CAREGIVER_ADDMED_BTN, CAREGIVER_LISTMEDS_BTN, CAREGIVER_REMOVEMED_BTN, CAREGIVER_SUMMARY_BTN,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def catch_all_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles plain text that isn't part of an active conversation — right
    now that's just the 'what's your name' registration step. Anything else
    gets a gentle nudge toward /help."""
    consumed = await handle_registration_text(update, context)
    if not consumed:
        await update.message.reply_text("Not sure what to do with that. Try /help for a list of commands.")


async def job_send_reminders(context: ContextTypes.DEFAULT_TYPE):
    await reminder_scheduler.check_and_send_reminders(context.bot)
    context.bot_data["last_reminder_check"] = datetime.now(timezone.utc)


async def job_check_escalations(context: ContextTypes.DEFAULT_TYPE):
    await reminder_scheduler.check_escalations(context.bot)


async def _post_init(application: Application):
    """Registers the '/' command menu Telegram shows next to the text box,
    records the bot's start time (for /status), and — if configured —
    tells the admin the bot just came online."""
    application.bot_data["start_time"] = datetime.now(timezone.utc)

    await application.bot.set_my_commands(
        [
            BotCommand("start", "Register / show welcome message"),
            BotCommand("help", "Show what I can do"),
            BotCommand("mycode", "Get a code to share with a caregiver (elder)"),
            BotCommand("link", "Link to an elder using their code (caregiver)"),
            BotCommand("addmed", "Add a medication (caregiver)"),
            BotCommand("listmeds", "List medications (caregiver)"),
            BotCommand("removemed", "Remove a medication (caregiver)"),
            BotCommand("summary", "Show 7-day adherence summary"),
            BotCommand("ask", "Ask a general health question"),
            BotCommand("status", "Check whether the bot is running"),
            BotCommand("cancel", "Cancel whatever you're in the middle of"),
        ]
    )

    if ADMIN_TELEGRAM_ID is not None:
        try:
            await application.bot.send_message(chat_id=ADMIN_TELEGRAM_ID, text="🟢 MediMind is online.")
        except Exception as e:
            logger.warning("Couldn't notify admin of startup: %s", e)


async def _post_shutdown(application: Application):
    """Best-effort notice on a graceful stop (Ctrl+C / SIGTERM). This will
    NOT fire on a crash, power loss, or lost internet — only a planned
    shutdown. For crash detection, see the README's uptime-monitoring
    option."""
    if ADMIN_TELEGRAM_ID is not None:
        try:
            await application.bot.send_message(chat_id=ADMIN_TELEGRAM_ID, text="🔴 MediMind is going offline.")
        except Exception as e:
            logger.warning("Couldn't notify admin of shutdown: %s", e)


def build_application() -> Application:
    application = ApplicationBuilder().token(BOT_TOKEN).post_init(_post_init).post_shutdown(_post_shutdown).build()

    # --- simple commands ---
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("mycode", mycode))
    application.add_handler(CommandHandler("summary", summary))
    application.add_handler(CommandHandler("link", link))
    application.add_handler(CommandHandler("listmeds", listmeds))
    application.add_handler(CommandHandler("removemed", removemed))
    application.add_handler(CommandHandler("status", status))

    # --- registration button callbacks ---
    application.add_handler(CallbackQueryHandler(role_selected, pattern=r"^role:"))
    application.add_handler(CallbackQueryHandler(timezone_selected, pattern=r"^tz:"))

    # --- reminder response / medication removal callbacks ---
    application.add_handler(CallbackQueryHandler(reminder_response, pattern=r"^resp:"))
    application.add_handler(CallbackQueryHandler(remove_medication, pattern=r"^rmmed:"))

    # --- add-medication conversation ---
    addmed_conv = ConversationHandler(
        entry_points=[
            CommandHandler("addmed", addmed_start),
            MessageHandler(filters.Text([CAREGIVER_ADDMED_BTN]), addmed_start),
        ],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_name)],
            DOSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_dose)],
            TIMES: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_times)],
            DAYS_CUSTOM: [
                CallbackQueryHandler(days_choice, pattern=r"^days:"),
                CallbackQueryHandler(weekday_toggle, pattern=r"^wd:"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(addmed_conv)

    # --- ask-a-question conversation (health-info assistant) ---
    ask_conv = ConversationHandler(
        entry_points=[
            CommandHandler("ask", ask_start),
            MessageHandler(filters.Text([ASK_QUESTION_BTN]), ask_start),
        ],
        states={
            ASKING: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_question)],
        },
        fallbacks=[CommandHandler("cancel", cancel_ask)],
    )
    application.add_handler(ask_conv)

    # --- persistent bottom-keyboard buttons (mainly for the elder, who
    # should never need to type a command) ---
    application.add_handler(MessageHandler(filters.Text([ELDER_SUMMARY_BTN, CAREGIVER_SUMMARY_BTN]), summary))
    application.add_handler(MessageHandler(filters.Text([ELDER_CODE_BTN]), mycode))
    application.add_handler(MessageHandler(filters.Text([CAREGIVER_LISTMEDS_BTN]), listmeds))
    application.add_handler(MessageHandler(filters.Text([CAREGIVER_REMOVEMED_BTN]), removemed))

    # --- catch-all for plain text (registration name capture) ---
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, catch_all_text))

    # --- background jobs ---
    if application.job_queue is None:
        raise RuntimeError(
            "JobQueue is not available. Install with: pip install \"python-telegram-bot[job-queue]\""
        )
    application.job_queue.run_repeating(
        job_send_reminders, interval=REMINDER_CHECK_INTERVAL_SECONDS, first=5
    )
    application.job_queue.run_repeating(
        job_check_escalations, interval=REMINDER_CHECK_INTERVAL_SECONDS, first=10
    )

    return application


def main():
    db.init_db()
    application = build_application()
    logger.info("Bot starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
