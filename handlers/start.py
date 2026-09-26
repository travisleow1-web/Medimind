from telegram import Update
from telegram.ext import ContextTypes

import db
from handlers.common import role_keyboard, elder_menu_keyboard, caregiver_menu_keyboard

HELP_TEXT_ELDER = (
    "Here's what I can do:\n\n"
    "• I'll remind you when it's time to take your medicine.\n"
    "• Just tap *Taken ✅* or *Skip ⏭️* on the reminder — no typing needed.\n"
    "• Use the buttons below to see your summary, get your linking code, or ask a "
    "general health question.\n"
)

HELP_TEXT_CAREGIVER = (
    "Here's what I can do:\n\n"
    "• Link to the person you're caring for with /link <code>\n"
    "• Use the buttons below to add, list, or remove medications, and see adherence\n"
    "• I'll message you if a dose is missed.\n"
    "• /status anytime to check I'm still running.\n"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    if user is None:
        await update.message.reply_text(
            "Welcome! First, tell me — are you the person taking medicine, "
            "or a family member / caregiver helping set things up?",
            reply_markup=role_keyboard(),
        )
        return

    if user["role"] == "elder":
        await update.message.reply_text(
            f"Welcome back{', ' + user['name'] if user['name'] else ''}!\n\n" + HELP_TEXT_ELDER,
            parse_mode="Markdown",
            reply_markup=elder_menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            f"Welcome back{', ' + user['name'] if user['name'] else ''}!\n\n" + HELP_TEXT_CAREGIVER,
            parse_mode="Markdown",
            reply_markup=caregiver_menu_keyboard(),
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    if user is None:
        await start(update, context)
        return
    text = HELP_TEXT_ELDER if user["role"] == "elder" else HELP_TEXT_CAREGIVER
    await update.message.reply_text(text, parse_mode="Markdown")
