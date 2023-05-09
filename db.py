import sqlite3

# Database setup
DATABASE = 'gVdb.db'

def initialize_database():
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS adc_data (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   timestamp TEXT,
                   num_channels INTEGER,
                   duration REAL,
                   radius REAL,
                   latitude REAL,
                   longitude REAL,
                   location TEXT)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS adc_values (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   event_id INTEGER,
                   channel INTEGER,
                   component TEXT,
                   value REAL,
                   FOREIGN KEY (event_id) REFERENCES adc_data (id))''')
    cur.execute('''CREATE TABLE IF NOT EXISTS users (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   username TEXT UNIQUE,
                   email TEXT UNIQUE,
                   password TEXT,
                   role TEXT)''')
    conn.commit()
    conn.close()


if __name__ == "__main__":
    initialize_database()
