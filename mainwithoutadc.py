from flask import Flask, render_template, request, jsonify, redirect
import time
import platform
systemOS = platform.system()
#import ADS1263
#import RPi.GPIO as GPIO
import plotly.graph_objs as go
import plotly
import json
from contextlib import closing
from datetime import datetime, timedelta
from flask_socketio import SocketIO, emit
from flask import copy_current_request_context
from flask_socketio import Namespace
from collections import defaultdict
from threading import Thread, Lock
from models import db, AdcData, AdcValues
from flask_sqlalchemy import SQLAlchemy
from auth import auth_bp
from flask_login import LoginManager, current_user, login_required
#from flask_mqtt import Mqtt


'''REF = 5.08          # Modify according to actual voltage
                    # external AVDD and AVSS(Default), or internal 2.5V

ADC = ADS1263.ADS1263()
if (ADC.ADS1263_init_ADC1('ADS1263_7200SPS') == -1):
    ADC.ADS1263_Exit()
    print("Failed to initialize ADC1")
    exit()
ADC.ADS1263_SetMode(1)'''

# Initialization

def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config['SECRET_KEY'] = 'gvWave01'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///gVdb2023.db'
    #app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://admin:Geoverse5@161.200.87.11:80/gvdb'

    
    '''app.config['MQTT_BROKER_URL'] = '1b31e8cbcd6d4d46aa695d71251f143c.s2.eu.hivemq.cloud'
    app.config['MQTT_BROKER_PORT'] = 8883
    app.config['MQTT_REFRESH_TIME'] = 1.0
    app.config['MQTT_USERNAME'] = 'gvdevmqtt'
    app.config['MQTT_PASSWORD'] = 'Geoverse@5'
    app.config['MQTT_TLS_ENABLED'] = True
    app.config['MQTT_TLS_VERSION'] = 2'''
    
    app.register_blueprint(auth_bp)
    db.init_app(app)
    login_manager = LoginManager()
    login_manager.login_view = 'auth_bp.login'
    login_manager.init_app(app)
    from models import User
    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))
    return app

app = create_app()


socketio = SocketIO(app, ping_timeout=1000)
sampling_rate = 128  # Hz
sleep_duration = 1 / sampling_rate

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/dashboard.html')
@login_required
def dashboard():
    return render_template('dashboard.html')


@app.route('/icons.html')
@login_required
def icons():
    return render_template('icons.html')

@app.route('/typography.html')
@login_required
def typography():
    return render_template('typography.html')

@app.route('/map.html')
@login_required
def map():
    # Fetch data from the database
    data = AdcData.query.with_entities(AdcData.id, AdcData.timestamp, AdcData.num_channels, AdcData.duration, AdcData.radius, AdcData.latitude, AdcData.longitude).all()
    data_dicts = [row._asdict() for row in data]
    # Render the map.html template and pass the data
    return render_template('map.html', data=data_dicts)

@app.route('/user.html')
def user():
    return render_template('user.html')

@app.route('/rtl.html')
def rtl():
    return render_template('rtl.html')

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
    channelList = [0, 1, 2]
    start_time = time.perf_counter()
    ADC_Value_List = []

    interval = 1 / sampling_rate
    next_sample_time = start_time + interval
    no_sample = duration * sampling_rate
    while len(ADC_Value_List) < no_sample:
        current_time = time.perf_counter()
        if current_time >= next_sample_time:
            ADC_Value = ADC.ADS1263_GetAll(channelList)
            ADC_Value_List.append(ADC_Value)
            next_sample_time += interval

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
    
    store_event_in_database(timestamp, num_channels, duration, radius, lat, lon, converted_data, location)
        
    
    return converted_data, actual_sampling_rate

def store_event_in_database(timestamp, num_channels, duration, radius, lat, lon, converted_data, location, components=None):
    datetime_string = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')

    new_adc_data = AdcData(timestamp=datetime_string, num_channels=num_channels, duration=duration, radius=radius, latitude=lat, longitude=lon, location=location)
    db.session.add(new_adc_data)
    db.session.commit()
    event_id = new_adc_data.id

    total_values = sum(len(channel_data) for channel_data in converted_data.values())
    stored_values = 0

    if components is None:
        # Default components for vertical only
        components = ['z']

    for channel, values in converted_data.items():
        component = components[int(channel) % len(components)]
        for value in values:
            new_adc_value = AdcValues(event_id=event_id, channel=channel, component=component, value=value)
            db.session.add(new_adc_value)

    db.session.commit()

def create_plot(converted_data):
    channelList = [0, 1, 2]
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
    data = AdcData.query.with_entities(AdcData.id, AdcData.timestamp, AdcData.num_channels, AdcData.duration, AdcData.radius, AdcData.latitude, AdcData.longitude, AdcData.location).all()
    data_dicts = [row._asdict() for row in data]
    return render_template('tables.html', data=data_dicts)


@app.route('/get_waveform_data', methods=['GET'])
def get_waveform_data():
    event_id = request.args.get('id', type=int)

    if not event_id:
        return jsonify({'error': 'Event ID is required'}), 400

    rows = AdcValues.query.filter_by(event_id=event_id).order_by(AdcValues.channel, AdcValues.component, AdcValues.id).all()

    waveform_data = defaultdict(lambda: defaultdict(list))
    for row in rows:
        channel, component, value = row.channel, row.component, row.value
        waveform_data[channel][component].append(value)
    

    return jsonify(waveform_data)

@app.route('/delete_event', methods=['POST'])
def delete_event():
    event_id = request.form['id']
    
    try:
        adc_values = AdcValues.query.filter_by(event_id=event_id).all()
        for value in adc_values:
            db.session.delete(value)

        adc_data = adc_data = db.session.get(AdcData, event_id)
        if adc_data:
            db.session.delete(adc_data)

        db.session.commit()
        
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
        event = AdcData.query.get(event_id)
        if event is None:
            return jsonify(status="error", message="No such event")

        event.num_channels = num_channels
        event.duration = duration
        event.radius = radius
        event.latitude = latitude
        event.longitude = longitude
        event.location = location

        db.session.commit()

        return jsonify(status="success")

    except Exception as e:
        print(e)
        return jsonify(status="error")

    
def fetch_waveform_data_by_id(event_id):
    # Fetch waveform data
    rows = AdcValues.query.filter_by(event_id=event_id).order_by(AdcValues.channel, AdcValues.id).all()

    waveform_data = defaultdict(list)
    for row in rows:
        channel, value = row.channel, row.value
        waveform_data[str(channel)].append(value)  # Convert channel to string to avoid key duplication

    # Fetch metadata
    metadata_row = AdcData.query.get(event_id)

    if metadata_row:
        metadata = {
            'id': metadata_row.id,
            'timestamp': metadata_row.timestamp,
            'num_channels': metadata_row.num_channels,
            'duration': metadata_row.duration,
            'radius': metadata_row.radius,
            'latitude': metadata_row.latitude,
            'longitude': metadata_row.longitude,
            'location': metadata_row.location
        }
    else:
        metadata = None

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

    adc_data = AdcData(
        timestamp=datetime.now(),
        num_channels=len(waveform_data),
        duration=metadata['duration'],
        radius=metadata['radius'],
        latitude=metadata['latitude'],
        longitude=metadata['longitude'],
        location=metadata['location']
    )
    db.session.add(adc_data)
    db.session.commit()

    for channel, values in waveform_data.items():
        for value in values:
            adc_value = AdcValues(
                event_id=adc_data.id,
                channel=channel,
                value=value
            )
            db.session.add(adc_value)

    db.session.commit()

    return jsonify({'success': True, 'message': 'Data stored successfully'})



current_command = 0
command_processed_dict = {}
received_data_dict = {}
connected_devices = {}
connections_lock = Lock()

@app.route('/dashboard3D.html', methods=['GET', 'POST'])
@login_required
def dashboard3D():
    global current_command, command_processed_dict
    if request.method == 'POST':
        duration = int(request.form['duration'])
        current_command = int(duration*128)
        with connections_lock:
            for device_id in connected_devices:
                command_processed_dict[device_id] = False
        socketio.emit('command', current_command)
        return redirect('/dashborad3D')
    else:
        return render_template('/dashboard3D.html')

@app.route('/get_data', methods=['POST'])
def get_data():
    global current_command, command_processed_dict, received_data_dict, connected_devices
    if request.method == 'POST':
        duration = float(request.form['duration'])
        radius = float(request.form['radius'])
        latitude = float(request.form['latitude'])
        longitude = float(request.form['longitude'])
        location = request.form['location']
        current_command = int(duration * 128)

        # Set all command_processed flags to False
        with connections_lock:
            for device_id in connected_devices:
                command_processed_dict[device_id] = False
        print(command_processed_dict, current_command)
        socketio.emit('sample_count', current_command)
        

        # Wait until the command is processed for all devices
        while not all(command_processed_dict.values()):
            time.sleep(0.1)

        # Merge data from all devices
        merged_data = defaultdict(list)
        id_device = received_data_dict.keys()
        channels = [n for n in range(len(id_device) * 3)]
        channel_idx = 0
        for device_data in received_data_dict.values():
            for idx, values in enumerate(device_data.values()):
                print(channel_idx)
                merged_data[channels[channel_idx]].extend(values)
                channel_idx += 1

        timestamp = int(time.time())
        num_channels = len(merged_data)
        store_event_in_database(timestamp, num_channels, duration, radius, latitude, longitude, merged_data, location, components=['z', 'x', 'y'])
        
        # Convert the merged data to a format suitable for plotting
        plot_data = []
        for channel, values in merged_data.items():
            for i, value in enumerate(values):
                plot_data.append({'channel': int(channel), 'sample': i, 'value': value})

        return jsonify(plot_data)

@socketio.on('connect')
def handle_client_connection():
    global command_processed_dict, received_data_dict, connected_devices

    # Receive the device identifier (assuming it's sent by the client as the first message)
    device_id = request.sid

    with connections_lock:
        if device_id in connected_devices:
            print(f"Device {device_id} reconnected")
        else:
            print(f"New device {device_id} connected")
            connected_devices[device_id] = None
            command_processed_dict[device_id] = True

@socketio.on('mac_address')
def handle_mac_address(mac_address):
    print(f"Received mac_address: {mac_address}")

@socketio.on('data')
def handle_data(data):
    global command_processed_dict, received_data_dict, connected_devices

    device_id = request.sid

    if not command_processed_dict[device_id]:
        try:
            command_to_send = current_command
            #emit('command', str(command_to_send))

            received_data = json.loads(data)  # Deserialize JSON data

            with connections_lock:
                received_data_dict[device_id] = received_data

            command_processed_dict[device_id] = True
        except Exception as e:
            print(f"Error in handle_data: {e}")

@socketio.on('disconnect')
def handle_disconnect():
    device_id = request.sid

    with connections_lock:
        del connected_devices[device_id]

    print(f"Device {device_id} disconnected")

@app.route('/connected_devices', methods=['GET'])
def connected_devices_count():
    with connections_lock:
        count = len(connected_devices)
    return jsonify({"count": count})

@app.route('/iot.html')
def iot():
    return render_template('iot.html')

'''mqtt = Mqtt(app)

temperature = 0.0
humidity = 0.0
accl = {"x": 0.0, "y": 0.0, "z": 0.0}
last_update = datetime.now()

@mqtt.on_connect()
def handle_connect(client, userdata, flags, rc):
    mqtt.subscribe('Temperature/gv01')
    mqtt.subscribe('Humidity/gv01')
    mqtt.subscribe('Accl/gv01')

@mqtt.on_message()
def handle_mqtt_message(client, userdata, message):
    global temperature
    global humidity
    global accl
    global last_update
    data = dict(
        topic=message.topic,
        payload=message.payload.decode()
    )
    if data['topic'] == 'Temperature/gv01':
        temperature = float(data['payload'])
    elif data['topic'] == 'Humidity/gv01':
        humidity = float(data['payload'])
    elif data['topic'] == 'Accl/gv01':
    # Assuming accl data is a comma-separated string "x,y,z"
        accl_vals = data['payload'].split(",")
        accl = {"x": float(accl_vals[0]), "y": float(accl_vals[1]), "z": float(accl_vals[2])}
    last_update = datetime.now()

@app.route('/data', methods=['GET'])
def data():
    global temperature
    global humidity
    global accl
    global last_update
    if datetime.now() - last_update > timedelta(seconds=6):
        # If more than 5 seconds have passed since the last update, return a special value
        return json.dumps({"temperature": None, "humidity": None, "accl": {"x": None, "y": None, "z": None}})
    else:
        return json.dumps({"temperature": temperature, "humidity": humidity, "accl": accl})'''

if __name__ == '__main__':
    try:
        #socketio.run(app, host='0.0.0.0', port=8080, allow_unsafe_werkzeug=True)
        socketio.run(app, host='0.0.0.0', port=8080)
    finally:
        try:
            ADC.ADS1263_Exit()
        except:
            pass

