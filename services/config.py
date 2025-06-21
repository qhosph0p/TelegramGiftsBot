# --- Стандартные библиотеки ---
import json
import os
import logging

# --- Сторонние библиотеки ---
import aiofiles

logger = logging.getLogger(__name__)

CURRENCY = 'XTR'
VERSION = '1.1.0'
CONFIG_PATH = "config.json"

DEFAULT_CONFIG = lambda user_id: {
    "MIN_PRICE": 5000,
    "MAX_PRICE": 10000,
    "MIN_SUPPLY": 1000,
    "MAX_SUPPLY": 10000,
    "COUNT": 5,
    "TARGET_USER_ID": user_id,
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


def format_config_summary(config: dict, user_id: int) -> str:
    """Формирует краткое текстовое описание конфигурации для вывода в меню."""
    status_text = "🟢 Активен" if config.get("ACTIVE") else "🔴 Неактивен"
    balance = config["BALANCE"]
    target_display = get_target_display(config, user_id)

    return (
        f"🚦 <b>Статус:</b> {status_text}\n\n"
        f"💰 <b>Цена</b>: {config.get('MIN_PRICE'):,} – {config.get('MAX_PRICE'):,} ★\n"
        f"📦 <b>Саплай</b>: {config.get('MIN_SUPPLY'):,} – {config.get('MAX_SUPPLY'):,}\n"
        f"🎁 <b>Количество</b>: {config.get('BOUGHT'):,} / {config.get('COUNT'):,}\n"
        f"👤 <b>Получатель</b>: {target_display}\n\n"
        f"💰 <b>Баланс</b>: {balance:,} ★\n"
    )


def get_target_display(config: dict, user_id: int) -> str:
    """Возвращает строковое описание получателя подарка на основе конфига и user_id."""
    target_chat_id = config.get("TARGET_CHAT_ID")
    target_user_id = config.get("TARGET_USER_ID")
    if target_chat_id:
        return f"{target_chat_id} (Канал)"
    elif str(target_user_id) == str(user_id):
        return f"<code>{target_user_id}</code> (Вы)"
    else:
        return f"<code>{target_user_id}</code>"
    
    
def is_valid_type(value, expected_type, allow_none=False):
    """Проверяет, соответствует ли значение ожидаемому типу (или None, если разрешено)."""
    if value is None:
        return allow_none
    return isinstance(value, expected_type)
    

async def get_valid_config(user_id: int) -> dict:
    """Загружает, валидирует и возвращает актуальную конфигурацию для указанного пользователя."""
    raw = await load_config()
    default_config = DEFAULT_CONFIG(user_id)
    return await validate_config(raw, default_config=default_config)


async def ensure_config(path=CONFIG_PATH, default_config=None):
    """Гарантирует наличие файла конфигурации, создает его с дефолтными значениями при отсутствии."""
    if not os.path.exists(path):
        async with aiofiles.open(path, mode="w", encoding="utf-8") as f:
            await f.write(json.dumps(default_config, indent=2))
        logger.info(f"Создана конфигурация: {path}")


async def load_config(path=CONFIG_PATH):
    """Асинхронно загружает конфигурацию из файла. Если файл не найден — создает дефолтный."""
    await ensure_config(path)
    async with aiofiles.open(path, mode="r", encoding="utf-8") as f:
        data = await f.read()
        return json.loads(data)


async def save_config(new_data: dict, path=CONFIG_PATH):
    """Асинхронно сохраняет новую конфигурацию в файл, обновляя существующую."""
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

        logger.info(f"Конфигурация сохранена.")

    except Exception as e:
        logger.error(f"Не удалось сохранить config: {e}")

async def validate_config(config: dict, default_config: dict) -> dict:
    """Проверяет и дополняет конфиг, возвращает актуальный конфиг, обновляет файл при необходимости."""
    updated = False
    validated = {}

    for key, default_value in default_config.items():
        expected_type, allow_none = CONFIG_TYPES.get(key, (type(default_value), False))
        if key not in config or not is_valid_type(config[key], expected_type, allow_none):
            logger.error(f"Недопустимое или отсутствующее поле '{key}', используется значение по умолчанию: {default_value}")
            validated[key] = default_value
            updated = True
        else:
            validated[key] = config[key]

    if updated:
        await save_config(validated)
        logger.info(f"Конфигурация обновлена с недостающими полями.")

    return validated

