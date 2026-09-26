"""
The "Ask a Question" feature. Deliberately NOT called an "emergency
consultant" anywhere in the UI — see README for why. Two safety layers sit
in front of the AI:

1. Emergency/crisis keyword detection happens locally, in plain Python,
   BEFORE anything is sent to Gemini. If it matches, the user gets an
   immediate, deterministic response with real emergency numbers — no LLM
   call, no chance of the model saying the wrong thing at the wrong moment.
2. Every AI answer carries a "not a doctor" disclaimer.
"""
import time

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from config import (
    EMERGENCY_NUMBER, CRISIS_HOTLINE_NAME, CRISIS_HOTLINE_NUMBER, ASK_COOLDOWN_SECONDS,
)
from gemini import ask_gemini, GeminiError
import db

ASKING = range(1)[0]  # single state; kept as a range-derived constant for
                       # consistency with the other conversation modules

EMERGENCY_KEYWORDS = [
    "chest pain", "can't breathe", "cant breathe", "cannot breathe",
    "difficulty breathing", "trouble breathing", "not breathing",
    "stopped breathing", "stroke", "face drooping", "slurred speech",
    "severe bleeding", "bleeding heavily", "unconscious", "unresponsive",
    "won't wake up", "wont wake up", "overdose", "overdosed",
    "heart attack", "seizure", "can't get up", "cant get up",
    "severe allergic reaction", "anaphylaxis", "choking", "collapsed",
]

SELF_HARM_KEYWORDS = [
    "suicide", "suicidal", "kill myself", "end my life", "want to die",
    "don't want to live", "dont want to live", "hurt myself", "harm myself",
    "no reason to live", "better off dead",
]


def _contains_any(text: str, keywords) -> bool:
    lowered = text.lower()
    return any(k in lowered for k in keywords)


async def _alert_caregivers(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str):
    """Best-effort notification to any caregiver linked to this elder. Silently
    does nothing if the sender isn't a registered elder or has no caregiver
    linked yet — the on-screen crisis/emergency message to the person
    themselves is the primary safety net either way."""
    user = db.get_user(update.effective_user.id)
    if user is None or user["role"] != "elder":
        return
    name = user["name"] or "Your family member"
    for cg in db.get_caregivers_for_elder(update.effective_user.id):
        try:
            await context.bot.send_message(chat_id=cg["telegram_id"], text=f"{name}: {message}")
        except Exception:
            pass


async def ask_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    last_ask = context.user_data.get("last_ask_ts", 0)
    remaining = ASK_COOLDOWN_SECONDS - (time.time() - last_ask)
    if remaining > 0:
        await update.message.reply_text(
            f"Give me about {int(remaining) + 1} more second(s) before asking another question."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "What would you like to ask? (This isn't for emergencies — "
        f"for those, call {EMERGENCY_NUMBER} right away instead of messaging me.)"
    )
    return ASKING


async def got_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = update.message.text.strip()

    if _contains_any(question, SELF_HARM_KEYWORDS):
        await update.message.reply_text(
            "I'm really glad you reached out, and I want you to have real support right now — "
            "more than I can offer as a bot.\n\n"
            f"Please contact {CRISIS_HOTLINE_NAME} at {CRISIS_HOTLINE_NUMBER} — "
            "they're available right now to talk this through with you.\n\n"
            f"If you're in immediate danger, please call {EMERGENCY_NUMBER}."
        )
        # Deliberately not quoting their exact words to the caregiver — this
        # gets a trusted person involved quickly without broadcasting the
        # full content of a sensitive personal disclosure.
        await _alert_caregivers(
            update, context,
            "reached out to MediMind about something serious just now — please check in on them soon.",
        )
        return ConversationHandler.END

    if _contains_any(question, EMERGENCY_KEYWORDS):
        await update.message.reply_text(
            "⚠️ This sounds like it could be a medical emergency.\n\n"
            f"Please call {EMERGENCY_NUMBER} right now, or get to the nearest emergency room. "
            "Please don't wait for a reply here — I'm not able to help with emergencies."
        )
        await _alert_caregivers(
            update, context,
            f"just asked MediMind something that sounded like a possible medical emergency "
            f"(\"{question}\"). Please check on them right away.",
        )
        return ConversationHandler.END

    if len(question) > 500:
        await update.message.reply_text("Could you make that a bit shorter? Try again in one or two sentences.")
        return ASKING

    thinking_msg = await update.message.reply_text("Let me think about that...")
    try:
        answer = await ask_gemini(question)
    except GeminiError:
        await thinking_msg.edit_text(
            "Sorry, I couldn't get an answer just now. Please try again in a moment, "
            "or ask a caregiver / doctor directly if it's important."
        )
        return ConversationHandler.END

    context.user_data["last_ask_ts"] = time.time()
    await thinking_msg.edit_text(
        f"{answer}\n\n"
        "_I'm not a doctor — for anything specific to you, please check with a real "
        "doctor or pharmacist._",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def cancel_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Okay, no question asked.")
    return ConversationHandler.END
