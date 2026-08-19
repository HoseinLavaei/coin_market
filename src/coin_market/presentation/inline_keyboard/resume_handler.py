"""
Resume subscription handler – multi‑select toggles.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from .common import safe_edit, get_user_data
from ...infrastructure.repositories import (
    get_subscriptions_for_user,
    resume_subscription_by_id,
)
from ...services.subscription_scheduler import (
    reload_subscriptions_immediate,
)
from ...domain.value_objects import build_subscription_description

# ─── State constants ─────────────────────────────────────────
SELECT_RESUME_SUB = 22
CONFIRM_RESUME = 23


# ─── Helper: build keyboard ─────────────────────────────────

def _resume_toggle_keyboard(subs: list, selected_ids: list[int]) -> InlineKeyboardMarkup:
    buttons = []
    for sub in subs:
        if sub.status != "paused":
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
                f"{checked}▶️ #{sub.id}: {desc}",
                callback_data=f"resume_toggle:{sub.id}"
            )
        ])

    buttons.append([
        InlineKeyboardButton("🌐 Select All", callback_data="resume:all"),
        InlineKeyboardButton("❌ Clear All", callback_data="resume:clear"),
    ])
    buttons.append([
        InlineKeyboardButton("🚫 Cancel", callback_data="cancel"),
        InlineKeyboardButton("🔙 Back", callback_data="resume:back"),
        InlineKeyboardButton("➡️ Next", callback_data="resume:next"),
    ])
    return InlineKeyboardMarkup(buttons)


# ─── Helper: format IDs ─────────────────────────────────────

def _format_id_list(ids: list[int]) -> str:
    return ", ".join(f"#{sid}" for sid in sorted(ids))


# ─── Helper: process resume ─────────────────────────────────

async def _process_resume_selected(selected: list[int], user_id: int) -> tuple[list[str], list[str]]:
    resumed = []
    failed = []
    for sub_id in selected:
        count = await resume_subscription_by_id(sub_id, user_id)
        if count:
            resumed.append(str(sub_id))
        else:
            failed.append(str(sub_id))
    return resumed, failed


# ─── Main menu entry ─────────────────────────────────────────

async def resume_subscription_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()

    user = update.effective_user
    if not user:
        await safe_edit(query, "❌ Could not identify user.")
        return ConversationHandler.END

    subs = await get_subscriptions_for_user(user.id)
    paused_subs = [s for s in subs if s.status == "paused"]

    if not paused_subs:
        await safe_edit(query, "✅ You have no paused subscriptions to resume.")
        return ConversationHandler.END

    user_data = get_user_data(context)
    if "resume_selected" not in user_data:
        user_data["resume_selected"] = []

    await safe_edit(
        query,
        "📋 Select subscriptions to resume (toggle each):",
        reply_markup=_resume_toggle_keyboard(paused_subs, user_data["resume_selected"]),
    )
    return SELECT_RESUME_SUB


# ─── Toggle callbacks ────────────────────────────────────────

async def resume_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()
    data = query.data
    if not data:
        return SELECT_RESUME_SUB

    user = update.effective_user
    if not user:
        await safe_edit(query, "❌ Could not identify user.")
        return ConversationHandler.END

    subs = await get_subscriptions_for_user(user.id)
    paused_subs = [s for s in subs if s.status == "paused"]
    user_data = get_user_data(context)
    selected = user_data.get("resume_selected", [])

    # ─── Toggle ──────────────────────────────────────────────
    if data.startswith("resume_toggle:"):
        sub_id = int(data.split(":", 1)[1])
        if sub_id in selected:
            selected.remove(sub_id)
        else:
            selected.append(sub_id)
        user_data["resume_selected"] = selected
        await safe_edit(
            query,
            "📋 Select subscriptions to resume (toggle each):",
            reply_markup=_resume_toggle_keyboard(paused_subs, selected),
        )
        return SELECT_RESUME_SUB

    # ─── All ──────────────────────────────────────────────────
    if data == "resume:all":
        selected = [s.id for s in paused_subs]
        user_data["resume_selected"] = selected
        await safe_edit(
            query,
            "📋 Select subscriptions to resume (toggle each):",
            reply_markup=_resume_toggle_keyboard(paused_subs, selected),
        )
        return SELECT_RESUME_SUB

    # ─── Clear ────────────────────────────────────────────────
    if data == "resume:clear":
        selected = []
        user_data["resume_selected"] = selected
        await safe_edit(
            query,
            "📋 Select subscriptions to resume (toggle each):",
            reply_markup=_resume_toggle_keyboard(paused_subs, selected),
        )
        return SELECT_RESUME_SUB

    # ─── Back ─────────────────────────────────────────────────
    if data == "resume:back":
        user_data.pop("resume_selected", None)
        # End the conversation; main menu will not be shown automatically.
        # The user can use /start or /menu.
        return ConversationHandler.END

    # ─── Next ─────────────────────────────────────────────────
    if data == "resume:next":
        if not selected:
            await safe_edit(
                query,
                "❌ Please select at least one subscription to resume.",
                reply_markup=_resume_toggle_keyboard(paused_subs, selected),
            )
            return SELECT_RESUME_SUB

        ids_str = _format_id_list(selected)
        buttons = [
            [InlineKeyboardButton("✅ Yes, resume them", callback_data="resume_confirm:yes")],
            [InlineKeyboardButton("❌ No, go back", callback_data="resume_confirm:no")],
        ]
        await safe_edit(
            query,
            f"⚠️ Are you sure you want to resume subscriptions: {ids_str}?",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return CONFIRM_RESUME

    return SELECT_RESUME_SUB


# ─── Confirm callback ────────────────────────────────────────

async def resume_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()
    data = query.data
    if not data:
        return CONFIRM_RESUME

    if not data.startswith("resume_confirm:"):
        return CONFIRM_RESUME

    action = data.split(":", 1)[1]
    user_data = get_user_data(context)
    selected = user_data.get("resume_selected", [])

    if action == "no":
        user = update.effective_user
        if user:
            subs = await get_subscriptions_for_user(user.id)
            paused_subs = [s for s in subs if s.status == "paused"]
            await safe_edit(
                query,
                "📋 Select subscriptions to resume (toggle each):",
                reply_markup=_resume_toggle_keyboard(paused_subs, selected),
            )
            return SELECT_RESUME_SUB
        return ConversationHandler.END

    if action == "yes":
        user = update.effective_user
        if not user:
            await safe_edit(query, "❌ Could not identify user.")
            user_data.pop("resume_selected", None)
            return ConversationHandler.END

        resumed, failed = await _process_resume_selected(selected, user.id)
        await reload_subscriptions_immediate()

        msg_parts = []
        if resumed:
            msg_parts.append(f"✅ Resumed: #{', #'.join(resumed)}")
        if failed:
            msg_parts.append(f"❌ Failed: #{', #'.join(failed)}")

        user_data.pop("resume_selected", None)
        await safe_edit(query, "\n".join(msg_parts) or "✅ No subscriptions selected.")
        return ConversationHandler.END

    return CONFIRM_RESUME