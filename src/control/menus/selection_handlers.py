"""
Selection handlers for provider and type steps.
Auto‑saves to DB immediately.
"""

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from .common import safe_edit, get_user_data, SELECT_PROVIDER, SELECT_TYPE, SELECT_VOLUME
from .menus import build_provider_keyboard, build_type_keyboard
from ...coins import ProviderName
from ...db.repositories.subscription_repository import save_subscription_settings


# ─── Internal helpers ──────────────────────────────────────

def _get_config(prefix: str) -> dict:
    if prefix == "prov":
        return {
            "field": "provider",
            "builder": build_provider_keyboard,
            "label": "🏛️ Select providers",
            "all_items": [p.value for p in ProviderName],
            "state": SELECT_PROVIDER,
            "next_state": SELECT_TYPE,
            "save_field": "provider",
        }
    elif prefix == "type":
        return {
            "field": "type_filter",
            "builder": build_type_keyboard,
            "label": "📊 Select types",
            "all_items": ["OTC", "P2P"],
            "state": SELECT_TYPE,
            "next_state": SELECT_VOLUME,
            "save_field": "type_filter",
        }
    return {}


def _get_current_values(sub: dict, field: str) -> list[str]:
    """Get current values from subscription dict."""
    if field == "provider":
        val: str | None = sub.get("provider")
        if val is not None:
            return val.split(",")
        return []
    elif field == "type_filter":
        val: str | None = sub.get("type_filter")
        if val is not None:
            return val.split(",")
        return []
    return []


def _render_text(_field: str, items: list[str], label: str) -> str:
    selected_names = ", ".join(items) if items else "None"
    count = len(items)
    return f"{label} ({count} selected: {selected_names}) – toggle each, or use All/Clear"


# ─── Entry point for showing a selection step ──────────────

async def show_selection(query, context: ContextTypes.DEFAULT_TYPE, prefix: str) -> int:
    config = _get_config(prefix)
    if not config:
        return ConversationHandler.END

    user_data = get_user_data(context)
    sub = user_data.get("current_subscription", {})
    items = _get_current_values(sub, config["field"])

    text = _render_text(config["field"], items, config["label"])
    await safe_edit(query, text, reply_markup=config["builder"](items))
    return config["state"]


# ─── Handlers for specific actions ──────────────────────────

async def _save_to_db(context: ContextTypes.DEFAULT_TYPE, save_field: str, value: str | None) -> None:
    """Save a single field to the database."""
    user_data = get_user_data(context)
    user_id = user_data.get("user_id")

    if not isinstance(user_id, int):
        return

    kwargs = {save_field: value}
    await save_subscription_settings(user_id=user_id, **kwargs)

    # Update current_subscription in user_data
    sub = user_data.get("current_subscription", {})
    sub[save_field] = value
    user_data["current_subscription"] = sub


async def _handle_toggle(query, context: ContextTypes.DEFAULT_TYPE, prefix: str, name: str) -> int:
    config = _get_config(prefix)
    if not config:
        return ConversationHandler.END

    user_data = get_user_data(context)
    sub = user_data.get("current_subscription", {})
    items = _get_current_values(sub, config["field"])

    if name in items:
        items.remove(name)
    else:
        items.append(name)

    # Save to DB immediately
    value = ",".join(items) if items else None
    await _save_to_db(context, config["save_field"], value)

    # Update display
    text = _render_text(config["field"], items, config["label"])
    await safe_edit(query, text, reply_markup=config["builder"](items))
    return config["state"]


async def _handle_all(query, context: ContextTypes.DEFAULT_TYPE, prefix: str) -> int:
    config = _get_config(prefix)
    if not config:
        return ConversationHandler.END

    items = config["all_items"][:]

    # Save to DB immediately
    value = ",".join(items) if items else None
    await _save_to_db(context, config["save_field"], value)

    text = _render_text(config["field"], items, config["label"])
    await safe_edit(query, text, reply_markup=config["builder"](items))
    return config["state"]


async def _handle_clear(query, context: ContextTypes.DEFAULT_TYPE, prefix: str) -> int:
    config = _get_config(prefix)
    if not config:
        return ConversationHandler.END

    items = []

    # Save to DB immediately
    await _save_to_db(context, config["save_field"], None)

    text = _render_text(config["field"], items, config["label"])
    await safe_edit(query, text, reply_markup=config["builder"](items))
    return config["state"]


async def _handle_back(update: Update, context: ContextTypes.DEFAULT_TYPE, prefix: str) -> int:
    """Handle Back button (only for types, providers has no Back)."""
    config = _get_config(prefix)
    if not config:
        return ConversationHandler.END

    query = update.callback_query
    if not query:
        return ConversationHandler.END

    # For providers, go to main menu (Back button doesn't exist here)
    if prefix == "prov":
        from .control_menus import show_main_menu
        return await show_main_menu(query, context)
    else:
        # prefix == "type" – go back to providers
        return await show_selection(query, context, "prov")


async def _handle_next(update: Update, context: ContextTypes.DEFAULT_TYPE, prefix: str) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    config = _get_config(prefix)
    if not config:
        return ConversationHandler.END

    user_data = get_user_data(context)
    sub = user_data.get("current_subscription", {})
    items = _get_current_values(sub, config["field"])

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
        # prefix == "type"
        from .volume_handler import show_volume
        return await show_volume(query, context)


async def _handle_menu(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Return to main menu."""
    from .control_menus import show_main_menu
    return await show_main_menu(query, context)


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

    if action == "all":
        return await _handle_all(query, context, prefix)
    elif action == "clear":
        return await _handle_clear(query, context, prefix)
    elif action == "back":
        return await _handle_back(update, context, prefix)
    elif action == "next":
        return await _handle_next(update, context, prefix)
    elif action == "menu":
        return await _handle_menu(query, context)
    else:
        return ConversationHandler.END
