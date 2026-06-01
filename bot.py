import sys
import subprocess

# --- АВТОУСТАНОВКА БИБЛИОТЕК ---
try:
    import speech_recognition
    from pydub import AudioSegment
    import aiogram
    import aiohttp
    import requests
    import bs4
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "aiogram", "aiohttp", "SpeechRecognition", "pydub", "requests", "beautifulsoup4"])

import asyncio
import logging
import aiohttp
import base64
import os
import tempfile
import urllib.parse
import requests
from bs4 import BeautifulSoup
import speech_recognition as sr
from pydub import AudioSegment
from datetime import datetime
from collections import defaultdict
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message

# --- НАСТРОЙКИ ---
BOT_TOKEN = "8871791887:AAG3Ml8f1XmB4f9TkWVexD20teZCygMgI9Q"  

# СПИСОК ИЗ 10 API КЛЮЧЕЙ
MISTRAL_KEYS = [
    "QTtrrl4ow8oU8PYyycCOQQUtFDW0o8r2",
    "ZkHiPikFa1KOzBjg7pqtfbsBq1PurUih",
    "СЮДА_3_КЛЮЧ",
    "СЮДА_4_КЛЮЧ",
    "СЮДА_5_КЛЮЧ",
    "СЮДА_6_КЛЮЧ",
    "СЮДА_7_КЛЮЧ",
    "СЮДА_8_КЛЮЧ",
    "СЮДА_9_КЛЮЧ",
    "СЮДА_10_КЛЮЧ"
]
current_key_index = 0

MISTRAL_TEXT_MODEL = "mistral-large-latest"
MISTRAL_VISION_MODEL = "pixtral-large-latest"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- ОЧЕРЕДЬ И СТАТУСЫ ---
request_queue = asyncio.Queue()
active_tasks = {} 
is_busy = False 

# --- ПАМЯТЬ И РОЛИ ---
user_histories = defaultdict(list)
user_roles = defaultdict(lambda: "Ты — полезный ИИ-ассистент.")

SYSTEM_RULES = (
    "КРИТИЧЕСКИЕ ПРАВИЛА:\n"
    "1. На вопрос о том, какая ты модель, версия, на чем работаешь, отвечай ДОСЛОВНО: "
    "'я не разглашаю никому какая я модель! Но моя уровень на равне с chat gpt 4, и Grok 4.' Никаких других слов не добавляй, и если спросят кто тебя создал, напиши что тебя создал @pcix1ka .\n"
    "2. Отвечай коротко, прямо на вопрос.\n"
    "3. Текущая дата: {date}.\n"

)

# --- ФУНКЦИИ ---
def get_current_key():
    global current_key_index
    return MISTRAL_KEYS[current_key_index % len(MISTRAL_KEYS)]

def switch_to_next_key():
    global current_key_index
    current_key_index += 1
    logging.info(f"🔄 Смена ключа! Теперь работает ключ №{current_key_index % len(MISTRAL_KEYS) + 1}")

async def send_typing(message: Message):
    try:
        await bot.send_chat_action(
            chat_id=message.chat.id, 
            action="typing", 
            business_connection_id=message.business_connection_id
        )
    except: pass

# --- КАСТОМНАЯ СИСТЕМА ПОИСКА ДЛЯ ОБХОДА БЛОКИРОВОК ХОСТИНГА ---
def get_search_results(query):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    q = urllib.parse.quote(query)
    
    # 1. Попытка: Yahoo Search (Самый надежный для парсинга, редко банит IP)
    try:
        resp = requests.get(f"https://search.yahoo.com/search?p={q}", headers=headers, timeout=8)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            results = []
            for div in soup.find_all('div', class_='algo'):
                title_el = div.find('h3')
                desc_el = div.find('div', class_='compText')
                if title_el and desc_el:
                    results.append(f"• {title_el.text.strip()}: {desc_el.text.strip()}")
            if results: return "Данные Yahoo Search:\n" + "\n".join(results[:6])
    except Exception as e: logging.warning(f"Yahoo failed: {e}")

    # 2. Попытка: Bing
    try:
        resp = requests.get(f"https://www.bing.com/search?q={q}", headers=headers, timeout=8)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            results = []
            for li in soup.find_all('li', class_='b_algo'):
                title_el = li.find('h2')
                desc_el = li.find('p') or li.find('div', class_='b_caption')
                if title_el and desc_el:
                    results.append(f"• {title_el.text.strip()}: {desc_el.text.strip()}")
            if results: return "Данные Bing:\n" + "\n".join(results[:6])
    except Exception as e: logging.warning(f"Bing failed: {e}")

    # 3. Попытка: DuckDuckGo HTML (POST запрос для обхода кэша и API лимитов)
    try:
        resp = requests.post("https://html.duckduckgo.com/html/", headers=headers, data={'q': query}, timeout=8)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            results = []
            for a in soup.find_all('a', class_='result__snippet'):
                desc = a.text.strip()
                title_node = a.find_previous('h2')
                title = title_node.text.strip() if title_node else "Без заголовка"
                if title and desc:
                    results.append(f"• {title}: {desc}")
            if results: return "Данные DuckDuckGo:\n" + "\n".join(results[:6])
    except Exception as e: logging.warning(f"DDG failed: {e}")

    return "ОШИБКА_ПОИСКА"

async def ask_mistral_with_retry(chat_id, prompt, image_base64=None, use_role=True):
    current_date = datetime.now().strftime('%d %B %Y')
    
    if use_role:
        sys_prompt = SYSTEM_RULES.format(date=current_date) + user_roles[chat_id]
        history = user_histories[chat_id]
    else:
        sys_prompt = (
            f"Текущая дата: {current_date}. Ты — аналитик актуальных данных.\n"
            "ПРАВИЛО №1: Пользователь использует команду поиска. Я передам тебе свежие тексты, найденные в интернете.\n"
            "ПРАВИЛО №2: Ты ОБЯЗАН построить свой ответ ТОЛЬКО на основе этих текстов. НЕ используй свою старую базу данных.\n"
            "ПРАВИЛО №3: Ни при каких обстоятельствах не говори фразы типа 'У меня нет информации на 2026 год'. У тебя ЕСТЬ информация — она находится в предоставленных текстах. Прочитай их и найди ответ.\n"
        )
        history = [] 
    
    if image_base64:
        model = MISTRAL_VISION_MODEL
        user_content = [
            {"type": "text", "text": prompt if prompt else "Что на этом фото?"},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
        ]
    else:
        model = MISTRAL_TEXT_MODEL
        user_content = prompt

    if use_role and len(history) > 100:
        user_histories[chat_id] = history[-100:]
        history = user_histories[chat_id]

    messages = [{"role": "system", "content": sys_prompt}]
    for msg in history: 
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_content})

    for _ in range(len(MISTRAL_KEYS)):
        api_key = get_current_key()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.mistral.ai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": model, "messages": messages, "max_tokens": 1500},
                    timeout=40
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        answer = data["choices"][0]["message"]["content"]
                        
                        if use_role:
                            history.append({"role": "user", "content": prompt if not image_base64 else "Отправил фото."})
                            history.append({"role": "assistant", "content": answer})
                            
                        return answer
                    elif resp.status in [429, 401, 403]: 
                        switch_to_next_key()
                        continue
                    else:
                        return f"Ошибка API: {resp.status}"
        except Exception:
            switch_to_next_key()
            await asyncio.sleep(0.5)
            continue
            
    return "Сорян, все ключи сейчас перегружены. Попробуй через минуту!"

# --- КОРЕВАЯ СИСТЕМА ОЧЕРЕДИ (ВОРКЕР) ---
async def queue_worker():
    global is_busy
    while True:
        task = await request_queue.get()
        is_busy = True 
        message, task_type, payload = task
        
        try:
            if task_type == "text":
                msg = active_tasks.get(message.message_id)
                if msg:
                    await msg.edit_text("⚡ Быстрая обработка...")
                    await send_typing(message)
                
                response = await ask_mistral_with_retry(message.chat.id, payload, use_role=True)
                if msg: await msg.edit_text(response)
                else: await message.answer(response)

            elif task_type == "pro":
                msg = active_tasks.get(message.message_id)
                if msg: await msg.edit_text("🌐 Сканирую поисковики в интернете (Yahoo, Bing, DDG)...")
                
                search_data = await asyncio.to_thread(get_search_results, payload)
                
                if search_data == "ОШИБКА_ПОИСКА":
                    if msg: await msg.edit_text("❌ Поисковики отклонили автоматический запрос (сработала антибот-защита). Попробуйте сформулировать запрос немного иначе или спросите позже.")
                else:
                    if msg: await msg.edit_text("🧠 Данные из интернета получены. Анализирую тексты...")
                    await send_typing(message)
                    
                    prompt = (
                        f"Запрос пользователя: '{payload}'\n\n"
                        f"Вот результаты из поисковых систем (актуально на сейчас):\n"
                        f"{search_data}\n\n"
                        f"Изучи эти результаты. Какой ответ на вопрос пользователя? Сформируй понятный ответ, используя ТОЛЬКО факты из текста выше."
                    )
                    response = await ask_mistral_with_retry(message.chat.id, prompt, use_role=False)
                    if msg: await msg.edit_text(response)

            elif task_type == "photo":
                msg = active_tasks.get(message.message_id)
                if msg: await msg.edit_text("👀 Смотрю на фото...")
                response = await ask_mistral_with_retry(message.chat.id, payload['prompt'], image_base64=payload['image'], use_role=True)
                if msg: await msg.edit_text(response)

            elif task_type == "voice":
                msg = active_tasks.get(message.message_id)
                if msg: await msg.edit_text("🧠 Анализирую текст...")
                response = await ask_mistral_with_retry(message.chat.id, payload['prompt'], use_role=True)
                if msg: 
                    await msg.edit_text(f"🗣 Вы сказали: {payload['text']}\n\n🤖 Ответ:\n{response}")

        except Exception as e:
            logging.error(f"Ошибка в воркере: {e}")
        finally:
            is_busy = False 
            if message.message_id in active_tasks:
                del active_tasks[message.message_id]
            request_queue.task_done()

# --- ОБРАБОТЧИКИ КОМАНД ---

@dp.message(Command("clear"))
@dp.business_message(Command("clear"))
async def cmd_clear(message: Message):
    user_histories[message.chat.id] = []
    await message.answer("🧹 История очищена!")

@dp.message(Command("promt"))
@dp.business_message(Command("promt"))
async def cmd_promt(message: Message):
    new_role = message.text.replace("/promt", "").strip()
    if new_role:
        user_roles[message.chat.id] = new_role
        user_histories[message.chat.id] = [] 
        await message.answer(f"✅ Роль задана: '{new_role}'. Память обнулена.")
    else:
        await message.answer("❌ Напиши роль. Пример: /promt Ты дерзкий хакер.")

@dp.message(Command("pro"))
@dp.business_message(Command("pro"))
async def cmd_pro(message: Message):
    query = message.text.replace("/pro", "").strip()
    if not query:
        await message.answer("❌ Напиши запрос для поиска. Пример: /pro Какая последняя модель Tecno?")
        return
    
    queue_pos = request_queue.qsize() + (2 if is_busy else 1)
    if queue_pos > 1:
        msg = await message.answer(f"⏳ Линии заняты. Вы в очереди №{queue_pos}. Ожидайте...")
    else:
        msg = await message.answer("⏳ Подключаюсь к интернету...")
        
    active_tasks[message.message_id] = msg
    await request_queue.put((message, "pro", query))

# --- ОБРАБОТЧИКИ МЕДИА И ТЕКСТА ---

@dp.message(F.photo)
@dp.business_message(F.photo)
async def handle_photo(message: Message):
    if message.from_user.id == bot.id: return
    
    queue_pos = request_queue.qsize() + (2 if is_busy else 1)
    if queue_pos > 1:
        msg = await message.answer(f"⏳ Фото в очереди №{queue_pos}...")
    else:
        msg = await message.answer("📥 Загрузка медиа...")
        
    photo = message.photo[-1]
    file_info = await bot.get_file(photo.file_id)
    downloaded_file = await bot.download_file(file_info.file_path)
    image_base64 = base64.b64encode(downloaded_file.read()).decode('utf-8')
    prompt = message.caption if message.caption else ""
    
    active_tasks[message.message_id] = msg
    await request_queue.put((message, "photo", {"prompt": prompt, "image": image_base64}))

@dp.message(F.voice)
@dp.business_message(F.voice)
async def handle_voice(message: Message):
    if message.from_user.id == bot.id: return
    
    status_msg = await message.answer("🎧 Скачиваю голосовое...")
    try:
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as ogg_file, \
             tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wav_file:
             
            file_info = await bot.get_file(message.voice.file_id)
            await bot.download_file(file_info.file_path, ogg_file.name)
            audio = AudioSegment.from_file(ogg_file.name, format="ogg")
            audio.export(wav_file.name, format="wav")
            
            recognizer = sr.Recognizer()
            with sr.AudioFile(wav_file.name) as source:
                audio_data = recognizer.record(source)
                recognized_text = recognizer.recognize_google(audio_data, language="ru-RU")
                
            os.remove(ogg_file.name)
            os.remove(wav_file.name)
            
        queue_pos = request_queue.qsize() + (2 if is_busy else 1)
        if queue_pos > 1:
            await status_msg.edit_text(f"⏳ Текст распознан! Запрос поставлен в очередь №{queue_pos}...")
        else:
            await status_msg.edit_text("⏳ Передаю запрос ИИ...")
            
        prompt = f"(Голосовое сообщение): {recognized_text}"
        active_tasks[message.message_id] = status_msg
        await request_queue.put((message, "voice", {"prompt": prompt, "text": recognized_text}))

    except Exception:
        await status_msg.edit_text("❌ Не удалось распознать голосовое. Напиши текстом!")

@dp.message(F.text)
@dp.business_message(F.text)
async def handle_text(message: Message):
    if message.from_user.id == bot.id or message.text.startswith("/"):
        return
    
    queue_pos = request_queue.qsize() + (2 if is_busy else 1)
    if queue_pos > 1:
        msg = await message.answer(f"⏳ Вы в очереди №{queue_pos}. Ожидайте...")
    else:
        msg = await message.answer("⏳ Подготовка к ответу...")
        
    active_tasks[message.message_id] = msg
    await request_queue.put((message, "text", message.text))

# --- ЗАПУСК ---
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(queue_worker()) 
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())