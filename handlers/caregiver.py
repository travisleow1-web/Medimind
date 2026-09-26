from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import db
from handlers.common import resolve_single_elder


async def link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    if user is None:
        await update.message.reply_text("Send /start first so I know who you are.")
        return
    if user["role"] != "caregiver":
        await update.message.reply_text("This command is for caregivers.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /link <code>  (ask the elder for their code via /mycode)")
        return

    code = context.args[0]
    elder_id = db.consume_link_code(code, update.effective_user.id)
    if elder_id is None:
        await update.message.reply_text("That code is invalid or has expired. Ask for a new one with /mycode.")
        return

    elder = db.get_user(elder_id)
    elder_name = elder["name"] if elder and elder["name"] else "them"
    await update.message.reply_text(f"✅ Linked! You'll now get alerts if {elder_name} misses a dose.")

    try:
        await context.bot.send_message(
            chat_id=elder_id,
            text="👨‍👩‍👧 A family member just linked their account to help manage your medicines.",
        )
    except Exception:
        pass


async def listmeds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    elder_id = await resolve_single_elder(update, context)
    if elder_id is None:
        return
    meds = db.list_medications(elder_id)
    if not meds:
        await update.message.reply_text("No medications set up yet. Add one with /addmed.")
        return
    lines = ["💊 *Current medications:*\n"]
    for m in meds:
        dose = f" ({m['dose']})" if m["dose"] else ""
        lines.append(f"• {m['name']}{dose} — {m['times']} — {m['days']}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def removemed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    elder_id = await resolve_single_elder(update, context)
    if elder_id is None:
        return
    meds = db.list_medications(elder_id)
    if not meds:
        await update.message.reply_text("No medications to remove.")
        return
    rows = [[InlineKeyboardButton(m["name"], callback_data=f"rmmed:{m['id']}")] for m in meds]
    await update.message.reply_text(
        "Which medication should I remove?", reply_markup=InlineKeyboardMarkup(rows)
    )
