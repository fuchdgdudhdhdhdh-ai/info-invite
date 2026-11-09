import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.filters.chat_member_updated import ChatMemberUpdatedFilter, IS_MEMBER, IS_LEFT
from aiogram.types import Message, ChatMemberUpdated
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from database import (
    init_db, save_link, get_link_for_chat,
    increment_join_request, register_join, register_leave, get_stats
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан")

WEBHOOK_HOST = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("WEBHOOK_HOST")
if not WEBHOOK_HOST:
    raise ValueError("WEBHOOK_HOST или RENDER_EXTERNAL_URL не задан")

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)


@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Я бот для отслеживания статистики по пригласительной ссылке.\n\n"
        "Добавьте меня в группу администратором с правом «Приглашать пользователей»,\n"
        "затем отправьте в группе команду:\n"
        "/setlink <ваша_пригласительная_ссылка>\n\n"
        "После этого я буду считать заявки, вступления и выходы.\n"
        "Статистика: /stats"
    )


@router.message(Command("setlink"))
async def cmd_setlink(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /setlink <пригласительная_ссылка>")
        return

    invite_link = args[1].strip()
    if not (invite_link.startswith("https://t.me/") or invite_link.startswith("https://telegram.me/")):
        await message.answer("Пожалуйста, отправьте корректную пригласительную ссылку Telegram.")
        return

    chat_id = message.chat.id
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("Эту команду нужно отправлять в группе, чтобы я знал, к какому чату привязать ссылку.")
        return

    await save_link(chat_id, invite_link)
    await message.answer("✅ Ссылка сохранена. Теперь я буду собирать статистику по этой ссылке.")


@router.chat_join_request()
async def on_join_request(event):
    chat_id = event.chat.id
    invite_link = event.invite_link.invite_link if event.invite_link else None
    if not invite_link:
        return

    link_row = await get_link_for_chat(chat_id)
    if not link_row or link_row[0] != invite_link:
        return

    await increment_join_request(chat_id, invite_link)
    logging.info(f"Заявка от {event.from_user.id} по ссылке {invite_link}")


@router.chat_member(ChatMemberUpdatedFilter(member_status_changed=IS_MEMBER))
async def on_user_join(event: ChatMemberUpdated):
    chat_id = event.chat.id
    user_id = event.new_chat_member.user.id
    invite_link = event.invite_link.invite_link if event.invite_link else None
    if not invite_link:
        return

    link_row = await get_link_for_chat(chat_id)
    if not link_row or link_row[0] != invite_link:
        return

    await register_join(chat_id, user_id, invite_link)
    logging.info(f"Вступление {user_id} по ссылке {invite_link}")


@router.chat_member(ChatMemberUpdatedFilter(member_status_changed=IS_LEFT))
async def on_user_leave(event: ChatMemberUpdated):
    chat_id = event.chat.id
    user_id = event.new_chat_member.user.id
    await register_leave(chat_id, user_id)
    logging.info(f"Выход {user_id} из чата {chat_id}")


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    chat_id = message.chat.id
    link_row = await get_link_for_chat(chat_id)
    if not link_row:
        await message.answer("Ссылка ещё не настроена. Отправьте /setlink <ссылка>")
        return

    invite_link, name = link_row
    stats = await get_stats(chat_id, invite_link)
    if not stats:
        await message.answer("Статистика пока пуста.")
        return

    join_requests, joins, leaves, active_members = stats
    text = (
        f"📊 <b>Статистика по ссылке</b>\n"
        f"🔗 {invite_link}\n\n"
        f"📩 Заявок: <b>{join_requests}</b>\n"
        f"✅ Вступили: <b>{joins}</b>\n"
        f"🚪 Вышли: <b>{leaves}</b>\n"
        f"👥 Активных участников: <b>{active_members}</b>"
    )
    await message.answer(text, parse_mode="HTML")


async def on_startup(bot: Bot):
    await bot.set_webhook(WEBHOOK_URL)
    logging.info(f"Вебхук установлен: {WEBHOOK_URL}")


async def on_shutdown(bot: Bot):
    await bot.delete_webhook()
    logging.info("Вебхук удалён")


def main():
    asyncio.run(init_db())

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()
    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    port = int(os.getenv("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
