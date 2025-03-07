from config import DEFAULT_COMMANDS
from telebot.custom_filters import StateFilter
from telebot.types import BotCommand
from handler_worker import bot
from models import create_models

if __name__ == '__main__':
    create_models()
    bot.add_custom_filter(StateFilter(bot))
    bot.set_my_commands([BotCommand(*cmd) for cmd in DEFAULT_COMMANDS])
    bot.polling()
