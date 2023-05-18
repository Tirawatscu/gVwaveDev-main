from flask import Flask, render_template
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)

@socketio.on('connect')
def test_connect():
    print('Client connected')
    emit('server_message', {'data': 'Hello, client!'})

@socketio.on('client_message')
def receive_message(message):
    print('Received message: ' + str(message))

if __name__ == '__main__':
    socketio.run(app, '192.168.1.103', 5000)
