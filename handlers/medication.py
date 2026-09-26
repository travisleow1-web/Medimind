"""
The /addmed conversation. This is the one multi-step text flow in the app —
caregivers are assumed to be comfortable typing, unlike the elder, who only
ever needs to tap buttons.
"""
import re

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

import db
from handlers.common import resolve_single_elder, days_keyboard, weekday_toggle_keyboard

NAME, DOSE, TIMES, DAYS_CUSTOM = range(4)

TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


async def addmed_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    elder_id = await resolve_single_elder(update, context)
    if elder_id is None:
        return ConversationHandler.END

    context.user_data["draft_med"] = {"elder_id": elder_id}
    await update.message.reply_text(
        "Let's add a medication. What's it called?\n(Send /cancel anytime to stop.)"
    )
    return NAME


async def got_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if not name:
        await update.message.reply_text("Please send a medication name.")
        return NAME
    context.user_data["draft_med"]["name"] = name
    await update.message.reply_text("What's the dose? (e.g. '1 tablet', '500mg'). Send - to skip.")
    return DOSE


async def got_dose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dose = update.message.text.strip()
    context.user_data["draft_med"]["dose"] = None if dose == "-" else dose
    await update.message.reply_text(
        "What time(s) should I send reminders? Use 24-hour HH:MM.\n"
        "For multiple times a day, separate with commas — e.g. 08:00,20:00"
    )
    return TIMES


async def got_times(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts or not all(TIME_RE.match(p) for p in parts):
        await update.message.reply_text(
            "That doesn't look like a valid time list. Use 24-hour HH:MM, "
            "e.g. 08:00 or 08:00,20:00 — try again."
        )
        return TIMES
    context.user_data["draft_med"]["times"] = ",".join(parts)
    await update.message.reply_text("Which days?", reply_markup=days_keyboard())
    return DAYS_CUSTOM  # reused as the "waiting for a days: callback" state


async def days_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice = query.data.split(":", 1)[1]

    if choice == "daily":
        return await _save_medication(update, context, "daily", edit=True)

    context.user_data["selected_weekdays"] = set()
    await query.edit_message_text(
        "Tap the days it should remind on, then tap Done.",
    )
    await query.message.reply_text("Pick days:", reply_markup=weekday_toggle_keyboard(set()))
    return DAYS_CUSTOM


async def weekday_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    code = query.data.split(":", 1)[1]

    selected = context.user_data.setdefault("selected_weekdays", set())

    if code == "done":
        if not selected:
            await query.answer("Pick at least one day first.", show_alert=True)
            return DAYS_CUSTOM
        ordered = [d for d in db.WEEKDAYS if d in selected]
        return await _save_medication(update, context, ",".join(ordered), edit=False)

    if code in selected:
        selected.discard(code)
    else:
        selected.add(code)
    await query.edit_message_reply_markup(reply_markup=weekday_toggle_keyboard(selected))
    return DAYS_CUSTOM


async def _save_medication(update: Update, context: ContextTypes.DEFAULT_TYPE, days: str, edit: bool):
    draft = context.user_data.get("draft_med", {})
    med_id = db.add_medication(
        elder_id=draft["elder_id"],
        name=draft["name"],
        dose=draft.get("dose"),
        times=draft["times"],
        days=days,
    )
    text = f"✅ Added *{draft['name']}* — {draft['times']} — {days}"
    query = update.callback_query
    if edit:
        await query.edit_message_text(text, parse_mode="Markdown")
    else:
        await query.message.reply_text(text, parse_mode="Markdown")

    context.user_data.pop("draft_med", None)
    context.user_data.pop("selected_weekdays", None)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("draft_med", None)
    context.user_data.pop("selected_weekdays", None)
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END
