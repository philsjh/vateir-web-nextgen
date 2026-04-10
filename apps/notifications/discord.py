"""
Discord bot REST API integration for VATéir.

All functions use the Discord REST API v10 via requests.
The gateway bot (runbot command) is separate.
"""

import logging
from datetime import datetime

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

DISCORD_API = "https://discord.com/api/v10"


def _headers():
    return {
        "Authorization": f"Bot {settings.DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json",
    }


def _is_configured():
    return bool(getattr(settings, "DISCORD_BOT_TOKEN", ""))


def _get_config():
    try:
        from apps.accounts.models import SiteConfig
        return SiteConfig.get()
    except Exception:
        return None


# ─── Low-level API ────────────────────────────────────────────────

def get_bot_user() -> dict | None:
    """Get the bot's own user info."""
    if not _is_configured():
        return None
    try:
        resp = requests.get(f"{DISCORD_API}/users/@me", headers=_headers(), timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.error("Failed to get bot user: %s", exc)
        return None


def get_guild_info(guild_id: str) -> dict | None:
    if not _is_configured() or not guild_id:
        return None
    try:
        resp = requests.get(
            f"{DISCORD_API}/guilds/{guild_id}?with_counts=true",
            headers=_headers(), timeout=10,
        )
        resp.raise_for_status()
        d = resp.json()
        return {
            "id": d["id"],
            "name": d.get("name", ""),
            "icon": d.get("icon"),
            "member_count": d.get("approximate_member_count", 0),
        }
    except Exception as exc:
        logger.error("Failed to get guild info: %s", exc)
        return None


def get_guild_channels(guild_id: str) -> list[dict]:
    if not _is_configured() or not guild_id:
        return []
    try:
        resp = requests.get(
            f"{DISCORD_API}/guilds/{guild_id}/channels",
            headers=_headers(), timeout=10,
        )
        resp.raise_for_status()
        channels = []
        for ch in resp.json():
            if ch.get("type") in (0, 5):
                channels.append({
                    "id": ch["id"],
                    "name": ch.get("name", ""),
                    "type": ch.get("type"),
                    "position": ch.get("position", 0),
                    "parent_id": ch.get("parent_id"),
                })
        channels.sort(key=lambda c: c["position"])
        return channels
    except Exception as exc:
        logger.error("Failed to get guild channels: %s", exc)
        return []


def get_guild_member(guild_id: str, user_id: str) -> dict | None:
    if not _is_configured():
        return None
    try:
        resp = requests.get(
            f"{DISCORD_API}/guilds/{guild_id}/members/{user_id}",
            headers=_headers(), timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def search_guild_members(guild_id: str, query: str, limit: int = 20) -> list[dict]:
    """Search guild members by username. Requires GUILD_MEMBERS intent."""
    if not _is_configured() or not guild_id or not query:
        return []
    try:
        resp = requests.get(
            f"{DISCORD_API}/guilds/{guild_id}/members/search",
            params={"query": query, "limit": limit},
            headers=_headers(), timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.error("Member search failed: %s", exc)
        return []


def get_guild_roles(guild_id: str) -> list[dict]:
    """Fetch all roles in a guild."""
    if not _is_configured() or not guild_id:
        return []
    try:
        resp = requests.get(
            f"{DISCORD_API}/guilds/{guild_id}/roles",
            headers=_headers(), timeout=10,
        )
        resp.raise_for_status()
        roles = resp.json()
        roles.sort(key=lambda r: r.get("position", 0), reverse=True)
        return roles
    except Exception as exc:
        logger.error("Failed to get guild roles: %s", exc)
        return []


def add_member_role(guild_id: str, user_id: str, role_id: str) -> bool:
    if not _is_configured():
        return False
    try:
        resp = requests.put(
            f"{DISCORD_API}/guilds/{guild_id}/members/{user_id}/roles/{role_id}",
            headers=_headers(), timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as exc:
        logger.error("Add role failed: %s", exc)
        return False


def remove_member_role(guild_id: str, user_id: str, role_id: str) -> bool:
    if not _is_configured():
        return False
    try:
        resp = requests.delete(
            f"{DISCORD_API}/guilds/{guild_id}/members/{user_id}/roles/{role_id}",
            headers=_headers(), timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as exc:
        logger.error("Remove role failed: %s", exc)
        return False


def set_bot_status(status_text: str, status_type: int = 3) -> bool:
    """Set bot custom status. Type: 0=playing, 1=streaming, 2=listening, 3=watching, 5=competing."""
    # Note: This only works via the gateway, not REST. Leaving as a placeholder
    # that the runbot command handles via change_presence.
    return False


# ─── Message sending ──────────────────────────────────────────────

def send_channel_message(channel_id: str, message: str = "", embed: dict = None) -> str | None:
    """Send a message. Returns the Discord message ID on success, None on failure."""
    if not _is_configured() or not channel_id:
        return None
    try:
        payload = {}
        if message:
            payload["content"] = message
        if embed:
            payload["embeds"] = [embed]
        resp = requests.post(
            f"{DISCORD_API}/channels/{channel_id}/messages",
            json=payload, headers=_headers(), timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("id")
    except Exception as exc:
        logger.error("Channel message failed (%s): %s", channel_id, exc)
        return None


def send_dm(discord_user_id: str, message: str = "", embed: dict = None) -> bool:
    if not _is_configured() or not discord_user_id:
        return False
    try:
        dm_resp = requests.post(
            f"{DISCORD_API}/users/@me/channels",
            json={"recipient_id": discord_user_id},
            headers=_headers(), timeout=10,
        )
        dm_resp.raise_for_status()
        channel_id = dm_resp.json()["id"]
        return send_channel_message(channel_id, message, embed) is not None
    except Exception as exc:
        logger.error("DM failed (%s): %s", discord_user_id, exc)
        return False


# ─── Guild management ─────────────────────────────────────────────

def change_bot_nickname(guild_id: str, nickname: str) -> bool:
    if not _is_configured():
        return False
    try:
        resp = requests.patch(
            f"{DISCORD_API}/guilds/{guild_id}/members/@me",
            json={"nick": nickname},
            headers=_headers(), timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as exc:
        logger.error("Nickname change failed: %s", exc)
        return False


def ban_guild_member(guild_id: str, user_id: str, reason: str = "", delete_message_seconds: int = 0) -> bool:
    if not _is_configured():
        return False
    try:
        payload = {}
        if delete_message_seconds:
            payload["delete_message_seconds"] = delete_message_seconds
        headers = _headers()
        if reason:
            headers["X-Audit-Log-Reason"] = reason[:512]
        resp = requests.put(
            f"{DISCORD_API}/guilds/{guild_id}/bans/{user_id}",
            json=payload, headers=headers, timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as exc:
        logger.error("Ban failed (%s): %s", user_id, exc)
        return False


def unban_guild_member(guild_id: str, user_id: str) -> bool:
    if not _is_configured():
        return False
    try:
        resp = requests.delete(
            f"{DISCORD_API}/guilds/{guild_id}/bans/{user_id}",
            headers=_headers(), timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as exc:
        logger.error("Unban failed (%s): %s", user_id, exc)
        return False


def kick_guild_member(guild_id: str, user_id: str, reason: str = "") -> bool:
    if not _is_configured():
        return False
    try:
        headers = _headers()
        if reason:
            headers["X-Audit-Log-Reason"] = reason[:512]
        resp = requests.delete(
            f"{DISCORD_API}/guilds/{guild_id}/members/{user_id}",
            headers=headers, timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as exc:
        logger.error("Kick failed (%s): %s", user_id, exc)
        return False


def get_guild_bans(guild_id: str) -> list[dict]:
    if not _is_configured():
        return []
    try:
        resp = requests.get(
            f"{DISCORD_API}/guilds/{guild_id}/bans",
            headers=_headers(), timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.error("Failed to get guild bans: %s", exc)
        return []


# ─── Embed builders ───────────────────────────────────────────────

BRAND_COLOR = 0x059669
GOLD_COLOR = 0xfbbf24
RED_COLOR = 0xef4444


def _embed(title, description="", fields=None, color=None, image_url=None, footer=None, timestamp=False):
    e = {"title": title, "color": color or BRAND_COLOR}
    if description:
        e["description"] = description
    if fields:
        e["fields"] = fields
    if image_url:
        e["image"] = {"url": image_url}
    if footer:
        e["footer"] = {"text": footer}
    if timestamp:
        e["timestamp"] = datetime.utcnow().isoformat()
    e["author"] = {"name": "VATéir Control Centre"}
    return e


def build_announcement_embed(title, body, color_hex="#059669", banner_url="", ann_type="GENERAL"):
    color = int(color_hex.lstrip("#"), 16) if color_hex else BRAND_COLOR
    type_labels = {"GENERAL": "Announcement", "EVENT": "Event Notification", "EXAM": "Exam Notification", "TRAINING": "Training Update"}
    footer = type_labels.get(ann_type, "Announcement")
    return _embed(title, body, color=color, image_url=banner_url or None, footer=footer, timestamp=True)


def build_event_embed(event):
    fields = [
        {"name": "Date", "value": f"{event.start_datetime:%d %b %Y %H:%M}z", "inline": True},
        {"name": "Airport", "value": event.airport_icao or "TBD", "inline": True},
    ]
    return _embed(
        title=event.title,
        description=event.description[:500] + ("..." if len(event.description) > 500 else ""),
        fields=fields,
        color=GOLD_COLOR,
        image_url=event.banner_display_url or None,
        footer="VATéir Events",
        timestamp=True,
    )


def build_exam_embed(student_name, exam_type, result, examiner_name):
    color = BRAND_COLOR if result == "PASSED" else RED_COLOR
    emoji = "✅" if result == "PASSED" else "❌"
    return _embed(
        title=f"Exam Result: {exam_type}",
        description=f"{emoji} **{student_name}** has **{result}** their {exam_type} examination.",
        fields=[
            {"name": "Examiner", "value": examiner_name, "inline": True},
            {"name": "Result", "value": result, "inline": True},
        ],
        color=color,
        footer="VATéir Training",
        timestamp=True,
    )


# ─── High-level notifications ─────────────────────────────────────

def notify_roster_sync(created, updated, removed, new_members=None, rating_changes=None, departed=None):
    config = _get_config()
    if not config or not config.discord_roster_channel_id:
        return
    if created == 0 and updated == 0 and removed == 0:
        return

    fields = []
    if created:
        fields.append({"name": "New Members", "value": str(created), "inline": True})
    if updated:
        fields.append({"name": "Updated", "value": str(updated), "inline": True})
    if removed:
        fields.append({"name": "Departed", "value": str(removed), "inline": True})

    parts = []
    if new_members:
        names = ", ".join(f"**{m}**" for m in new_members[:10])
        if len(new_members) > 10:
            names += f" and {len(new_members) - 10} more"
        parts.append(f"**Joined:** {names}")
    if rating_changes:
        changes = ", ".join(f"**{n}** ({o} → {new})" for n, o, new in rating_changes[:10])
        if len(rating_changes) > 10:
            changes += f" and {len(rating_changes) - 10} more"
        parts.append(f"**Rating Changes:** {changes}")
    if departed:
        names = ", ".join(f"**{m}**" for m in departed[:10])
        if len(departed) > 10:
            names += f" and {len(departed) - 10} more"
        parts.append(f"**Departed:** {names}")

    send_channel_message(config.discord_roster_channel_id, "", _embed(
        "Roster Sync Complete",
        "\n".join(parts) or "Roster sync completed.",
        fields, timestamp=True,
    ))


def notify_training_session_pickup(student_user, mentor_user, session):
    config = _get_config()
    if config and config.discord_training_channel_id:
        send_channel_message(config.discord_training_channel_id, "", _embed(
            "Training Session Scheduled",
            f"**{mentor_user.vatsim_name}** has picked up a session with **{student_user.vatsim_name}** (CID {student_user.cid})",
            [
                {"name": "Date", "value": f"{session.session_date:%d %b %Y %H:%M}z", "inline": True},
                {"name": "Type", "value": session.get_session_type_display(), "inline": True},
            ],
            timestamp=True,
        ))
    if student_user.discord_user_id:
        send_dm(student_user.discord_user_id, "", _embed(
            "Training Session Scheduled!",
            f"**{mentor_user.vatsim_name}** will mentor you on **{session.session_date:%d %b %Y %H:%M}z**.",
            color=0x10b981,
        ))


def notify_report_published(student_user, session, report):
    config = _get_config()
    if student_user.discord_user_id:
        send_dm(student_user.discord_user_id, "", _embed(
            "Training Report Published",
            f"Your **{session.get_session_type_display()}** session on **{session.session_date:%d %b %Y}** has been reviewed.\nCheck your training dashboard.",
            color=0x10b981,
        ))
    if config and config.discord_training_channel_id:
        send_channel_message(config.discord_training_channel_id, "", _embed(
            "Report Published",
            f"Report published for **{student_user.vatsim_name}** ({session.get_session_type_display()} on {session.session_date:%d %b %Y})",
        ))


def notify_event_roster_published(event, rostered_controllers):
    config = _get_config()
    if not config:
        return
    if config.discord_events_channel_id:
        pos_list = "\n".join(f"• **{cs}** — {name}" for cs, name in rostered_controllers[:20])
        if len(rostered_controllers) > 20:
            pos_list += f"\n... and {len(rostered_controllers) - 20} more"
        send_channel_message(config.discord_events_channel_id, "", _embed(
            f"Event Roster: {event.title}",
            f"**Date:** {event.start_datetime:%d %b %Y %H:%M}z\n**Airport:** {event.airport_icao or 'TBD'}\n\n{pos_list}",
            color=GOLD_COLOR, image_url=event.banner_display_url or None, timestamp=True,
        ))
    for ep in event.positions.select_related("assigned_controller", "position").filter(assigned_controller__isnull=False):
        if ep.assigned_controller.discord_user_id:
            send_dm(ep.assigned_controller.discord_user_id, "", _embed(
                f"You've Been Rostered — {event.title}",
                f"Position: **{ep.position.callsign}**\nDate: **{event.start_datetime:%d %b %Y %H:%M}z**",
                color=GOLD_COLOR,
            ))


def _ticket_url(ticket):
    """Build an absolute URL for a ticket (staff view)."""
    from django.conf import settings
    base = getattr(settings, "SITE_URL", "http://localhost:8000").rstrip("/")
    return f"{base}/tickets/manage/{ticket.reference}/"


def _ticket_color(priority):
    colors = {"LOW": BRAND_COLOR, "MEDIUM": GOLD_COLOR, "HIGH": 0xff8c00, "URGENT": RED_COLOR}
    return colors.get(priority, BRAND_COLOR)


def notify_new_ticket(ticket):
    config = _get_config()
    if not config or not config.discord_tickets_channel_id:
        return
    send_channel_message(config.discord_tickets_channel_id, "", _embed(
        f"New Ticket: {ticket.reference}",
        f"**{ticket.subject}**\n\n{ticket.description[:300]}{'...' if len(ticket.description) > 300 else ''}"
        f"\n\n[View Ticket]({_ticket_url(ticket)})",
        fields=[
            {"name": "Category", "value": ticket.get_category_display(), "inline": True},
            {"name": "Priority", "value": ticket.get_priority_display(), "inline": True},
            {"name": "From", "value": f"{ticket.created_by.vatsim_name} (CID {ticket.created_by.cid})", "inline": True},
        ],
        color=_ticket_color(ticket.priority),
        footer="VATéir Support",
        timestamp=True,
    ))


def notify_ticket_reply(ticket, replier, is_staff=False):
    config = _get_config()
    if not config:
        return
    if is_staff:
        # Notify user via DM
        if ticket.created_by.discord_user_id:
            send_dm(ticket.created_by.discord_user_id, "", _embed(
                f"Staff Reply on {ticket.reference}",
                f"Your ticket **{ticket.subject}** has a new staff reply.\nCheck your support tickets to respond.",
                color=BRAND_COLOR,
            ))
    else:
        # Notify staff channel
        if config.discord_tickets_channel_id:
            send_channel_message(config.discord_tickets_channel_id, "", _embed(
                f"User Reply: {ticket.reference}",
                f"**{replier.vatsim_name}** replied to **{ticket.subject}**\n\n[View Ticket]({_ticket_url(ticket)})",
                color=BRAND_COLOR,
                footer="VATéir Support",
                timestamp=True,
            ))


def notify_ticket_status_change(ticket, changed_by, old_status, new_status):
    config = _get_config()
    if not config:
        return
    from apps.tickets.models import TicketStatus
    status_labels = dict(TicketStatus.choices)
    # Notify user via DM
    if ticket.created_by.discord_user_id:
        send_dm(ticket.created_by.discord_user_id, "", _embed(
            f"Ticket Update: {ticket.reference}",
            f"Your ticket **{ticket.subject}** status changed from "
            f"**{status_labels.get(old_status, old_status)}** to **{status_labels.get(new_status, new_status)}**.",
            color=BRAND_COLOR,
        ))
    # Notify staff channel
    if config.discord_tickets_channel_id:
        send_channel_message(config.discord_tickets_channel_id, "", _embed(
            f"Status Change: {ticket.reference}",
            f"**{changed_by.vatsim_name}** changed **{ticket.subject}** from "
            f"**{status_labels.get(old_status, old_status)}** to **{status_labels.get(new_status, new_status)}**"
            f"\n\n[View Ticket]({_ticket_url(ticket)})",
            color=BRAND_COLOR,
            footer="VATéir Support",
            timestamp=True,
        ))


def notify_ticket_assigned(ticket, assignee, assigned_by):
    config = _get_config()
    if not config or not config.discord_tickets_channel_id:
        return
    name = assignee.vatsim_name if assignee else "Unassigned"
    send_channel_message(config.discord_tickets_channel_id, "", _embed(
        f"Ticket Assigned: {ticket.reference}",
        f"**{ticket.subject}** assigned to **{name}** by {assigned_by.vatsim_name}"
        f"\n\n[View Ticket]({_ticket_url(ticket)})",
        color=BRAND_COLOR,
        footer="VATéir Support",
        timestamp=True,
    ))
    # DM the assignee
    if assignee and assignee.discord_user_id:
        send_dm(assignee.discord_user_id, "", _embed(
            f"Ticket Assigned to You: {ticket.reference}",
            f"**{ticket.subject}**\nAssigned by {assigned_by.vatsim_name}",
            color=GOLD_COLOR,
        ))


def notify_ticket_sla_breach(tickets):
    """Notify staff channel about tickets that have breached SLA."""
    config = _get_config()
    if not config or not config.discord_tickets_channel_id or not tickets:
        return
    lines = []
    for t in tickets[:15]:
        hours = int(t.age_hours)
        lines.append(f"- **{t.reference}** — {t.subject} ({hours}h open)")
    send_channel_message(config.discord_tickets_channel_id, "", _embed(
        f"SLA Alert: {len(tickets)} Ticket{'s' if len(tickets) != 1 else ''} Overdue",
        "\n".join(lines),
        color=RED_COLOR,
        footer=f"SLA threshold: {config.ticket_sla_hours}h",
        timestamp=True,
    ))


def _feedback_color(feedback_type):
    colors = {
        "COMPLIMENT": BRAND_COLOR,
        "CONCERN": GOLD_COLOR,
        "SUGGESTION": 0x3b82f6,  # blue
        "BUG_REPORT": RED_COLOR,
    }
    return colors.get(feedback_type, BRAND_COLOR)


def notify_feedback_submitted(feedback):
    """Notify staff channel when new feedback is received."""
    config = _get_config()
    if not config or not config.discord_feedback_channel_id:
        return

    from django.conf import settings
    base = getattr(settings, "SITE_URL", "http://localhost:8000").rstrip("/")
    url = f"{base}/admin-panel/feedback/{feedback.pk}/"

    fields = [
        {"name": "Type", "value": feedback.get_feedback_type_display(), "inline": True},
        {"name": "From", "value": f"{feedback.submitter_name} (CID {feedback.submitter_cid})", "inline": True},
    ]
    if feedback.controller:
        fields.append({"name": "Controller", "value": f"{feedback.controller} (CID {feedback.controller.cid})", "inline": True})
    if feedback.controller_callsign:
        fields.append({"name": "Callsign", "value": feedback.controller_callsign, "inline": True})

    send_channel_message(config.discord_feedback_channel_id, "", _embed(
        f"New Feedback: {feedback.get_feedback_type_display()}",
        f"{feedback.content[:400]}{'...' if len(feedback.content) > 400 else ''}"
        f"\n\n[Review Feedback]({url})",
        fields=fields,
        color=_feedback_color(feedback.feedback_type),
        footer="VATéir Feedback",
        timestamp=True,
    ))


def notify_user_banned(banned_user_name, reason, banned_by_name):
    config = _get_config()
    if config and config.discord_general_channel_id:
        send_channel_message(config.discord_general_channel_id, "", _embed(
            "User Banned",
            f"**{banned_user_name}** has been banned.\n**Reason:** {reason}\n**By:** {banned_by_name}",
            color=RED_COLOR, timestamp=True,
        ))


def notify_vateud_sync(endorsements_added, endorsements_removed, new_visitor_requests, roster_discrepancies):
    """Notify staff channel about VATEUD sync changes."""
    config = _get_config()
    if not config or not config.discord_roster_channel_id:
        return

    total = len(endorsements_added) + len(endorsements_removed) + len(new_visitor_requests)
    if total == 0:
        return

    fields = []
    if endorsements_added:
        fields.append({"name": "Endorsements Added", "value": str(len(endorsements_added)), "inline": True})
    if endorsements_removed:
        fields.append({"name": "Endorsements Removed", "value": str(len(endorsements_removed)), "inline": True})
    if new_visitor_requests:
        fields.append({"name": "New Visitor Requests", "value": str(len(new_visitor_requests)), "inline": True})

    parts = []
    if endorsements_added:
        lines = ", ".join(f"**{t}** {p} (CID {c})" for t, p, c in endorsements_added[:10])
        if len(endorsements_added) > 10:
            lines += f" and {len(endorsements_added) - 10} more"
        parts.append(f"**Added:** {lines}")
    if endorsements_removed:
        lines = ", ".join(f"**{t}** {p} (CID {c})" for t, p, c in endorsements_removed[:10])
        if len(endorsements_removed) > 10:
            lines += f" and {len(endorsements_removed) - 10} more"
        parts.append(f"**Removed:** {lines}")
    if new_visitor_requests:
        cids = ", ".join(f"**{c}**" for c in new_visitor_requests[:10])
        if len(new_visitor_requests) > 10:
            cids += f" and {len(new_visitor_requests) - 10} more"
        parts.append(f"**Visitor Requests:** {cids}")

    discrepancies = roster_discrepancies or {}
    in_vateud = discrepancies.get("in_vateud_not_local", [])
    in_local = discrepancies.get("in_local_not_vateud", [])
    if in_vateud:
        cids = ", ".join(str(c) for c in in_vateud[:10])
        if len(in_vateud) > 10:
            cids += f" and {len(in_vateud) - 10} more"
        parts.append(f"**Roster (in VATEUD, not local):** {cids}")
    if in_local:
        cids = ", ".join(str(c) for c in in_local[:10])
        if len(in_local) > 10:
            cids += f" and {len(in_local) - 10} more"
        parts.append(f"**Roster (local, not in VATEUD):** {cids}")

    send_channel_message(config.discord_roster_channel_id, "", _embed(
        "VATEUD Sync Complete",
        "\n".join(parts) or "Sync completed.",
        fields, timestamp=True,
    ))
