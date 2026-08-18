from decimal import Decimal

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from ...domain import ProviderName

# ─── Conversation States ─────────────────────────────────────
SELECT_PROVIDER, SELECT_TYPE, SELECT_VOLUME, SELECT_REPEAT, SELECT_CHAT, CONFIRM = range(6)


# ─── Keyboard Builders ──────────────────────────────────────

def build_provider_keyboard(selected: list[str]) -> InlineKeyboardMarkup:
    buttons = []
    for p in ProviderName:
        name = p.value
        checked = "✅ " if name in selected else ""
        buttons.append([InlineKeyboardButton(f"{checked}{name}", callback_data=f"prov_toggle:{name}")])

    buttons.append([
        InlineKeyboardButton("🌐 Select All", callback_data="prov:all"),
        InlineKeyboardButton("❌ Clear All", callback_data="prov:clear"),
    ])

    buttons.append([
        InlineKeyboardButton("🚫 Cancel", callback_data="cancel"),
        InlineKeyboardButton("🔙 Back", callback_data="prov:back"),
        InlineKeyboardButton("➡️ Next", callback_data="prov:next"),
    ])
    return InlineKeyboardMarkup(buttons)


def build_type_keyboard(selected: list[str]) -> InlineKeyboardMarkup:
    buttons = []
    for opt in ["OTC", "P2P"]:
        checked = "✅ " if opt in selected else ""
        buttons.append([InlineKeyboardButton(f"{checked}{opt}", callback_data=f"type_toggle:{opt}")])

    all_checked = "✅ " if len(selected) == 2 else ""
    buttons.append([
        InlineKeyboardButton(f"{all_checked}🌐 All", callback_data="type:all"),
        InlineKeyboardButton("❌ Clear", callback_data="type:clear"),
    ])
    buttons.append([
        InlineKeyboardButton("🚫 Cancel", callback_data="cancel"),
        InlineKeyboardButton("🔙 Back", callback_data="type:back"),
        InlineKeyboardButton("➡️ Next", callback_data="type:next"),
    ])
    return InlineKeyboardMarkup(buttons)


def build_volume_keyboard(current: Decimal | None) -> InlineKeyboardMarkup:
    presets = [1, 10, 100, 1000]
    buttons = []
    for v in presets:
        checked = "✅ " if current == Decimal(v) else ""
        buttons.append([InlineKeyboardButton(f"{checked}{v}", callback_data=f"vol:{v}")])

    buttons.append([InlineKeyboardButton("✏️ Custom", callback_data="vol:custom"), ])

    buttons.append([
        InlineKeyboardButton("🚫 Cancel", callback_data="cancel"),
        InlineKeyboardButton("🔙 Back", callback_data="vol:back"),
        InlineKeyboardButton("➡️ Next", callback_data="vol:next"),
    ])
    return InlineKeyboardMarkup(buttons)


def build_repeat_keyboard(current: int | None) -> InlineKeyboardMarkup:
    presets = [10, 30, 60, 300, 600]
    buttons = []
    for sec in presets:
        label = f"{sec}s" if sec < 60 else f"{sec // 60}m"
        checked = "✅ " if current == sec else ""
        buttons.append([InlineKeyboardButton(f"{checked}{label}", callback_data=f"rep:{sec}")])

    buttons.append([InlineKeyboardButton("✏️ Custom", callback_data="rep:custom"), ])

    buttons.append([
        InlineKeyboardButton("🚫 Cancel", callback_data="cancel"),
        InlineKeyboardButton("🔙 Back", callback_data="rep:back"),
        InlineKeyboardButton("➡️ Next", callback_data="rep:next"),
    ])
    return InlineKeyboardMarkup(buttons)


def build_chat_keyboard(selected: str | None) -> InlineKeyboardMarkup:
    custom_checked = "✅ " if selected == "custom" else ""
    key_checked = "✅ " if selected == "key" else ""
    buttons = [
        [InlineKeyboardButton(f"{custom_checked}✏️ Custom Chat ID", callback_data="chat:custom")],
        [InlineKeyboardButton(f"{key_checked}🔑 Get Key", callback_data="chat:key")],
        [
            InlineKeyboardButton("🚫 Cancel", callback_data="cancel"),
            InlineKeyboardButton("🔙 Back", callback_data="chat:back"),
            InlineKeyboardButton("➡️ Next", callback_data="chat:next"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def build_confirm_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("🚫 Cancel", callback_data="confirm:cancel"),
            InlineKeyboardButton("🔙 Back", callback_data="confirm:back"),
            InlineKeyboardButton("➡️ Next", callback_data="confirm:next"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def build_numeric_keyboard() -> InlineKeyboardMarkup:
    """
    Build a numeric keypad with digits, dot, backspace, next, back, cancel.
    """
    buttons = []
    # First three rows: 1-9
    for i in range(1, 10, 3):
        row = []
        for j in range(i, i + 3):
            row.append(InlineKeyboardButton(str(j), callback_data=f"num:{j}"))
        buttons.append(row)

    # Row 4: dot, 0, backspace
    buttons.append([
        InlineKeyboardButton(".", callback_data="num:."),
        InlineKeyboardButton("0", callback_data="num:0"),
        InlineKeyboardButton("⌫", callback_data="num:backspace"),
    ])

    # Row 5: Cancel, Back, Next
    buttons.append([
        InlineKeyboardButton("🚫 Cancel", callback_data="cancel"),
        InlineKeyboardButton("🔙 Back", callback_data="num:back"),
        InlineKeyboardButton("➡️ Next", callback_data="num:next"),
    ])

    return InlineKeyboardMarkup(buttons)


def build_control_main_menu() -> InlineKeyboardMarkup:
    """
    Build the main menu keyboard for both bots.
    """
    buttons = [
        [InlineKeyboardButton("📊 New Subscription", callback_data="main:new")],
        [InlineKeyboardButton("📋 My Subscriptions", callback_data="main:list")],
        [InlineKeyboardButton("⏸️ Stop Subscription", callback_data="main:stop")],
        [InlineKeyboardButton("▶️ Resume Subscription", callback_data="main:resume")],
        [InlineKeyboardButton("✏️ Edit Subscription", callback_data="main:edit")],
        [InlineKeyboardButton("🗑️ Delete Subscription", callback_data="main:delete")],
        [InlineKeyboardButton("❓ Help", callback_data="main:help")],
    ]
    return InlineKeyboardMarkup(buttons)


def build_broadcast_main_menu() -> InlineKeyboardMarkup:
    """
    Build the main menu for the Broadcast bot.
    """
    buttons = [
        [InlineKeyboardButton("📊 View Prices", callback_data="bcast:prices")],
        [InlineKeyboardButton("🔑 Activate Subscription", callback_data="bcast:activate")],
        [InlineKeyboardButton("❓ Help", callback_data="bcast:help")],
    ]
    return InlineKeyboardMarkup(buttons)
