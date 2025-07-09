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
        types.KeyboardButton(text="Помощь")
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