from flask import Flask, render_template, request, jsonify
import time
import platform
systemOS = platform.system()
if systemOS == "Linux":
    import ADS1263
    import RPi.GPIO as GPIO
import plotly.graph_objs as go
import plotly
import json
import sqlite3
from contextlib import closing
from datetime import datetime
from flask_socketio import SocketIO, emit
from flask import copy_current_request_context
from flask_socketio import Namespace, emit
from collections import defaultdict


REF = 5.08          # Modify according to actual voltage
                    # external AVDD and AVSS(Default), or internal 2.5V

try:
    ADC = ADS1263.ADS1263()
    if (ADC.ADS1263_init_ADC1('ADS1263_7200SPS') == -1):
        ADC.ADS1263_Exit()
        print("Failed to initialize ADC1")
        exit()
    ADC.ADS1263_SetMode(1)
except:
    pass

app = Flask(__name__)
socketio = SocketIO(app)

sampling_rate = 128  # Hz
sleep_duration = 1 / sampling_rate

# Database setup
DATABASE = 'adc_data.db'

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
                   value REAL,
                   FOREIGN KEY (event_id) REFERENCES adc_data (id))''')
    conn.commit()
    conn.close()




initialize_database()

@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/dashboard.html')
def dashboard():
    return render_template('dashboard.html')

@app.route('/dashboard3D.html')
def dashboard3D():
    return render_template('dashboard3D.html')

@app.route('/icons.html')
def icons():
    return render_template('icons.html')

@app.route('/typography.html')
def typography():
    return render_template('typography.html')

@app.route('/map.html')
def map():
    # Fetch data from the database
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, timestamp, num_channels, duration, radius, latitude, longitude FROM adc_data")
    data = cursor.fetchall()
    conn.close()

    # Render the map.html template and pass the data
    return render_template('map.html', data=data)

@app.route('/user.html')
def user():
    return render_template('user.html')

@app.route('/rtl.html')
def rtl():
    return render_template('rtl.html')

class StoreDataNamespace(Namespace):
    def on_connect(self):
        print('Client connected to store_data_progress namespace')

    def on_disconnect(self):
        print('Client disconnected from store_data_progress namespace')

    def on_show_storage_progress(self):
        self.emit('show_storage_progress')


socketio.on_namespace(StoreDataNamespace('/store_data_progress'))

@app.route('/collect_data', methods=['POST'])
def collect_data():
    duration = float(request.form['duration'])
    radius = float(request.form['radius'])
    latitude = float(request.form['latitude'])
    longitude = float(request.form['longitude'])
    location = request.form['location']
    ADC_Value_List, sampling_rate = collect_adc_data(duration, radius, latitude, longitude, location)

    graphJSON = create_plot(ADC_Value_List)
    return jsonify({'graphJSON': json.loads(graphJSON), 'sampling_rate': sampling_rate})

def collect_adc_data(duration, radius, lat, lon, location):
    global ADC
    channelList = [0, 1, 2, 3]
    start_time = time.perf_counter()
    ADC_Value_List = []

    sampling_rate = 128  # Hz
    interval = 1 / sampling_rate
    next_sample_time = start_time + interval
    no_sample = duration * sampling_rate
    while len(ADC_Value_List) < no_sample:
        current_time = time.perf_counter()
        if current_time >= next_sample_time:
            ADC_Value = ADC.ADS1263_GetAll(channelList)
            ADC_Value_List.append(ADC_Value)
            next_sample_time = current_time + interval

    actual_sampling_rate = len(ADC_Value_List) / (current_time - start_time)
    
    converted_data = {channel: [] for channel in channelList}
    for data in ADC_Value_List:
        for channel, value in enumerate(data):
            if value >> 31 == 1:
                converted_data[channel].append(-(REF * 2 - value * REF / 0x80000000))
            else:
                converted_data[channel].append(value * REF / 0x7fffffff)

    # Store the event information in the database
    timestamp = int(time.time())
    num_channels = len(channelList)
    
    @copy_current_request_context
    def store_data_task():
        store_event_in_database(socketio, timestamp, num_channels, duration, radius, lat, lon, converted_data, location)
        socketio.emit('storage_complete', {'status': 'success'}, namespace='/store_data_progress')

    # Show the storage progress bar
    socketio.emit('show_storage_progress', {}, namespace='/store_data_progress')
    socketio.start_background_task(store_data_task)
    
    return converted_data, actual_sampling_rate



def store_event_in_database(socketio, timestamp, num_channels, duration, radius, lat, lon, converted_data, location):
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()

    datetime_string = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')

    cur.execute("INSERT INTO adc_data (timestamp, num_channels, duration, radius, latitude, longitude, location) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (datetime_string, num_channels, duration, radius, lat, lon, location))
    event_id = cur.lastrowid

    total_values = sum(len(channel_data) for channel_data in converted_data.values())
    stored_values = 0

    for channel, values in converted_data.items():
        for value in values:
            cur.execute("INSERT INTO adc_values (event_id, channel, value) VALUES (?, ?, ?)",
                        (event_id, channel, value))

            stored_values += 1
            progress = stored_values / total_values * 100
                                                  
            # Emit progress update
            socketio.emit('store_data_progress', {'progress': progress}, namespace='/store_data_progress')

    conn.commit()
    conn.close()


def create_plot(converted_data):
    channelList = [0, 1, 2, 3]
    time_axis = list(range(len(converted_data[0])))  # assuming channel 0 has data


    traces = []
    for channel in channelList:
        traces.append(go.Scatter(x=time_axis, y=converted_data[channel], mode='lines', name=f'ADC1 IN{channel}'))

    layout = go.Layout(
        title='ADC1 Waveform',
        xaxis=dict(title='Sample number'),
        yaxis=dict(title='ADC Value (V)', range=[0, 1]),
        autosize=True,
        height=600,
        width=None,
        legend=dict(
            x=0.85,
            y=0.95,
        )
        )
    
    fig = go.Figure(data=traces, layout=layout)
    graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
    return graphJSON

@app.route('/tables.html')
def adc_data():
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("SELECT * FROM adc_data ORDER BY timestamp DESC")
    data = cur.fetchall()
    conn.close()
    return render_template('tables.html', data=data)

@app.route('/get_waveform_data', methods=['GET'])
def get_waveform_data():
    event_id = request.args.get('id', type=int)

    if not event_id:
        return jsonify({'error': 'Event ID is required'}), 400

    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()

    cur.execute("SELECT channel, value FROM adc_values WHERE event_id = ? ORDER BY channel, id", (event_id,))
    rows = cur.fetchall()

    waveform_data = defaultdict(list)
    for row in rows:
        channel, value = row
        waveform_data[channel].append(value)

    conn.close()

    return jsonify(waveform_data)

@app.route('/delete_event', methods=['POST'])
def delete_event():
    event_id = request.form['id']
    
    try:
        conn = sqlite3.connect(DATABASE)
        cur = conn.cursor()

        cur.execute("DELETE FROM adc_values WHERE event_id=?", (event_id,))
        cur.execute("DELETE FROM adc_data WHERE id=?", (event_id,))

        conn.commit()
        conn.close()
        
        return jsonify({'status': 'success'})
    except Exception as e:
        print(e)
        return jsonify({'status': 'error'})

@app.route('/update_event', methods=['POST'])
def update_event():
    # Retrieve the updated data from the request
    event_id = request.form.get('id')
    num_channels = request.form.get('num_channels')
    duration = request.form.get('duration')
    radius = request.form.get('radius')
    latitude = request.form.get('latitude')
    longitude = request.form.get('longitude')
    location = request.form.get('location')

    try:
        # Update the data in the SQLite database
        conn = sqlite3.connect(DATABASE)
        cur = conn.cursor()
        cur.execute('''UPDATE adc_data SET
                       num_channels = ?,
                       duration = ?,
                       radius = ?,
                       latitude = ?,
                       longitude = ?,
                       location = ?
                       WHERE id = ?''', (num_channels, duration, radius, latitude, longitude, location, event_id))
        conn.commit()
        conn.close()

        return jsonify(status="success")

    except Exception as e:
        print(e)
        return jsonify(status="error")
    
def fetch_waveform_data_by_id(event_id):
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()

    # Fetch waveform data
    cur.execute("SELECT channel, value FROM adc_values WHERE event_id = ? ORDER BY channel, id", (event_id,))
    rows = cur.fetchall()

    waveform_data = defaultdict(list)
    for row in rows:
        channel, value = row
        waveform_data[str(channel)].append(value)  # Convert channel to string to avoid key duplication

    # Fetch metadata
    cur.execute("SELECT * FROM adc_data WHERE id = ?", (event_id,))
    metadata_row = cur.fetchone()

    if metadata_row:
        metadata = {
            'id': metadata_row[0],
            'timestamp': metadata_row[1],
            'num_channels': metadata_row[2],
            'duration': metadata_row[3],
            'radius': metadata_row[4],
            'latitude': metadata_row[5],
            'longitude': metadata_row[6],
            'location': metadata_row[7]
        }
    else:
        metadata = None

    conn.close()

    return waveform_data, metadata



@app.route('/download_waveform_data', methods=['GET'])
def download_waveform_data():
    event_id = request.args.get('id', type=int)
    
    if not event_id:
        return jsonify({'error': 'Event ID is required'}), 400

    waveform_data = fetch_waveform_data_by_id(event_id)  # Use the new function to get the waveform data
    
    if not waveform_data:
        return jsonify({'error': 'No data found'}), 404

    # Calculate the sampling rate
    duration = waveform_data[1]['duration']
    num_samples = len(waveform_data[0]['0'])
    sampling_rate = num_samples/duration

    # Build the response dictionary with the desired structure
    response_data = {
        "metadata": {
            "duration": duration,
            "radius": waveform_data[1]['radius'],
            "latitude": waveform_data[1]['latitude'],
            "longitude": waveform_data[1]['longitude'],
            "location": waveform_data[1]['location'],
            "sampling_rate": sampling_rate
        },
        "waveform_data": waveform_data[0]
    }

    response = jsonify(response_data)
    response.headers.set('Content-Disposition', f'attachment; filename=waveform_data_{event_id}.json')
    response.headers.set('Content-Type', 'application/json')
    return response




@app.route('/store_uploaded_data', methods=['POST'])
def store_uploaded_data():
    data = request.json
    metadata = data['metadata']
    waveform_data = data['waveform_data']

    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()

    cur.execute('''INSERT INTO adc_data (timestamp, num_channels, duration, radius, latitude, longitude, location)
                   VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), len(waveform_data), metadata['duration'], metadata['radius'],
                 metadata['latitude'], metadata['longitude'], metadata['location']))
    event_id = cur.lastrowid

    for channel, values in waveform_data.items():
        for value in values:
            cur.execute('''INSERT INTO adc_values (event_id, channel, value) VALUES (?, ?, ?)''', (event_id, channel, value))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Data stored successfully'})





if __name__ == '__main__':
    try:
        socketio.run(app, host='0.0.0.0', port=8080, debug=True)
    finally:
        try:
            ADC.ADS1263_Exit()
        except:
            pass
