"""
Answers the question "is the bot actually running?" in two ways:
- push: message the admin when the bot starts and (on a graceful stop) stops
- pull: anyone can send /status and get an immediate answer

Note the honest limitation: the "going offline" message only fires on a
graceful shutdown (Ctrl+C / SIGTERM). A crash, power outage, or lost
internet connection won't trigger it — only a "didn't come back online"
gap will reveal that. For an early build this is fine; the README's
"external uptime monitoring" option is the way to catch real crashes too.
"""
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes


def _format_duration(seconds: float) -> str:
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    start_time = context.bot_data.get("start_time")
    last_check = context.bot_data.get("last_reminder_check")

    if start_time is None:
        await update.message.reply_text("🟢 Online (uptime not yet available)")
        return

    uptime = (datetime.now(timezone.utc) - start_time).total_seconds()
    lines = [f"🟢 Online — running for {_format_duration(uptime)}."]

    if last_check is not None:
        since_check = (datetime.now(timezone.utc) - last_check).total_seconds()
        lines.append(f"Last checked for due reminders {_format_duration(since_check)} ago.")
    else:
        lines.append("Haven't run a reminder check yet.")

    await update.message.reply_text("\n".join(lines))
