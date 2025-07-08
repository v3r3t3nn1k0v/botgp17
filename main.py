import logging
from typing import Dict, List
import gspread
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
            # Обновляем кэш не чаще чем раз в 5 минут
            result = [] 
            records = self.sheet.get_all_records()
            print(records)
            for record in records:
                print(record['фио врача'])
                currdoc = { 'id': record['id врача'],
                    'name': record['фио врача'],
                    'specialization': record['специализация']}
                print(currdoc)
                result.append(currdoc)
                currdoc = {}
            print(result)
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
            
        today = datetime.now().weekday()  # 0-пн, 1-вт, ..., 6-вс
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

async def get_doctors_keyboard():
    """Создает инлайн-клавиатуру со списком врачей"""
    doctors = await doctor_schedule.get_all_doctors()
    builder = InlineKeyboardBuilder()
    print(f"Получено врачей: {len(doctors)}")
    for doctor in doctors:
        print(f"Врач: {doctor['name']}, ID: {doctor['id']}")
    for doctor in doctors:
        builder.button(
            text=f"{doctor['name']} ({doctor['specialization']})", 
            callback_data=f"doctor_{doctor['id']}"
        )
    
    builder.adjust(1)
    print(builder.as_markup())
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

@router.callback_query(F.data.startswith("doctor_"))
async def process_doctor_selection(callback: types.CallbackQuery):
    doctor_id = int(callback.data.split("_")[1])
    doctors = await doctor_schedule.get_all_doctors()
    doctorInfo = {}
    for doctor in doctors:
        if int(doctor["id"]) == doctor_id:
            doctorInfo = doctor
            break
    
    if doctor:
        print(doctorInfo)
        schedule = await doctor_schedule.get_schedule(doctorInfo['name'])
        if schedule:
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
            )
        else:
            response = f"Не удалось получить расписание для врача {doctor['name']}"
    else:
        response = "Врач не найден"
    
    await callback.message.edit_text(response)
    await callback.answer()

@router.message(F.text == "Сегодняшнее расписание")
async def today_schedule_handler(message: types.Message):
    keyboard = await get_doctors_keyboard()
    await message.answer("Выберите врача для просмотра расписания на сегодня:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("doctor_"))
async def process_doctor_selection(callback: types.CallbackQuery):
    doctor_id = int(callback.data.split("_")[1])
    doctors = await doctor_schedule.get_all_doctors()
    doctorInfo = {}
    for doctor in doctors:
        if int(doctor["id"]) == doctor_id:
            doctorInfo = doctor
            break
    
    if doctorInfo:
        print(doctorInfo)
        schedule = await doctor_schedule.get_schedule(doctorInfo['name'])
        if schedule:
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
                f"Вс: {schedule['schedule']['вс']}\n\n"
                "Вы можете записаться на прием через Портал Горздрав:"
            )
            
            await callback.message.edit_text(response, reply_markup=builder.as_markup())
        else:
            await callback.message.edit_text(f"Не удалось получить расписание для врача {doctorInfo['name']}")
    else:
        await callback.message.edit_text("Врач не найден")
    
    await callback.answer()

@router.callback_query(F.data.startswith("doctor_"))
async def process_today_schedule(callback: types.CallbackQuery):
    doctor_id = callback.data.split("_")[1]
    doctors = await doctor_schedule.get_all_doctors()
    doctor = next((doc for doc in doctors if doc['id'] == doctor_id), None)
    
    if doctor:
        schedule = await doctor_schedule.get_today_schedule(doctor['name'])
        if schedule:
            # Создаем inline-кнопку с ссылкой на Горздрав
            builder = InlineKeyboardBuilder()
            builder.add(types.InlineKeyboardButton(
                text="Записаться на прием через Горздрав",
                url="https://gorzdrav.spb.ru/"
            ))
            
            response = (
                f"👨‍⚕️ Врач: {schedule['name']}\n"
                f"📌 Специализация: {schedule['specialization']}\n\n"
                f"📅 Сегодня ({schedule['today']}): {schedule['hours']}\n\n"
                "Вы можете записаться на прием через Портал Горздрав:"
            )
            
            await callback.message.edit_text(response, reply_markup=builder.as_markup())
        else:
            await callback.message.edit_text(f"Врач {doctor['name']} сегодня не принимает")
    else:
        await callback.message.edit_text("Врач не найден")
    
    await callback.answer()

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