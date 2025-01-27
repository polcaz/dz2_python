import os
from dotenv import load_dotenv

# Загрузка переменных из .env файла
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")