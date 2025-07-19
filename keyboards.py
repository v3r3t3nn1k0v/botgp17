from aiogram import Bot, Dispatcher, types
from texts import Buttons
from database import getAllDoctorsForTimetable, getDoctorsWithSurname
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


beginningKeyboard = types.ReplyKeyboardMarkup(
    keyboard=[
        [types.KeyboardButton(text=Buttons.TIMETABLE_BUTTON) , types.KeyboardButton(text=Buttons.ADRESSES_BUTTON)], 
        [types.KeyboardButton(text=Buttons.CONTACTS_BUTTON) , types.KeyboardButton(text=Buttons.DOCS_BUTTON)] , 
        [types.KeyboardButton(text=Buttons.FAQ_BUTTON)]
    ]
)



def generateDoctorsInlineKeyboard(page: int = 0):
    doctors = getAllDoctorsForTimetable()
    builder = InlineKeyboardBuilder()
    
    # Разбиваем список на страницы по 7 врачей
    doctors_per_page = 7
    total_pages = (len(doctors) + doctors_per_page - 1) // doctors_per_page
    start_idx = page * doctors_per_page
    end_idx = start_idx + doctors_per_page
    page_doctors = doctors[start_idx:end_idx]
    
    # Добавляем кнопки врачей
    for doctor_id, name, speciality in page_doctors:
        builder.button(
            text=f"{name} ({speciality})", 
            callback_data=f"doctor_{doctor_id}"
        )
    
    # Добавляем кнопки пагинации
    pagination_buttons = []
    if page > 0:
        pagination_buttons.append(
            InlineKeyboardButton(text="◀ Назад", callback_data=f"page_{page-1}")
        )
    if page < total_pages - 1:
        pagination_buttons.append(
            InlineKeyboardButton(text="Вперед ▶", callback_data=f"page_{page+1}")
        )
    
    if pagination_buttons:
        builder.row(*pagination_buttons)
    
    # Добавляем кнопку "Главное меню"
    builder.row(
        InlineKeyboardButton(text="Найти по фамилии", callback_data="search_by_surname")
    )
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


def generateDoctorsInlineKeyboardWithSearch(name: str):
    doctors = getDoctorsWithSurname(name)
    builder = InlineKeyboardBuilder()
    for doctor_id, name, speciality  in doctors: 
        builder.button(text=f"{name} ({speciality})", 
            callback_data=f"doctor_{doctor_id}")
    builder.adjust(2,2,2)

    return builder.as_markup()