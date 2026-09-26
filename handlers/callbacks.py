from telegram import Update
from telegram.ext import ContextTypes

import db
from handlers.common import timezone_keyboard, elder_menu_keyboard
from handlers.start import HELP_TEXT_ELDER, HELP_TEXT_CAREGIVER


async def role_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    role = query.data.split(":", 1)[1]  # "elder" or "caregiver"

    db.upsert_user(update.effective_user.id, role=role)
    context.user_data["awaiting"] = f"name_{role}"

    await query.edit_message_text("Got it. What should I call you? (just type your name)")


async def timezone_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tzname = query.data.split(":", 1)[1]

    db.upsert_user(update.effective_user.id, tz=tzname)
    # Editing the existing message can only update its own (inline) keyboard —
    # attaching the persistent bottom keyboard requires sending a new message.
    await query.edit_message_text("Timezone set ✅")
    await query.message.reply_text(
        HELP_TEXT_ELDER, parse_mode="Markdown", reply_markup=elder_menu_keyboard()
    )


async def reminder_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, action, log_id_str = query.data.split(":", 2)
    log_id = int(log_id_str)

    log = db.get_log(log_id)
    if log is None:
        await query.edit_message_text("This reminder is no longer valid.")
        return

    if log["status"] != "pending":
        # Already responded to (e.g. double-tap) — just confirm quietly.
        await query.answer("Already recorded.", show_alert=False)
        return

    status = "taken" if action == "taken" else "skipped"
    db.update_log_status(log_id, status)

    med = db.get_medication(log["medication_id"])
    confirm = "Nice, marked as taken ✅" if status == "taken" else "Okay, marked as skipped."
    med_name = med["name"] if med else "medication"
    await query.edit_message_text(f"{confirm}\n({med_name})")


async def remove_medication(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    med_id = int(query.data.split(":", 1)[1])
    med = db.get_medication(med_id)
    if med is None:
        await query.edit_message_text("Already removed.")
        return
    db.deactivate_medication(med_id)
    await query.edit_message_text(f"Removed {med['name']}.")
