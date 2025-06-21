# --- Сторонние библиотеки ---
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, LabeledPrice, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# --- Внутренние модули ---
from services.config import save_config, get_valid_config
from services.menu import update_menu, payment_keyboard
from services.balance import refresh_balance, refund_all_star_payments
from services.config import CURRENCY

wizard_router = Router()

class ConfigWizard(StatesGroup):
    """
    Класс состояний для FSM wizard (пошаговое редактирование конфигурации).
    Каждый state — отдельный шаг процесса.
    """
    min_price = State()
    max_price = State()
    min_supply = State()
    max_supply = State()
    count = State()
    user_id = State()
    deposit_amount = State()
    refund_id = State()


@wizard_router.callback_query(F.data == "edit_config")
async def edit_config_handler(call: CallbackQuery, state: FSMContext):
    """
    Запуск мастера редактирования конфигурации.
    """
    await call.message.answer("💰 Минимальная цена подарка, например: <code>5000</code>\n\n/cancel — отменить")
    await state.set_state(ConfigWizard.min_price)
    await call.answer()


@wizard_router.message(ConfigWizard.min_price)
async def step_min_price(message: Message, state: FSMContext):
    """
    Обработка ввода минимальной цены подарка.
    """
    if await try_cancel(message, state):
        return
    
    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError
        await state.update_data(MIN_PRICE=value)
        await message.answer("💰 Максимальная цена подарка, например: <code>10000</code>\n\n/cancel — отменить")
        await state.set_state(ConfigWizard.max_price)
    except ValueError:
        await message.answer("🚫 Введите положительное число. Попробуйте ещё раз.")


@wizard_router.message(ConfigWizard.max_price)
async def step_max_price(message: Message, state: FSMContext):
    """
    Обработка ввода максимальной цены подарка и проверка корректности диапазона.
    """
    if await try_cancel(message, state):
        return
    
    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError

        data = await state.get_data()
        min_price = data.get("MIN_PRICE")
        if min_price and value < min_price:
            await message.answer("🚫 Максимальная цена не может быть меньше минимальной.")
            return

        await state.update_data(MAX_PRICE=value)
        await message.answer("📦 Минимальный саплай подарка, например: <code>1000</code>\n\n/cancel — отменить")
        await state.set_state(ConfigWizard.min_supply)
    except ValueError:
        await message.answer("🚫 Введите положительное число. Попробуйте ещё раз.")


@wizard_router.message(ConfigWizard.min_supply)
async def step_min_supply(message: Message, state: FSMContext):
    """
    Обработка ввода минимального саплая для подарка.
    """
    if await try_cancel(message, state):
        return
    
    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError
        await state.update_data(MIN_SUPPLY=value)
        await message.answer("📦 Максимальный саплай подарка, например: <code>10000</code>\n\n/cancel — отменить")
        await state.set_state(ConfigWizard.max_supply)
    except ValueError:
        await message.answer("🚫 Введите положительное число. Попробуйте ещё раз.")


@wizard_router.message(ConfigWizard.max_supply)
async def step_max_supply(message: Message, state: FSMContext):
    """
    Обработка ввода максимального саплая для подарка, проверка диапазона.
    """
    if await try_cancel(message, state):
        return
    
    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError

        data = await state.get_data()
        min_supply = data.get("MIN_SUPPLY")
        if min_supply and value < min_supply:
            await message.answer("🚫 Максимальный саплай не может быть меньше минимального. Попробуйте ещё раз.")
            return

        await state.update_data(MAX_SUPPLY=value)
        await message.answer("🎁 Количество подарков, например: <code>5</code>\n\n/cancel — отменить")
        await state.set_state(ConfigWizard.count)
    except ValueError:
        await message.answer("🚫 Введите положительное число. Попробуйте ещё раз.")


@wizard_router.message(ConfigWizard.count)
async def step_count(message: Message, state: FSMContext):
    """
    Обработка ввода количества подарков.
    """
    if await try_cancel(message, state):
        return
    
    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError
        await state.update_data(COUNT=value)
        await message.answer(
            "👤 Введите адрес получателя:\n\n"
            f"• <b>ID пользователя</b> (например ваш: <code>{message.from_user.id}</code>)\n"
            "• Или <b>username канала</b> (например: <code>@channel</code>)\n\n"
            "❗️ Узнать ID пользователя тут @userinfobot\n\n"
            "/cancel — отменить"
        )
        await state.set_state(ConfigWizard.user_id)
    except ValueError:
        await message.answer("🚫 Введите положительное число. Попробуйте ещё раз.")


@wizard_router.message(ConfigWizard.user_id)
async def step_user_id(message: Message, state: FSMContext):
    """
    Обработка ввода получателя (ID пользователя или username канала).
    По завершении — обновление и сохранение конфигурации.
    """
    if await try_cancel(message, state):
        return
    
    user_input = message.text.strip()
    if user_input.startswith("@"):
        target_chat = user_input
        target_user = None
    elif user_input.isdigit():
        target_chat = None
        target_user = int(user_input)
    else:
        await message.answer(
            "🚫 Если получатель аккаунт, необходимо ввести ID аккаунта. "
            "Если получатеоль канал, то необходимо ввести username канала, который начинается с @. Попробуйте ещё раз."
        )
        return

    await state.update_data(
        TARGET_USER_ID=target_user,
        TARGET_CHAT_ID=target_chat
    )

    data = await state.get_data()
    config = await get_valid_config(message.from_user.id)

    config.update({
        "MIN_PRICE": data["MIN_PRICE"],
        "MAX_PRICE": data["MAX_PRICE"],
        "MIN_SUPPLY": data["MIN_SUPPLY"],
        "MAX_SUPPLY": data["MAX_SUPPLY"],
        "COUNT": data["COUNT"],
        "TARGET_USER_ID": target_user,
        "TARGET_CHAT_ID": target_chat,
        "BOUGHT": 0,
        "ACTIVE": False,
        "DONE": False,
    })

    await save_config(config)
    await state.clear()
    await message.answer("✅ Конфигурация обновлена.\n⚠️ Не забудьте поменять 🟢 статус!")
    await update_menu(bot=message.bot, chat_id=message.chat.id, user_id=message.from_user.id, message_id=message.message_id)


@wizard_router.callback_query(F.data == "deposit_menu")
async def deposit_menu(call: CallbackQuery, state: FSMContext):
    """
    Переход к шагу пополнения баланса.
    """
    await call.message.answer("💰 Введите сумму для пополнения, например: <code>5000</code>\n\n/cancel — отменить")
    await state.set_state(ConfigWizard.deposit_amount)
    await call.answer()


@wizard_router.message(ConfigWizard.deposit_amount)
async def deposit_amount_input(message: Message, state: FSMContext):
    """
    Обработка суммы для пополнения и отправка счёта на оплату.
    """
    if await try_cancel(message, state):
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
            provider_token="",  # Укажи свой токен
            payload="stars_deposit",
            currency=CURRENCY,
            start_parameter="deposit",
            reply_markup=payment_keyboard(amount=amount),
        )
        await state.clear()
    except ValueError:
        await message.answer("🚫 Введите число от 1 до 10000.")


@wizard_router.callback_query(F.data == "refund_menu")
async def refund_menu(call: CallbackQuery, state: FSMContext):
    """
    Переход к возврату звёзд (по ID транзакции).
    """
    await call.message.answer("🆔 Введите ID транзакции для возврата:\n\n/withdraw_all — вывести весь баланс\n/cancel — отменить")
    await state.set_state(ConfigWizard.refund_id)
    await call.answer()


@wizard_router.message(ConfigWizard.refund_id)
async def refund_input(message: Message, state: FSMContext):
    """
    Обработка возврата по ID транзакции. Также поддерживается команда /withdraw_all.
    """
    if message.text and message.text.strip().lower() == "/withdraw_all":
        await state.clear()
        await withdraw_all_handler(message)
        return
    
    if await try_cancel(message, state):
        return

    txn_id = message.text.strip()
    try:
        await message.bot.refund_star_payment(
            user_id=message.from_user.id,
            telegram_payment_charge_id=txn_id
        )
        await message.answer("✅ Возврат успешно выполнен.")
        balance = await refresh_balance(message.bot)
        await update_menu(bot=message.bot, chat_id=message.chat.id, user_id=message.from_user.id, message_id=message.message_id)
    except Exception as e:
        await message.answer(f"🚫 Ошибка при возврате:\n<code>{e}</code>")
    await state.clear()


@wizard_router.message(Command("withdraw_all"))
async def withdraw_all_handler(message: Message):
    """
    Запрос подтверждения на вывод всех звёзд с баланса.
    """
    balance = await refresh_balance(message.bot)
    if balance == 0:
        await message.answer("⚠️ Не найдено звёзд для возврата.")
        await update_menu(bot=message.bot, chat_id=message.chat.id, user_id=message.from_user.id, message_id=message.message_id)
        return
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data="withdraw_all_confirm"),
                InlineKeyboardButton(text="❌ Нет", callback_data="withdraw_all_cancel"),
            ]
        ]
    )
    await message.answer(
        "⚠️ Вы уверены, что хотите вывести все звёзды?",
        reply_markup=keyboard,
    )


@wizard_router.callback_query(lambda c: c.data == "withdraw_all_confirm")
async def withdraw_all_confirmed(call: CallbackQuery):
    """
    Подтверждение и запуск процедуры возврата всех звёзд. Выводит отчёт пользователю.
    """
    await call.message.edit_text("⏳ Выполняется вывод звёзд...")  # можно тут добавить вывод/отчёт

    async def send_status(msg):
        await call.message.answer(msg)

    await call.answer()

    result = await refund_all_star_payments(
        bot=call.bot,
        user_id=call.from_user.id,
        username=call.from_user.username,
        message_func=send_status,
    )
    if result["count"] > 0:
        msg = f"✅ Возвращено: ★{result['refunded']}\n🔄 Транзакций: {result['count']}"
        if result["left"] > 0:
            msg += f"\n💰 Остаток звёзд: {result['left']}"
            dep = result.get("next_deposit")
            if dep:
                need = dep['amount'] - result['left']
                msg += (
                    f"\n➕ Пополните баланс ещё минимум на ★{need} (или суммарно до ★{dep['amount']})."
                )
        await call.message.answer(msg)
    else:
        await call.message.answer("🚫 Звёзд для возврата не найдено.")

    balance = await refresh_balance(call.bot)
    await update_menu(bot=call.bot, chat_id=call.message.chat.id, user_id=call.from_user.id, message_id=call.message.message_id)


@wizard_router.callback_query(lambda c: c.data == "withdraw_all_cancel")
async def withdraw_all_cancel(call: CallbackQuery):
    """
    Обработка отмены возврата всех звёзд.
    """
    await call.message.edit_text("🚫 Действие отменено.")
    await call.answer()
    await update_menu(bot=call.bot, chat_id=call.message.chat.id, user_id=call.from_user.id, message_id=call.message.message_id)


async def try_cancel(message: Message, state: FSMContext) -> bool:
    """
    Проверка, ввёл ли пользователь /cancel, и отмена мастера, если да.
    """
    if message.text and message.text.strip().lower() == "/cancel":
        await state.clear()
        await message.answer("🚫 Действие отменено.")
        await update_menu(bot=message.bot, chat_id=message.chat.id, user_id=message.from_user.id, message_id=message.message_id)
        return True
    return False


def register_wizard_handlers(dp):
    """
    Регистрация wizard_router в диспетчере (Dispatcher).
    """
    dp.include_router(wizard_router)
