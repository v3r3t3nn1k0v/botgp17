import sqlite3
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('doctors_ratings.db')
    cursor = conn.cursor()
    
    # Создаем таблицу для хранения оценок
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

# Функции для работы с базой данных
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
    
    # Получаем средний рейтинг и количество оценок
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

# Клавиатуры для оценки
def get_visit_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton(text="Да"), KeyboardButton(text="Нет"))
    return keyboard

def get_rating_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(KeyboardButton(text="1"), KeyboardButton(text="2"), KeyboardButton(text="3"))
    keyboard.row(KeyboardButton(text="4"), KeyboardButton(text="5"))
    return keyboard

# Состояния для FSM
class RatingStates(StatesGroup):
    waiting_for_visit_answer = State()
    waiting_for_rating = State()

# Модифицируем обработчик выбора врача
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
                f"{stats_text}"
            )
            
            await callback.message.edit_text(response)
            
            # Предлагаем оценить врача
            await callback.message.answer(
                "Вы посещали этого врача? Оцените качество приема:",
                reply_markup=get_visit_keyboard()
            )
            await state.set_state(RatingStates.waiting_for_visit_answer)
        else:
            await callback.message.edit_text(f"Не удалось получить расписание для врача {doctor['name']}")
    else:
        await callback.message.edit_text("Врач не найден")
    
    await callback.answer()

# Обработчики для оценки врача
@router.message(RatingStates.waiting_for_visit_answer)
async def process_visit_answer(message: types.Message, state: FSMContext):
    data = await state.get_data()
    
    if message.text.lower() == 'да':
        await message.answer(
            "Пожалуйста, оцените качество приема (от 1 до 5):",
            reply_markup=get_rating_keyboard()
        )
        await state.set_state(RatingStates.waiting_for_rating)
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

@router.message(RatingStates.waiting_for_rating)
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