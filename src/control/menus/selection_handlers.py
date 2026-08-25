"""
Selection handlers for provider and type steps.
"""

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from .common import safe_edit, get_draft, clear_draft, SELECT_PROVIDER, SELECT_TYPE
from .menus import build_provider_keyboard, build_type_keyboard
from ...coins import ProviderName


# ─── Internal helpers ──────────────────────────────────────

def _get_config(prefix: str) -> dict:
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


def _render_text(field: str, draft: dict, label: str) -> str:
    items = draft.get(field, [])
    selected_names = ", ".join(items) if items else "None"
    count = len(items)
    return f"{label} ({count} selected: {selected_names}) – toggle each, or use All/Clear"


# ─── Entry point for showing a selection step ──────────────

async def show_selection(query, context: ContextTypes.DEFAULT_TYPE, prefix: str) -> int:
    config = _get_config(prefix)
    if not config:
        return ConversationHandler.END

    draft = get_draft(context)
    text = _render_text(config["field"], draft, config["label"])
    await safe_edit(query, text, reply_markup=config["builder"](draft.get(config["field"], [])))
    return config["state"]


# ─── Handlers for specific actions ──────────────────────────

async def _handle_toggle(query, context: ContextTypes.DEFAULT_TYPE, prefix: str, name: str) -> int:
    config = _get_config(prefix)
    if not config:
        return ConversationHandler.END

    draft = get_draft(context)
    items = draft.get(config["field"], [])

    if name in items:
        items.remove(name)
    else:
        items.append(name)

    draft[config["field"]] = items
    text = _render_text(config["field"], draft, config["label"])
    await safe_edit(query, text, reply_markup=config["builder"](items))
    return config["state"]


async def _handle_all(query, context: ContextTypes.DEFAULT_TYPE, prefix: str) -> int:
    config = _get_config(prefix)
    if not config:
        return ConversationHandler.END

    draft = get_draft(context)
    items = config["all_items"][:]
    draft[config["field"]] = items

    text = _render_text(config["field"], draft, config["label"])
    await safe_edit(query, text, reply_markup=config["builder"](items))
    return config["state"]


async def _handle_clear(query, context: ContextTypes.DEFAULT_TYPE, prefix: str) -> int:
    config = _get_config(prefix)
    if not config:
        return ConversationHandler.END

    draft = get_draft(context)
    items = []
    draft[config["field"]] = items

    text = _render_text(config["field"], draft, config["label"])
    await safe_edit(query, text, reply_markup=config["builder"](items))
    return config["state"]


async def _handle_back(update: Update, context: ContextTypes.DEFAULT_TYPE, prefix: str) -> int:
    config = _get_config(prefix)
    if not config:
        return ConversationHandler.END

    query = update.callback_query
    if not query:
        return ConversationHandler.END

    if prefix == "type":
        return await show_selection(query, context, "prov")
    else:
        clear_draft(context)
        await safe_edit(query, "❌ Cancelled.")
        return ConversationHandler.END


async def _handle_next(update: Update, context: ContextTypes.DEFAULT_TYPE, prefix: str) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    config = _get_config(prefix)
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
    else:
        # Lazy import to avoid circular dependency
        from .volume_handler import show_volume
        return await show_volume(query, context)


# ─── Main callback router ────────────────────────────────────

async def selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Generic handler for provider and type selection.
    Routes to specific helpers based on the callback data.
    """
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()
    data = query.data
    if not data:
        return ConversationHandler.END

    # ─── Toggle ──────────────────────────────────────────────
    if data.startswith("prov_toggle:"):
        name = data.split(":", 1)[1]
        return await _handle_toggle(query, context, "prov", name)

    if data.startswith("type_toggle:"):
        name = data.split(":", 1)[1]
        return await _handle_toggle(query, context, "type", name)

    # ─── Other actions ──────────────────────────────────────
    parts = data.split(":", 1)
    if len(parts) < 2:
        return ConversationHandler.END

    prefix, action = parts[0], parts[1]

    # Cancel is global
    if action == "cancel" or data == "cancel":
        clear_draft(context)
        await safe_edit(query, "❌ Subscription cancelled.")
        return ConversationHandler.END

    if action == "all":
        return await _handle_all(query, context, prefix)
    elif action == "clear":
        return await _handle_clear(query, context, prefix)
    elif action == "back":
        return await _handle_back(update, context, prefix)
    elif action == "next":
        return await _handle_next(update, context, prefix)
    else:
        return ConversationHandler.END
