from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
import random
import sqlite3
from datetime import datetime, timedelta

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")

# In-memory game state (simplified with SQLite for persistence)
def init_db():
    conn = sqlite3.connect('mafia.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS games 
                 (game_code TEXT PRIMARY KEY, state TEXT, players TEXT, roles TEXT, phase TEXT, timer INTEGER)''')
    conn.commit()
    conn.close()

init_db()

def get_game_state(game_code):
    conn = sqlite3.connect('mafia.db')
    c = conn.cursor()
    c.execute("SELECT state, players, roles, phase, timer FROM games WHERE game_code = ?", (game_code,))
    result = c.fetchone()
    conn.close()
    return result if result else (None, None, None, None, None)

def update_game_state(game_code, state, players, roles, phase, timer):
    conn = sqlite3.connect('mafia.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO games (game_code, state, players, roles, phase, timer) VALUES (?, ?, ?, ?, ?, ?)",
              (game_code, state, players, roles, phase, timer))
    conn.commit()
    conn.close()

# Role assignment logic
def assign_roles(player_count):
    roles = ['villager'] * player_count
    mafia_count = max(2, (player_count + 3) // 4)  # 1 mafia per 4 players, min 2
    roles[-mafia_count:] = ['mafia'] * mafia_count
    roles[random.randrange(1, player_count-1)] = 'doctor'  # Avoid first/last for balance
    roles[random.randrange(1, player_count-1)] = 'sheriff'
    random.shuffle(roles)
    return roles

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/create_game', methods=['POST'])
def create_game():
    game_code = ''.join(random.choices('0123456789', k=6))
    players = [request.json['player_name']]
    roles = assign_roles(1)  # Initial role for host
    update_game_state(game_code, 'lobby', str(players), str(roles), 'lobby', 0)
    return jsonify({'game_code': game_code})

@app.route('/join_game', methods=['POST'])
def join_game():
    data = request.json
    game_code, player_name = data['game_code'], data['player_name']
    state, players_str, roles_str, phase, timer = get_game_state(game_code)
    if state:
        players = eval(players_str)
        roles = eval(roles_str)
        if player_name not in players and len(players) < 16:
            players.append(player_name)
            roles = assign_roles(len(players))
            update_game_state(game_code, state, str(players), str(roles), phase, timer)
            socketio.emit('player_joined', {'player_name': player_name, 'players': players}, room=game_code)
        return jsonify({'status': 'success', 'players': players})
    return jsonify({'status': 'error', 'message': 'Game not found'})

@socketio.on('connect')
def handle_connect():
    emit('connected', {'message': 'Connected to server'})

@socketio.on('join_room')
def on_join(data):
    game_code = data['game_code']
    join_room(game_code)
    state, players_str, roles_str, phase, timer = get_game_state(game_code)
    if state:
        emit('game_state', {'players': eval(players_str), 'roles': eval(roles_str), 'phase': phase, 'timer': timer}, room=game_code)

@socketio.on('start_game')
def start_game(data):
    game_code = data['game_code']
    state, players_str, roles_str, phase, timer = get_game_state(game_code)
    if state == 'lobby' and len(eval(players_str)) >= 5:
        update_game_state(game_code, 'night', players_str, roles_str, 'night', 60)
        emit('game_started', {'phase': 'night'}, room=game_code)

@socketio.on('night_action')
def night_action(data):
    game_code = data['game_code']
    player_name = data['player_name']
    action = data['action']
    target = data['target']
    state, players_str, roles_str, phase, timer = get_game_state(game_code)
    if phase == 'night' and timer > 0:
        players, roles = eval(players_str), eval(roles_str)
        role = roles[players.index(player_name)]
        if role in ['sheriff', 'doctor', 'mafia']:
            # Logic for actions (simplified)
            if role == 'sheriff' and action == 'check':
                result = 'mafia' if roles[players.index(target)] == 'mafia' else 'good'
                emit('action_result', {'player': player_name, 'result': result}, room=game_code)
            elif role == 'doctor' and action == 'save':
                # Prevent self-save two nights in a row (simplified tracking needed)
                emit('action_result', {'player': player_name, 'result': 'saved'}, room=game_code)
            elif role == 'mafia' and action == 'eliminate':
                # Collective mafia vote (simplified)
                emit('action_result', {'player': player_name, 'result': 'voted'}, room=game_code)
        if timer <= 0:
            update_game_state(game_code, 'day', players_str, roles_str, 'day', random.randint(180, 300))

@socketio.on('vote_skip')
def vote_skip(data):
    game_code = data['game_code']
    state, players_str, roles_str, phase, timer = get_game_state(game_code)
    if phase == 'day' and timer > 0:
        players = eval(players_str)
        skip_votes = data.get('skip_votes', 0) + 1
        if skip_votes > len(players) / 2:
            update_game_state(game_code, 'day', players_str, roles_str, 'day', 0)
            emit('phase_ended', {'phase': 'day'}, room=game_code)

@socketio.on('vote_eliminate')
def vote_eliminate(data):
    game_code = data['game_code']
    target = data['target']
    state, players_str, roles_str, phase, timer = get_game_state(game_code)
    if phase == 'day' and timer > 0:
        players, roles = eval(players_str), eval(roles_str)
        # Simplified voting logic
        if timer <= 0:  # After defense
            eliminated = target
            roles[players.index(eliminated)] = 'dead_' + roles[players.index(eliminated)]
            update_game_state(game_code, 'night', str(players), str(roles), 'night', 60)
            emit('elimination', {'player': eliminated, 'role': roles[players.index(eliminated)].replace('dead_', '')}, room=game_code)

def check_win_condition(players, roles):
    alive_players = [p for p, r in zip(players, roles) if not r.startswith('dead_')]
    alive_roles = [r for r in roles if not r.startswith('dead_')]
    mafia_count = alive_roles.count('mafia')
    villager_count = len(alive_roles) - mafia_count
    if mafia_count >= villager_count:
        return 'mafia'
    elif mafia_count == 0:
        return 'villagers'
    return None

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)