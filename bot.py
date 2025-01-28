import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters.command import Command
from config import TOKEN
import requests
from aiogram.types import Update
from aiogram.dispatcher.middlewares.base import BaseMiddleware
import logging

# Включаем логирование, чтобы не пропустить важные сообщения
logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Подключаем middleware
class LoggingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user_id = None
        message_text = None

        if isinstance(event, types.Message):
            user_id = event.from_user.id
            message_text = event.text
        elif isinstance(event, types.CallbackQuery):
            user_id = event.from_user.id
            message_text = event.data

        logging.info(f"Пользователь ID: {user_id}, Сообщение: {message_text}")
        return await handler(event, data)

dp.message.middleware(LoggingMiddleware())

users = {}

# Функция для подсчета нормы воды
def water_level(weight, activity, temperature):
    base_water = weight * 30
    activity_water = 500 * (activity // 30)
    temperature_water = 800 if temperature > 25 else 0
    return base_water + activity_water + temperature_water

# Функция для подсчета калорий
def calorie_level(weight, height, age, activity):
    base_calorie = 10 * weight + 6.25 * height - 5 * age + 5
    activity_calorie = (activity // 30) * 100
    return base_calorie + activity_calorie

def get_lat_lon(city):
    api_key = '2bbf71791159863c390f044fa06313b0'
    url = f'http://api.openweathermap.org/geo/1.0/direct?q={city}&appid={api_key}'

    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        if not data:  
            logging.error(f"Город '{city}' не найден")
            return None, "Город не найден"  
        lat = data[0].get('lat')
        lon = data[0].get('lon')

        if lat is None or lon is None:  
            logging.error(f"Координаты для '{city}' не найдены в API")
            return None, "Ошибка получения координат" 

        return lat, lon  

    except requests.RequestException as e:
        logging.error(f"Ошибка при получении координат: {e}")
        return None  


# Получение температуры в городе
def get_temperature(city):
    api_key = '2bbf71791159863c390f044fa06313b0'
    coords = get_lat_lon(city)

    if coords is None:  
        logging.warning(f"Возникла ошибка. Используется дефолтное значение температуры.")
        return 20  

    lat, lon = coords  
    url = f'http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=metric'

    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return data['main']['temp']
    except Exception as e:
        logging.error(f"Ошибка при получении температуры: {e}")
        return 20   
 
'''
Хендлеры
'''

# Хэндлер на команду /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer('Добро пожаловать! Настройте профиль с помощью команды /set_profile')

# Хендлер на команду /log_water
@dp.message(Command("log_water"))
async def log_water(message: types.Message):
    logging.info(f"Обработчик команды /log_water вызван: {message.text}")
    chat_id = message.chat.id
    if chat_id not in users:
        await message.reply("Сначала настройте профиль с помощью команды /set_profile.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("Пожалуйста, укажите количество воды в миллилитрах. Например: /log_water 500")
        return

    try:
        amount = int(args[1])
        users[chat_id]['logged_water'] += amount
        remaining = users[chat_id]['water_goal'] - users[chat_id]['logged_water']
        await message.reply(f"Вы выпили {amount} мл воды. Осталось: {remaining} мл.")
    except ValueError:
        await message.reply("Пожалуйста, вводите только числа!")

# Хендлер на команду /log_workout
@dp.message(Command("log_workout"))
async def log_workout(message: types.Message):
    chat_id = message.chat.id
    if chat_id not in users:
        await message.reply("Сначала настройте профиль с помощью команды /set_profile.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("Пожалуйста, укажите тип тренировки и длительность. Например: /log_workout бег 30")
        return

    try:
        workout, time = args[1].split()
        # тут можно еще подумать как оценивать разные типы активности
        time = int(time)
        burned_calories = (time // 30) * 200
        users[chat_id]['burned_calories'] += burned_calories
        extra_water = (time // 30) * 200
        await message.reply(f"Вы сожгли {burned_calories} ккал. Дополнительно выпейте {extra_water} мл воды.")
    except ValueError:
        await message.reply("Пожалуйста, укажите корректное время (в минутах).")

# Хендлер на команду /log_food
@dp.message(Command("log_food"))
async def log_food(message: types.Message):
    
    chat_id = message.chat.id
    if chat_id not in users:
        await message.reply("Сначала настройте профиль с помощью команды /set_profile.")
        return

    command_parts = message.text.split(maxsplit=1)
    if len(command_parts) < 2:
        await message.reply("Пожалуйста, укажите название продукта на английском. Например: /log_food apple")
        return

    product_name = command_parts[1].strip().lower()

    try:

        url = f"https://world.openfoodfacts.org/cgi/search.pl?search_terms={product_name}&fields=product_name,nutriments&json=1"
        response = requests.get(url)
        logging.info(f"Ответ от OpenFoodFacts: {response.text}")
        response.raise_for_status()
        data = response.json()

        if not data.get('products'):
            await message.reply(f"Продукт с названием '{product_name}' не найден.")
            return

        first_product = data['products'][0]
        product_name = first_product.get('product_name', 'Неизвестный продукт')
        calories = first_product.get('nutriments', {}).get('energy-kcal_100g')

        if not calories:
            await message.reply(f"Калорийность для продукта '{product_name}' не найдена.")
            return

        users[chat_id]['calories_per_100g'] = calories
        users[chat_id]['awaiting_grams'] = True
        await message.reply(f"{product_name.capitalize()} содержит {calories} ккал на 100 г. Сколько грамм вы съели?")

    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка при запросе к OpenFoodFacts: {e}")
        await message.reply("Не удалось получить информацию о продукте. Проверьте название или повторите попытку позже.")
    except Exception as e:
        logging.error(f"Неожиданная ошибка: {e}")
        await message.reply("Произошла ошибка. Пожалуйста, попробуйте ещё раз.")

@dp.message(Command('log_workout'))
async def log_workout(message: types.Message):
    chat_id = message.chat.id
    if chat_id not in users:
        await message.reply("Сначала настройте профиль с помощью команды /set_profile.")
        return

    args = message.get_args().split()
    if len(args) < 2:
        await message.reply("Пожалуйста, укажите тип тренировки и длительность (в минутах). Например: /log_workout бег 30")
        return

    workout, time = args[0], int(args[1])
    burned_calories = (time // 30) * 200
    users[chat_id]['burned_calories'] += burned_calories
    extra_water = (time // 30) * 200
    await message.reply(f"Вы сожгли {burned_calories} ккал. Дополнительно выпейте {extra_water} мл воды.")

@dp.message(Command('check_progress'))
async def check_progress(message: types.Message):
    chat_id = message.chat.id
    if chat_id not in users:
        await message.reply("Сначала настройте профиль с помощью команды /set_profile.")
        return

    user = users[chat_id]
    remaining_water = user['water_goal'] - user['logged_water']
    remaining_calories = user['calorie_goal'] - user['logged_calories']

    water_progress = (
        f"Выпито: {user['logged_water']} мл из {user['water_goal']} мл.\n"
        f"Осталось выпить: {remaining_water} мл."
    )
    calorie_progress = (
        f"Потреблено: {user['logged_calories']} ккал из {user['calorie_goal']} ккал.\n"
        f"Осталось съесть: {remaining_calories} ккал."
    )
    burned_calories = f"Сожжено: {user['burned_calories']} ккал."

    await message.reply(f"📊 Прогресс:\n{water_progress}\n{calorie_progress}\n{burned_calories}")


# Хендлер для команды /set_profile
@dp.message(Command("set_profile"))
async def set_profile(message: types.Message):
    chat_id = message.chat.id
    users[chat_id] = {}  
    await message.reply("Введите ваш вес (в кг):")
    users[chat_id]['step'] = 'weight'

# Общий хендлер для обработки некоторых шагов
@dp.message()
async def unified_handler(message: types.Message):
    chat_id = message.chat.id

    if message.text.startswith("/"):
        return
    
    # Проверяем, находится ли пользователь на шаге заполнения съеденной еды
    if chat_id in users and users[chat_id].get('awaiting_grams'):
        try:
            grams = int(message.text)
            calories_per_100g = users[chat_id]['calories_per_100g']
            total_calories = (calories_per_100g * grams) / 100

            if 'logged_calories' not in users[chat_id]:
                users[chat_id]['logged_calories'] = 0
            users[chat_id]['logged_calories'] += total_calories

            calorie_goal = users[chat_id].get('calorie_goal', 0)
            remaining_calories = calorie_goal - users[chat_id]['logged_calories']

            users[chat_id].pop('awaiting_grams', None)
            users[chat_id].pop('calories_per_100g', None)

            await message.reply(
                f"Записано: {total_calories:.2f} ккал.\n"
                f"Осталось: {remaining_calories:.2f} ккал до выполнения цели."
            )
        except ValueError:
            await message.reply("Пожалуйста, введите количество граммов числом.")
        return
    
    # Проверяем, находится ли пользователь на шаге заполнения профиля
    if chat_id in users and 'step' in users[chat_id]:
        step = users[chat_id]['step']
        text = message.text

        try:
            if step == 'weight':
                users[chat_id]['weight'] = int(text)
                await message.reply("Введите ваш рост (в см):")
                users[chat_id]['step'] = 'height'
            elif step == 'height':
                users[chat_id]['height'] = int(text)
                await message.reply("Введите ваш возраст:")
                users[chat_id]['step'] = 'age'
            elif step == 'age':
                users[chat_id]['age'] = int(text)
                await message.reply("Сколько минут активности у вас в день?")
                users[chat_id]['step'] = 'activity'
            elif step == 'activity':
                users[chat_id]['activity'] = int(text)
                await message.reply("В каком городе вы находитесь?")
                users[chat_id]['step'] = 'city'
            elif step == 'city':
                users[chat_id]['city'] = text

                temperature = get_temperature(text)
                weight = users[chat_id]['weight']
                activity = users[chat_id]['activity']
                users[chat_id]['water_goal'] = water_level(weight, activity, temperature)
                height = users[chat_id]['height']
                age = users[chat_id]['age']
                users[chat_id]['calorie_goal'] = calorie_level(weight, height, age, activity)

                users[chat_id]['logged_water'] = 0
                users[chat_id]['logged_calories'] = 0
                users[chat_id]['burned_calories'] = 0

                await message.reply(
                    f"Профиль настроен! Ваша дневная норма воды: {users[chat_id]['water_goal']} мл, "
                    f"калорий: {users[chat_id]['calorie_goal']} ккал."
                )
                del users[chat_id]['step']
        except ValueError:
            await message.reply("Пожалуйста, вводите только числа!")
        return
    await message.reply("Я не понимаю это сообщение. Используйте команды, чтобы начать.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

