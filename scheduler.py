"""
Background jobs, run on a fixed interval via APScheduler:

1. check_and_send_reminders — for every active medication, checks whether
   "now" (in the elder's own timezone) matches one of its scheduled times
   AND today matches its scheduled days. If so, creates a log entry and
   sends the elder a reminder with Taken/Skip buttons.

2. check_escalations — looks at all still-"pending" logs. After
   FOLLOWUP_NUDGE_MINUTES with no response, sends one gentle nudge to the
   elder. After ESCALATION_WINDOW_MINUTES with no response, marks the dose
   "missed" and notifies the elder's linked caregiver(s).
"""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

import db
from config import FOLLOWUP_NUDGE_MINUTES, ESCALATION_WINDOW_MINUTES

logger = logging.getLogger(__name__)


def _reminder_keyboard(log_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Taken ✅", callback_data=f"resp:taken:{log_id}"),
                InlineKeyboardButton("Skip ⏭️", callback_data=f"resp:skip:{log_id}"),
            ]
        ]
    )


async def check_and_send_reminders(bot: Bot):
    meds = db.all_active_medications()
    for med in meds:
        elder = db.get_user(med["elder_id"])
        if elder is None:
            continue
        try:
            tz = ZoneInfo(elder["timezone"] or "UTC")
        except Exception:
            tz = ZoneInfo("UTC")

        now_local = datetime.now(tz)
        today_abbr = db.WEEKDAYS[now_local.weekday()]

        days = med["days"]
        if days != "daily" and today_abbr not in [d.strip() for d in days.split(",")]:
            continue

        times = [t.strip() for t in med["times"].split(",") if t.strip()]
        now_hhmm = now_local.strftime("%H:%M")
        if now_hhmm not in times:
            continue

        slot_key = now_local.strftime("%Y-%m-%dT%H:%M")
        if db.log_exists_for_slot(med["id"], slot_key):
            continue  # already sent for this exact slot

        log_id = db.create_log(med["id"], slot_key)

        dose_text = f" ({med['dose']})" if med["dose"] else ""
        text = f"💊 Time for your medicine: *{med['name']}*{dose_text}\n\nHave you taken it?"
        try:
            await bot.send_message(
                chat_id=med["elder_id"],
                text=text,
                parse_mode="Markdown",
                reply_markup=_reminder_keyboard(log_id),
            )
        except TelegramError as e:
            logger.warning("Failed to send reminder to %s: %s", med["elder_id"], e)


async def check_escalations(bot: Bot):
    # Step 1: gentle nudge after FOLLOWUP_NUDGE_MINUTES
    nudge_candidates = db.pending_logs_older_than(FOLLOWUP_NUDGE_MINUTES, not_nudged_only=True)
    for log in nudge_candidates:
        # Don't nudge something that's already past the escalation window —
        # that will be handled below instead.
        med = db.get_medication(log["medication_id"])
        if med is None:
            continue
        try:
            await bot.send_message(
                chat_id=med["elder_id"],
                text=f"👋 Just checking in — did you take your *{med['name']}* yet?",
                parse_mode="Markdown",
                reply_markup=_reminder_keyboard(log["id"]),
            )
            db.mark_nudged(log["id"])
        except TelegramError as e:
            logger.warning("Failed to send nudge to %s: %s", med["elder_id"], e)

    # Step 2: escalate to caregivers after ESCALATION_WINDOW_MINUTES
    escalation_candidates = db.pending_logs_older_than(ESCALATION_WINDOW_MINUTES)
    for log in escalation_candidates:
        med = db.get_medication(log["medication_id"])
        if med is None:
            continue
        elder = db.get_user(med["elder_id"])
        db.mark_missed_and_escalated(log["id"])

        caregivers = db.get_caregivers_for_elder(med["elder_id"])
        elder_name = (elder["name"] if elder and elder["name"] else "Your family member")
        for cg in caregivers:
            try:
                await bot.send_message(
                    chat_id=cg["telegram_id"],
                    text=(
                        f"⚠️ {elder_name} hasn't confirmed taking *{med['name']}* "
                        f"(scheduled {log['scheduled_for'].split('T')[1]}). "
                        f"You may want to check in."
                    ),
                    parse_mode="Markdown",
                )
            except TelegramError as e:
                logger.warning("Failed to notify caregiver %s: %s", cg["telegram_id"], e)
