"""
Generic selection handlers for provider and type selection.
Used by control_menus.
"""

from typing import Any

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from .common import safe_edit, get_draft
from .menus import (
    build_provider_keyboard,
    build_type_keyboard,
    SELECT_PROVIDER,
    SELECT_TYPE,
)
from ...domain import ProviderName


# ─── Generic Selection State ──────────────────────────────

def get_selection_state(prefix: str) -> dict[str, Any]:
    if prefix == "prov":
        return {
            "field": "providers",
            "builder": build_provider_keyboard,
            "label": "🏛️ Select providers",
            "all_items": [p.value for p in ProviderName],
            "state": SELECT_PROVIDER,
            "back_state": None,
        }
    elif prefix == "type":
        return {
            "field": "types",
            "builder": build_type_keyboard,
            "label": "💵 Select types",
            "all_items": ["OTC", "P2P"],
            "state": SELECT_TYPE,
            "back_state": SELECT_PROVIDER,
        }
    return {}


def render_selection(field: str, draft: dict, label: str) -> str:
    items = draft.get(field, [])
    selected_names = ", ".join(items) if items else "None"
    count = len(items)
    return f"{label} ({count} selected: {selected_names}) – toggle each, or use All/Clear"


async def show_selection(query, context: ContextTypes.DEFAULT_TYPE, prefix: str) -> int:
    config = get_selection_state(prefix)
    if not config:
        return ConversationHandler.END

    draft = get_draft(context)
    text = render_selection(config["field"], draft, config["label"])
    await safe_edit(query, text, reply_markup=config["builder"](draft.get(config["field"], [])))
    return config["state"]


async def handle_toggle(query, context: ContextTypes.DEFAULT_TYPE, prefix: str, name: str) -> int:
    config = get_selection_state(prefix)
    if not config:
        return ConversationHandler.END

    draft = get_draft(context)
    items = draft.get(config["field"], [])

    if name in items:
        items.remove(name)
    else:
        items.append(name)

    draft[config["field"]] = items
    text = render_selection(config["field"], draft, config["label"])
    await safe_edit(query, text, reply_markup=config["builder"](items))
    return config["state"]


async def handle_all(query, context: ContextTypes.DEFAULT_TYPE, prefix: str) -> int:
    config = get_selection_state(prefix)
    if not config:
        return ConversationHandler.END

    draft = get_draft(context)
    items = config["all_items"][:]
    draft[config["field"]] = items

    text = render_selection(config["field"], draft, config["label"])
    await safe_edit(query, text, reply_markup=config["builder"](items))
    return config["state"]


async def handle_clear(query, context: ContextTypes.DEFAULT_TYPE, prefix: str) -> int:
    config = get_selection_state(prefix)
    if not config:
        return ConversationHandler.END

    draft = get_draft(context)
    items = []
    draft[config["field"]] = items

    text = render_selection(config["field"], draft, config["label"])
    await safe_edit(query, text, reply_markup=config["builder"](items))
    return config["state"]


async def handle_back(update: Update, context: ContextTypes.DEFAULT_TYPE, prefix: str, show_main_menu_callback) -> int:
    config = get_selection_state(prefix)
    if not config:
        return ConversationHandler.END

    query = update.callback_query
    if not query:
        return ConversationHandler.END

    if config["back_state"] == SELECT_PROVIDER:
        return await show_selection(query, context, "prov")
    else:
        await show_main_menu_callback(update, context)
        return ConversationHandler.END


async def handle_next(update: Update, context: ContextTypes.DEFAULT_TYPE, prefix: str) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    config = get_selection_state(prefix)
    if not config:
        return ConversationHandler.END

    draft = get_draft(context)
    items = draft.get(config["field"], [])

    if not items:
        await safe_edit(
            query,
            f"❌ Please select at least one, or use 'All'.",
            reply_markup=config["builder"](items),
        )
        return config["state"]

    if prefix == "prov":
        return await show_selection(query, context, "type")
    else:  # type → volume
        from .volume_handler import show_volume
        return await show_volume(query, context)


async def selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, show_main_menu_callback) -> int:
    """Generic handler for provider and type selection."""
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()
    data = query.data
    if not data:
        return ConversationHandler.END

    # Handle toggles
    if data.startswith("prov_toggle:"):
        name = data.split(":", 1)[1]
        return await handle_toggle(query, context, "prov", name)
    if data.startswith("type_toggle:"):
        name = data.split(":", 1)[1]
        return await handle_toggle(query, context, "type", name)

    # Handle other actions
    parts = data.split(":", 1)
    if len(parts) < 2:
        return ConversationHandler.END

    prefix, action = parts[0], parts[1]

    if action == "cancel" or data == "cancel":
        await safe_edit(query, "❌ Subscription cancelled.")
        return ConversationHandler.END

    if action == "all":
        return await handle_all(query, context, prefix)
    elif action == "clear":
        return await handle_clear(query, context, prefix)
    elif action == "back":
        return await handle_back(update, context, prefix, show_main_menu_callback)
    elif action == "next":
        return await handle_next(update, context, prefix)
    else:
        return ConversationHandler.END
