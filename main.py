# --- Стандартные библиотеки ---
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone

# --- Сторонние библиотеки ---
import aiofiles
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramNetworkError, TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    TelegramObject,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- Загрузка параметров ---
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
USER_ID = int(os.getenv("TELEGRAM_USER_ID"))

ALLOWED_USER_IDS = []
ALLOWED_USER_IDS.append(USER_ID)
CURRENCY = 'XTR'
VERSION = '1.0.1'

# --- Формирование конфигурации ---
CONFIG_PATH = "config.json"
DEFAULT_CONFIG = {
    "MIN_PRICE": 5000,
    "MAX_PRICE": 10000,
    "MIN_SUPPLY": 1000,
    "MAX_SUPPLY": 10000,
    "COUNT": 5,
    "TARGET_USER_ID": USER_ID,
    "TARGET_CHAT_ID": None,
    "BALANCE": 0,
    "BOUGHT": 0,
    "ACTIVE": False,
    "DONE": False,
    "LAST_MENU_MESSAGE_ID": None
}
CONFIG_TYPES = {
    "MIN_PRICE": (int, False),
    "MAX_PRICE": (int, False),
    "MIN_SUPPLY": (int, False),
    "MAX_SUPPLY": (int, False),
    "COUNT": (int, False),
    "TARGET_USER_ID": (int, True),
    "TARGET_CHAT_ID": (str, True),
    "BALANCE": (int, False),
    "BOUGHT": (int, False),
    "ACTIVE": (bool, False),
    "DONE": (bool, False),
    "LAST_MENU_MESSAGE_ID": (int, True)
}

class AccessControlMiddleware(BaseMiddleware):
    def __init__(self, allowed_user_ids: list[int], bot: Bot):
        self.allowed_user_ids = allowed_user_ids
        self.bot = bot
        super().__init__()

    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = data.get("event_from_user")
        if user and user.id not in self.allowed_user_ids:
            try:
                if isinstance(event, Message):
                    await event.answer("✅ Вы сможете получать подарки от этого бота.\n⛔️ У вас нет доступа к панели управления.\n\n<b>🤖 Исходный код: <a href=\"https://github.com/leozizu/TelegramGiftsBot\">GitHub</a></b>\n<b>🐸 Автор: @leozizu</b>\n<b>📢 Канал: @pepeksey</b>")
                elif isinstance(event, CallbackQuery):
                    await event.answer("⛔️ Нет доступа", show_alert=True)
            except Exception as e:
                print(f"{now_str()}: [WARN] Не удалось отправить отказ пользователю {user.id}: {e}")
            return
        return await handler(event, data)

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
dp.message.middleware(AccessControlMiddleware(ALLOWED_USER_IDS, bot))
dp.callback_query.middleware(AccessControlMiddleware(ALLOWED_USER_IDS, bot))

class ConfigWizard(StatesGroup):
    min_price = State()
    max_price = State()
    min_supply = State()
    max_supply = State()
    count = State()
    user_id = State()
    deposit_amount = State()
    refund_id = State()

def now_str() -> str:
    return datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M:%S")

def is_valid_type(value, expected_type, allow_none=False):
    if value is None:
        return allow_none
    return isinstance(value, expected_type)

async def ensure_config(path=CONFIG_PATH):
    if not os.path.exists(path):
        async with aiofiles.open(path, mode="w", encoding="utf-8") as f:
            await f.write(json.dumps(DEFAULT_CONFIG, indent=2))
        print(f"{now_str()}: [INFO] Создана конфигурация: {path}")

async def load_config(path=CONFIG_PATH):
    async with aiofiles.open(path, mode="r", encoding="utf-8") as f:
        data = await f.read()
        return json.loads(data)

async def save_config(new_data: dict, path=CONFIG_PATH):
    try:
        current_data = {}
        if os.path.exists(path):
            async with aiofiles.open(path, mode="r", encoding="utf-8") as f:
                current_raw = await f.read()
                if current_raw.strip():
                    current_data = json.loads(current_raw)

        current_data.update(new_data)

        async with aiofiles.open(path, mode="w", encoding="utf-8") as f:
            await f.write(json.dumps(current_data, indent=2))

        print(f"{now_str()}: [INFO] Конфигурация сохранена.")

    except Exception as e:
        print(f"{now_str()}: [ERROR] Не удалось сохранить config: {e}")

async def validate_config(config: dict) -> dict:
    updated = False
    validated = {}

    for key, default_value in DEFAULT_CONFIG.items():
        expected_type, allow_none = CONFIG_TYPES.get(key, (type(default_value), False))
        if key not in config or not is_valid_type(config[key], expected_type, allow_none):
            print(f"{now_str()}: [WARN] Недопустимое или отсутствующее поле '{key}', используется значение по умолчанию: {default_value}")
            validated[key] = default_value
            updated = True
        else:
            validated[key] = config[key]

    if updated:
        await save_config(validated)
        print(f"{now_str()}: [INFO] Конфигурация обновлена с недостающими полями.")

    return validated

def config_action_keyboard(active: bool) -> InlineKeyboardMarkup:
    toggle_text = "🔴 Выключить" if active else "🟢 Включить"

    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=toggle_text, callback_data="toggle_active"),
            InlineKeyboardButton(text="✏️ Изменить", callback_data="edit_config")
        ],
        [
            InlineKeyboardButton(text="♻️ Сбросить", callback_data="reset_bought"),
            InlineKeyboardButton(text="❓ Помощь", callback_data="show_help")
        ],
        [
            InlineKeyboardButton(text="💰 Пополнить", callback_data="deposit_menu"),
            InlineKeyboardButton(text="↩️ Вывести", callback_data="refund_menu")
        ]
    ])

async def delete_menu(chat_id: int = USER_ID, current_message_id: int = None):
    last_menu_message_id = await get_last_menu_message_id()

    if last_menu_message_id and last_menu_message_id != current_message_id:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=last_menu_message_id)
        except TelegramBadRequest as e:
            error_text = str(e)
            if "message can't be deleted for everyone" in error_text:
                await bot.send_message(
                    chat_id,
                    "⚠️ Предыдущее меню устарело и не может быть удалено (прошло более 48 часов). Используйте актуальное меню.\n"
                )
            elif "message to delete not found" in error_text:
                pass
            else:
                raise

async def send_menu(chat_id: int = USER_ID, config: dict = None, text: str = None) -> int:
    sent = await bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=config_action_keyboard(config.get("ACTIVE"))
    )
    await update_last_menu_message_id(sent.message_id)
    return sent.message_id

async def update_last_menu_message_id(message_id: int):
    config = await load_config()
    config["LAST_MENU_MESSAGE_ID"] = message_id
    await save_config(config)

async def get_last_menu_message_id():
    config = await load_config()
    return config.get("LAST_MENU_MESSAGE_ID")

async def refresh_balance() -> int:
    balance = await get_stars_balance()
    config = await load_config()
    config["BALANCE"] = balance
    await save_config(config)
    return balance

async def change_balance(delta: int) -> int:
    config = await load_config()
    config["BALANCE"] = max(0, config.get("BALANCE", 0) + delta)
    await save_config(config)
    return config["BALANCE"]

@dp.callback_query(F.data == "show_help")
async def help_callback(call: CallbackQuery):
    raw_config = await load_config()
    config = await validate_config(raw_config)
    TARGET_USER_ID = config["TARGET_USER_ID"]
    TARGET_CHAT_ID = config["TARGET_CHAT_ID"]
    target_display = (
        f"{TARGET_CHAT_ID}"
        if TARGET_CHAT_ID
        else f"<code>{TARGET_USER_ID}</code> (Вы)" if str(TARGET_USER_ID) == str(USER_ID)
        else f"<code>{TARGET_USER_ID}</code>"
    )

    help_text = (
        f"<b>🛠 Управление ботом (v{VERSION}):</b>\n\n"
        "<b>🟢 Включить / 🔴 Выключить</b> — запускает или останавливает покупки.\n"
        "<b>✏️ Изменить</b> — пошаговое изменение параметров конфигурации.\n"
        "<b>♻️ Сбросить счётчик</b> — обнуляет количество уже купленных подарков.\n"
        "<b>💰 Пополнить</b> — депозит звёзд в бот.\n"
        "<b>↩️ Вывести</b> — возврат звёзд по ID транзакции.\n\n"
        "<b>📌 Подсказки:</b>\n\n"
        "❕ Если получатель подарка — другой пользователь, он должен зайти в этот бот и нажать <code>/start</code>.\n"
        "❕ После изменения конфигурации, покупки автоматически не стартуют — включите 🟢 вручную.\n"
        "❗️ Получатель подарка <b>аккаунт</b> — пишите <b>id</b> пользователя (узнать можно тут @userinfobot).\n"
        "❗️ Получатель подарка <b>канал</b> — пишите <b>username</b> канала.\n"
        "❓ Как посмотреть <b>ID транзакции</b> для возврата звёзд?  Нажми на сообщение об оплате в чате с ботом и там будет ID транзакции.\n"
        f"✅ Хотите протестировать бот? Купите подарок 🧸 за ★15, получатель {target_display}.\n\n"
        "<b>🐸 Автор: @leozizu</b>\n"
        "<b>📢 Канал: @pepeksey</b>"
    )
    button = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Тест? Купить 🧸 за ★15", callback_data="buy_bear")
        ]
    ])

    await call.answer()
    await call.message.answer(help_text, reply_markup=button)

@dp.callback_query(F.data == "buy_bear")
async def buy_bear(call: CallbackQuery):
    gift_id = '5170233102089322756'
    raw_config = await load_config()
    config = await validate_config(raw_config)
    TARGET_USER_ID = config["TARGET_USER_ID"]
    TARGET_CHAT_ID = config["TARGET_CHAT_ID"]
    target_display = (
        f"{TARGET_CHAT_ID}"
        if TARGET_CHAT_ID
        else f"<code>{TARGET_USER_ID}</code> (Вы)" if str(TARGET_USER_ID) == str(USER_ID)
        else f"<code>{TARGET_USER_ID}</code>"
    )

    success = await buy_gift(
        gift_id=gift_id,
        user_id=TARGET_USER_ID,
        chat_id=TARGET_CHAT_ID,
        gift_price=15,
        file_id=None
    )
    if not success:
        await call.answer()
        await call.message.answer("⚠️ Покупка подарка 🧸 за ★15 невозможна.\n💰 Пополните баланс.\n")
        return
    
    await call.answer()
    await call.message.answer(f"✅ Подарок 🧸 за ★15 куплен. Получатель: {target_display}.")

@dp.callback_query(F.data == "reset_bought")
async def reset_bought_callback(call: CallbackQuery):
    config = await load_config()
    config["BOUGHT"] = 0
    config["DONE"] = False
    config["ACTIVE"] = False
    await save_config(config)

    info = format_config_summary(config)
    try:
        await call.message.edit_text(
            info,
            reply_markup=config_action_keyboard(config["ACTIVE"])
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise

    await call.answer("Счётчик покупок сброшен.")

@dp.callback_query(F.data == "deposit_menu")
async def deposit_menu(call: CallbackQuery, state: FSMContext):
    await call.message.answer("💰 Введите сумму для пополнения, например: <code>5000</code>\n\n/cancel — отменить")
    await state.set_state(ConfigWizard.deposit_amount)
    await call.answer()

@dp.message(ConfigWizard.deposit_amount)
async def deposit_amount_input(message: Message, state: FSMContext):
    if message.text.strip().lower() == "/cancel":
        await cancel_edit(message, state)
        return
    
    try:
        amount = int(message.text)
        if amount < 1 or amount > 10000:
            raise ValueError
        prices = [LabeledPrice(label=CURRENCY, amount=amount)]
        await message.answer_invoice(
            title="Бот для подарков",
            description="Пополнение баланса",
            prices=prices,
            provider_token="",
            payload="stars_deposit",
            currency=CURRENCY,
            start_parameter="deposit",
            reply_markup=payment_keyboard(amount=amount),
        )
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите число от 1 до 10000.")

@dp.callback_query(F.data == "refund_menu")
async def refund_menu(call: CallbackQuery, state: FSMContext):
    await call.message.answer("🆔 Введите ID транзакции для возврата:\n\n/cancel — отменить")
    await state.set_state(ConfigWizard.refund_id)
    await call.answer()

@dp.message(ConfigWizard.refund_id)
async def refund_input(message: Message, state: FSMContext):
    if message.text.strip().lower() == "/cancel":
        await cancel_edit(message, state)
        return
    
    txn_id = message.text.strip()
    try:
        await bot.refund_star_payment(
            user_id=message.from_user.id,
            telegram_payment_charge_id=txn_id
        )
        await message.answer("✅ Возврат успешно выполнен.")
        balance = await refresh_balance()
        raw_config = await load_config()
        config = await validate_config(raw_config)
        await delete_menu(current_message_id=message.message_id)
        await send_menu(config=config, text=format_config_summary(config))
    except Exception as e:
        await message.answer(f"❌ Ошибка при возврате:\n<code>{e}</code>")
    await state.clear()

@dp.message(Command("cancel"))
async def cancel_edit(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Действие отменено.")
    raw_config = await load_config()
    config = await validate_config(raw_config)
    await delete_menu(current_message_id=message.message_id)
    await send_menu(config=config, text=format_config_summary(config))

@dp.message(CommandStart())
async def command_status_handler(message: Message):
    balance = await refresh_balance()
    config = await load_config()
    info = format_config_summary(config)

    await delete_menu(current_message_id=message.message_id)
    await send_menu(config=config, text=info)

@dp.callback_query(F.data == "toggle_active")
async def toggle_active_callback(call: CallbackQuery):
    config = await load_config()
    config["ACTIVE"] = not config.get("ACTIVE", False)
    await save_config(config)

    info = format_config_summary(config)
    await call.message.edit_text(
        info,
        reply_markup=config_action_keyboard(config["ACTIVE"])
    )
    await call.answer("Статус обновлён")

@dp.callback_query(F.data == "edit_config")
async def edit_config_handler(call: CallbackQuery, state: FSMContext):
    await call.message.answer("💰 Минимальная цена подарка, например: <code>5000</code>\n\n/cancel — отменить")
    await state.set_state(ConfigWizard.min_price)
    await call.answer()

@dp.message(ConfigWizard.min_price)
async def step_min_price(message: Message, state: FSMContext):
    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError
        await state.update_data(MIN_PRICE=value)
        await message.answer("💰 Максимальная цена подарка, например: <code>10000</code>\n\n/cancel — отменить")
        await state.set_state(ConfigWizard.max_price)
    except ValueError:
        await message.answer("❌ Введите положительное число. Попробуйте ещё раз.")

@dp.message(ConfigWizard.max_price)
async def step_max_price(message: Message, state: FSMContext):
    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError

        data = await state.get_data()
        min_price = data.get("MIN_PRICE")
        if min_price and value < min_price:
            await message.answer("❌ Максимальная цена не может быть меньше минимальной.")
            return

        await state.update_data(MAX_PRICE=value)
        await message.answer("📦 Минимальный саплай подарка, например: <code>1000</code>\n\n/cancel — отменить")
        await state.set_state(ConfigWizard.min_supply)
    except ValueError:
        await message.answer("❌ Введите положительное число. Попробуйте ещё раз.")

@dp.message(ConfigWizard.min_supply)
async def step_min_supply(message: Message, state: FSMContext):
    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError
        await state.update_data(MIN_SUPPLY=value)
        await message.answer("📦 Максимальный саплай подарка, например: <code>10000</code>\n\n/cancel — отменить")
        await state.set_state(ConfigWizard.max_supply)
    except ValueError:
        await message.answer("❌ Введите положительное число. Попробуйте ещё раз.")

@dp.message(ConfigWizard.max_supply)
async def step_max_supply(message: Message, state: FSMContext):
    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError

        data = await state.get_data()
        min_supply = data.get("MIN_SUPPLY")
        if min_supply and value < min_supply:
            await message.answer("❌ Максимальный саплай не может быть меньше минимального. Попробуйте ещё раз.")
            return

        await state.update_data(MAX_SUPPLY=value)
        await message.answer("🎁 Количество подарков, например: <code>5</code>\n\n/cancel — отменить")
        await state.set_state(ConfigWizard.count)
    except ValueError:
        await message.answer("❌ Введите положительное число. Попробуйте ещё раз.")

@dp.message(ConfigWizard.count)
async def step_count(message: Message, state: FSMContext):
    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError
        await state.update_data(COUNT=value)
        await message.answer(
            "👤 Введите адрес получателя:\n\n"
            f"• <b>ID пользователя</b> (например ваш: <code>{USER_ID}</code>)\n"
            "• Или <b>username канала</b> (например: <code>@channel</code>)\n\n"
            "❗️ Узнать ID пользователя тут @userinfobot\n\n"
            "/cancel — отменить"
        )
        await state.set_state(ConfigWizard.user_id)
    except ValueError:
        await message.answer("❌ Введите положительное число. Попробуйте ещё раз.")

@dp.message(ConfigWizard.user_id)
async def step_user_id(message: Message, state: FSMContext):
    user_input = message.text.strip()

    if user_input.startswith("@"):
        target_chat = user_input
        target_user = None
    elif user_input.isdigit():
        target_chat = None
        target_user = int(user_input)
    else:
        await message.answer("❌ Если получатель аккаунт, необходимо ввести ID аккаунта. Если получатеоль канал, то необходимо ввести username канала, который начинается с @. Попробуйте ещё раз.")
        return

    await state.update_data(
        TARGET_USER_ID=target_user,
        TARGET_CHAT_ID=target_chat
    )

    data = await state.get_data()
    balance = await refresh_balance()
    config = await load_config()

    config.update({
        "MIN_PRICE": data["MIN_PRICE"],
        "MAX_PRICE": data["MAX_PRICE"],
        "MIN_SUPPLY": data["MIN_SUPPLY"],
        "MAX_SUPPLY": data["MAX_SUPPLY"],
        "COUNT": data["COUNT"],
        "TARGET_USER_ID": target_user,
        "TARGET_CHAT_ID": target_chat,
        "BALANCE": balance,
        "BOUGHT": 0,
        "ACTIVE": False,
        "DONE": False,
    })

    await save_config(config)
    await state.clear()
    await message.answer("✅ Конфигурация обновлена.\n❗️ Не забудьте поменять 🟢 статус!")

    await delete_menu(current_message_id=message.message_id)
    await send_menu(config=config, text=format_config_summary(config))

def format_config_summary(config: dict) -> str:
    status_text = "🟢 Активен" if config.get("ACTIVE") else "🔴 Неактивен"
    target_chat_id = config.get("TARGET_CHAT_ID")
    target_user_id = config.get("TARGET_USER_ID")
    target_display = (
        f"{target_chat_id}"
        if target_chat_id
        else f"<code>{target_user_id}</code> (Вы)" if str(target_user_id) == str(USER_ID)
        else f"<code>{target_user_id}</code>"
    )
    balance = config["BALANCE"]

    return (
        f"🚦 <b>Статус:</b> {status_text}\n\n"
        f"💰 <b>Цена</b>: {config.get('MIN_PRICE'):,} – {config.get('MAX_PRICE'):,} ★\n"
        f"📦 <b>Саплай</b>: {config.get('MIN_SUPPLY'):,} – {config.get('MAX_SUPPLY'):,}\n"
        f"🎁 <b>Количество</b>: {config.get('BOUGHT'):,} / {config.get('COUNT'):,}\n"
        f"👤 <b>Получатель</b>: {target_display}\n\n"
        f"💸 <b>Баланс</b>: {balance:,} ★\n"
    )

def payment_keyboard(amount):
    builder = InlineKeyboardBuilder()
    builder.button(text=f"Пополнить ★{amount:,}", pay=True)
    return builder.as_markup()

@dp.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)

@dp.message(F.successful_payment)
async def process_successful_payment(message: Message) -> None:
    await message.answer(
        f'✅ Баланс успешно пополнен.',
        message_effect_id="5104841245755180586"
    )
    balance = await refresh_balance()
    raw_config = await load_config()
    config = await validate_config(raw_config)
    await delete_menu(current_message_id=message.message_id)
    await send_menu(config=config, text=format_config_summary(config))

async def buy_gift(gift_id, user_id, chat_id, gift_price, file_id, retries=3):
    balance = await refresh_balance()
    if balance < gift_price:
        print(f"{now_str()}: [WARN] ❌ Недостаточно звёзд для покупки подарка {gift_id} (требуется: {gift_price}, доступно: {balance})")
        
        raw_config = await load_config()
        config = await validate_config(raw_config)
        config["ACTIVE"] = False
        await save_config(config)

        return False
    
    for attempt in range(1, retries + 1):
        try:
            if user_id is not None and chat_id is None:
                result = await bot.send_gift(gift_id=gift_id, user_id=user_id)
            elif user_id is None and chat_id is not None:
                result = await bot.send_gift(gift_id=gift_id, chat_id=chat_id)
            else:
                break

            if result:
                new_balance = await change_balance(int(-gift_price))
                print(f"{now_str()}: [INFO] ✅ Успешная покупка подарка {gift_id} за {gift_price} звёзд. Остаток: {new_balance}")
                return True
            
            print(f"{now_str()}: [WARN] Попытка {attempt}/{retries}: Не удалось купить подарок {gift_id}. Повтор...")

        except TelegramNetworkError as e:
            print(f"{now_str()}: [ERROR] Попытка {attempt}/{retries}: Сетевая ошибка: {e}. Повтор через {2**attempt} секунд...")
            await asyncio.sleep(2**attempt)

        except TelegramAPIError as e:
            print(f"{now_str()}: [ERROR] Ошибка Telegram API: {e}")
            break

    print(f"{now_str()}: ❌ [ERROR] Не удалось купить подарок {gift_id} после {retries} попыток.")
    return False

async def get_gifts():
    await ensure_config()
    balance = await refresh_balance()

    while True:
        try:
            raw_config = await load_config()
            config = await validate_config(raw_config)

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

            get_market_gifts = await bot.get_available_gifts()
            gifts = get_market_gifts.gifts
            
            filtered_gifts = [
                gift for gift in gifts
                    if MIN_PRICE <= gift.star_count <= MAX_PRICE and
                    MIN_SUPPLY <= (gift.total_count or 0) <= MAX_SUPPLY
            ]
            filtered_gifts.sort(key=lambda g: g.star_count, reverse=True)

            purchases = []

            for gift in filtered_gifts:
                gift_id = gift.id
                gift_price = gift.star_count
                gift_total_count = gift.total_count or 0
                sticker_file_id = gift.sticker.file_id

                if config["DONE"] == False and config["ACTIVE"] == True:
                    print(f"{now_str()}: [MATCH] {gift_id} - {gift_price} stars - supply: {gift_total_count}")

                while config["BOUGHT"] < COUNT:
                    success = await buy_gift(
                        gift_id=gift_id,
                        user_id=TARGET_USER_ID,
                        chat_id=TARGET_CHAT_ID,
                        gift_price=gift_price,
                        file_id=sticker_file_id
                    )

                    if not success:
                        break

                    config["BOUGHT"] += 1
                    purchases.append({"id": gift_id, "price": gift_price})
                    await save_config(config)
                    await asyncio.sleep(0.1)

                if config["BOUGHT"] >= COUNT and not config["DONE"]:
                    config["ACTIVE"] = False
                    config["DONE"] = True
                    await save_config(config)

                    target_display = (
                        f"{TARGET_CHAT_ID}" if TARGET_CHAT_ID else str(TARGET_USER_ID)
                    )

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

                    balance = await refresh_balance()

                    await delete_menu(current_message_id=message.message_id)
                    await send_menu(config=config, text=format_config_summary(config))
                    break

            if len(filtered_gifts) > 0 and 0 <= config["BOUGHT"] < COUNT and not config["DONE"]:
                config["ACTIVE"] = False
                config["DONE"] = False
                await save_config(config)

                target_display = (
                    f"{TARGET_CHAT_ID}" if TARGET_CHAT_ID else str(TARGET_USER_ID)
                )

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

                balance = await refresh_balance()
                await delete_menu(current_message_id=message.message_id)
                await send_menu(config=config, text=format_config_summary(config))

        except Exception as e:
            print(f"{now_str()}: [ERROR] Ошибка в get_gifts: {e}")

        await asyncio.sleep(0.1)

async def get_stars_balance():
    offset = 0
    limit = 100
    balance = 0
    total_transactions = 0

    while True:
        get_transactions = await bot.get_star_transactions(offset=offset, limit=limit)
        transactions = get_transactions.transactions

        if not transactions:
            break

        for transaction in transactions:
            source = transaction.source
            amount = transaction.amount
            if source is not None:
                balance += amount
            else:
                balance -= amount

        total_transactions += len(transactions)
        offset += limit

    return balance

async def main() -> None:
    asyncio.create_task(get_gifts())
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
