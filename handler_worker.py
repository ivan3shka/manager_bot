from config import BOT_TOKEN
import datetime
from telebot.types import (
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from peewee import IntegrityError, State
from models import UserWorker, UserManager, Task
from telebot import StateMemoryStorage, TeleBot
from states import UserState
from telebot.types import Message
import logging


state_storage = StateMemoryStorage()
bot = TeleBot(BOT_TOKEN, state_storage=state_storage)


logger = logging.getLogger('manager_bot_logger')
logger.setLevel(logging.DEBUG)

info_handler = logging.FileHandler('info.log')
info_handler.setLevel(logging.INFO)

error_handler = logging.FileHandler('errors.log')
error_handler.setLevel(logging.ERROR)

formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s - %(filename)s'
    ' - Line: %(lineno)d', '%H:%M')
info_handler.setFormatter(formatter)
error_handler.setFormatter(formatter)


class InfoFilter(logging.Filter):
    def filter(self, record):
        return record.levelno < logging.ERROR


info_handler.addFilter(InfoFilter())

logger.addHandler(info_handler)
logger.addHandler(error_handler)


def error_handler(func):
    def wrapper(message: Message):
        try:
            return func(message)
        except Exception as e:
            logger.error(f'Ошибка: {e}')
            bot.reply_to(message, 'Что-то пошло не так.\n '
                                  'Попробуйте перезапустить с помощью /start.')
    return wrapper


def error_handler_callback(func):
    def wrapper(callback):
        try:
            return func(callback)
        except Exception as e:
            logger.error(f'Ошибка: {e}')
            bot.send_message(callback.from_user.id,
                             'Что-то пошло не так.'
                             '\nПопробуйте перезапустить с помощью /start.')
    return wrapper


@bot.message_handler(commands=['start'])
@error_handler
def handle_start(message: Message) -> None:
    """Запуск бота. Узнаем роль сотрудника"""

    logger.info(f'Команда /start от пользователя: {message.from_user.id}')
    bot.send_message(message.chat.id, 'Добро пожаловать!\n'
                                      'Выберите свою роль:',
                     reply_markup=gen_buttons_role())

    bot.set_state(message.from_user.id, UserState.choose_role)


@bot.callback_query_handler(
    func=lambda callback: callback.data in ['menu'])
@error_handler_callback
def handler_back_to_manager_menu(callback) -> None:
    """Возращение в меню"""
    logger.info(f'Возврат в меню пользователя: {callback.from_user.id}')
    bot.set_state(callback.from_user.id, UserState.to_do_manager)
    bot.edit_message_reply_markup(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id
    )
    handle_manager_to_do(callback.message)


def gen_buttons_role():
    """Создаём кнопки дял выбора роли."""
    logger.debug('Генерация кнопок для выбора роли')
    manager = InlineKeyboardButton(
        text='🧑Менеджер ',
        callback_data='manager',
    )
    worker = InlineKeyboardButton(
        text='🧑‍💻Исполнитель',
        callback_data='worker',
    )

    keyboard = InlineKeyboardMarkup()
    keyboard.add(manager)
    keyboard.add(worker)
    return keyboard


@bot.callback_query_handler(state=UserState.choose_role,
                            func=lambda callback: callback.data in ['manager'])
@error_handler_callback
def handle_role(callback) -> None:
    """Пользователь выбрал роль - manager. Запрашиваем имя"""

    logger.info(f'Выбор роли менеджера пользователем: {callback.from_user.id}')
    bot.send_message(callback.from_user.id,
                     'Теперь введите своё имя и фамилию:',
                     reply_markup=ReplyKeyboardRemove())
    bot.edit_message_reply_markup(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id
    )
    bot.set_state(callback.from_user.id, UserState.name_manager)


@bot.message_handler(state=UserState.name_manager)
@error_handler
def handle_data(message: Message) -> None:
    """Узнали имя. Заполняем таблицу данными"""

    logger.info(f'Заполняем таблицу данными для пользователя:'
                f' {message.from_user.id}')
    user_id = message.from_user.id
    user_name = message.text

    try:
        user = UserManager.get_or_none(UserManager.user_id == user_id)
        if user is None:
            UserManager.create(
                user_id=user_id,
                user_name=user_name,
                id_task=0
            )
            bot.send_message(
                message.chat.id,
                'Регистрация прошла успешно!',
                reply_markup=ReplyKeyboardRemove()
            )
        else:
            bot.reply_to(
                message,
                f'Рад вас снова видеть, {user.user_name}!',
                reply_markup=ReplyKeyboardRemove()
            )
        bot.set_state(message.chat.id, UserState.to_do_manager)
        handle_manager_to_do(message)

    except IntegrityError as e:
        print(f'ValueError: {e}')
        bot.reply_to(message,
                     'Ошибка регистрации. Попробуйте с самого начала - '
                     '/start')


@bot.message_handler(state=UserState.to_do_manager)
@error_handler
def handle_manager_to_do(message: Message) -> None:
    """Менеджер выбирает действие"""

    logger.info(f'{message.from_user.id} Менеджер выбирает действие')
    bot.send_message(message.chat.id,
                     'Выберите действие',
                     reply_markup=gen_buttons_manager_to_do())


def gen_buttons_manager_to_do():
    """Функция кнопок выбора действия для менеджера"""
    new_task = InlineKeyboardButton(
        text='💡Назначить работу',
        callback_data='new_task',
    )
    task_list = InlineKeyboardButton(
        text='📑Смотреть список работ',
        callback_data='task_list_manager',
    )
    report = InlineKeyboardButton(
        text='📊Смотреть отчет',
        callback_data='report',
    )

    keyboard = InlineKeyboardMarkup()
    keyboard.add(new_task)
    keyboard.add(task_list)
    keyboard.add(report)
    return keyboard


@bot.callback_query_handler(
    func=lambda callback: callback.data in ['new_task', 'end_circle'])
@error_handler_callback
def handler_new_task_name(callback) -> None:
    """Узнаем имя для задачи"""

    logger.info(f'Запрашиваем имя задачи у {callback.from_user.id}')
    if callback.data == 'end_circle':
        handle_manager_to_do(callback.message)
    else:
        bot.send_message(callback.from_user.id,
                         '✍️Введите название работы',
                         )
        bot.set_state(callback.from_user.id, UserState.task_name)
    bot.edit_message_reply_markup(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id
    )


@bot.message_handler(state=UserState.task_name)
@error_handler
def handler_info_for_task(message: Message) -> None:
    """Создаём задачу в б/д. Узнаем информацию для задачи"""

    logger.info('Создаём задачу в б/д. Узнаем информацию для задачи')
    new_task_name = message.text
    manager_id = message.chat.id
    worker = UserWorker.get()
    Task.create(
        task_name=new_task_name,
        id_worker=worker.user_id,
        id_manager=manager_id,
        date_start='',
        date_finish='',
        status='process'
    )
    bot.send_message(message.chat.id,
                     "📋Добавьте файл/информацию к задаче:", )
    bot.set_state(message.chat.id, UserState.forward_to_worker)

@bot.message_handler(state=UserState.forward_to_worker,
                     content_types=['photo', 'document', 'text'])
@error_handler
def forward_message_task_to_worker(message: Message) -> None:
    """Получаем файл у менеджера и пересылаем его воркеру"""

    logger.info('Получаем файл у менеджера и пересылаем его воркеру')
    worker = UserWorker.get()
    worker_id = worker.user_id
    if message.content_type == 'document':
        bot.send_document(worker_id, message.document.file_id)
    elif message.content_type == 'photo':
        bot.send_photo(worker_id, message.photo[0].file_id)
    elif message.content_type == 'text':
        bot.send_message(worker_id, message.text)
    else:
        bot.send_message(worker_id,
                         'Произошла ошибка при пересылки сообщения')
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(
        text='Добавить ещё файл/информацию',
        callback_data='send_more',
    ))
    markup.add(InlineKeyboardButton(
        text='Отправить задачу исполнителю',
        callback_data='send',
    ))
    bot.send_message(message.chat.id,
                     'Выберите действие: ',
                     reply_markup=markup)
    return

@bot.callback_query_handler(
    func=lambda callback: callback.data in ['send', 'send_more'])
@error_handler_callback
def handler_send_or_send_more_to_worker(callback) -> None:
    """Отправляем задачу, либо получаем ещё файл"""

    logger.info('')
    if callback.data == 'send':
        bot.edit_message_reply_markup(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id
        )
        bot.set_state(callback.from_user.id, UserState.info_for_task)
        handle_new_task_send_to_worker(callback.message)
    else:
        bot.send_message(callback.from_user.id,
                         "📋Добавьте файл/информацию к задаче:", )
        bot.edit_message_reply_markup(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id
        )
        bot.set_state(callback.from_user.id, UserState.forward_to_worker)



@bot.message_handler(state=UserState.info_for_task)
@error_handler
def handle_new_task_send_to_worker(message: Message) -> None:
    """"""

    logger.info('')

    manager_id = message.from_user.id
    id_manager = Task.id_manager
    status = Task.status
    task = Task.get((id_manager == manager_id) &
                    (status == 'process'))

    manager = UserManager.get(UserManager.user_id == manager_id)
    bot.send_message(task.id_worker,
                     f'📩Новая задача "{task.task_name}"\n от: '
                     f' {manager.user_name}!')

@bot.message_handler(state=UserState.info_for_task_1)
@error_handler
def handle_new_task_send_to_worker(message: Message) -> None:
    """Отправляем задачу воркеру"""

    logger.info('Отправляем задачу воркеру')

    manager_id = message.chat.id
    task = Task.get((Task.id_manager == manager_id) &
                    (Task.status == 'process'))
    manager = UserManager.get(UserManager.user_id == manager_id)

    bot.send_message(task.id_worker,
                     f'📩Новая задача "{task.task_name}"\n от: '
                     f' {manager.user_name}!')

    bot.send_message(message.chat.id, '🚀Задача успешно отправлена!')
    handle_accept_question_to_worker(message)
    bot.set_state(message.chat.id, UserState.to_do_manager)
    handle_manager_to_do(message)


@bot.message_handler(state=UserState.fin_task_id)
@error_handler
def handle_accept_question_to_worker(message: Message) -> None:
    """Спрашиваем worker принять работу или нет."""

    logger.info('Спрашиваем worker принять работу или нет.')

    task = Task.get((Task.id_manager == message.chat.id) &
                    (Task.status == 'process'))
    bot.send_message(task.id_worker,
                     'Принять работу?',
                     reply_markup=gen_buttons_finish_or_stop())


def gen_buttons_finish_or_stop():
    """Функция кнопки принять работу"""

    logger.info('')
    yes = InlineKeyboardButton(
        text='✅',
        callback_data='accept',
    )

    keyboard = InlineKeyboardMarkup()
    keyboard.add(yes)
    return keyboard


@bot.message_handler(state=UserState.worker_end_task)
@error_handler
def handle_accept_question_to_worker(message: Message) -> None:
    """Спрашиваем worker принять работу или нет."""

    logger.info('Спрашиваем worker принять работу или нет')

    id_manager = Task.id_manager
    task = Task.get((id_manager == message.chat.id) &
                    (Task.status == 'process'))
    bot.send_message(task.id_worker,
                     'Принять работу?',
                     reply_markup=gen_buttons_finish_or_stop())


@bot.callback_query_handler(
    func=lambda callback: callback.data in ['task_list_manager'])
@error_handler_callback
def handler_task_list_to_manager(callback) -> None:
    """Узнаем, какие работы хочет увидеть пользователь."""

    logger.info('Узнаем, какие работы хочет увидеть пользователь.')

    bot.send_message(callback.from_user.id,
                     'Какие задачи хотите увидеть?',
                     reply_markup=gen_buttons_tip_of_tasks()
                     )
    bot.edit_message_reply_markup(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id
    )

def gen_buttons_tip_of_tasks():
    """
    Создаём кнопки дял выбора типа заданий
    all - Все
    status - Работы в определённом статусе
    time - Работы за временной промежуток
    worker - Работы одного исполнителя
    """

    logger.info('Создаём кнопки дял выбора типа заданий'
    'all - Все'
    'status - Работы в определённом статусе'
    'time - Работы за временной промежуток'
    'worker - Работы одного исполнителя')

    all_tasks = InlineKeyboardButton(
        text='Все задания',
        callback_data='all',
    )
    status_task = InlineKeyboardButton(
        text='В определённом статусе',
        callback_data='status',
    )
    menu = InlineKeyboardButton(
        text='Вернуться в меню',
        callback_data='menu',
    )

    keyboard = InlineKeyboardMarkup()
    keyboard.add(all_tasks)
    keyboard.add(status_task)
    keyboard.add(menu)

    return keyboard


@bot.callback_query_handler(state=UserState.chose_task_info_id_manager)
@error_handler_callback
def handler_task_list_to_manager_send(callback) -> None:
    """Отправляем информацию конкретной задачи"""

    logger.info('Отправляем информацию конкретной задачи')

    task = Task.get(Task.task_id == callback.data)
    worker = UserWorker.get(task.id_worker == UserWorker.user_id)
    date_finish = task.date_finish
    status = task.status
    date_start = task.date_start

    if status == 'finishing':
        status = 'Исполнитель завершает и вот-вот отправит задание'
        date_finish = 'Работа не завершена'
    elif status == 'process':
        status = 'Исполнитель ещё не принял работу'
        date_start = 'Работа не начата'
        date_finish = 'Работа не завершена'
    elif status == 'work':
        status = 'Исполнитель работает над задачей'
        date_finish = 'Работа не завершена'
    elif status == 'finish':
        status = 'Работа завершена'

    bot.send_message(callback.from_user.id,
                     f'Имя работы: \n{task.task_name}\n\n'
                     f'🧑‍💻Исполнитель: \n{worker.user_name}\n\n'
                     f'📆Дата начала работы: \n{date_start}\n\n'
                     f'Статус: \n{status}\n\n'
                     f'📆Дата завершения работы: \n{date_finish}')

    bot.edit_message_reply_markup(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id
    )
    bot.set_state(callback.from_user.id, UserState.to_do_manager)
    handle_manager_to_do(callback.message)


@bot.message_handler(state=UserState.chose_times_borders_status)
@error_handler
def handler_task_list_to_manager_ask_status(message) -> None:
    """Узнаем, задания в каком статусе нужны"""

    logger.info('Узнаем, задания в каком статусе нужны')

    time_borders = message.text
    bot.send_message(message.chat.id,
                     'Выберите в каком статусе',
                     reply_markup=gen_buttons_status_task(time_borders))
    bot.set_state(message.chat.id, UserState.send_task_status)


def gen_buttons_status_task(time_borders):
    """Создаем кнопки статусов, чтобы узнать какие задания отправлять"""

    logger.info(
        'Создаем кнопки статусов, чтобы узнать какие задания отправлять')

    work = InlineKeyboardButton(
        text='В работе (у исполнителя)',
        callback_data=f'work, {time_borders}',
    )
    finish = InlineKeyboardButton(
        text='Завершенные работы',
        callback_data=f'finish, {time_borders}',
    )
    menu = InlineKeyboardButton(
        text='Вернуться в меню',
        callback_data='menu',
    )

    keyboard = InlineKeyboardMarkup()
    keyboard.add(work)
    keyboard.add(finish)
    keyboard.add(menu)
    return keyboard


@bot.callback_query_handler(state=UserState.send_task_status)
def handler_task_list_to_manager_time_status(callback) -> None:
    """Узнали отрезок времени. Запрашиваем статус"""

    logger.info('Узнали отрезок времени. Запрашиваем статус')

    tasks = []
    try:
        bot.edit_message_reply_markup(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id
        )
        status, borders = callback.data.split(', ')

        left_border, right_border = borders.split(' - ')

        left_date = datetime.datetime.strptime(left_border.strip(),
                                               '%d/%m/%Y')
        right_date = datetime.datetime.strptime(right_border.strip(),
                                                '%d/%m/%Y')

        for task in Task.select():
            if task.date_start == '':
                task_start_date = '12/12/1000'
            else:
                task_start_date = task.date_start
            task_start_date = datetime.datetime.strptime(task_start_date,
                                                         "%d/%m/%Y")
            if task.date_finish == '':
                task_finish_date = '12/12/9999'
            else:
                task_finish_date = task.date_finish
            task_finish_date = datetime.datetime.strptime(task_finish_date,
                                                          "%d/%m/%Y")
            if ((left_date <= task_start_date <= right_date or
                 left_date <= task_finish_date <= right_date)
                    and (task.status == status)):
                tasks.append(task)

        markup = InlineKeyboardMarkup()
        if tasks:
            bot.send_message(callback.from_user.id,
                             f'📋 Задачи в период:\n'
                             f'{left_border} - {right_border}')
            for task_i in tasks:
                markup.add(InlineKeyboardButton(
                    text=f'"{task_i.task_name}"',
                    callback_data=task_i.task_id,
                ))
            markup.add(InlineKeyboardButton(
                text='Вернуться в меню',
                callback_data='menu',
            ))
            bot.send_message(callback.from_user.id,
                             'Выберите, про какую прислать информацию',
                             reply_markup=markup)
            bot.set_state(callback.from_user.id,
                          UserState.chose_task_info_id_manager)
        else:
            bot.send_message(callback.from_user.id,
                             '❌ Нет задач за указанный период.')
            bot.set_state(callback.from_user.id, UserState.to_do_manager)
            handle_manager_to_do(callback.message)

    except ValueError as e:
        print(f'ValueError: {e}')
        bot.send_message(callback.from_user.id,
                         '❌Ошибка. Проверьте формат даты')

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(
            text='Вернуться в меню',
            callback_data='menu',
        ))
        bot.send_message(callback.from_user.id,
                         'Выберите действие: ',
                         reply_markup=markup)


@bot.callback_query_handler(
    func=lambda callback: callback.data in ['all', 'report', 'status'])
@error_handler_callback
def handler_task_list_to_manager_time_borders(callback) -> None:
    """Отправляем задачи за нужный отрезок времени. Узнаем периоды"""

    logger.info('Отправляем задачи за нужный отрезок времени. Узнаем периоды')

    today = datetime.date.today().strftime("%d/%m/%Y")
    random_day = datetime.date.today() - datetime.timedelta(days=30)
    random_day = random_day.strftime("%d/%m/%Y")
    bot.send_message(callback.from_user.id,
                     'Отправьте одним сообщением, дата начала - дата конца'
                     '\nВ формате: dd/mm/yyyy - dd/mm/yyyy\n\n'
                     f'Пример:\n{random_day} - {today}')
    bot.edit_message_reply_markup(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id
    )
    if callback.data in ['all']:
        bot.set_state(callback.from_user.id, UserState.chose_times_borders)
    elif callback.data in ['report']:
        bot.set_state(callback.from_user.id,
                      UserState.chose_times_borders_report)
    elif callback.data in ['status']:
        bot.set_state(callback.from_user.id,
                      UserState.chose_times_borders_status)


@bot.message_handler(state=UserState.chose_times_borders)
def handler_task_list_to_manager_time_all(message: Message) -> None:
    """Отправляем ВСЕ задачи за нужный отрезок времени"""

    logger.info('Отправляем ВСЕ задачи за нужный отрезок времени')

    tasks = []
    try:
        left_border, right_border = message.text.split(' - ')

        left_date = datetime.datetime.strptime(left_border.strip(),
                                               '%d/%m/%Y')
        right_date = datetime.datetime.strptime(right_border.strip(),
                                                '%d/%m/%Y')
        for task in Task.select():
            if task.date_start == '':
                task_start_date = '12/12/1000'
            else:
                task_start_date = task.date_start
            task_start_date = datetime.datetime.strptime(task_start_date,
                                                         "%d/%m/%Y")
            if task.date_finish == '':
                task_finish_date = '12/12/9999'
            else:
                task_finish_date = task.date_finish
            task_finish_date = datetime.datetime.strptime(task_finish_date,
                                                          "%d/%m/%Y")
            if (left_date <= task_start_date <= right_date or
                    left_date <= task_finish_date <= right_date):
                tasks.append(task)

        markup = InlineKeyboardMarkup()
        if tasks:
            bot.send_message(message.chat.id,
                             f'📋 Задачи в период:\n'
                             f'{left_border} - {right_border}')
            for task_i in tasks:
                if task_i.status == 'work':
                    status = 'В работе у исполнителя'
                elif task_i.status == 'finish':
                    status = 'Завершена'
                elif task_i.status == 'process':
                    status = 'Вы создаёте работу'
                else:
                    status = 'Неизвестный статус'
                markup.add(InlineKeyboardButton(
                    text=f'"{task_i.task_name}". {status}',
                    callback_data=task_i.task_id,
                ))
            markup.add(InlineKeyboardButton(
                text='Вернуться в меню',
                callback_data='menu',
            ))
            bot.send_message(message.chat.id,
                             'Выберите, про какую прислать информацию',
                             reply_markup=markup)
            bot.set_state(message.chat.id,
                          UserState.chose_task_info_id_manager)
        else:
            bot.send_message(message.chat.id,
                             '❌ Нет задач за указанный период.')
            bot.set_state(message.chat.id, UserState.to_do_manager)
            handle_manager_to_do(message)

    except ValueError as e:
        print(f'ValueError: {e}')
        bot.send_message(message.chat.id,
                         '❌Ошибка. Проверьте формат даты')

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(
            text='Вернуться в меню',
            callback_data='menu',
        ))
        markup.add(InlineKeyboardButton(
            text='Попробовать снова',
            callback_data='all',
        ))
        bot.send_message(message.chat.id,
                         'Выберите действие: ',
                         reply_markup=markup)


@bot.message_handler(state=UserState.chose_times_borders_report)
@error_handler
def handler_task_report(message: Message) -> None:
    """Отправляем ОТЧЕТ о работах"""

    logger.info('Отправляем ОТЧЕТ о работах')

    tasks_started = []
    tasks_finished = []

    left_border, right_border = message.text.split(' - ')

    left_date = datetime.datetime.strptime(left_border.strip(),
                                           '%d/%m/%Y')
    right_date = datetime.datetime.strptime(right_border.strip(),
                                            '%d/%m/%Y')
    for task in Task.select():
        if task.date_start == '':
            task_start_date = '12/12/1000'
        else:
            task_start_date = task.date_start
        task_start_date = datetime.datetime.strptime(task_start_date,
                                                     "%d/%m/%Y")
        if task.date_finish == '':
            task_finish_date = '12/12/9999'
        else:
            task_finish_date = task.date_finish
        task_finish_date = datetime.datetime.strptime(task_finish_date,
                                                      "%d/%m/%Y")
        if left_date <= task_start_date <= right_date:
            tasks_started.append(task)
        if left_date <= task_finish_date <= right_date:
            tasks_finished.append(task)

    if tasks_started or tasks_finished:
        len_started = len(tasks_started)
        len_finished = len(tasks_finished)
        bot.send_message(message.chat.id,
                         f'📋 Задачи в период:\n'
                         f'{left_border} - {right_border}')
        bot.send_message(message.chat.id,
                         f'🚀Начатых задач: {len_started}\n\n'
                         f'🏁Завершенных задач: {len_finished}')
        handle_manager_to_do(message)
    else:
        bot.send_message(message.chat.id,
                         '❌ Нет задач за указанный период.')
        bot.set_state(message.chat.id, UserState.to_do_manager)
        handle_manager_to_do(message)


########################################################################


"""Началась цепочка worker"""


###########################################################################


@bot.callback_query_handler(
    func=lambda callback: callback.data in ['menu_w'])
@error_handler_callback
def handler_back_to_worker_menu(callback) -> None:
    """Возращение в меню"""

    logger.info('Возращение в меню')

    bot.set_state(callback.from_user.id, UserState.to_do_manager)
    bot.edit_message_reply_markup(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id
    )
    handle_worker_to_do(callback.message)


@bot.callback_query_handler(func=lambda callback: callback.data in ['worker'])
@error_handler_callback
def handle_role(callback) -> None:
    """Пользователь выбрал роль - worker. Запрашиваем имя"""

    logger.info('Пользователь выбрал роль - worker. Запрашиваем имя')

    bot.send_message(callback.from_user.id,
                     '✍️Теперь введите своё имя и фамилию:')
    bot.edit_message_reply_markup(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id
    )
    bot.set_state(callback.from_user.id, UserState.name_worker)


@bot.message_handler(state=UserState.name_worker)
@error_handler
def handle_data(message: Message) -> None:
    """Узнали имя. Заполняем таблицу данными"""

    logger.info('Узнали имя. Заполняем таблицу данными')

    user_id = message.from_user.id
    user_name = message.text

    user = UserWorker.get_or_none(UserWorker.user_id == user_id)
    if user is None:
        UserWorker.create(
            user_id=user_id,
            user_name=user_name,
            id_task=0
        )
        bot.send_message(
            message.chat.id,
            'Регистрация прошла успешно!',
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        bot.reply_to(
            message,
            f"Рад вас снова видеть, {user.user_name}!",
            reply_markup=ReplyKeyboardRemove()
        )
    handle_worker_to_do(message)


@bot.callback_query_handler(func=lambda callback: callback.data in ['accept'])
@error_handler_callback
def handle_accept_task(callback) -> None:
    """Принимаем новую задачу. Меняем статус в Task"""

    logger.info('Принимаем новую задачу. Меняем статус в Task')

    task = Task.get((Task.id_worker == callback.from_user.id) &
                    (Task.status == 'process'))
    task.status = 'work'
    task.date_start = datetime.date.today().strftime("%d/%m/%Y")
    task.save()
    bot.send_message(callback.from_user.id,
                     '✅ Задача принята!',
                     )
    bot.send_message(callback.from_user.id,
                     'Выберите действие: ',
                     reply_markup=gen_buttons_worker_to_do()
                     )
    bot.edit_message_reply_markup(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id
    )

@bot.message_handler(state=UserState.to_do_worker)
@error_handler
def handle_worker_to_do(message: Message) -> None:
    """worker выбирает действие"""

    logger.info('worker выбирает действие')

    bot.send_message(message.chat.id,
                     'Выберите действие',
                     reply_markup=gen_buttons_worker_to_do())


def gen_buttons_worker_to_do():
    """Функция кнопок выбора действия для worker"""

    logger.info('Функция кнопок выбора действия для worker')

    task_info = InlineKeyboardButton(
        text='📑 Список задач',
        callback_data='task_list_worker',
    )
    task_fin = InlineKeyboardButton(
        text='☑️Сдать работу',
        callback_data='task_fin',
    )
    report = InlineKeyboardButton(
        text='📊Смотреть отчет',
        callback_data='report_w',
    )
    keyboard = InlineKeyboardMarkup()
    keyboard.add(task_info)
    keyboard.add(task_fin)
    keyboard.add(report)
    return keyboard


@bot.callback_query_handler(
    func=lambda callback: callback.data in ['task_fin'])
@error_handler_callback
def handle_fin_task_task_id(callback) -> None:
    """Узнаем id для задачи, которую надо закончить"""

    logger.info('Узнаем id для задачи, которую надо закончить')

    markup = InlineKeyboardMarkup()
    tasks = Task.select().where((Task.status == 'work') &
                                (Task.id_worker == callback.from_user.id))

    bot.edit_message_reply_markup(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id
    )

    if not tasks.exists():
        bot.send_message(callback.from_user.id,
                         '📭Задач пока нет📭')
        bot.set_state(callback.from_user.id, UserState.to_do_worker)
        handle_worker_to_do(callback.message)
        return
    else:
        for task in tasks:
            markup.add(InlineKeyboardButton(
                text=task.task_name,
                callback_data=task.task_id,
            ),
            )

        bot.send_message(callback.from_user.id,
                         "Выберите задачу:",
                         reply_markup=markup)
        bot.set_state(callback.from_user.id, UserState.chose_task_id)


@bot.callback_query_handler(state=UserState.chose_task_id)
@error_handler_callback
def handle_fin_task_chak(callback) -> None:
    """Сдаем работу менеджеру"""

    logger.info('Сдаем работу менеджеру')

    task_id = callback.data
    task = Task.get(Task.task_id == task_id)
    task.status = 'finishing'
    task.save()
    bot.edit_message_reply_markup(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id
    )
    bot.send_message(callback.from_user.id, '📎Прикрепите работу: ')
    bot.set_state(callback.from_user.id, UserState.forward_to_manager)


@bot.message_handler(state=UserState.send_task)
@error_handler
def handle_send_task_to_manager(message: Message):
    """Сообщаем менеджеру об окончании работы"""

    logger.info('Сообщаем менеджеру об окончании работы')

    task = Task.get((Task.id_worker == message.chat.id) &
                    (Task.status == 'finishing'))

    worker = UserWorker.get(UserWorker.user_id == task.id_worker)
    bot.send_message(message.chat.id,
                     '🎊Отлично, работа завершена!')
    bot.send_message(task.id_manager,
                     f'💡{worker.user_name} - сдаёт работу'
                     f' "{task.task_name}!"')

    handle_end_circle(message)
    handle_worker_to_do(message)


def gen_buttons_yes_no():
    """Функция кнопки да\нет"""

    logger.info('Функция кнопки да\нет')

    yes = InlineKeyboardButton(
        text='✅',
        callback_data='finish_finish',
    )
    no = InlineKeyboardButton(
        text='❌',
        callback_data='stop',
    )

    keyboard = InlineKeyboardMarkup()
    keyboard.add(yes)
    keyboard.add(no)
    return keyboard


@bot.message_handler(state=UserState.end_task)
@error_handler
def handle_end_circle(message: Message) -> None:
    """Спрашиваем worker принять работу или нет."""

    logger.info('Спрашиваем worker принять работу или нет.')

    task = Task.get((Task.id_worker == message.chat.id) &
                    (Task.status == 'finishing'))
    task.status = 'finish'
    task.date_finish = datetime.date.today().strftime("%d/%m/%Y")
    task.save()
    bot.send_message(task.id_manager,
                     f'Работа "{task.task_name}" завершена',
                     reply_markup=gen_buttons_end_circle())


def gen_buttons_end_circle():
    """Функция кнопки принять работу"""

    logger.info('Функция кнопки принять работу')

    end = InlineKeyboardButton(
        text='OK',
        callback_data='end_circle',
    )
    keyboard = InlineKeyboardMarkup()
    keyboard.add(end)
    return keyboard


@bot.callback_query_handler(
    func=lambda callback: callback.data in ['task_list_worker'])
@error_handler_callback
def handler_task_list_to_worker(callback) -> None:
    """ Узнаем, какие работы хочет увидеть worker."""

    logger.info('Узнаем, какие работы хочет увидеть worker.')

    bot.send_message(callback.from_user.id,
                     'Какие задачи хотите увидеть?',
                     reply_markup=gen_buttons_tip_of_tasks_w()
                     )
    bot.edit_message_reply_markup(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id
    )


def gen_buttons_tip_of_tasks_w():
    """
    Создаём кнопки дял выбора типа заданий
    all_w - Все
    status_w - Работы в определённом статусе
    need_manager - Работы одного менеджера
    """

    logger.info('Создаём кнопки дял выбора типа заданий'
    'all_w - Все'
    'status_w - Работы в определённом статусе'
    'need_manager - Работы одного менеджера')

    all_tasks = InlineKeyboardButton(
        text='Все задания',
        callback_data='all_w',
    )
    status_task = InlineKeyboardButton(
        text='В определённом статусе',
        callback_data='status_w',
    )
    worker_tasks = InlineKeyboardButton(
        text='От определённого менеджера',
        callback_data='need_manager',
    )
    menu = InlineKeyboardButton(
        text='Вернуться в меню',
        callback_data='menu_w',
    )

    keyboard = InlineKeyboardMarkup()
    keyboard.add(all_tasks)
    keyboard.add(status_task)
    keyboard.add(worker_tasks)
    keyboard.add(menu)

    return keyboard


@bot.callback_query_handler(state=UserState.chose_task_info_id_worker)
@error_handler_callback
def handler_task_list_to_worker_send(callback) -> None:
    """Отправляем информацию конкретной задачи"""

    logger.info('Отправляем информацию конкретной задачи')

    task = Task.get(Task.task_id == callback.data)
    manager = UserManager.get(task.id_manager == UserManager.user_id)
    date_finish = task.date_finish
    status = task.status
    date_start = task.date_start

    if status == 'finishing':
        status = 'Вы завершает задание'
        date_finish = 'Работа не завершена'
    elif status == 'process':
        status = 'Вы ещё не приняли работу'
        date_start = 'Работа не начата'
        date_finish = 'Работа не завершена'
    elif status == 'work':
        status = 'Вы работает над задачей'
        date_finish = 'Работа не завершена'
    elif status == 'finish':
        status = 'Работа завершена'

    bot.send_message(callback.from_user.id,
                     f'Имя работы: \n{task.task_name}\n\n'
                     f'Работу назначил: \n{manager.user_name}\n\n'
                     f'📆Дата начала работы: \n{date_start}\n\n'
                     f'Статус: \n{status}\n\n'
                     f'📆Дата завершения работы: \n{date_finish}')

    bot.edit_message_reply_markup(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id
    )
    bot.set_state(callback.from_user.id, UserState.to_do_worker)
    handle_worker_to_do(callback.message)



@bot.message_handler(state=UserState.chose_times_borders_status_w)
@error_handler
def handler_task_list_to_worker_ask_status(message) -> None:
    """Узнаем, задания в каком статусе нужны"""

    logger.info('Узнаем, задания в каком статусе нужны')
    time_borders = message.text
    bot.send_message(message.chat.id,
                     'Выберите в каком статусе',
                     reply_markup=gen_buttons_status_task_w(time_borders))
    bot.set_state(message.chat.id, UserState.send_task_status_w)


def gen_buttons_status_task_w(time_borders):
    """Создаем кнопки статусов, чтобы узнать какие задания отправлять"""

    logger.info(
        'Создаем кнопки статусов, чтобы узнать какие задания отправлять')

    work = InlineKeyboardButton(
        text='В работе (у вас)',
        callback_data=f'work, {time_borders}',
    )
    finish = InlineKeyboardButton(
        text='Завершенные работы',
        callback_data=f'finish, {time_borders}',
    )
    menu = InlineKeyboardButton(
        text='Вернуться в меню',
        callback_data='menu_w',
    )

    keyboard = InlineKeyboardMarkup()
    keyboard.add(work)
    keyboard.add(finish)
    keyboard.add(menu)
    return keyboard


@bot.callback_query_handler(state=UserState.send_task_status_w)
def handler_task_list_to_worker_time_status(callback) -> None:
    """Узнали отрезок времени. Запрашиваем статус"""

    logger.info('Узнали отрезок времени. Запрашиваем статус')

    tasks = []
    try:
        bot.edit_message_reply_markup(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id
        )
        status, borders = callback.data.split(', ')

        left_border, right_border = borders.split(' - ')

        left_date = datetime.datetime.strptime(left_border.strip(),
                                               '%d/%m/%Y')
        right_date = datetime.datetime.strptime(right_border.strip(),
                                                '%d/%m/%Y')
        for task in Task.select():
            if task.date_start == '':
                task_start_date = '12/12/1000'
            else:
                task_start_date = task.date_start
            task_start_date = datetime.datetime.strptime(task_start_date,
                                                         "%d/%m/%Y")
            if task.date_finish == '':
                task_finish_date = '12/12/9999'
            else:
                task_finish_date = task.date_finish
            task_finish_date = datetime.datetime.strptime(task_finish_date,
                                                          "%d/%m/%Y")
            if ((left_date <= task_start_date <= right_date or
                 left_date <= task_finish_date <= right_date)
                    and (task.status == status)):
                tasks.append(task)

        markup = InlineKeyboardMarkup()
        if tasks:
            bot.send_message(callback.from_user.id,
                             f'📋 Задачи в период:\n'
                             f'{left_border} - {right_border}')
            for task_i in tasks:
                markup.add(InlineKeyboardButton(
                    text=f'"{task_i.task_name}"',
                    callback_data=task_i.task_id,
                ))
            markup.add(InlineKeyboardButton(
                text='Вернуться в меню',
                callback_data='menu_w',
            ))
            bot.send_message(callback.from_user.id,
                             'Выберите, про какую прислать информацию',
                             reply_markup=markup)
            bot.set_state(callback.from_user.id,
                          UserState.chose_task_info_id_worker)
        else:
            bot.send_message(callback.from_user.id,
                             '❌ Нет задач за указанный период.')
            bot.set_state(callback.from_user.id, UserState.to_do_worker)
            handle_worker_to_do(callback.message)

    except ValueError as e:
        print(f'ValueError: {e}')
        bot.send_message(callback.from_user.id,
                         '❌Ошибка. Проверьте формат даты')

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(
            text='Вернуться в меню',
            callback_data='menu_w',
        ))
        bot.send_message(callback.from_user.id,
                         'Выберите действие: ',
                         reply_markup=markup)


@bot.callback_query_handler(
    func=lambda callback: callback.data in ['all_w', 'report_w', 'status_w'])
@error_handler_callback
def handler_task_list_to_manager_time_borders(callback) -> None:
    """Отправляем задачи за нужный отрезок времени. Узнаем периоды"""

    logger.info('Отправляем задачи за нужный отрезок времени. Узнаем периоды')


    today = datetime.date.today().strftime("%d/%m/%Y")
    random_day = datetime.date.today() - datetime.timedelta(days=30)
    random_day = random_day.strftime("%d/%m/%Y")
    bot.send_message(callback.from_user.id,
                     'Отправьте одним сообщением, дата начала - дата конца'
                     '\nВ формате: dd/mm/yyyy - dd/mm/yyyy\n\n'
                     f'Пример:\n{random_day} - {today}')
    bot.edit_message_reply_markup(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id
    )
    if callback.data in ['all_w']:
        bot.set_state(callback.from_user.id,
                      UserState.chose_times_borders_w)
    elif callback.data in ['report_w']:
        bot.set_state(callback.from_user.id,
                      UserState.chose_times_borders_report_w)
    elif callback.data in ['status_w']:
        bot.set_state(callback.from_user.id,
                      UserState.chose_times_borders_status_w)



@bot.message_handler(state=UserState.chose_times_borders_w)
@error_handler
def handler_task_list_to_manager_time_all(message: Message) -> None:
    """Отправляем ВСЕ задачи за нужный отрезок времени"""

    logger.info('Отправляем ВСЕ задачи за нужный отрезок времени')

    tasks = []

    left_border, right_border = message.text.split(' - ')

    left_date = datetime.datetime.strptime(left_border.strip(),
                                           '%d/%m/%Y')
    right_date = datetime.datetime.strptime(right_border.strip(),
                                            '%d/%m/%Y')
    for task in Task.select():
        if task.date_start == '':
            task_start_date = '12/12/1000'
        else:
            task_start_date = task.date_start
        task_start_date = datetime.datetime.strptime(task_start_date,
                                                     "%d/%m/%Y")
        if task.date_finish == '':
            task_finish_date = '12/12/9999'
        else:
            task_finish_date = task.date_finish
        task_finish_date = datetime.datetime.strptime(task_finish_date,
                                                      "%d/%m/%Y")
        if (left_date <= task_start_date <= right_date or
                left_date <= task_finish_date <= right_date):
            tasks.append(task)

    markup = InlineKeyboardMarkup()
    if tasks:
        bot.send_message(message.chat.id,
                         f'📋 Задачи в период:\n'
                         f'{left_border} - {right_border}')
        for task_i in tasks:
            if task_i.status == 'work':
                status = 'В работе(у вас)'
            elif task_i.status == 'finish':
                status = 'Завершена'
            elif task_i.status == 'process':
                status = 'Менеджер создаёт работу'
            else:
                status = 'Неизвестный статус'
            markup.add(InlineKeyboardButton(
                text=f'"{task_i.task_name}". {status}',
                callback_data=task_i.task_id,
            ))
        markup.add(InlineKeyboardButton(
            text='Вернуться в меню',
            callback_data='menu_w',
        ))
        bot.send_message(message.chat.id,
                         'Выберите, про какую прислать информацию',
                         reply_markup=markup)
        bot.set_state(message.chat.id,
                      UserState.chose_task_info_id_worker)
    else:
        bot.send_message(message.chat.id,
                         '❌ Нет задач за указанный период.')
        bot.set_state(message.chat.id, UserState.to_do_manager)
        handle_worker_to_do(message)



@bot.message_handler(state=UserState.chose_times_borders_report_w)
@error_handler
def handler_task_report_to_worker(message: Message) -> None:
    """Создаём и отправляем ОТЧЕТ о работах воркеру"""

    logger.info('Отправляем ОТЧЕТ о работах')

    tasks_started = []
    tasks_finished = []

    left_border, right_border = message.text.split(' - ')

    left_date = datetime.datetime.strptime(left_border.strip(),
                                           '%d/%m/%Y')
    right_date = datetime.datetime.strptime(right_border.strip(),
                                            '%d/%m/%Y')

    for task in Task.select():
        if task.date_start == '':
            task_start_date = '12/12/1000'
        else:
            task_start_date = task.date_start
        task_start_date = datetime.datetime.strptime(task_start_date,
                                                     "%d/%m/%Y")
        if task.date_finish == '':
            task_finish_date = '12/12/9999'
        else:
            task_finish_date = task.date_finish
        task_finish_date = datetime.datetime.strptime(task_finish_date,
                                                      "%d/%m/%Y")
        if left_date <= task_start_date <= right_date:
            tasks_started.append(task)
        if left_date <= task_finish_date <= right_date:
            tasks_finished.append(task)

    if tasks_started or tasks_finished:
        len_started = len(tasks_started)
        len_finished = len(tasks_finished)
        bot.send_message(message.chat.id,
                         f'📋 Задачи в период:\n'
                         f'{left_border} - {right_border}')
        bot.send_message(message.chat.id,
                         f'🚀Начатых задач: {len_started}\n\n'
                         f'🏁Завершенных задач: {len_finished}')
        handle_worker_to_do(message)
    else:
        bot.send_message(message.chat.id,
                         '❌ Нет задач за указанный период.')
        bot.set_state(message.chat.id, UserState.to_do_manager)
        handle_worker_to_do(message)


@bot.callback_query_handler(
    func=lambda callback: callback.data in ['need_manager'])
@error_handler_callback
def handler_task_list_to_worker_choose_need_worker(callback) -> None:
    """Отправляем workers, чтобы отправить задачи определённого"""

    logger.info('Отправляем workers, чтобы отправить задачи определённого')


    markup = InlineKeyboardMarkup()
    managers = UserManager.select()
    for manager in managers:
        markup.add(InlineKeyboardButton(
            text=manager.user_name,
            callback_data=manager.user_id,
        ),
        )

    markup.add(InlineKeyboardButton(
        text='Вернуться в меню',
        callback_data='menu_w',
    ))
    bot.send_message(callback.from_user.id,
                     "🧑‍💻Выберите от кого пришла работа:",
                     reply_markup=markup)
    bot.edit_message_reply_markup(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id
    )
    bot.set_state(callback.from_user.id, UserState.chose_task_manager)


@bot.callback_query_handler(state=UserState.chose_task_manager)
@error_handler_callback
def handler_task_list_to_worker_need_worker(callback) -> None:
    """Отправляем список нужных по статусу заданий"""

    logger.info('Отправляем список нужных по статусу заданий')


    tasks = Task.select().where((Task.id_worker == callback.from_user.id) &
                                (Task.id_manager == callback.data))
    markup = InlineKeyboardMarkup()
    for task in tasks:
        if task.status == 'work':
            status = 'В работе(у вас)'
        elif task.status == 'finish':
            status = 'Завершена'
        elif task.status == 'process':
            status = 'Менеджер создаёт работу'
        else:
            status = 'Неизвестный статус'

        markup.add(InlineKeyboardButton(
            text=f'"{task.task_name}". {status}',
            callback_data=task.task_id,
        ),
        )
    markup.add(InlineKeyboardButton(
        text='Вернуться в меню',
        callback_data='menu_w',
    ))
    bot.send_message(callback.from_user.id,
                     'Список задач:\n'
                     'Выберите, про какую прислать информацию',
                     reply_markup=markup)
    bot.edit_message_reply_markup(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id
    )
    bot.set_state(callback.from_user.id,
                  UserState.chose_task_info_id_worker)


@bot.message_handler(state=UserState.forward_to_manager,
                     content_types=['photo', 'document', 'text'])
@error_handler
def forward_message_task_to_manager(message: Message) -> None:
    """Получаем файл от воркера и отправляем менеджеру"""
    logger.info('Отправляем задачу, либо получаем ещё файл')

    manager = UserManager.get()
    manager_id = manager.user_id
    if message.content_type == 'document':
        bot.send_document(manager_id, message.document.file_id)
    elif message.content_type == 'photo':
        bot.send_photo(manager_id, message.photo[0].file_id)
    elif message.content_type == 'text':
        bot.send_message(manager_id, message.text)
    else:
        bot.send_message(manager_id,
                         'Произошла ошибка при пересылки сообщения')
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(
        text='Добавить ещё файл/информацию',
        callback_data='send_more_w',
    ))
    markup.add(InlineKeyboardButton(
        text='Отправить задачу менеджеру',
        callback_data='send_w',
    ))
    bot.send_message(message.chat.id,
                     'Выберите действие: ',
                     reply_markup=markup)
    return


@bot.callback_query_handler(
    func=lambda callback: callback.data in ['send_w', 'send_more_w'])
@error_handler_callback
def handler_send_or_send_more_to_manager(callback) -> None:
    """Отправляем задачу, либо получаем ещё файл"""

    logger.info('Отправляем задачу, либо получаем ещё файл')

    if callback.data == 'send_w':
        bot.set_state(callback.from_user.id, UserState.send_task)
        handle_send_task_to_manager(callback.message)
    else:
        bot.send_message(callback.from_user.id,
                         "📋Добавьте файл/информацию к задаче:", )
        bot.set_state(callback.from_user.id, UserState.forward_to_manager)


@bot.message_handler(func=lambda message: True)
def handle_unexpected_messages(message: Message):
    """Ловим все неожиданные сообщения"""

    logger.info('Ловим все неожиданные сообщения')

    bot.reply_to(
        message,
        "Извините, я не могу понять ваш запрос. "
        "Давайте попробуем снова.\n"
        "Введите /start"
    )
