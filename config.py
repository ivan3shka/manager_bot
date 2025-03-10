import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
if BOT_TOKEN is None:
    exit('BOT_TOKEN отсутствует в переменных окружения')

DEFAULT_COMMANDS = (
    ('start', 'Начать с начала'),
)

DB_PATH = os.getenv("DB_PATH", "data/database.db")

# Получаем папку, где должна быть БД
DB_DIR = os.path.dirname(DB_PATH)

# Если путь относительный, создаём папку в текущем каталоге
if not os.path.isabs(DB_PATH):
    DB_DIR = os.path.join(os.getcwd(), DB_DIR)

# Создаём папку, если её нет
os.makedirs(DB_DIR, exist_ok=True)
