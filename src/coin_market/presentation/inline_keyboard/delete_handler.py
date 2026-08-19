"""
Delete subscription handler – multi‑select toggles.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from .common import safe_edit, get_user_data
from ...infrastructure.repositories import (
    get_subscriptions_for_user,
    delete_subscription_by_id,
)
from ...services.subscription_scheduler import (
    remove_subscription_job,
    reload_subscriptions_immediate,
)
from ...domain.value_objects import build_subscription_description

# ─── State constants ─────────────────────────────────────────
SELECT_DELETE_SUB = 24
CONFIRM_DELETE = 25


# ─── Helper: build keyboard ─────────────────────────────────

def _delete_toggle_keyboard(subs: list, selected_ids: list[int]) -> InlineKeyboardMarkup:
    buttons = []
    for sub in subs:
        desc = build_subscription_description(
            sub.provider,
            sub.type_filter,
            sub.volume,
            sub.repeat_interval,
        )
        status = "✅" if sub.status == "active" else "⏸️"
        checked = "✅ " if sub.id in selected_ids else ""
        buttons.append([
            InlineKeyboardButton(
                f"{checked}🗑️ #{sub.id}: {desc} {status}",
                callback_data=f"delete_toggle:{sub.id}"
            )
        ])

    buttons.append([
        InlineKeyboardButton("🌐 Select All", callback_data="delete:all"),
        InlineKeyboardButton("❌ Clear All", callback_data="delete:clear"),
    ])
    buttons.append([
        InlineKeyboardButton("🚫 Cancel", callback_data="cancel"),
        InlineKeyboardButton("🔙 Back", callback_data="delete:back"),
        InlineKeyboardButton("➡️ Next", callback_data="delete:next"),
    ])
    return InlineKeyboardMarkup(buttons)


# ─── Helper: format IDs ─────────────────────────────────────

def _format_id_list(ids: list[int]) -> str:
    return ", ".join(f"#{sid}" for sid in sorted(ids))


# ─── Helper: process delete ─────────────────────────────────

async def _process_delete_selected(selected: list[int], user_id: int) -> tuple[list[str], list[str]]:
    deleted = []
    failed = []
    for sub_id in selected:
        remove_subscription_job(sub_id)
        count = await delete_subscription_by_id(sub_id, user_id)
        if count:
            deleted.append(str(sub_id))
        else:
            failed.append(str(sub_id))
    return deleted, failed


# ─── Main menu entry ─────────────────────────────────────────

async def delete_subscription_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()

    user = update.effective_user
    if not user:
        await safe_edit(query, "❌ Could not identify user.")
        return ConversationHandler.END

    subs = await get_subscriptions_for_user(user.id)
    if not subs:
        await safe_edit(query, "📭 You have no subscriptions to delete.")
        return ConversationHandler.END

    user_data = get_user_data(context)
    if "delete_selected" not in user_data:
        user_data["delete_selected"] = []

    await safe_edit(
        query,
        "📋 Select subscriptions to delete (toggle each):",
        reply_markup=_delete_toggle_keyboard(subs, user_data["delete_selected"]),
    )
    return SELECT_DELETE_SUB


# ─── Toggle callbacks ────────────────────────────────────────

async def delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()
    data = query.data
    if not data:
        return SELECT_DELETE_SUB

    user = update.effective_user
    if not user:
        await safe_edit(query, "❌ Could not identify user.")
        return ConversationHandler.END

    subs = await get_subscriptions_for_user(user.id)
    user_data = get_user_data(context)
    selected = user_data.get("delete_selected", [])

    # ─── Toggle ──────────────────────────────────────────────
    if data.startswith("delete_toggle:"):
        sub_id = int(data.split(":", 1)[1])
        if sub_id in selected:
            selected.remove(sub_id)
        else:
            selected.append(sub_id)
        user_data["delete_selected"] = selected
        await safe_edit(
            query,
            "📋 Select subscriptions to delete (toggle each):",
            reply_markup=_delete_toggle_keyboard(subs, selected),
        )
        return SELECT_DELETE_SUB

    # ─── All ──────────────────────────────────────────────────
    if data == "delete:all":
        selected = [s.id for s in subs]
        user_data["delete_selected"] = selected
        await safe_edit(
            query,
            "📋 Select subscriptions to delete (toggle each):",
            reply_markup=_delete_toggle_keyboard(subs, selected),
        )
        return SELECT_DELETE_SUB

    # ─── Clear ────────────────────────────────────────────────
    if data == "delete:clear":
        selected = []
        user_data["delete_selected"] = selected
        await safe_edit(
            query,
            "📋 Select subscriptions to delete (toggle each):",
            reply_markup=_delete_toggle_keyboard(subs, selected),
        )
        return SELECT_DELETE_SUB

    # ─── Back ─────────────────────────────────────────────────
    if data == "delete:back":
        user_data.pop("delete_selected", None)
        return ConversationHandler.END

    # ─── Next ─────────────────────────────────────────────────
    if data == "delete:next":
        if not selected:
            await safe_edit(
                query,
                "❌ Please select at least one subscription to delete.",
                reply_markup=_delete_toggle_keyboard(subs, selected),
            )
            return SELECT_DELETE_SUB

        ids_str = _format_id_list(selected)
        buttons = [
            [InlineKeyboardButton("✅ Yes, delete them", callback_data="delete_confirm:yes")],
            [InlineKeyboardButton("❌ No, go back", callback_data="delete_confirm:no")],
        ]
        await safe_edit(
            query,
            f"⚠️ Are you sure you want to permanently delete subscriptions: {ids_str}?",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return CONFIRM_DELETE

    return SELECT_DELETE_SUB


# ─── Confirm callback ────────────────────────────────────────

async def delete_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()
    data = query.data
    if not data:
        return CONFIRM_DELETE

    if not data.startswith("delete_confirm:"):
        return CONFIRM_DELETE

    action = data.split(":", 1)[1]
    user_data = get_user_data(context)
    selected = user_data.get("delete_selected", [])
    user = update.effective_user
    if not user:
        await safe_edit(query, "❌ Could not identify user.")
        user_data.pop("delete_selected", None)
        return ConversationHandler.END

    if action == "no":
        subs = await get_subscriptions_for_user(user.id)
        await safe_edit(
            query,
            "📋 Select subscriptions to delete (toggle each):",
            reply_markup=_delete_toggle_keyboard(subs, selected),
        )
        return SELECT_DELETE_SUB

    if action == "yes":
        deleted, failed = await _process_delete_selected(selected, user.id)
        await reload_subscriptions_immediate()

        msg_parts = []
        if deleted:
            msg_parts.append(f"✅ Deleted: #{', #'.join(deleted)}")
        if failed:
            msg_parts.append(f"❌ Failed: #{', #'.join(failed)}")

        user_data.pop("delete_selected", None)
        await safe_edit(query, "\n".join(msg_parts) or "✅ No subscriptions selected.")
        return ConversationHandler.END

    return CONFIRM_DELETE