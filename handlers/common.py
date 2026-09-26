"""
Shared UI pieces: keyboards and simple text menus. Kept separate so handler
modules don't duplicate button layouts.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton

import db


async def resolve_single_elder(update, context):
    """Returns elder_id for a caregiver linked to exactly one elder.
    Sends an explanatory message and returns None otherwise."""
    elders = db.get_elders_for_caregiver(update.effective_user.id)
    if not elders:
        await update.message.reply_text("You're not linked to anyone yet. Use /link <code> first.")
        return None
    if len(elders) > 1:
        names = ", ".join(e["name"] or str(e["telegram_id"]) for e in elders)
        await update.message.reply_text(
            f"You're linked to multiple people ({names}). This simple command only supports one "
            "for now — a future version could let you pick."
        )
        return None
    return elders[0]["telegram_id"]

# A short, friendly list of timezones. Good enough for an MVP; add more if
# your users span other regions.
TIMEZONE_CHOICES = [
    ("🇺🇸 Los Angeles (UTC-8)", "America/Los_Angeles"),
    ("🇺🇸 New York (UTC-5)", "America/New_York"),
    ("🇬🇧 London (UTC+0)", "Europe/London"),
    ("🇩🇪 Berlin (UTC+1)", "Europe/Berlin"),
    ("🇮🇳 Mumbai (UTC+5:30)", "Asia/Kolkata"),
    ("🇹🇭 Bangkok (UTC+7)", "Asia/Bangkok"),
    ("🇸🇬 Singapore (UTC+8)", "Asia/Singapore"),
    ("🇯🇵 Tokyo (UTC+9)", "Asia/Tokyo"),
    ("🇦🇺 Sydney (UTC+10)", "Australia/Sydney"),
]


def role_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("👵 I'm the person taking medicine", callback_data="role:elder")],
            [InlineKeyboardButton("👨‍👩‍👧 I'm a caregiver / family member", callback_data="role:caregiver")],
        ]
    )


def timezone_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(label, callback_data=f"tz:{tzname}")] for label, tzname in TIMEZONE_CHOICES]
    return InlineKeyboardMarkup(rows)


def days_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Every day", callback_data="days:daily")],
            [InlineKeyboardButton("Choose specific days", callback_data="days:custom")],
        ]
    )


WEEKDAY_LABELS = [("Mon", "Mon"), ("Tue", "Tue"), ("Wed", "Wed"), ("Thu", "Thu"),
                   ("Fri", "Fri"), ("Sat", "Sat"), ("Sun", "Sun")]


def weekday_toggle_keyboard(selected: set) -> InlineKeyboardMarkup:
    row = []
    for label, code in WEEKDAY_LABELS:
        mark = "✅ " if code in selected else ""
        row.append(InlineKeyboardButton(f"{mark}{label}", callback_data=f"wd:{code}"))
    # split into two rows of ~4 for readability
    rows = [row[:4], row[4:]]
    rows.append([InlineKeyboardButton("Done ✔️", callback_data="wd:done")])
    return InlineKeyboardMarkup(rows)


def elder_choice_keyboard(elders) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(e["name"] or f"Elder {e['telegram_id']}", callback_data=f"pickelder:{e['telegram_id']}")]
        for e in elders
    ]
    return InlineKeyboardMarkup(rows)


# --- Persistent bottom keyboards ---
# Unlike inline keyboards (which are attached to one specific message and
# disappear into chat history), these sit permanently below the text box,
# so the elder never has to remember or type a command.

ELDER_SUMMARY_BTN = "📊 My Summary"
ELDER_CODE_BTN = "🔑 Get Linking Code"
ASK_QUESTION_BTN = "❓ Ask a Question"

CAREGIVER_ADDMED_BTN = "➕ Add Medication"
CAREGIVER_LISTMEDS_BTN = "📋 List Medications"
CAREGIVER_REMOVEMED_BTN = "🗑 Remove Medication"
CAREGIVER_SUMMARY_BTN = "📊 Summary"


def elder_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(ELDER_SUMMARY_BTN), KeyboardButton(ELDER_CODE_BTN)],
            [KeyboardButton(ASK_QUESTION_BTN)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def caregiver_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(CAREGIVER_ADDMED_BTN), KeyboardButton(CAREGIVER_LISTMEDS_BTN)],
            [KeyboardButton(CAREGIVER_REMOVEMED_BTN), KeyboardButton(CAREGIVER_SUMMARY_BTN)],
            [KeyboardButton(ASK_QUESTION_BTN)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )
