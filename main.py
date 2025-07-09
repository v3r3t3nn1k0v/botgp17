import logging
from typing import Dict, List
import gspread
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, CommandStart
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram import Router
from google.oauth2.service_account import Credentials
from datetime import datetime
import asyncio
import platform
import sys

# Настройка event loop для Windows
if platform.system() == "Windows":
    if sys.version_info >= (3, 8):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
TOKEN = "7764187384:AAHNjQIu7soAzDzgbRI6qfLM0czGekjhN-k"
GOOGLE_SHEETS_CREDENTIALS = "credentials.json"  # Файл с ключами (см. инструкцию ниже)
GOOGLE_SHEET_KEY = "1USOCOY37WTye411sMGmCDWUfx0IXRt7tCYfDVwxtRL0"     # ID вашей Google таблицы

# Инициализация базы данных SQLite
def init_db():
    conn = sqlite3.connect('doctors_ratings.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS ratings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        doctor_id INTEGER NOT NULL,
        doctor_name TEXT NOT NULL,
        visited BOOLEAN NOT NULL,
        rating INTEGER,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    conn.commit()
    conn.close()

init_db()

# Инициализация бота и диспетчера
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# Состояния для FSM
class Form(StatesGroup):
    doctor_name = State()
    select_doctor = State()
    waiting_for_visit_answer = State()
    waiting_for_rating = State()

# Подключение к Google Sheets и обработка расписания
class DoctorSchedule:
    def __init__(self):
        self.sheet = self.connect_to_google_sheets()
        self.last_update = None
        self.doctors_cache = []
        
    def connect_to_google_sheets(self):
        try:
            scope = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive"
            ]
            creds = Credentials.from_service_account_file(GOOGLE_SHEETS_CREDENTIALS, scopes=scope)
            client = gspread.authorize(creds)
            return client.open_by_key(GOOGLE_SHEET_KEY).sheet1
        except Exception as e:
            logger.error(f"Ошибка подключения к Google Sheets: {e}")
            return None
    
    async def get_all_doctors(self) -> List[Dict]:
        """Получает список всех врачей из Google Sheets"""
        try:
            result = [] 
            records = self.sheet.get_all_records()
            for record in records:
                currdoc = { 
                    'id': record['id врача'],
                    'name': record['фио врача'],
                    'specialization': record['специализация']
                }
                result.append(currdoc)
            return result
        except Exception as e:
            logger.error(f"Error getting doctors list: {e}")
            return []
    
    async def get_schedule(self, doctor_name: str) -> Dict:
        """Получает расписание врача из Google Sheets"""
        try:
            records = self.sheet.get_all_records()
            for row in records:
                if row['фио врача'].lower() == doctor_name.lower():
                    return await self.format_schedule(row)
            return None
        except Exception as e:
            logger.error(f"Error getting schedule: {e}")
            return None
    
    async def format_schedule(self, row: Dict) -> Dict:
        """Форматирует расписание из строки таблицы"""
        days = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс']
        schedule = {
            'id': row['id врача'],
            'name': row['фио врача'],
            'specialization': row['специализация'],
            'schedule': {}
        }
        
        for day in days:
            schedule['schedule'][day] = row.get(day, 'выходной')
        
        return schedule
    
    async def get_today_schedule(self, doctor_name: str) -> Dict:
        """Получает расписание врача на сегодня"""
        schedule = await self.get_schedule(doctor_name)
        if not schedule:
            return None
            
        today = datetime.now().weekday()
        days = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс']
        today_day = days[today]
        
        return {
            'id': schedule['id'],
            'name': schedule['name'],
            'specialization': schedule['specialization'],
            'today': today_day,
            'hours': schedule['schedule'][today_day]
        }

# Инициализация модуля расписания
doctor_schedule = DoctorSchedule()

# Функции для работы с рейтингами
def save_rating(user_id: int, doctor_id: int, doctor_name: str, visited: bool, rating: int = None):
    conn = sqlite3.connect('doctors_ratings.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    INSERT INTO ratings (user_id, doctor_id, doctor_name, visited, rating)
    VALUES (?, ?, ?, ?, ?)
    ''', (user_id, doctor_id, doctor_name, visited, rating))
    
    conn.commit()
    conn.close()

def get_doctor_stats(doctor_id: int):
    conn = sqlite3.connect('doctors_ratings.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT AVG(rating), COUNT(rating) 
    FROM ratings 
    WHERE doctor_id = ? AND visited = 1 AND rating IS NOT NULL
    ''', (doctor_id,))
    
    avg_rating, count = cursor.fetchone()
    conn.close()
    
    return {
        'avg_rating': round(avg_rating, 1) if avg_rating else None,
        'rating_count': count or 0
    }

# Клавиатуры
def get_main_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.row(
        types.KeyboardButton(text="Расписание врачей"),
        types.KeyboardButton(text="Сегодняшнее расписание")
    )
    builder.row(
        types.KeyboardButton(text="Контакты поликлиники"),
        types.KeyboardButton(text="FAQ")
    )
    return builder.as_markup(resize_keyboard=True)

def get_visit_keyboard():
    """Клавиатура для вопроса о посещении врача"""
    builder = ReplyKeyboardBuilder()
    builder.add(types.KeyboardButton(text="Да"))
    builder.add(types.KeyboardButton(text="Нет"))
    builder.adjust(2)  # Располагаем кнопки в 2 колонки
    return builder.as_markup(resize_keyboard=True)

def get_rating_keyboard():
    """Клавиатура для оценки врача"""
    builder = ReplyKeyboardBuilder()
    builder.add(types.KeyboardButton(text="1"))
    builder.add(types.KeyboardButton(text="2"))
    builder.add(types.KeyboardButton(text="3"))
    builder.add(types.KeyboardButton(text="4"))
    builder.add(types.KeyboardButton(text="5"))
    builder.adjust(5)  # Все 5 кнопок в один ряд
    return builder.as_markup(resize_keyboard=True)

async def get_doctors_keyboard():
    """Создает инлайн-клавиатуру со списком врачей"""
    doctors = await doctor_schedule.get_all_doctors()
    builder = InlineKeyboardBuilder()
    
    for doctor in doctors:
        builder.button(
            text=f"{doctor['name']} ({doctor['specialization']})", 
            callback_data=f"doctor_{doctor['id']}"
        )
    
    builder.adjust(1)
    return builder.as_markup()

async def getFaq():
    """Создает инлайн-клавиатуру со списком врачей"""
    doctors = await doctor_schedule.get_all_doctors()

     

    builder = InlineKeyboardBuilder()
    
    for doctor in doctors:
        builder.button(
            text=f"{doctor['name']} ({doctor['specialization']})", 
            callback_data=f"doctor_{doctor['id']}"
        )
    
    builder.adjust(1)
    return builder.as_markup()


# Обработчики команд
@router.message(CommandStart())
@router.message(Command("help"))
async def send_welcome(message: types.Message):
    welcome_text = (
        f"Здравствуйте, {message.from_user.first_name}!\n"
        "Я - виртуальный помощник поликлиники. Чем могу помочь?\n\n"
        "Выберите нужный вариант из меню ниже:\n"
        "- Расписание врачей\n"
        "- Сегодняшнее расписание\n"
        "- Контакты поликлиники"
    )
    await message.reply(welcome_text, reply_markup=get_main_keyboard())

@router.message(F.text == "Расписание врачей")
async def schedule_handler(message: types.Message):
    keyboard = await get_doctors_keyboard()
    await message.answer("Выберите врача из списка:", reply_markup=keyboard)

@router.message(F.text == "Сегодняшнее расписание")
async def today_schedule_handler(message: types.Message):
    keyboard = await get_doctors_keyboard()
    await message.answer("Выберите врача для просмотра расписания на сегодня:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("doctor_"))
async def process_doctor_selection(callback: types.CallbackQuery, state: FSMContext):
    doctor_id = int(callback.data.split("_")[1])
    doctors = await doctor_schedule.get_all_doctors()
    doctor = next((doc for doc in doctors if int(doc["id"]) == doctor_id), None)
    
    if doctor:
        await state.update_data(doctor_id=doctor_id, doctor_name=doctor['name'])
        
        # Показываем расписание
        schedule = await doctor_schedule.get_schedule(doctor['name'])
        if schedule:
            # Добавляем статистику по оценкам
            stats = get_doctor_stats(doctor_id)
            stats_text = ""
            if stats['avg_rating']:
                stats_text = f"\n\n⭐ Средняя оценка: {stats['avg_rating']} (на основе {stats['rating_count']} оценок)"
            
            # Создаем inline-кнопку с ссылкой на Горздрав
            builder = InlineKeyboardBuilder()
            builder.add(types.InlineKeyboardButton(
                text="Записаться на прием через Горздрав",
                url="https://gorzdrav.spb.ru/"
            ))
            
            response = (
                f"👨‍⚕️ Врач: {schedule['name']}\n"
                f"📌 Специализация: {schedule['specialization']}\n\n"
                "📅 Расписание:\n"
                f"Пн: {schedule['schedule']['пн']}\n"
                f"Вт: {schedule['schedule']['вт']}\n"
                f"Ср: {schedule['schedule']['ср']}\n"
                f"Чт: {schedule['schedule']['чт']}\n"
                f"Пт: {schedule['schedule']['пт']}\n"
                f"Сб: {schedule['schedule']['сб']}\n"
                f"Вс: {schedule['schedule']['вс']}"
                f"{stats_text}\n\n"
                "Вы можете записаться на прием через Портал Горздрав:"
            )
            
            await callback.message.edit_text(response, reply_markup=builder.as_markup())
            
            # Предлагаем оценить врача
            await callback.message.answer(
                "Вы посещали этого врача? Оцените качество приема:",
                reply_markup=get_visit_keyboard()
            )
            await state.set_state(Form.waiting_for_visit_answer)
        else:
            await callback.message.edit_text(f"Не удалось получить расписание для врача {doctor['name']}")
    else:
        await callback.message.edit_text("Врач не найден")
    
    await callback.answer()

@router.message(Form.waiting_for_visit_answer)
async def process_visit_answer(message: types.Message, state: FSMContext):
    data = await state.get_data()
    
    if message.text.lower() == 'да':
        await message.answer(
            "Пожалуйста, оцените качество приема (от 1 до 5):",
            reply_markup=get_rating_keyboard()
        )
        await state.set_state(Form.waiting_for_rating)
    elif message.text.lower() == 'нет':
        save_rating(
            user_id=message.from_user.id,
            doctor_id=data['doctor_id'],
            doctor_name=data['doctor_name'],
            visited=False
        )
        await message.answer(
            "Спасибо за ответ! Если посетите врача, оцените качество приема.",
            reply_markup=get_main_keyboard()
        )
        await state.clear()
    else:
        await message.answer("Пожалуйста, ответьте 'Да' или 'Нет'")

@router.message(Form.waiting_for_rating)
async def process_rating(message: types.Message, state: FSMContext):
    if message.text.isdigit() and 1 <= int(message.text) <= 5:
        data = await state.get_data()
        
        save_rating(
            user_id=message.from_user.id,
            doctor_id=data['doctor_id'],
            doctor_name=data['doctor_name'],
            visited=True,
            rating=int(message.text)
        )
        
        await message.answer(
            "Спасибо за вашу оценку! Она поможет улучшить качество обслуживания.",
            reply_markup=get_main_keyboard()
        )
        await state.clear()
    else:
        await message.answer("Пожалуйста, выберите оценку от 1 до 5")

@router.message(F.text == "Контакты поликлиники")
async def contacts_handler(message: types.Message):
    response_text = (
        "📞 Контактный центр: +7 (812) 246-55-55\n"
        "🏥 Адрес: пр. Металлистов, д. 56\n"
        "🕒 Часы работы: пн-пт 8:00-20:00, сб 9:00-15:00\n"
        "🌐 Сайт: https://p17-spb.ru/"
    )
    await message.reply(response_text)



@router.message(F.text == "FAQ")
async def today_schedule_handler(message: types.Message):
    keyboard = await get_doctors_keyboard()
    await message.answer("Выберите врача для просмотра расписания на сегодня:", reply_markup=keyboard)

@router.message()
async def unknown_message(message: types.Message):
    await message.reply(
        "Извините, я не понял ваш запрос. Пожалуйста, используйте кнопки меню.",
        reply_markup=get_main_keyboard()
    )

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())

























# # Настройка логирования
# logging.basicConfig(
#     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
#     level=logging.INFO
# )
# logger = logging.getLogger(__name__)

# # Словарь с вопросами и ответами из скриптов
# FAQ_SCRIPTS = {
#     "Запись на прием к врачу": "Записаться на прием можно несколькими способами:\n\n*Онлайн:* Через Портал Горздрав (https://gorzdrav.spb.ru/). Вам понадобится подтвержденная учетная запись.\n\n*По телефону:* Позвоните в колл-центр нашей поликлиники: +7 (812) 246-55-55.\n\n*Лично:* В регистратуре поликлиники или через инфомат в холле.\n\n*Важно:* При первичном обращении в этом году сначала нужен прием терапевта/врача общей практики (ВОП). К узким специалистам чаще всего направляет терапевт/ВОП.",
#     "Узнать расписание врача": "Актуальное расписание врачей доступно:\n\n*Онлайн:* Через Портал Горздрав (https://gorzdrav.spb.ru/).\n\n*На сайте поликлиники:* Раздел 'Расписание врачей' на нашем официальном сайте (https://p17-spb.ru/raspisanie/).\n\n*По телефону:* Позвоните в колл-центр нашей поликлиники: +7 (812) 246-55-55.\n\n*В холле поликлиники:* На информационных стендах или терминалах (инфоматах). Расписание может меняться, онлайн-источники наиболее актуальны.",
#     "Вызов врача на дом": "Вызвать участкового терапевта на дом можно:\n\n*По телефону:* по номеру 122.\n\n*ВАЖНО:* Если у вас или у близкого человека **сильная боль, затрудненное дыхание, признаки острого состояния (боль в груди, внезапная слабость, потеря сознания и т.п.) -- НЕМЕДЛЕННО звоните по номеру экстренных служб 103 или 112!** Чат-бот не предназначен для вызова скорой помощи.",
#     "Прикрепиться к поликлинике": "Вы можете прикрепиться к нашей поликлинике:\n\nВ соответствии с Законом «Об основах охраны здоровья граждан в Российской Федерации» каждый житель Санкт-Петербурга имеет право на выбор медицинской организации. Прикрепиться к поликлинике можно не чаще одного раза в год (за исключением случаев изменения места жительства или места пребывания). Для прикрепления необходимо обратиться к страховому представителю в наших подразделениях.\n\nПодробные адреса и время работы страховых представителей можно уточнить в регистратуре или на сайте поликлиники.",
#     "Получить справку / Выписку": "Порядок получения справок и выписок:\n\n*Многие справки* (например, для бассейна, санатория) оформляются у вашего участкового терапевта/ВОП или профильного врача после осмотра. Запишитесь на прием.\n\n*Выписка из амбулаторной карты (форма 027/у):* Заказывается у лечащего врача или через регистратуру. Уточните порядок и сроки подготовки по телефону +7 (812) 246-55-55.\n\n*Справки по форме 086/у* (для поступления) требуют прохождения врачебной комиссии (ВК) в поликлинике.",
#     "Получить результаты анализов": "Доступ к результатам анализов и исследований:\n\n*Электронная Медицинская Карта (ЭМК):* Основной способ. Просматривайте в личном кабинете на Портале Госуслуг (www.gosuslugi.ru) или в приложении 'Госуслуги.Здоровье'. Результаты появляются там после обработки врачом лаборатории/кабинета.\n\n*На приеме у врача:* Ваш лечащий врач прокомментирует результаты на очередном приеме.\n\n*В поликлинике:* Некоторые результаты (например, флюорографии) могут быть доступны на информационном стенде или у врача-рентгенолога/фтизиатра.",
#     "График работы поликлиники": "График работы нашей поликлиники:\n\nПо будням: с 08.00 до 20.00. Суббота: 09.00-15.00. Воскресенье: Уточняйте по т.246-55-55.",
#     "Получить больничный лист": "Листок нетрудоспособности (больничный):\n\n*Открывается врачом:* Терапевтом/ВОП, врачом-специалистом или врачом скорой помощи (на короткий срок) при наличии медицинских показаний.\n\n*При амбулаторном лечении:* Открывается в день обращения/осмотра, подтверждающего нетрудоспособность. Продлевается на последующих приемах.\n\n*Электронный больничный (ЭЛН):* С 2025 года подавляющее большинство больничных оформляется электронно. Данные автоматически передаются в ФСС.",
#     "Потерял полис ОМС": "Если вы потеряли полис ОМС:\n\n1. *Вы все равно имеете право на помощь!* Предоставьте паспорт и СНИЛС в регистратуру. Ваши данные проверят по единому реестру застрахованных.\n\n2. *Восстановление:* Обратитесь в свою страховую медицинскую организацию (СМО), которая выдала полис. Контакты СМО можно узнать в регистратуре поликлиники или на сайте Территориального фонда ОМС вашего региона.\n\n3. *Электронный полис:* Если у вас есть подтвержденная учетная запись на Госуслугах, ваш электронный полис ОМС доступен в приложении 'Госуслуги.Здоровье'.",
#     "Запись на диспансеризацию": "Диспансеризация очень важна для контроля вашего здоровья! Записаться можно:\n\n*Через участкового терапевта/ВОП:* Запишитесь на прием, врач определит объем обследований по вашему возрасту и анамнезу.\n\n*Самостоятельно:* Через Портал Госуслуг (www.gosuslugi.ru) или приложение 'Госуслуги.Здоровье' выберите услугу \"Прохождение диспансеризации\".\n\n*График:* Диспансеризация проводится 1 раз в 3 года для лиц 18-39 лет, ежегодно - для лиц 40 лет и старше.",
#     "Контакты поликлиники": "Контактная информация нашей поликлиники:\n\n*Официальное название:* СПБ ГБУЗ ГП №17\n\n*Адреса отделений:*\n- Отделение №17: пр. Металлистов, д. 56\n- Отделение №10: пр. Шаумяна, д. 51\n- Отделение №18: ул. Бестужевская, д. 79\n\n*Телефон Контакт-центра:* (812) 246-55-55\n\n*Официальный сайт:* https://p17-spb.ru/",
#     "Флюорография": "Для прохождения исследования ФЛГ предварительная запись не нужна. Вам нужно подойти в часы работы кабинета ФЛГ в ПО №10 (пр. Шаумяна,д.51), либо в ПО №18 (ул. Бестужевская, д. 79) -- понедельник, среда, пятница с 08.00 до 13.00, вторник, четверг с 14.00 до 19.00. Принимают с направлением от врача, если нет направления, то обратиться в регистратуру для получения талона. При себе иметь паспорт.\n\nВНИМАНИЕ! В ПО №17 (пр. Металлистов, д.56) кабинет ФЛГ ЗАКРЫТ на плановую замену оборудования.",
#     "Экстренная помощь": "❗ **ВНИМАНИЕ! ЭТО ОПАСНОЕ СОСТОЯНИЕ!** ❌ ЧАТ-БОТ НЕ МОЖЕТ ВЫЗВАТЬ СКОРУЮ ПОМОЩЬ. ❌\n\n*НЕМЕДЛЕННО ПОЗВОНИТЕ ПО ТЕЛЕФОНУ:*\n*103 или 112* (с мобильного)\n*03* (со стационарного телефона)\n\nЧетко сообщите диспетчеру: **1. ЧТО СЛУЧИЛОСЬ? 2. ГДЕ ВЫ НАХОДИТЕСЬ? (Адрес!) 3. КТО ПОСТРАДАВШИЙ? (ФИО, возраст, состояние).**\n\n*НЕ ТЕРЯЙТЕ ВРЕМЯ НА ЧАТ С БОТОМ! ЗВОНИТЕ 103/112 СЕЙЧАС ЖЕ!*"
# }

# async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     """Отправляет приветственное сообщение с кнопкой FAQ"""
#     keyboard = [
#         [InlineKeyboardButton("FAQ - Частые вопросы", callback_data="open_faq")]
#     ]
#     reply_markup = InlineKeyboardMarkup(keyboard)
#     await update.message.reply_text(
#         "Добро пожаловать в бот поликлиники №17! "
#         "Нажмите на кнопку ниже, чтобы открыть список часто задаваемых вопросов.",
#         reply_markup=reply_markup
#     )

# async def open_faq(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     """Открывает меню FAQ с инлайн-клавиатурой"""
#     query = update.callback_query
#     await query.answer()
    
#     # Создаем кнопки для FAQ (по 2 в ряд)
#     keyboard = []
#     faq_items = list(FAQ_SCRIPTS.keys())
    
#     for i in range(0, len(faq_items), 2):
#         row = []
#         if i < len(faq_items):
#             row.append(InlineKeyboardButton(faq_items[i], callback_data=f"faq_{i}"))
#         if i+1 < len(faq_items):
#             row.append(InlineKeyboardButton(faq_items[i+1], callback_data=f"faq_{i+1}"))
#         keyboard.append(row)
    
#     # Добавляем кнопку "Назад" если это не главное меню
#     if query.data != "open_faq":
#         keyboard.append([InlineKeyboardButton("Назад", callback_data="open_faq")])
    
#     reply_markup = InlineKeyboardMarkup(keyboard)
#     await query.edit_message_text(
#         text="Выберите интересующий вас вопрос из списка:",
#         reply_markup=reply_markup
#     )

# async def faq_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     """Отправляет ответ на выбранный вопрос FAQ"""
#     query = update.callback_query
#     await query.answer()
    
#     # Получаем индекс вопроса из callback_data
#     question_index = int(query.data.split("_")[1])
#     question = list(FAQ_SCRIPTS.keys())[question_index]
#     answer = FAQ_SCRIPTS[question]
    
#     # Создаем клавиатуру с кнопкой "Назад"
#     keyboard = [[InlineKeyboardButton("Назад", callback_data="open_faq")]]
#     reply_markup = InlineKeyboardMarkup(keyboard)
    
#     await query.edit_message_text(
#         text=f"<b>{question}</b>\n\n{answer}",
#         reply_markup=reply_markup,
#         parse_mode="HTML"
#     )

# async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     """Обрабатывает текстовые сообщения"""
#     text = update.message.text.lower()
    
#     # Проверяем триггерные слова для экстренной помощи
#     emergency_words = ["плохо", "скорая", "умираю", "боль", "давление", "травма", "сердце", "задыхаюсь"]
#     if any(word in text for word in emergency_words):
#         await update.message.reply_text(
#             "❗ **ВНИМАНИЕ! ЭТО ОПАСНОЕ СОСТОЯНИЕ!** ❌ ЧАТ-БОТ НЕ МОЖЕТ ВЫЗВАТЬ СКОРУЮ ПОМОЩЬ. ❌\n\n"
#             "*НЕМЕДЛЕННО ПОЗВОНИТЕ ПО ТЕЛЕФОНУ:*\n"
#             "*103 или 112* (с мобильного)\n"
#             "*03* (со стационарного телефона)\n\n"
#             "Четко сообщите диспетчеру: **1. ЧТО СЛУЧИЛОСЬ? 2. ГДЕ ВЫ НАХОДИТЕСЬ? (Адрес!) 3. КТО ПОСТРАДАВШИЙ? (ФИО, возраст, состояние).**\n\n"
#             "*НЕ ТЕРЯЙТЕ ВРЕМЯ НА ЧАТ С БОТОМ! ЗВОНИТЕ 103/112 СЕЙЧАС ЖЕ!*",
#             parse_mode="HTML"
#         )
#     else:
#         # Предлагаем открыть FAQ для других сообщений
#         keyboard = [[InlineKeyboardButton("FAQ - Частые вопросы", callback_data="open_faq")]]
#         reply_markup = InlineKeyboardMarkup(keyboard)
#         await update.message.reply_text(
#             "Извините, я не совсем понял ваш вопрос. Пожалуйста, выберите интересующий вас вопрос из списка FAQ:",
#             reply_markup=reply_markup
#         )

