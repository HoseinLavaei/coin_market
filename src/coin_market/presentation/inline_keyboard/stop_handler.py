"""
Stop subscription handler – multi‑select toggles.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from .common import safe_edit, get_user_data
from ...domain.value_objects import build_subscription_description
from ...infrastructure.repositories import (
    get_subscriptions_for_user,
    pause_subscription_by_id,
)
from ...services.subscription_scheduler import (
    remove_subscription_job,
    reload_subscriptions_immediate,
)

# ─── State constants ─────────────────────────────────────────
SELECT_STOP_SUB = 20
CONFIRM_STOP = 21


# ─── Helper: build keyboard ─────────────────────────────────

def _stop_toggle_keyboard(subs: list, selected_ids: list[int]) -> InlineKeyboardMarkup:
    buttons = []
    for sub in subs:
        if sub.status != "active":
            continue
        checked = "✅ " if sub.id in selected_ids else ""
        desc = build_subscription_description(
            sub.provider,
            sub.type_filter,
            sub.volume,
            sub.repeat_interval,
        )
        buttons.append([
            InlineKeyboardButton(
                f"{checked}⏸️ #{sub.id}: {desc}",
                callback_data=f"stop_toggle:{sub.id}"
            )
        ])

    buttons.append([
        InlineKeyboardButton("🌐 Select All", callback_data="stop:all"),
        InlineKeyboardButton("❌ Clear All", callback_data="stop:clear"),
    ])
    buttons.append([
        InlineKeyboardButton("🚫 Cancel", callback_data="cancel"),
        InlineKeyboardButton("🔙 Back", callback_data="stop:back"),
        InlineKeyboardButton("➡️ Next", callback_data="stop:next"),
    ])
    return InlineKeyboardMarkup(buttons)


# ─── Helper: format IDs ─────────────────────────────────────

def _format_id_list(ids: list[int]) -> str:
    return ", ".join(f"#{sid}" for sid in sorted(ids))


# ─── Helper: process stop ───────────────────────────────────

async def _process_stop_selected(selected: list[int], user_id: int) -> tuple[list[str], list[str]]:
    stopped = []
    failed = []
    for sub_id in selected:
        count = await pause_subscription_by_id(sub_id, user_id)
        if count:
            remove_subscription_job(sub_id)
            stopped.append(str(sub_id))
        else:
            failed.append(str(sub_id))
    return stopped, failed


# ─── Main menu entry ─────────────────────────────────────────

async def stop_subscription_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()

    user = update.effective_user
    if not user:
        await safe_edit(query, "❌ Could not identify user.")
        return ConversationHandler.END

    subs = await get_subscriptions_for_user(user.id)
    active_subs = [s for s in subs if s.status == "active"]

    if not active_subs:
        await safe_edit(query, "✅ You have no active subscriptions to stop.")
        return ConversationHandler.END

    user_data = get_user_data(context)
    if "stop_selected" not in user_data:
        user_data["stop_selected"] = []

    await safe_edit(
        query,
        "📋 Select subscriptions to stop (toggle each):",
        reply_markup=_stop_toggle_keyboard(active_subs, user_data["stop_selected"]),
    )
    return SELECT_STOP_SUB


# ─── Toggle callbacks ────────────────────────────────────────

async def stop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()
    data = query.data
    if not data:
        return SELECT_STOP_SUB

    user = update.effective_user
    if not user:
        await safe_edit(query, "❌ Could not identify user.")
        return ConversationHandler.END

    subs = await get_subscriptions_for_user(user.id)
    active_subs = [s for s in subs if s.status == "active"]
    user_data = get_user_data(context)
    selected = user_data.get("stop_selected", [])

    # ─── Toggle ──────────────────────────────────────────────
    if data.startswith("stop_toggle:"):
        sub_id = int(data.split(":", 1)[1])
        if sub_id in selected:
            selected.remove(sub_id)
        else:
            selected.append(sub_id)
        user_data["stop_selected"] = selected
        await safe_edit(
            query,
            "📋 Select subscriptions to stop (toggle each):",
            reply_markup=_stop_toggle_keyboard(active_subs, selected),
        )
        return SELECT_STOP_SUB

    # ─── All ──────────────────────────────────────────────────
    if data == "stop:all":
        selected = [s.id for s in active_subs]
        user_data["stop_selected"] = selected
        await safe_edit(
            query,
            "📋 Select subscriptions to stop (toggle each):",
            reply_markup=_stop_toggle_keyboard(active_subs, selected),
        )
        return SELECT_STOP_SUB

    # ─── Clear ────────────────────────────────────────────────
    if data == "stop:clear":
        selected = []
        user_data["stop_selected"] = selected
        await safe_edit(
            query,
            "📋 Select subscriptions to stop (toggle each):",
            reply_markup=_stop_toggle_keyboard(active_subs, selected),
        )
        return SELECT_STOP_SUB

    # ─── Back ─────────────────────────────────────────────────
    if data == "stop:back":
        user_data.pop("stop_selected", None)
        # End the conversation; main menu will not be shown automatically.
        # The user can use /start or /menu.
        return ConversationHandler.END

    # ─── Next ─────────────────────────────────────────────────
    if data == "stop:next":
        if not selected:
            await safe_edit(
                query,
                "❌ Please select at least one subscription to stop.",
                reply_markup=_stop_toggle_keyboard(active_subs, selected),
            )
            return SELECT_STOP_SUB

        ids_str = _format_id_list(selected)
        buttons = [
            [InlineKeyboardButton("✅ Yes, stop them", callback_data="stop_confirm:yes")],
            [InlineKeyboardButton("❌ No, go back", callback_data="stop_confirm:no")],
        ]
        await safe_edit(
            query,
            f"⚠️ Are you sure you want to stop subscriptions: {ids_str}?",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return CONFIRM_STOP

    return SELECT_STOP_SUB


# ─── Confirm callback ────────────────────────────────────────

async def stop_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()
    data = query.data
    if not data:
        return CONFIRM_STOP

    if not data.startswith("stop_confirm:"):
        return CONFIRM_STOP

    action = data.split(":", 1)[1]
    user_data = get_user_data(context)
    selected = user_data.get("stop_selected", [])

    if action == "no":
        user = update.effective_user
        if user:
            subs = await get_subscriptions_for_user(user.id)
            active_subs = [s for s in subs if s.status == "active"]
            await safe_edit(
                query,
                "📋 Select subscriptions to stop (toggle each):",
                reply_markup=_stop_toggle_keyboard(active_subs, selected),
            )
            return SELECT_STOP_SUB
        return ConversationHandler.END

    if action == "yes":
        user = update.effective_user
        if not user:
            await safe_edit(query, "❌ Could not identify user.")
            user_data.pop("stop_selected", None)
            return ConversationHandler.END

        stopped, failed = await _process_stop_selected(selected, user.id)
        await reload_subscriptions_immediate()

        msg_parts = []
        if stopped:
            msg_parts.append(f"✅ Stopped: #{', #'.join(stopped)}")
        if failed:
            msg_parts.append(f"❌ Failed: #{', #'.join(failed)}")

        user_data.pop("stop_selected", None)
        await safe_edit(query, "\n".join(msg_parts) or "✅ No subscriptions selected.")
        return ConversationHandler.END

    return CONFIRM_STOP
