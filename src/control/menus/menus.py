"""
Inline keyboard builders for the subscription flow.
"""

from decimal import Decimal
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from ...coins import ProviderName
from ...environment import BROADCAST_BOT_USERNAME


def build_main_menu_keyboard(
        show_confirm: bool = False,
        activation_key: Optional[str] = None,
) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🏛️ Select Providers", callback_data="menu:providers")],
        [InlineKeyboardButton("📊 Select Types", callback_data="menu:types")],
        [InlineKeyboardButton("💰 Set Volume", callback_data="menu:volume")],
        [InlineKeyboardButton("🔄 Set Repeat", callback_data="menu:repeat")],
    ]
    if show_confirm and activation_key:
        link = f"https://t.me/{BROADCAST_BOT_USERNAME}?start={activation_key}"
        keyboard.append([InlineKeyboardButton("✅ Confirm", url=link)])
    return InlineKeyboardMarkup(keyboard)


def build_provider_keyboard(
        selected: list[str],
        show_confirm: bool = False,
        activation_key: Optional[str] = None,
) -> InlineKeyboardMarkup:
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
        InlineKeyboardButton("🔙 Back", callback_data="prov:back"),
        InlineKeyboardButton("🏠 Menu", callback_data="prov:menu"),
        InlineKeyboardButton("➡️ Next", callback_data="prov:next"),
    ])

    if show_confirm and activation_key:
        link = f"https://t.me/{BROADCAST_BOT_USERNAME}?start={activation_key}"
        buttons.append([InlineKeyboardButton("✅ Confirm", url=link)])

    return InlineKeyboardMarkup(buttons)


def build_type_keyboard(
        selected: list[str],
        show_confirm: bool = False,
        activation_key: Optional[str] = None,
) -> InlineKeyboardMarkup:
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
        InlineKeyboardButton("🔙 Back", callback_data="type:back"),
        InlineKeyboardButton("🏠 Menu", callback_data="type:menu"),
        InlineKeyboardButton("➡️ Next", callback_data="type:next"),
    ])

    if show_confirm and activation_key:
        link = f"https://t.me/{BROADCAST_BOT_USERNAME}?start={activation_key}"
        buttons.append([InlineKeyboardButton("✅ Confirm", url=link)])

    return InlineKeyboardMarkup(buttons)


def build_volume_keyboard(
        current: Decimal | None,
        show_confirm: bool = False,
        activation_key: Optional[str] = None,
) -> InlineKeyboardMarkup:
    presets = [1, 10, 100, 1000]
    buttons = []
    for v in presets:
        checked = "✅ " if current == Decimal(v) else ""
        buttons.append([InlineKeyboardButton(f"{checked}{v}", callback_data=f"vol:{v}")])

    buttons.append([InlineKeyboardButton("✏️ Custom", callback_data="vol:custom")])

    buttons.append([
        InlineKeyboardButton("🔙 Back", callback_data="vol:back"),
        InlineKeyboardButton("🏠 Menu", callback_data="vol:menu"),
        InlineKeyboardButton("➡️ Next", callback_data="vol:next"),
    ])

    if show_confirm and activation_key:
        link = f"https://t.me/{BROADCAST_BOT_USERNAME}?start={activation_key}"
        buttons.append([InlineKeyboardButton("✅ Confirm", url=link)])

    return InlineKeyboardMarkup(buttons)


def build_repeat_keyboard(
        current: int | None,
        show_confirm: bool = False,
        activation_key: Optional[str] = None,
) -> InlineKeyboardMarkup:
    presets = [1, 2, 5, 10, 30, 60]
    buttons = []
    for minutes in presets:
        label = f"{minutes}m" if minutes >= 1 else f"{minutes}s"
        checked = "✅ " if current == minutes else ""
        buttons.append([InlineKeyboardButton(f"{checked}{label}", callback_data=f"rep:{minutes}")])

    buttons.append([InlineKeyboardButton("✏️ Custom", callback_data="rep:custom")])

    buttons.append([
        InlineKeyboardButton("🔙 Back", callback_data="rep:back"),
        InlineKeyboardButton("🏠 Menu", callback_data="rep:menu"),
        InlineKeyboardButton("➡️ Next", callback_data="rep:next"),
    ])

    if show_confirm and activation_key:
        link = f"https://t.me/{BROADCAST_BOT_USERNAME}?start={activation_key}"
        buttons.append([InlineKeyboardButton("✅ Confirm", url=link)])

    return InlineKeyboardMarkup(buttons)


# ─── Numeric Keypad ─────────────────────────────────────────

def build_numeric_keyboard(
        include_negative: bool = False,
        allow_decimal: bool = False,
) -> InlineKeyboardMarkup:
    buttons = []
    for i in range(1, 10, 3):
        row = []
        for j in range(i, i + 3):
            row.append(InlineKeyboardButton(str(j), callback_data=f"num:{j}"))
        buttons.append(row)

    row4 = []
    if include_negative:
        row4.append(InlineKeyboardButton("±", callback_data="num:negative"))
    if allow_decimal:
        row4.append(InlineKeyboardButton(".", callback_data="num:."))
    row4.append(InlineKeyboardButton("0", callback_data="num:0"))
    row4.append(InlineKeyboardButton("⌫", callback_data="num:backspace"))
    buttons.append(row4)

    buttons.append([
        InlineKeyboardButton("🔙 Back", callback_data="num:back"),
        InlineKeyboardButton("➡️ Next", callback_data="num:next"),
    ])

    return InlineKeyboardMarkup(buttons)
