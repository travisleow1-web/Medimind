from telegram import Update
from telegram.ext import ContextTypes

import db
from handlers.common import timezone_keyboard, caregiver_menu_keyboard
from handlers.start import HELP_TEXT_CAREGIVER


async def handle_registration_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Returns True if this message was consumed as a registration step
    (so main.py's catch-all handler knows not to process it further)."""
    awaiting = context.user_data.get("awaiting")
    if awaiting not in ("name_elder", "name_caregiver"):
        return False

    name = update.message.text.strip()
    db.upsert_user(update.effective_user.id, name=name)
    context.user_data.pop("awaiting", None)

    if awaiting == "name_elder":
        await update.message.reply_text(
            f"Nice to meet you, {name}! One last thing — what timezone are you in? "
            "This makes sure reminders arrive at the right time.",
            reply_markup=timezone_keyboard(),
        )
    else:
        await update.message.reply_text(
            f"Thanks, {name}!\n\n" + HELP_TEXT_CAREGIVER,
            parse_mode="Markdown",
            reply_markup=caregiver_menu_keyboard(),
        )
    return True
