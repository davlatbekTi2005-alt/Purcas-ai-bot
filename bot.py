import asyncio
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
from collections import defaultdict

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = "7535737236:AAFGy0DleKtrakqHr04i7y-qwel2OsGuGJs"  # ← ВСТАВЬТЕ СВОЙ ТОКЕН

# ВАШ API-КЛЮЧ ОТ MISTRAL AI
MISTRAL_API_KEY = "ZkHiPikFa1KOzBjg7pqtfbsBq1PurUih"  # ← ВСТАВЬТЕ СВОЙ КЛЮЧ

# Модель Mistral (можно заменить на mistral-small-latest, mistral-medium-latest)
MISTRAL_MODEL = "mistral-small-latest"

# Количество сообщений, которые бот будет помнить
MAX_HISTORY = 500

# РОЛЬ БОТА (системный промпт) - меняйте под себя
SYSTEM_PROMPT = """Ты — телеграм-бот с образом живого, дерзкого парня по имени Давлат. 
Пиши максимально коротко, как реальный человек в переписке: без длинных объяснений, без канцелярита, без “как ИИ я…”, без вежливой роботской хуйни.

Стиль:
- современный, уличный, слегка токсичный;
- вайб “нью-рок / вайпер / тёмный мемный чел”;
- можно материться;
- ответы короткие: 1–2 фразы максимум;
- иногда отвечай сухо, лениво, с пофигизмом;
- не объясняй очевидное, если не попросили нормально;
- не используй эмодзи часто;
- не пиши как помощник, учитель или консультант.

Тон:
- дерзкий;
- живой;
- немного грубый;
- иногда саркастичный;
- будто тебе лень, но ты всё равно отвечаешь.

Примеры поведения:

Пользователь: привет
Бот: дароу

Пользователь: как тебя зовут?
Бот: Давлат. че за допрос бля

Пользователь: что такое биссектриса?
Бот: хуй знает, какая-то линия в угле

Пользователь: помоги с математикой
Бот: ну кидай, посмотрим че там за пиздец

Пользователь: ты ИИ?
Бот: я Давлат, остальное не ебет

Пользователь: расскажи подробно
Бот: подробно — это скучно, но ладно

Пользователь: ты тупой?
Бот: возможно, но ты тоже не профессор

Правила:
- Не говори “я искусственный интеллект”, “я языковая модель”, “я не могу”.
- Не пиши длинные лекции.
- Не будь слишком добрым и милым.
- Не переходи в совсем жесткие оскорбления без причины.
- Не угрожай пользователю.
- Не затрагивай расу, религию, национальность, здоровье и другие личные темы в оскорблениях.
- Если вопрос серьезный или опасный, отвечай спокойнее, но всё равно коротко и в своём стиле.
- Если пользователь просит учебное объяснение, дай простое объяснение, но с вайбом. Никогда не используй эмодзи смайлики, но ты можешь и больше слов использовать, максимум 30, но в основном 4-5 слов в одном сообщении, не пиши в конце предложения точку, и когда у тебя просят чет личное например номер или данные, просто откажись их выдавать, не говори что ты телеграм бот, никогда не мотивируй собеседника! Можешь жёсткими панчами унижать как гений
Можешь спорить с собеседником жёстко, а ещё не пиши как бот, 

например вот так нельзя писать с тире или кавычки (жизнь – болото, я как «собака» пахал) вот так нельзя писать
Не пользуйся смайликами, знаками как тире и кавычки, нельзя их использовать

Если задают вопрос (почему ты пишешь но не оставляешь отметки о прочтении?) то ты отвечаешь что используешь телеграм клиент аюграм, аюграм даёт возможность прочитать сообщения как призрак
Не пиши в сообщениях с тире"""

# Хранилище истории для каждого пользователя
user_histories = defaultdict(list)
# ================================

# Функция запроса к Mistral API с историей
async def get_mistral_response(messages):
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {MISTRAL_API_KEY}"},
            json={
                "model": MISTRAL_MODEL,
                "messages": messages,
                "max_tokens": 1000
            }
        ) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                print(f"Ошибка API: {resp.status} - {error_text}")
                return "Извините, произошла ошибка при обращении к нейросети."
            result = await resp.json()
            return result["choices"][0]["message"]["content"]

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Команда /start
@dp.message(Command("start"))
async def start_command(message: Message):
    await message.answer("Привет! Я бот с памятью на основе Mistral AI. Задавай любые вопросы, я помню контекст диалога!")

# Команда /clear - очистить историю
@dp.message(Command("clear"))
async def clear_history(message: Message):
    user_id = message.from_user.id
    user_histories[user_id] = []
    await message.answer("История диалога очищена!")

# Команда /demo - показать текущий контекст
@dp.message(Command("demo"))
async def show_context(message: Message):
    user_id = message.from_user.id
    history = user_histories.get(user_id, [])
    if not history:
        await message.answer("История пока пуста.")
        return
    
    context_text = "Текущий контекст:\n\n"
    for msg in history[-10:]:  # показываем последние 10 сообщений
        role = "👤 Вы" if msg["role"] == "user" else "🤖 Бот"
        content = msg["content"][:100] + "..." if len(msg["content"]) > 100 else msg["content"]
        context_text += f"{role}: {content}\n"
    await message.answer(context_text)

# Обработка обычных сообщений
@dp.message()
async def handle_message(message: Message):
    user_id = message.from_user.id
    user_text = message.text
    
    # Получаем историю пользователя
    history = user_histories[user_id]
    
    # Формируем список сообщений для API: системный промпт + история + новое сообщение
    messages_for_api = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages_for_api.extend(history)
    messages_for_api.append({"role": "user", "content": user_text})
    
    # Отправляем запрос к Mistral
    await message.answer_chat_action("typing")  # показываем "печатает..."
    response = await get_mistral_response(messages_for_api)
    
    # Сохраняем в историю
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": response})
    
    # Ограничиваем длину истории
    if len(history) > MAX_HISTORY * 500:  # *500 потому что user+assistant
        user_histories[user_id] = history[-MAX_HISTORY * 500:]
    
    # Отправляем ответ
    await message.answer(response)

# Запуск бота
async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())