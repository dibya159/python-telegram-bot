# -*- coding: utf-8 -*-
import telebot
import sqlite3
import difflib
import os
import sys
import time
import threading
import random

TOKEN = '8857677089:AAGN57W0U0VYPhZopRySa7DViyLtZ-2mAKM'
ADMIN_ID = 123456789
OWNER_PASSWORD = "dibya159t800ultra"

bot = telebot.TeleBot(TOKEN)
quiz_sessions = {}
user_state = {}

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('quiz_bot.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, points INTEGER DEFAULT 0)')
    cursor.execute('CREATE TABLE IF NOT EXISTS welcome_status (user_id INTEGER PRIMARY KEY)')
    cursor.execute('CREATE TABLE IF NOT EXISTS questions (id INTEGER PRIMARY KEY AUTOINCREMENT, q TEXT, a TEXT)')
    conn.commit()
    conn.close()

def add_question_to_db(q, a):
    conn = sqlite3.connect('quiz_bot.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO questions (q, a) VALUES (?, ?)", (q, a))
    conn.commit()
    conn.close()

def get_random_questions(n=10):
    conn = sqlite3.connect('quiz_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT q, a FROM questions ORDER BY RANDOM() LIMIT ?", (n,))
    rows = cursor.fetchall()
    conn.close()
    return [{"q": r[0], "a": r[1]} for r in rows]

# --- LEADERBOARD FUNCTIONS ---
def update_user_score(user_id, username, points_to_add):
    conn = sqlite3.connect('quiz_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT points FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row:
        cursor.execute("UPDATE users SET points = points + ?, username = ? WHERE user_id = ?", (points_to_add, username, user_id))
    else:
        cursor.execute("INSERT INTO users (user_id, username, points) VALUES (?, ?, ?)", (user_id, username, points_to_add))
    conn.commit()
    conn.close()

def get_top_10():
    conn = sqlite3.connect('quiz_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    rows = cursor.fetchall()
    conn.close()
    return rows

# --- QUIZ HANDLERS ---
@bot.message_handler(commands=['start'])
def start_quiz(message):
    chat_id = message.chat.id
    if chat_id in quiz_sessions and quiz_sessions.get(chat_id, {}).get('active'):
        bot.reply_to(message, "⚠️ *Game already running hai!*")
        return
    
    user_id = message.from_user.id
    conn = sqlite3.connect('quiz_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM welcome_status WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        bot.send_message(chat_id, "🔥 *WELCOME TO GK QUIZ!* \nRules: 10 questions, 30s each.")
        cursor.execute("INSERT INTO welcome_status (user_id) VALUES (?)", (user_id,))
        conn.commit()
    conn.close()

    questions = get_random_questions(10)
    if len(questions) < 10:
        bot.send_message(chat_id, "❌ *Error:* Bot mein kam se kam 10 sawal hone chahiye.")
        return

    quiz_sessions[chat_id] = {
        'active': True, 'questions': questions, 'current_q': 0, 
        'score': 0, 'is_answered': False
    }
    send_question(chat_id)

@bot.message_handler(commands=['stop'])
def stop_quiz(message):
    if message.chat.id in quiz_sessions:
        if 'timer' in quiz_sessions[message.chat.id]: quiz_sessions[message.chat.id]['timer'].cancel()
        quiz_sessions.pop(message.chat.id)
        bot.send_message(message.chat.id, "⏹ *Quiz band kar diya gaya hai.*")

# --- ADDED LEADERBOARD COMMAND ---
@bot.message_handler(commands=['leaderboard'])
def show_leaderboard(message):
    top_players = get_top_10()
    if not top_players:
        bot.send_message(message.chat.id, "📊 *Leaderboard filhal khali hai.*")
    else:
        text = "🏆 *TOP 10 LEADERBOARD* 🏆\n\n"
        for i, (name, pts) in enumerate(top_players, 1):
            text += f"{i}. {name or 'Unknown'} — {pts} PTS\n"
        bot.send_message(message.chat.id, text, parse_mode="Markdown")

# --- QUIZ LOGIC ---
def send_question(chat_id):
    session = quiz_sessions.get(chat_id)
    if not session or session['current_q'] >= 10:
        end_quiz(chat_id)
        return
    session['is_answered'] = False
    q_data = session['questions'][session['current_q']]
    bot.send_message(chat_id, f"❓ *Q {session['current_q']+1}/10:* {q_data['q']}")
    session['timer'] = threading.Timer(30.0, lambda: handle_timeout(chat_id))
    session['timer'].start()

def handle_timeout(chat_id):
    if chat_id in quiz_sessions:
        session = quiz_sessions[chat_id]
        correct = session['questions'][session['current_q']]['a']
        bot.send_message(chat_id, f"⏰ *Time's up!*\nSahi jawab tha: *{correct}*")
        session['current_q'] += 1
        time.sleep(2)
        send_question(chat_id)

def end_quiz(chat_id):
    session = quiz_sessions.get(chat_id)
    if session:
        # Score save karna (1 sahi jawab = 10 points)
        uname = bot.get_chat_member(chat_id, chat_id).user.first_name if chat_id > 0 else "Group_User"
        update_user_score(chat_id, uname, session['score'] * 10)
        bot.send_message(chat_id, f"🏁 *Quiz Khatam!* \nSahi jawab: {session['score']}/10. (Points saved)")
        quiz_sessions.pop(chat_id, None)

@bot.message_handler(func=lambda m: m.chat.id in quiz_sessions and not quiz_sessions[m.chat.id]['is_answered'])
def check_answer(message):
    session = quiz_sessions[message.chat.id]
    correct = session['questions'][session['current_q']]['a']
    if difflib.get_close_matches(message.text.lower(), [correct.lower()], cutoff=0.8):
        session['is_answered'] = True
        session['timer'].cancel()
        session['score'] += 1
        bot.reply_to(message, "✅ *Sahi Jawab!*")
        session['current_q'] += 1
        time.sleep(1)
        send_question(message.chat.id)

# --- OWNER COMMANDS ---
@bot.message_handler(commands=['addq'])
def add_question_start(message):
    bot.send_message(message.chat.id, "🔐 *Password enter karein:*")
    user_state[message.chat.id] = {'step': 'password'}

@bot.message_handler(func=lambda m: m.chat.id in user_state)
def handle_owner_input(message):
    chat_id = message.chat.id
    state = user_state[chat_id]
    if state['step'] == 'password':
        if message.text == OWNER_PASSWORD:
            state['step'] = 'ask_q'
            bot.send_message(chat_id, "✅ *Sahi password!* Ab Question likhein:")
        else:
            bot.send_message(chat_id, "❌ *Galat password!*")
            user_state.pop(chat_id)
    elif state['step'] == 'ask_q':
        state['q'] = message.text
        state['step'] = 'ask_a'
        bot.send_message(chat_id, "📝 *Ab Answer likhein:*")
    elif state['step'] == 'ask_a':
        add_question_to_db(state['q'], message.text)
        bot.send_message(chat_id, "🎉 *Question and Answer added successfully!*")
        user_state.pop(chat_id)

if __name__ == '__main__':
    init_db()
    bot.infinity_polling()
