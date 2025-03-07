import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
if BOT_TOKEN is None:
    exit('BOT_TOKEN отсутствует в переменных окружения')

DEFAULT_COMMANDS = (
    ('start', 'Начать с начала'),
)

DB_PATH = os.getenv("DB_PATH", "/app/data/database.db")


