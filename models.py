import sqlite3
from db import DATABASE

class User:
    def __init__(self, id, username, email, password, role='user'):
        self.id = id
        self.username = username
        self.email = email
        self.password = password
        self.role = role


    @classmethod
    def get(cls, user_id):
        conn = sqlite3.connect(DATABASE)
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE id=?", (user_id,))
        user = cur.fetchone()
        conn.close()
        if user:
            return cls(*user)
        return None

    @classmethod
    def find_by_username(cls, username):
        conn = sqlite3.connect(DATABASE)
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username=?", (username,))
        user = cur.fetchone()
        conn.close()
        if user:
            return cls(*user)
        return None
    
    @staticmethod
    def find_by_email(email):
        conn = sqlite3.connect(DATABASE)
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email=?", (email,))
        row = cur.fetchone()
        conn.close()

        if row:
            return User(row[0], row[1], row[2], row[3], row[4])
        else:
            return None
    
    @classmethod
    def add_user(cls, user):
        conn = sqlite3.connect(DATABASE)
        cur = conn.cursor()
        cur.execute("INSERT INTO users (username, password, email) VALUES (?, ?, ?)", (user.username, user.password, user.email))
        conn.commit()
        conn.close()

