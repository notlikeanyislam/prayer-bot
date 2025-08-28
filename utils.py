import logging
from telegram import ChatPermissions
from telegram.ext import ContextTypes

async def close_topic_or_lock(chat_id: int, thread_id: int, ctx: ContextTypes.DEFAULT_TYPE, reason_text: str):
    """إذا كان thread_id موجودًا، نحاول إغلاق الموضوع، وإلا نغير صلاحيات الشات (fallback)."""
    try:
        if thread_id:
            await ctx.bot.send_message(chat_id=chat_id, text=reason_text, message_thread_id=thread_id)
            await ctx.bot.close_forum_topic(chat_id=chat_id, message_thread_id=thread_id)
            return True
        else:
            await ctx.bot.set_chat_permissions(chat_id=chat_id, permissions=ChatPermissions(can_send_messages=False))
            await ctx.bot.send_message(chat_id=chat_id, text=reason_text)
            return True
    except Exception as e:
        logging.exception("close_topic_or_lock failed:")
        return False

async def reopen_topic_or_unlock(chat_id: int, thread_id: int, ctx: ContextTypes.DEFAULT_TYPE, text: str):
    """اعادة فتح الموضوع أو استرجاع صلاحيات الدردشة"""
    try:
        if thread_id:
            await ctx.bot.send_message(chat_id=chat_id, text=text, message_thread_id=thread_id)
            await ctx.bot.reopen_forum_topic(chat_id=chat_id, message_thread_id=thread_id)
            return True
        else:
            await ctx.bot.set_chat_permissions(chat_id=chat_id, permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            ))
            await ctx.bot.send_message(chat_id=chat_id, text=text)
            return True
    except Exception as e:
        logging.exception("reopen_topic_or_unlock failed:")
        return False
