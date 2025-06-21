# --- Стандартные библиотеки ---
import asyncio
import logging
import os
import sys
# --- Сторонние библиотеки ---
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    Message,
    TelegramObject,
)
# --- Внутренние модули ---
from services.config import (
    ensure_config,
    save_config,
    get_valid_config,
    get_target_display,
    DEFAULT_CONFIG,
    VERSION
)
from services.menu import update_menu
from services.balance import refresh_balance
from services.gifts import get_filtered_gifts
from handlers.handlers_wizard import register_wizard_handlers
from handlers.handlers_catalog import register_catalog_handlers
from handlers.handlers_main import register_main_handlers
from services.buy import buy_gift
from utils.logging import setup_logging

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
USER_ID = int(os.getenv("TELEGRAM_USER_ID"))
default_config = DEFAULT_CONFIG(USER_ID)
ALLOWED_USER_IDS = []
ALLOWED_USER_IDS.append(USER_ID)

setup_logging()
logger = logging.getLogger(__name__)

class AccessControlMiddleware(BaseMiddleware):
    """
    Мидлварь доступа: разрешает работу только определённым user_id.
    Отклоняет все остальные запросы.
    """
    def __init__(self, allowed_user_ids: list[int], bot: Bot):
        """
        :param allowed_user_ids: Список разрешённых user_id.
        :param bot: Экземпляр бота.
        """
        self.allowed_user_ids = allowed_user_ids
        self.bot = bot
        super().__init__()

    async def __call__(self, handler, event: TelegramObject, data: dict):
        """
        Проверяет наличие пользователя в списке разрешённых.
        При отказе отправляет уведомление и блокирует обработку.
        """
        user = data.get("event_from_user")
        if user and user.id not in self.allowed_user_ids:
            try:
                if isinstance(event, Message):
                    await event.answer("✅ Вы сможете получать подарки от этого бота.\n⛔️ У вас нет доступа к панели управления.\n\n<b>🤖 Исходный код: <a href=\"https://github.com/leozizu/TelegramGiftsBot\">GitHub</a></b>\n<b>🐸 Автор: @leozizu</b>\n<b>📢 Канал: @pepeksey</b>")
                elif isinstance(event, CallbackQuery):
                    await event.answer("⛔️ Нет доступа", show_alert=True)
            except Exception as e:
                logger.error(f"Не удалось отправить отказ пользователю {user.id}: {e}")
            return
        return await handler(event, data)

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
dp.message.middleware(AccessControlMiddleware(ALLOWED_USER_IDS, bot))
dp.callback_query.middleware(AccessControlMiddleware(ALLOWED_USER_IDS, bot))

register_wizard_handlers(dp)
register_catalog_handlers(dp)
register_main_handlers(
    dp=dp,
    bot=bot,
    version=VERSION
)


async def get_gifts():
    """
    Основной цикл авто-покупки подарков.
    Проверяет конфиг, выбирает подходящие подарки, совершает покупки до достижения лимита COUNT.
    После завершения отправляет отчет и обновляет меню.
    """
    await refresh_balance(bot)
    while True:
        try:
            config = await get_valid_config(USER_ID)

            if not config["ACTIVE"]:
                await asyncio.sleep(1)
                continue

            MIN_PRICE = config["MIN_PRICE"]
            MAX_PRICE = config["MAX_PRICE"]
            MIN_SUPPLY = config["MIN_SUPPLY"]
            MAX_SUPPLY = config["MAX_SUPPLY"]
            COUNT = config["COUNT"]
            TARGET_USER_ID = config["TARGET_USER_ID"]
            TARGET_CHAT_ID = config["TARGET_CHAT_ID"]

            filtered_gifts = await get_filtered_gifts(bot, MIN_PRICE, MAX_PRICE, MIN_SUPPLY, MAX_SUPPLY)

            purchases = []

            for gift in filtered_gifts:
                gift_id = gift["id"]
                gift_price = gift["price"]
                gift_total_count = gift["supply"]
                sticker_file_id = gift["sticker_file_id"]

                if config["DONE"] == False and config["ACTIVE"] == True:
                    logger.info(f"Match: {gift_id} - {gift_price} stars - supply: {gift_total_count}")

                while config["BOUGHT"] < COUNT:
                    success = await buy_gift(
                        bot=bot,
                        env_user_id=USER_ID,
                        gift_id=gift_id,
                        user_id=TARGET_USER_ID,
                        chat_id=TARGET_CHAT_ID,
                        gift_price=gift_price,
                        file_id=sticker_file_id
                    )

                    if not success:
                        break

                    config = await get_valid_config(USER_ID)
                    config["BOUGHT"] += 1
                    purchases.append({"id": gift_id, "price": gift_price})
                    await save_config(config)
                    await asyncio.sleep(0.3)

                if config["BOUGHT"] >= COUNT and not config["DONE"]:
                    config = await get_valid_config(USER_ID)
                    config["ACTIVE"] = False
                    config["DONE"] = True
                    await save_config(config)

                    target_display = get_target_display(config, USER_ID)

                    summary_lines = ["✅ Все подарки куплены!\n"]
                    total_spent = 0
                    gift_summary = {}

                    for p in purchases:
                        key = p["id"]
                        if key not in gift_summary:
                            gift_summary[key] = {"price": p["price"], "count": 0}
                        gift_summary[key]["count"] += 1
                        total_spent += p["price"]

                    for gid, data in gift_summary.items():
                        summary_lines.append(
                            f"📦 <b>ID:</b> {gid} | 💰 {data['price']:,} ★ × {data['count']}"
                        )

                    summary_lines.append(f"\n💸 <b>Общая сумма:</b> {total_spent:,} ★")
                    summary_lines.append(f"👤 <b>Получатель:</b> {target_display}")
                    summary = "\n".join(summary_lines)

                    message = await bot.send_message(chat_id=USER_ID, text=summary)

                    balance = await refresh_balance(bot)

                    await update_menu(bot=bot, chat_id=USER_ID, user_id=USER_ID, message_id=message.message_id)
                    break

            if len(filtered_gifts) > 0 and 0 <= config["BOUGHT"] < COUNT and not config["DONE"]:
                config = await get_valid_config(USER_ID)
                config["ACTIVE"] = False
                config["DONE"] = False
                await save_config(config)

                target_display = get_target_display(config, USER_ID)

                summary_lines = ["⚠️ Покупка остановлена.\n💰 Пополните баланс.\n"]
                total_spent = 0
                gift_summary = {}

                for p in purchases:
                    key = p["id"]
                    if key not in gift_summary:
                        gift_summary[key] = {"price": p["price"], "count": 0}
                    gift_summary[key]["count"] += 1
                    total_spent += p["price"]

                for gid, data in gift_summary.items():
                    summary_lines.append(
                        f"📦 <b>ID:</b> {gid} | 💰 {data['price']:,} ★ × {data['count']}"
                    )

                if len(gift_summary.items()) > 0: summary_lines.append("\n")

                summary_lines.append(f"💸 <b>Итого потрачено:</b> {total_spent:,} ★")
                summary_lines.append(f"🎁 <b>Куплено:</b> {config['BOUGHT']} из {COUNT}")
                summary_lines.append(f"👤 <b>Получатель:</b> {target_display}")

                summary = "\n".join(summary_lines)

                message = await bot.send_message(chat_id=USER_ID, text=summary)

                balance = await refresh_balance(bot)

                await update_menu(bot=bot, chat_id=USER_ID, user_id=USER_ID, message_id=message.message_id)

        except Exception as e:
            logger.error(f"Ошибка в get_gifts: {e}")

        await asyncio.sleep(0.3)

async def main() -> None:
    """
    Точка входа: инициализация, запуск обновления баланса, запуск polling.
    """
    logger.info("Бот запущен!")
    await ensure_config(default_config=default_config)
    asyncio.create_task(get_gifts())
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
