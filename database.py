import sqlite3
from google.oauth2.service_account import Credentials
import gspread
from typing import Dict, List

databaseFilename = 'database.db'





def createConnection():
    conn = sqlite3.connect(databaseFilename)
    cursor = conn.cursor()
    return conn, cursor 

def createDoctorsTable():
    conn, cursor = createConnection()
    cursor.execute('''
        CREATE TABLE  IF NOT EXISTS doctors(
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        doctor_name TEXT  NOT NULL, 
        speciality TEXT NOT NULL, 
        mon TEXT NOT NULL,
        tue TEXT NOT NULL, 
        wed TEXT NOT NULL, 
        thu TEXT NOT NULL,
        fri TEXT NOT NULL, 
        sat TEXT NOT NULL, 
        sun TEXT NOT NULL)
    ''')
    conn.commit()


def createRatingsTable():
    conn, cursor = createConnection()
    cursor.execute('''
        CREATE TABLE  IF NOT EXISTS ratings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        doctor_id INTEGER NOT NULL,
        doctor_name TEXT NOT NULL,
        visited BOOLEAN NOT NULL,
        rating INTEGER,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, 
        text_report TEXT
    )
    ''')
    conn.commit()

def initDatabase(): 
    createDoctorsTable()
    createRatingsTable()


def setOrUpdateDoctorRecord(name: str, spec: str ,mon: str, tue: str, wed: str , thu: str , fri:str , sat: str, sun: str):
    conn, cursor = createConnection()
    cursor.execute("SELECT id FROM doctors WHERE doctor_name = ?", (name,))
    existing = cursor.fetchone()

    if existing:
        cursor.execute('''
            UPDATE doctors SET
                speciality = ?,
                mon = ?, tue = ?, wed = ?, thu = ?,
                fri = ?, sat = ?, sun = ?
            WHERE doctor_name = ?
        ''', (spec, mon, tue, wed, thu, fri, sat, sun, name))
    else:
        cursor.execute('''
            INSERT INTO doctors (
                doctor_name, speciality,
                mon, tue, wed, thu, fri, sat, sun
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (name, spec, mon, tue, wed, thu, fri, sat, sun))

    conn.commit()

def getAllDoctorsForTimetable():
    conn, cursor = createConnection()
    cursor.execute('''
    SELECT id, doctor_name , speciality FROM doctors;   
    ''')
    result = cursor.fetchall()
    return result


def getDoctorsWithSurname(surname: str): 
    conn, cursor = createConnection()
    cursor.execute("""
                SELECT id, doctor_name, speciality 
                FROM doctors 
                WHERE doctor_name LIKE ? || '%'
                ORDER BY doctor_name
                LIMIT 20
            """, (surname,))
    return cursor.fetchall()
