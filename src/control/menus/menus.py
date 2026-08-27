"""
Inline keyboard builders for the subscription flow.
"""

from decimal import Decimal

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from ...coins import ProviderName


# ─── Main Menu Keyboard ─────────────────────────────────────

def build_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Build the main menu dashboard keyboard."""
    keyboard = [
        [InlineKeyboardButton("🏛️ Select Providers", callback_data="menu:providers")],
        [InlineKeyboardButton("📊 Select Types", callback_data="menu:types")],
        [InlineKeyboardButton("💰 Set Volume", callback_data="menu:volume")],
        [InlineKeyboardButton("🔄 Set Repeat", callback_data="menu:repeat")],
        [InlineKeyboardButton("✅ Confirm & Activate", callback_data="menu:confirm")],
        [InlineKeyboardButton("❌ Cancel", callback_data="menu:cancel")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ─── Provider Keyboard ─────────────────────────────────────

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
        InlineKeyboardButton("➡️ Next", callback_data="prov:next"),
        InlineKeyboardButton("✅ Done", callback_data="prov:done"),
    ])
    return InlineKeyboardMarkup(buttons)


# ─── Type Keyboard ──────────────────────────────────────────

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
        InlineKeyboardButton("✅ Done", callback_data="type:done"),
    ])
    return InlineKeyboardMarkup(buttons)


# ─── Volume Keyboard ────────────────────────────────────────

def build_volume_keyboard(current: Decimal | None) -> InlineKeyboardMarkup:
    presets = [1, 10, 100, 1000]
    buttons = []
    for v in presets:
        checked = "✅ " if current == Decimal(v) else ""
        buttons.append([InlineKeyboardButton(f"{checked}{v}", callback_data=f"vol:{v}")])

    buttons.append([InlineKeyboardButton("✏️ Custom", callback_data="vol:custom")])

    buttons.append([
        InlineKeyboardButton("🚫 Cancel", callback_data="cancel"),
        InlineKeyboardButton("🔙 Back", callback_data="vol:back"),
        InlineKeyboardButton("➡️ Next", callback_data="vol:next"),
        InlineKeyboardButton("✅ Done", callback_data="vol:done"),
    ])
    return InlineKeyboardMarkup(buttons)


# ─── Repeat Keyboard ────────────────────────────────────────

def build_repeat_keyboard(current: int | None) -> InlineKeyboardMarkup:
    """Build repeat keyboard with options in minutes."""
    presets = [1, 2, 5, 10, 30, 60]  # minutes
    buttons = []
    for minutes in presets:
        label = f"{minutes}m" if minutes >= 1 else f"{minutes}s"
        checked = "✅ " if current == minutes else ""
        buttons.append([InlineKeyboardButton(f"{checked}{label}", callback_data=f"rep:{minutes}")])

    buttons.append([InlineKeyboardButton("✏️ Custom", callback_data="rep:custom")])

    buttons.append([
        InlineKeyboardButton("🚫 Cancel", callback_data="cancel"),
        InlineKeyboardButton("🔙 Back", callback_data="rep:back"),
        InlineKeyboardButton("➡️ Next", callback_data="rep:next"),
        InlineKeyboardButton("✅ Done", callback_data="rep:done"),
    ])
    return InlineKeyboardMarkup(buttons)


# ─── Confirm Keyboard ───────────────────────────────────────

def build_confirm_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("🚫 Cancel", callback_data="confirm:cancel"),
            InlineKeyboardButton("🔙 Back", callback_data="confirm:back"),
            InlineKeyboardButton("✅ Done", callback_data="confirm:done"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


# ─── Numeric Keypad ─────────────────────────────────────────

def build_numeric_keyboard(
        include_negative: bool = False,
        allow_decimal: bool = False,
) -> InlineKeyboardMarkup:
    buttons = []
    # First three rows: 1-9
    for i in range(1, 10, 3):
        row = []
        for j in range(i, i + 3):
            row.append(InlineKeyboardButton(str(j), callback_data=f"num:{j}"))
        buttons.append(row)

    # Row 4: dynamic buttons
    row4 = []
    if include_negative:
        row4.append(InlineKeyboardButton("±", callback_data="num:negative"))
    if allow_decimal:
        row4.append(InlineKeyboardButton(".", callback_data="num:."))
    row4.append(InlineKeyboardButton("0", callback_data="num:0"))
    row4.append(InlineKeyboardButton("⌫", callback_data="num:backspace"))
    buttons.append(row4)

    # Row 5: Cancel, Back, Next
    buttons.append([
        InlineKeyboardButton("🚫 Cancel", callback_data="cancel"),
        InlineKeyboardButton("🔙 Back", callback_data="num:back"),
        InlineKeyboardButton("➡️ Next", callback_data="num:next"),
    ])

    return InlineKeyboardMarkup(buttons)