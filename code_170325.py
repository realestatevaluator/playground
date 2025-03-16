from aiogram import Bot, types, executor, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Command, Text, RegexpCommandsFilter
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
import psycopg2
import datetime

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

DB_NAME = "rev_data"
DB_USER = "analyst"
DB_PASSWORD = "iPJenuTt"
DB_HOST = "31.184.253.116"
DB_PORT = "5432"

# Класс пользователя для работы с базой данных
class User:
    def __init__(self, telegram_id):
        self.telegram_id = telegram_id

    def check_agent_record(self):
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )
        cursor = conn.cursor()
        # Проверяем наличие таблицы agents и создаем, если ее нет
        cursor.execute('''CREATE TABLE IF NOT EXISTS agents (
                            telegram_id BIGINT PRIMARY KEY,
                            start_dt DATE,
                            end_dt DATE,
                            subscription_type INTEGER
                        )''')
        cursor.execute('SELECT * FROM agents WHERE telegram_id = %s', (self.telegram_id,))
        db_data = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        return db_data

    def create_agent_record(self):
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO agents (telegram_id) VALUES (%s)''', (self.telegram_id,))
        conn.commit()
        cursor.close()
        conn.close()

    def get_subscription_info(self):
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )
        cursor = conn.cursor()
        cursor.execute('SELECT start_dt, end_dt, subscription_type FROM agents WHERE telegram_id = %s', (self.telegram_id,))
        db_data = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        return db_data

    def update_subscription(self, start_dt, end_dt, subscription_type):
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )
        cursor = conn.cursor()
        cursor.execute('''UPDATE agents
                          SET start_dt = %s, end_dt = %s, subscription_type = %s
                          WHERE telegram_id = %s''',
                       (start_dt, end_dt, subscription_type, self.telegram_id))
        conn.commit()
        cursor.close()
        conn.close()

# ------------ Состояния ------------
class OfferObjectsStates(StatesGroup):
    City = State()
    SampleSize = State()
    FilterChoice = State()
    PriceFrom = State()
    PriceTo = State()
    RoomsFrom = State()
    RoomsTo = State()
    DisplayMode = State()      # Спрашиваем Готов ли пользователь давать отзыв по каждому объекту
    DisplayOneByOne = State()  # Последовательное отображение объектов для пользователей с подпиской feedback
    DisplayObjects = State()   # Одномоментное отображение (если подписка без feedback)
    LikeObject = State()

class OfferFeedbackStates(StatesGroup):
    WaitUndersaleAnswer = State()
    WaitMismatchAnswer = State()

class FeedbackStates(StatesGroup):
    Answer1 = State()
    Answer2 = State()
    Answer3 = State()
    Comment = State()

class FavouriteObjectsStates(StatesGroup):
    Idle = State()

# ------------ Вспомогательные функции ------------

def get_db_connection():
    return psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT
    )

# Получить дату максимального парсинга
def get_max_parsed_date():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(date(parsed_at)) FROM test_table_2;")
    max_date = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    return max_date

# Проверка, что объект уже в избранном
def is_in_favourite(telegram_id, source_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS favourite_objects (
            telegram_id BIGINT,
            source_id TEXT,
            parsed_at DATE
        )
    ''')
    cursor.execute('''
        SELECT 1 FROM favourite_objects
        WHERE telegram_id = %s AND source_id = %s
        LIMIT 1
    ''', (telegram_id, source_id))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return (row is not None)

# Добавить в избранное
def add_to_favourite(telegram_id, source_id, parsed_at):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS favourite_objects (
            telegram_id BIGINT,
            source_id TEXT,
            parsed_at DATE
        )
    ''')
    # Вставляем запись
    cursor.execute('''
        INSERT INTO favourite_objects (telegram_id, source_id, parsed_at)
        VALUES (%s, %s, %s)
    ''', (telegram_id, source_id, parsed_at))
    conn.commit()
    cursor.close()
    conn.close()

# Добавить в disliked
def add_to_dislike(telegram_id, source_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dislike_objects (
            telegram_id BIGINT,
            source_id TEXT,
            dislike_dt DATE
        )
    ''')
    cursor.execute('''
        INSERT INTO dislike_objects (telegram_id, source_id, dislike_dt)
        VALUES (%s, %s, %s)
    ''', (telegram_id, source_id, datetime.date.today()))
    conn.commit()
    cursor.close()
    conn.close()

# ------------ Интерфейсные клавиатуры ------------
def main_menu_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("/subscription", "/offerObjects", "/favouriteObjects", "/feedback", "/instruction", "/home")
    return keyboard

def emoji_keyboard():
    # Кнопки для реакции на объект
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("❤️", "👎", "Готово")
    return keyboard

def ready_keyboard():
    # Клавиатура для вопроса о готовности к оставлению обратной связи
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("Готов", "Рассмотрю позже")
    return keyboard

def yes_no_keyboard():
    # Да/Нет
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("Да", "Нет", "/home")
    return keyboard




# ------------------------------------------------------------------------------------------------------------------------------------------------ 
# ------------------------------------------------------------------------------------------------------------------------------------------------ 
# ------------------------------------------------------------------------------------------------------------------------------------------------ 
# ------------------------------------------------------------------------------------------------------------------------------------------------ 
# ------------------------------------------------------------------------------------------------------------------------------------------------ 
# ------------------------------------------------------------------------------------------------------------------------------------------------ 
# ------------------------------------------------------------------------------------------------------------------------------------------------ 
# ------------------------------------------------------------------------------------------------------------------------------------------------ 
# ------------------------------------------------------------------------------------------------------------------------------------------------ 
# ------------------------------------------------------------------------------------------------------------------------------------------------ 
# ------------------------------------------------------------------------------------------------------------------------------------------------ 
# ------------------------------------------------------------------------------------------------------------------------------------------------ 
# ------------------------------------------------------------------------------------------------------------------------------------------------ 
# ------------ Команды ------------
# ------------------------------------------------------------------------------------------------------------------------------------------------ 
@dp.message_handler(commands=['start'])
async def start_command(message: types.Message):
    user = User(message.from_user.id)
    agent_record = user.check_agent_record()
    if agent_record is None:
        # Новая регистрация пользователя
        user.create_agent_record()
        await message.reply("Добро пожаловать в приложение-ассистент по рекомендации объявлений о продаже жилья!")
    else:
        await message.reply("Рады снова видеть вас в приложении-ассистенте по рекомендации жилья!")

    await message.answer(
        "Перед началом использования вы можете ознакомиться с краткой инструкцией по команде /instruction.\n"
        "Также вы можете настроить или продлить свою подписку командой /subscription.\n"
        "Для просмотра главного меню введите /home.",
        reply_markup=main_menu_keyboard()
    )



# ------------------------------------------------------------------------------------------------------------------------------------------------ 
# ---------------- /feedback (общий отзыв о сервисе) ---------------
# ------------------------------------------------------------------------------------------------------------------------------------------------ 
@dp.message_handler(commands=['feedback'])
async def feedback_command(message: types.Message):
    await message.reply(
        "Наша команда стремится совершенствовать свой сервис и вносить корректировки в его работу. "
        "Нам будет полезно услышать Ваше мнение."
    )
    # Вопрос 1
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("Да", "Нет")
    await message.reply("1/4 Являются ли объекты недооцененными в целом? (Да/Нет)", reply_markup=keyboard)
    await FeedbackStates.Answer1.set()

@dp.message_handler(state=FeedbackStates.Answer1)
async def process_feedback_answer1(message: types.Message, state: FSMContext):
    if message.text.startswith('/'):
        await state.finish()
        await message.reply("Операция прервана.", reply_markup=main_menu_keyboard())
        return
    await state.update_data(answer1=message.text)
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("0", "1-3", ">3", "все предложенные варианты полезны")
    await message.reply("2/4 Сколько предложений оказались полезны?", reply_markup=keyboard)
    await FeedbackStates.Answer2.set()

@dp.message_handler(state=FeedbackStates.Answer2)
async def process_feedback_answer2(message: types.Message, state: FSMContext):
    if message.text.startswith('/'):
        await state.finish()
        await message.reply("Операция прервана.", reply_markup=main_menu_keyboard())
        return
    await state.update_data(answer2=message.text)
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("Да", "Нет")
    await message.reply("3/4Была ли информация об объектах полной и достоверной?", reply_markup=keyboard)
    await FeedbackStates.Answer3.set()

@dp.message_handler(state=FeedbackStates.Answer3)
async def process_feedback_answer3(message: types.Message, state: FSMContext):
    if message.text.startswith('/'):
        await state.finish()
        await message.reply("Операция прервана.", reply_markup=main_menu_keyboard())
        return
    await state.update_data(answer3=message.text)
    await message.reply("4/4 Ваш комментарий (опишите):", reply_markup=types.ReplyKeyboardRemove())
    await FeedbackStates.Comment.set()

@dp.message_handler(state=FeedbackStates.Comment)
async def process_feedback_comment(message: types.Message, state: FSMContext):
    if message.text.startswith('/'):
        await state.finish()
        await message.reply("Операция прервана.", reply_markup=main_menu_keyboard())
        return

    await state.update_data(comment=message.text)
    data = await state.get_data()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS feedback (
                        telegram_id BIGINT,
                        gregor_dt TIMESTAMP,
                        answer1 TEXT,
                        answer2 TEXT,
                        answer3 TEXT,
                        comment TEXT
                    )''')
    cursor.execute('''INSERT INTO feedback (telegram_id, gregor_dt, answer1, answer2, answer3, comment)
                      VALUES (%s, %s, %s, %s, %s, %s)''',
                   (message.from_user.id, datetime.datetime.now(),
                    data['answer1'], data['answer2'], data['answer3'], data['comment']))
    conn.commit()
    cursor.close()
    conn.close()

    await message.reply("Спасибо за ваш отзыв!", reply_markup=main_menu_keyboard())
    await state.finish()




# ------------------------------------------------------------------------------------------------------------------------------------------------ 
# ---------------- /favouriteObjects ----------------
# ------------------------------------------------------------------------------------------------------------------------------------------------ 
@dp.message_handler(commands=['favouriteObjects'])
async def favourite_objects_command(message: types.Message):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS favourite_objects (
            telegram_id BIGINT,
            source_id TEXT,
            parsed_at DATE
        )
    ''')
    # Для вывода описания так же нужно соединить с test_table, чтобы достать title, price_object и т.д.
    query = '''
        SELECT t.title,
               t.price_object,
               t.area,
               t.address,
               t.url_link,
               f.source_id,
               t.parsed_at
        FROM favourite_objects f
        JOIN test_table_2 t ON f.source_id = t.source_id
        WHERE f.telegram_id = %s
        ORDER BY t.price_object
    '''
    cursor.execute(query, (message.from_user.id,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    if not rows:
        await message.reply("У Вас ещё нет понравившихся объектов или эти объявления больше не актуальны.", reply_markup=main_menu_keyboard())
    else:
        await message.reply("Ваши избранные объекты:")
        max_date = get_max_parsed_date()
        for idx, obj in enumerate(rows, start=1):
            title, price_object, area, address, url_link, source_id, parsed_at = obj

            bracket_label = ""
            in_fav = True  # Это уже избранное
            parsed_date_only = parsed_at.date() if parsed_at else None
            if parsed_date_only == max_date:
                bracket_label = "(избранное предложение изменилось)"

            reply_text = (
                f"{title} {bracket_label}\n"
                f"Цена: {price_object}\n"
                f"Площадь: {area}\n"
                f"Адрес: {address}\n"
                # f"Source ID: {source_id}\n"
                # f"Дата парсинга: {parsed_date_only}\n"
                f"{url_link}"
            )
            await message.reply(reply_text, reply_markup=emoji_keyboard())
        await message.reply("Вот полный список Ваших избранных объектов.", reply_markup=main_menu_keyboard())

# Добавь логику ИСКЛЮЧЕНИЯ из избранного
# Добавь проверку, чтобы объект был в избранном и больше не актуален
# Добавь фильтр по городу

# ------------------------------------------------------------------------------------------------------------------------------------------------ 
# ------------------------------------------------------------------------------------------------------------------------------------------------ 
# ------------------------------------------------------------------------------------------------------------------------------------------------ 
@dp.message_handler(commands=['instruction'])
async def instruction_command(message: types.Message):
    await message.answer(
        "Инструкция по использованию бота:\n\n"
        "1) Оформите подписку: /subscription\n"
        "2) После оформления подписки используйте /offerObjects, чтобы получить список объектов.\n"
        "При выборе города и желаемого количества объектов можно задать фильтры.\n"
        "3) Если ваша подписка с обратной связью, перед показом объектов бот задаст вопрос о вашей готовности давать обратную связь по каждому объекту.\n"
        "4) Любой объект можно добавить в избранное, ответив на сообщение сердечком (❤️) или пометить как недостоверный (👎).\n"
        "5) Посмотреть своё избранное: /favouriteObjects\n"
        "6) В любое время вы можете оставить отзыв о сервисе: /feedback\n\n"
        "Приятного пользования!",
        reply_markup=main_menu_keyboard()
    )



# ------------------------------------------------------------------------------------------------------------------------------------------------ 
# ------------------------------------------------------------------------------------------------------------------------------------------------ 
# ------------------------------------------------------------------------------------------------------------------------------------------------ 
@dp.message_handler(commands=['home'])
async def home_command(message: types.Message):
    await message.reply(
        "Доступные команды:\n"
        "/start - Начать работу с ботом\n"
        "/subscription - Подписка: информация о подписке и тарифы\n"
        "/offerObjects - Получить предложения объектов недвижимости\n"
        "/favouriteObjects - Список понравившихся объектов\n"
        "/feedback - Оставить общий отзыв\n"
        "/instruction - Как пользоваться ботом\n"
        "/home - Показать это сообщение",
        reply_markup=main_menu_keyboard()
    )



# ------------------------------------------------------------------------------------------------------------------------------------------------ 
# ------------------------------------------------------------------------------------------------------------------------------------------------ 
# ------------------------------------------------------------------------------------------------------------------------------------------------ 
@dp.message_handler(commands=['subscription'])
async def subscription_command(message: types.Message):
    user = User(message.from_user.id)
    subscription_info = user.get_subscription_info()
    if subscription_info and subscription_info[1] and subscription_info[1] >= datetime.date.today():
        start_dt, end_dt, sub_type = subscription_info
        days_left = (end_dt - datetime.date.today()).days
        subscription_type = "с обратной связью" if sub_type == 1 else "классическая"
        await message.reply(
            f"Ваша подписка активна!\n"
            f"Тип подписки: {subscription_type}\n"
            # f"Дата начала: {start_dt}\n"
            # f"Дата окончания: {end_dt}\n"
            f"До конца подписки осталось {days_left} дней.\n",
            reply_markup=main_menu_keyboard()
        )
        await message.reply("Вы можете воспользоваться сервисом /offerObjects для подбора недвижимости.")
    else:
        # Предложение вариантов подписки
        keyboard = types.InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            types.InlineKeyboardButton(text="1 месяц - 1000р", callback_data="sub_1m_basic"),
            types.InlineKeyboardButton(text="3 месяца - 2500р", callback_data="sub_3m_basic"),
            types.InlineKeyboardButton(text="6 месяцев - 5000р", callback_data="sub_6m_basic"),
            types.InlineKeyboardButton(text="Год - 9500р", callback_data="sub_12m_basic"),
            types.InlineKeyboardButton(text="1 месяц с обратной связью - 500р", callback_data="sub_1m_feedback"),
            types.InlineKeyboardButton(text="3 месяца с обратной связью - 1250р", callback_data="sub_3m_feedback"),
        )
        await message.reply("Выберите вариант подписки:", reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data.startswith('sub_'))
async def process_subscription_callback(callback_query: types.CallbackQuery):
    data = callback_query.data
    user = User(callback_query.from_user.id)

    start_dt = datetime.date.today()
    end_dt = None
    sub_type = 0  # 0 - без обратной связи, 1 - с обратной связью

    if data == 'sub_1m_basic':
        end_dt = start_dt + datetime.timedelta(days=30)
        sub_type = 0
        await bot.answer_callback_query(callback_query.id, text="Подписка на 1 месяц оформлена!")
    elif data == 'sub_3m_basic':
        end_dt = start_dt + datetime.timedelta(days=90)
        sub_type = 0
        await bot.answer_callback_query(callback_query.id, text="Подписка на 3 месяца оформлена!")
    elif data == 'sub_6m_basic':
        end_dt = start_dt + datetime.timedelta(days=180)
        sub_type = 0
        await bot.answer_callback_query(callback_query.id, text="Подписка на 6 месяцев оформлена!")
    elif data == 'sub_12m_basic':
        end_dt = start_dt + datetime.timedelta(days=365)
        sub_type = 0
        await bot.answer_callback_query(callback_query.id, text="Подписка на 1 год оформлена!")
    elif data == 'sub_1m_feedback':
        end_dt = start_dt + datetime.timedelta(days=30)
        sub_type = 1
        await bot.answer_callback_query(callback_query.id, text="Подписка на 1 месяц с обратной связью оформлена!")
    elif data == 'sub_3m_feedback':
        end_dt = start_dt + datetime.timedelta(days=90)
        sub_type = 1
        await bot.answer_callback_query(callback_query.id, text="Подписка на 3 месяца с обратной связью оформлена!")

    user.update_subscription(start_dt, end_dt, sub_type)
    await bot.send_message(callback_query.from_user.id, "Спасибо за оформление подписки!", reply_markup=main_menu_keyboard())




# ------------------------------------------------------------------------------------------------------------------------------------------------
# ---------------- /offerObjects ----------------
# ------------------------------------------------------------------------------------------------------------------------------------------------
@dp.message_handler(commands=['offerObjects'])
async def offer_objects_command(message: types.Message, state: FSMContext):
    user = User(message.from_user.id)
    subscription_info = user.get_subscription_info()
    if not subscription_info or subscription_info[1] < datetime.date.today():
        await message.reply("У вас нет активной подписки. Оформите её с помощью команды /subscription", reply_markup=main_menu_keyboard())
        return

    # Спрашиваем город
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("Нижний Новгород", "Казань", "Самара", "/home")
    await message.reply("В каком городе вы бы хотели рассмотреть объявления?", reply_markup=keyboard)
    await OfferObjectsStates.City.set()

@dp.message_handler(state=OfferObjectsStates.City)
async def process_city(message: types.Message, state: FSMContext):
    if message.text.startswith('/'):
        await state.finish()
        await message.reply("Операция прервана.", reply_markup=main_menu_keyboard())
        return

    # Небольшая проверка, если хотите
    if message.text not in ["Нижний Новгород", "Казань", "Самара"]:
        await message.reply("Пожалуйста, выберите город из предложенных вариантов или введите /home для отмены.")
        return

    await state.update_data(city=message.text)

    # Предложить выбрать объём выборки
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("10 объектов", "20 объектов", "30 объектов", "50 объектов", "все объекты", "/home")
    await message.reply("Выберите объём желаемой выборки:", reply_markup=keyboard)
    await OfferObjectsStates.SampleSize.set()

@dp.message_handler(state=OfferObjectsStates.SampleSize)
async def process_sample_size(message: types.Message, state: FSMContext):
    if message.text.startswith('/'):
        await state.finish()
        await message.reply("Операция прервана.", reply_markup=main_menu_keyboard())
        return

    options = ["10 объектов", "20 объектов", "30 объектов", "50 объектов", "все объекты"]
    if message.text not in options:
        await message.reply("Пожалуйста, выберите объём выборки из предложенных вариантов.")
        return

    sample_size = None
    if message.text != "все объекты":
        sample_size = int(message.text.split()[0])

    await state.update_data(sample_size=sample_size)

    # Предложить задать фильтры
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("Готово", "по цене", "по кол-ву комнат", "/home")
    await message.reply("Укажите наличие фильтров (по цене, по кол-ву комнат) или нажмите 'Готово':", reply_markup=keyboard)
    await OfferObjectsStates.FilterChoice.set()

@dp.message_handler(state=OfferObjectsStates.FilterChoice)
async def process_filter_choice(message: types.Message, state: FSMContext):
    if message.text.startswith('/'):
        await state.finish()
        await message.reply("Операция прервана.", reply_markup=main_menu_keyboard())
        return

    if message.text == "Готово":
        await proceed_to_check_feedback_mode(message, state)
    elif message.text == "по цене":
        await message.reply("Введите минимальную цену (от):", reply_markup=types.ReplyKeyboardRemove())
        await OfferObjectsStates.PriceFrom.set()
    elif message.text == "по кол-ву комнат":
        await message.reply("Введите минимальное количество комнат (0 - студия):", reply_markup=types.ReplyKeyboardRemove())
        await OfferObjectsStates.RoomsFrom.set()
    else:
        await message.reply("Неизвестный вариант. Нажмите 'Готово', 'по цене' или 'по кол-ву комнат'.")

@dp.message_handler(state=OfferObjectsStates.PriceFrom)
async def process_price_from(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.reply("Пожалуйста, введите целое число.")
        return
    price_from = int(message.text)
    await state.update_data(price_from=price_from)
    await message.reply("Введите максимальную цену (до):")
    await OfferObjectsStates.PriceTo.set()

@dp.message_handler(state=OfferObjectsStates.PriceTo)
async def process_price_to(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.reply("Пожалуйста, введите целое число.")
        return
    price_to = int(message.text)

    data = await state.get_data()
    filters = data.get('filters', {})
    filters['price'] = (data['price_from'], price_to)
    await state.update_data(filters=filters)

    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("Готово", "по кол-ву комнат", "/home")
    await message.reply("Вы можете добавить ещё фильтры или нажать 'Готово'.", reply_markup=keyboard)
    await OfferObjectsStates.FilterChoice.set()

@dp.message_handler(state=OfferObjectsStates.RoomsFrom)
async def process_rooms_from(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.reply("Пожалуйста, введите целое число.")
        return
    rooms_from = int(message.text)
    await state.update_data(rooms_from=rooms_from)
    await message.reply("Введите максимальное количество комнат (до):")
    await OfferObjectsStates.RoomsTo.set()

@dp.message_handler(state=OfferObjectsStates.RoomsTo)
async def process_rooms_to(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.reply("Пожалуйста, введите целое число.")
        return
    rooms_to = int(message.text)

    data = await state.get_data()
    filters = data.get('filters', {})
    filters['rooms'] = (data['rooms_from'], rooms_to)
    await state.update_data(filters=filters)

    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("Готово", "по цене", "/home")
    await message.reply("Вы можете добавить ещё фильтры или нажать 'Готово'.", reply_markup=keyboard)
    await OfferObjectsStates.FilterChoice.set()

# После того, как пользователь сказал "Готово" по фильтрам, проверяем, есть ли у него подписка с обратной связью
async def proceed_to_check_feedback_mode(message: types.Message, state: FSMContext):
    user = User(message.from_user.id)
    subscription_info = user.get_subscription_info()
    if subscription_info and subscription_info[2] == 1:
        # Подписка с обратной связью, спрашиваем готовность
        await message.reply(
            "Сейчас Вам будет представлен ряд объектов и, поскольку Вы используете подписку с обратной связью, "
            "Вам необходимо будет оставить обратную связь по каждому из них. "
            "Это может занять значительное время - Вы готовы?",
            reply_markup=ready_keyboard()
        )
        await OfferObjectsStates.DisplayMode.set()
    else:
        # Без обратной связи - просто показываем объекты сразу списком
        await proceed_to_offers_list_mode(message, state)

@dp.message_handler(state=OfferObjectsStates.DisplayMode)
async def feedback_mode_decision(message: types.Message, state: FSMContext):
    if message.text == "Готов":
        # Переходим в пообъектный режим
        await proceed_to_offers_onebyone_mode(message, state)
    elif message.text == "Рассмотрю позже":
        await state.finish()
        await message.reply("Вы можете вернуться к подбору объектов позже командой /offerObjects.\n/home", reply_markup=main_menu_keyboard())
    else:
        await message.reply("Пожалуйста, выберите 'Готов' или 'Рассмотрю позже'.")

# ------------------------------------------------------------------------------------------------------------------------------------------------ 
# ------------------------------------------------------------------------------------------------------------------------------------------------ 
# ------------ Показ объектов одним списком (для тех, у кого нет feedback-подписки) ------------
# ------------------------------------------------------------------------------------------------------------------------------------------------ 
async def proceed_to_offers_list_mode(message: types.Message, state: FSMContext):
    data = await state.get_data()
    city = data['city']
    sample_size = data.get('sample_size')
    filters = data.get('filters', {})

    objects = get_filtered_objects(city, filters, sample_size)

    if not objects:
        await message.reply("К сожалению, по заданным фильтрам объекты не найдены.", reply_markup=main_menu_keyboard())
        await state.finish()
        return
    
    if filters:
        await message.reply("Предлагаем вам обратить внимание на следующие объекты по заданным фильтрам:")
    else:
        await message.reply("Предлагаем вам полный список объектов:")

    max_date = get_max_parsed_date()  # дата-максимум из test_table

    # Показываем все объекты одним списком
    for idx, obj in enumerate(objects, start=1):
        (title, price_object, area, address, url_link, source_id, parsed_at) = obj

        # Проверяем в избранном ли объект
        in_fav = is_in_favourite(message.from_user.id, source_id)
        # Формируем приписку
        bracket_label = ""
        parsed_date_only = parsed_at if parsed_at else None

        if parsed_date_only == max_date:
            if in_fav:
                bracket_label = "(избранное предложение изменилось)"
            else:
                bracket_label = "(новый)"
        else:
            if in_fav:
                bracket_label = "(уже в избранном)"

        reply_text = (
            f"{idx}) {title} {bracket_label}\n"
            f"Цена: {price_object}\n"
            f"Площадь: {area}\n"
            f"Адрес: {address}\n"
            # f"Source ID: {source_id}\n"
            # f"Дата парсинга: {parsed_date_only}\n"
            f"{url_link}"
        )
        await message.reply(reply_text, reply_markup=emoji_keyboard())

    await message.reply(
        "В любое время вы можете оценить объект (добавить его в избранное или поставить дизлайк). "
        "Для этого воспользуйтесь функцией telegram 'Ответить' для сообщения-объекта и отправьте '❤️' или '👎' вместе с ответом.\n\n"
        "Для завершения или повторного отбора нажмите 'Готово'.",
        reply_markup=emoji_keyboard()
    )
    await OfferObjectsStates.DisplayObjects.set()
# ------------------------------------------------------------------------------------------------------------------------------------------------ 
# ------------------------------------------------------------------------------------------------------------------------------------------------ 
# ------------ Показ объектов по одному (для тех, у кого есть feedback-подписка) ------------
# ------------------------------------------------------------------------------------------------------------------------------------------------ 
async def proceed_to_offers_onebyone_mode(message: types.Message, state: FSMContext):
    data = await state.get_data()
    city = data['city']
    sample_size = data.get('sample_size')
    filters = data.get('filters', {})

    objects_list = get_filtered_objects(city, filters, sample_size)
    if not objects_list:
        await message.reply("К сожалению, по заданным фильтрам объекты не найдены.", reply_markup=main_menu_keyboard())
        await state.finish()
        return

    # Сохраняем их в state, чтобы вести итерацию
    await state.update_data(objects_list=objects_list, current_index=0)

    await message.reply(
        "Начинаем показ объектов по одному. После каждого объекта Вы ответите на 2 вопроса.",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await show_next_object_onebyone(message, state)  # Показ первого объекта

# Показать следующий объект из списка (режим one-by-one)
async def show_next_object_onebyone(message: types.Message, state: FSMContext):
    data = await state.get_data()
    objects_list = data['objects_list']
    current_index = data['current_index']
    if current_index >= len(objects_list):
        await message.reply("Это были все объекты! Спасибо большое за предоставленную обратную связь🙏😊\n"
                            "Чтобы рассмотреть предложения по иному фильтру воспользуйтесь командой /offerObjects вновь.\n\n"
                            "Также любое время вы можете оценить объект (добавить его в избранное или поставить дизлайк). "
                            "Для этого воспользуйтесь функцией telegram 'Ответить' для сообщения-объекта и отправьте '❤️' или '👎' вместе с ответом.", reply_markup=main_menu_keyboard())
        await state.finish()
        return
    max_date = get_max_parsed_date()
    obj = objects_list[current_index]
    (title, price_object, area, address, url_link, source_id, parsed_at) = obj
    in_fav = is_in_favourite(message.from_user.id, source_id)
    bracket_label = ""
    parsed_date_only = parsed_at

    if parsed_date_only == max_date:
        if in_fav:
            bracket_label = "(избранное предложение изменилось)"
        else:
            bracket_label = "(новый)"
    else:
        if in_fav:
            bracket_label = "(уже в избранном)"

    reply_text = (
        f"Объект №{current_index + 1}: {title} {bracket_label}\n"
        f"Цена: {price_object}\n"
        f"Площадь: {area}\n"
        f"Адрес: {address}\n"
        # f"Source ID: {source_id}\n"
        # f"Дата парсинга: {parsed_date_only}\n"
        f"{url_link}"
    )
    await message.reply(reply_text)
    await state.update_data(current_source_id=source_id)
    await message.reply(
        "Вопрос 1: Является ли предложенный объект недвижимости недооцененным?",
        reply_markup=yes_no_keyboard()
    )
    await OfferFeedbackStates.WaitUndersaleAnswer.set()
@dp.message_handler(state=OfferFeedbackStates.WaitUndersaleAnswer)
async def process_undersale_answer(message: types.Message, state: FSMContext):
    if message.text not in ["Да", "Нет"]:
        await message.reply("Пожалуйста, ответьте 'Да' или 'Нет'.")
        return
    # Сохраняем ответ на первый вопрос
    answer1 = 1 if message.text == "Да" else 0
    await state.update_data(answer1=answer1)
    # Задаем второй вопрос
    await message.reply("Вопрос 2: Есть ли расхождения между описанием в объявлении и карточкой объекта?", reply_markup=yes_no_keyboard())
    await OfferFeedbackStates.WaitMismatchAnswer.set()

@dp.message_handler(state=OfferFeedbackStates.WaitMismatchAnswer)
async def process_mismatch_answer(message: types.Message, state: FSMContext):
    if message.text not in ["Да", "Нет"]:
        await message.reply("Пожалуйста, ответьте 'Да' или 'Нет'.")
        return
    # Сохраняем ответ на второй вопрос
    answer2 = 1 if message.text == "Да" else 0
    data = await state.get_data()
    answer1 = data.get('answer1')
    source_id = data.get('current_source_id')
    telegram_id = message.from_user.id
    # Записываем ответы в базу данных
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS basic_feedbacks (
            telegram_id BIGINT,
            source_id TEXT,
            question_1 INTEGER,
            question_2 INTEGER,
            feedback_dt TIMESTAMP
        )
    ''')
    cursor.execute('''
        INSERT INTO basic_feedbacks (telegram_id, source_id, question_1, question_2, feedback_dt)
        VALUES (%s, %s, %s, %s, %s)
    ''', (telegram_id, source_id, answer1, answer2, datetime.datetime.now()))
    conn.commit()
    cursor.close()
    conn.close()
    # Переходим к следующему объекту
    current_index = data.get('current_index', 0) + 1
    await state.update_data(current_index=current_index)
    await show_next_object_onebyone(message, state)


# Извлечение списка объектов с учётом фильтров
def get_filtered_objects(city, filters, sample_size):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name='test_table_2'
    ''')

    query = '''
        SELECT title,
               price_object,
               area,
               address,
               url_link,
               source_id,
               date(parsed_at)
        FROM test_table_2
        WHERE lower(city) = lower(%s)
          AND low_flag = 1
    '''
    params = [city]

    if 'price' in filters:
        price_from, price_to = filters['price']
        query += ' AND price_object BETWEEN %s AND %s'
        params.append(price_from)
        params.append(price_to)

    if 'rooms' in filters:
        r_from, r_to = filters['rooms']
        query += ' AND rooms_count BETWEEN %s AND %s'
        params.append(r_from)
        params.append(r_to)

    query += ' ORDER BY price_object'

    if sample_size is not None:
        query += ' LIMIT %s'
        params.append(sample_size)

    cursor.execute(query, params)
    objects = cursor.fetchall()
    cursor.close()
    conn.close()

    return objects

# ------------------------------------------------------------------------------------------------------------------------------------------------ 
@dp.message_handler(state=OfferObjectsStates.DisplayObjects)
async def handle_display_objects_ready(message: types.Message, state: FSMContext):
    if message.text == "Готово":
        await state.finish()
        await message.reply("Спасибо! Вы можете повторить подбор объектов командой /offerObjects.", reply_markup=main_menu_keyboard())
    else:
        await message.reply("Если вы закончили просмотр объектов, нажмите 'Готово'.")




# ------------------------------------------------------------------------------------------------------------------------------------------------ 
# ------------ Обработка лайков и дизлайков
# ------------------------------------------------------------------------------------------------------------------------------------------------ 
async def process_heart_or_dislike(message: types.Message):
    """
    Обработчик добавления в избранное (❤️) или дизлайка (👎).
    """
    # Вытаскиваем source_id из текста reply_to_message
    reply_text = message.reply_to_message.text
    # Найдём строку 'Source ID: ...'
    source_id = None
    parsed_at = None

    for line in reply_text.split('\n'):
        if line.strip().startswith("Source ID:"):
            source_id = line.split("Source ID:")[1].strip()
        if line.strip().startswith("Дата парсинга:"):
            parsed_at_str = line.split("Дата парсинга:")[1].strip()
            if parsed_at_str and parsed_at_str.lower() != 'none':
                # Попробуем привести к дате
                parsed_at = datetime.datetime.strptime(parsed_at_str, '%Y-%m-%d').date()

    if not source_id:
        await message.reply("Ошибка: не найден source_id у объекта.")
        return

    if message.text == "❤️":
        # Добавляем в избранное
        if is_in_favourite(message.from_user.id, source_id):
            await message.reply("Этот объект уже был добавлен в избранное ранее.")
        else:
            add_to_favourite(message.from_user.id, source_id, parsed_at)
            await message.reply("Объект добавлен в избранное.")
    elif message.text == "👎":
        # Дизлайк
        add_to_dislike(message.from_user.id, source_id)
        await message.reply("Объект помечен как недостоверный.")


# ------------------------------------------------------------------------------------------------------------------------------------------------ 
# ---------------- Обработчик неизвестных команд ----------------
# ------------------------------------------------------------------------------------------------------------------------------------------------ 
@dp.message_handler()
async def handle_unknown_command(message: types.Message):
    if message.text.startswith('/'):
        await message.reply("Неизвестная команда. Введите /home для получения списка команд.", reply_markup=main_menu_keyboard())
    else:
        await message.reply("Пожалуйста, используйте команды бота. Введите /home для получения списка команд.", reply_markup=main_menu_keyboard())



# ------------------------------------------------------------------------------------------------------------------------------------------------ 
# ------------------------------------------------------------------------------------------------------------------------------------------------ 
# ------------------------------------------------------------------------------------------------------------------------------------------------ 
# ------------------------------------------------------------------------------------------------------------------------------------------------ 
# Запуск бота
if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)


