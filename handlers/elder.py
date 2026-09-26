from telegram import Update
from telegram.ext import ContextTypes

import db
from handlers.common import resolve_single_elder


async def mycode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    if user is None or user["role"] != "elder":
        await update.message.reply_text(
            "This command is for the person taking medicine. If that's you, "
            "send /start first to register."
        )
        return

    code = db.create_link_code(update.effective_user.id)
    await update.message.reply_text(
        f"Share this code with your family member: `{code}`\n\n"
        f"It's valid for 30 minutes. They should send me `/link {code}` to connect.",
        parse_mode="Markdown",
    )


async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    if user is None:
        await update.message.reply_text("Send /start first to get set up.")
        return

    if user["role"] == "elder":
        elder_id = update.effective_user.id
    else:
        elder_id = await resolve_single_elder(update, context)
        if elder_id is None:
            return

    rows = db.weekly_summary(elder_id)
    if not rows:
        await update.message.reply_text("No medication activity in the last 7 days yet.")
        return

    lines = ["📊 *Last 7 days:*\n"]
    for r in rows:
        lines.append(
            f"• {r['med_name']}: {r['taken']} taken, {r['skipped']} skipped, "
            f"{r['missed']} missed, {r['pending']} pending"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
