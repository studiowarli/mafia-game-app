from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
import random
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")

# In-memory storage for games
games = {}

def get_game_state(game_code):
    state_data = games.get(game_code)
    if state_data:
        return (
            state_data['state'],
            state_data['players'],
            state_data['roles'],
            state_data['phase'],
            state_data['timer'],
            state_data['sockets']
        )
    return None, None, None, None, None, None

def update_game_state(game_code, state, players, roles, phase, timer, sockets):
    games[game_code] = {
        'state': state,
        'players': players,
        'roles': roles,
        'phase': phase,
        'timer': timer,
        'sockets': sockets
    }

# Role assignment logic
def assign_roles(player_count):
    if player_count < 5:
        return ['villager'] * player_count
    roles = ['villager'] * player_count
    mafia_count = max(2, (player_count + 3) // 4)
    if mafia_count > player_count // 2:
        mafia_count = player_count // 2
    roles[-mafia_count:] = ['mafia'] * mafia_count
    if player_count >= 3:
        doc_index = random.randrange(0, player_count)
        roles[doc_index] = 'doctor'
        sher_index = random.randrange(0, player_count)
        while sher_index == doc_index:
            sher_index = random.randrange(0, player_count)
        roles[sher_index] = 'sheriff'
    random.shuffle(roles)
    return roles

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health')
def health_check():
    return "OK", 200  # Simple health check endpoint

@app.route('/game')
def game():
    return render_template('game.html')

@app.route('/create_game', methods=['POST'])
def create_game():
    try:
        game_code = ''.join(random.choices('0123456789', k=6))
        players = [request.json['player_name']]
        roles = []  # Defer roles
        sockets = {}  # Dict for player:sid
        update_game_state(game_code, 'lobby', players, roles, 'lobby', 0, sockets)
        return jsonify({'game_code': game_code})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/join_game', methods=['POST'])
def join_game():
    try:
        data = request.json
        game_code, player_name = data['game_code'], data['player_name']
        state, players, roles, phase, timer, sockets = get_game_state(game_code)
        if state:
            if player_name not in players and len(players) < 16:
                players.append(player_name)
                update_game_state(game_code, state, players, roles, phase, timer, sockets)
                socketio.emit('player_joined', {'player_name': player_name, 'players': players, 'phase': phase}, room=game_code)
            return jsonify({'status': 'success', 'players': players})
        return jsonify({'status': 'error', 'message': 'Game not found'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@socketio.on('connect')
def handle_connect():
    emit('connected', {'message': 'Connected to server'})

@socketio.on('join_room')
def on_join(data):
    game_code = data['game_code']
    player_name = data['player']
    join_room(game_code)
    state, players, roles, phase, timer, sockets = get_game_state(game_code)
    if state:
        sockets[player_name] = request.sid  # Store socket ID
        update_game_state(game_code, state, players, roles, phase, timer, sockets)
        emit('game_state', {'players': players, 'roles': roles, 'phase': phase, 'timer': timer})

@socketio.on('start_game')
def start_game(data):
    game_code = data['game_code']
    state, players, roles, phase, timer, sockets = get_game_state(game_code)
    if state == 'lobby' and len(players) >= 5:
        roles = assign_roles(len(players))
        update_game_state(game_code, 'night', players, roles, 'night', 60, sockets)
        emit('game_started', {'phase': 'night', 'players': players}, room=game_code)
        # Send private roles
        for idx, player in enumerate(players):
            role = roles[idx]
            sid = sockets.get(player)
            if sid:
                emit('private_role', {'role': role}, to=sid)

@socketio.on('night_action')
def night_action(data):
    game_code = data['game_code']
    player_name = data['player_name']
    action = data['action']
    target = data['target']
    state, players, roles, phase, timer, sockets = get_game_state(game_code)
    if phase == 'night' and timer > 0:
        role = roles[players.index(player_name)]
        if role in ['sheriff', 'doctor', 'mafia']:
            # Simplified action logic
            if role == 'sheriff' and action == 'check':
                result = 'mafia' if roles[players.index(target)] == 'mafia' else 'good'
                emit('action_result', {'player': player_name, 'result': result}, to=request.sid)
            elif role == 'doctor' and action == 'save':
                emit('action_result', {'player': player_name, 'result': 'saved'}, to=request.sid)
            elif role == 'mafia' and action == 'eliminate':
                emit('action_result', {'player': player_name, 'result': 'voted'}, to=request.sid)
        if timer <= 0:
            update_game_state(game_code, 'day', players, roles, 'day', random.randint(180, 300), sockets)

@socketio.on('restart_game')
def restart_game(data):
    game_code = data['game_code']
    state, players, roles, phase, timer, sockets = get_game_state(game_code)
    if request.sid == sockets[players[0]]:  # Only host can restart
        roles = []  # Reset roles
        update_game_state(game_code, 'lobby', players, roles, 'lobby', 0, sockets)
        emit('game_restarted', {'phase': 'lobby', 'players': players}, room=game_code)

# Additional handlers (vote_skip, vote_eliminate, check_win_condition) as before

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    socketio.run(app, debug=True, host='0.0.0.0', port=port)