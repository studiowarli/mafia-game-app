from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO, emit, join_room
import random
import string
import time
import threading

app = Flask(__name__)
app.config["SECRET_KEY"] = "secret"
socketio = SocketIO(app, cors_allowed_origins="*")

games = {}

PHASE_TIMERS = {
    "day": 240,
    "defense": 120,
    "night": 60
}

# -------------------------
# Utilities
# -------------------------

def generate_code():
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=5))

def mafia_count(n):
    return max(1, n // 4)

def alive_players(game):
    return [p for p in game["players"] if game["players"][p]["alive"]]

def get_role(game, role):
    for p, data in game["players"].items():
        if data["role"] == role and data["alive"]:
            return p
    return None

def emit_state(game_code):
    game = games[game_code]
    emit("game_state", {
        "phase": game["phase"],
        "players": [
            {"name": p, "alive": d["alive"]}
            for p, d in game["players"].items()
        ]
    }, room=game_code)

# -------------------------
# Game Engine
# -------------------------

def advance_phase(game_code):
    game = games.get(game_code)
    if not game:
        return

    phase_order = ["day", "defense", "night"]
    current = game["phase"]

    if current == "day":
        game["phase"] = "defense"
        game["votes"] = {}
    elif current == "defense":
        resolve_day_elimination(game_code)
        game["phase"] = "night"
        game["night_actions"] = {"mafia": [], "doctor": None, "sheriff": None}
    elif current == "night":
        resolve_night(game_code)
        game["phase"] = "day"

    game["timer_ends"] = time.time() + PHASE_TIMERS[game["phase"]]
    emit_state(game_code)

def timer_loop(game_code):
    while game_code in games:
        game = games[game_code]
        if game["phase"] == "ended":
            return

        remaining = int(game["timer_ends"] - time.time())

        if remaining <= 0:
            advance_phase(game_code)
        else:
            socketio.emit(
                "timer",
                {"seconds": remaining},
                room=game_code
            )

        socketio.sleep(1)


def resolve_day_elimination(game_code):
    game = games[game_code]
    votes = game["votes"].values()
    if not votes:
        return

    target = max(set(votes), key=votes.count)
    game["players"][target]["alive"] = False

    emit("elimination", {
        "player": target,
        "role": game["players"][target]["role"]
    }, room=game_code)

    check_win(game_code)

def resolve_night(game_code):
    game = games[game_code]
    mafia_votes = game["night_actions"]["mafia"]

    if not mafia_votes:
        return

    mafia_target = max(set(mafia_votes), key=mafia_votes.count)
    doctor_target = game["night_actions"]["doctor"]

    if mafia_target == doctor_target:
        emit("night_result", {"message": "No one was eliminated."}, room=game_code)
        return

    if game["players"][mafia_target]["alive"]:
        game["players"][mafia_target]["alive"] = False
        emit("elimination", {
            "player": mafia_target,
            "role": game["players"][mafia_target]["role"]
        }, room=game_code)

    check_win(game_code)

def check_win(game_code):
    game = games[game_code]
    mafia = sum(1 for p in game["players"].values() if p["alive"] and p["role"] == "mafia")
    villagers = sum(1 for p in game["players"].values() if p["alive"] and p["role"] != "mafia")

    if mafia >= villagers:
        end_game(game_code, "Mafia")
    elif mafia == 0:
        end_game(game_code, "Villagers")

def end_game(game_code, winner):
    game = games[game_code]
    game["phase"] = "ended"
    emit("game_ended", {"winner": winner}, room=game_code)

# -------------------------
# Routes
# -------------------------

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/game")
def game():
    return render_template("game.html")

@app.route("/create_game", methods=["POST"])
def create_game():
    code = generate_code()
    games[code] = {
        "players": {},
        "host": None,
        "phase": "lobby",
        "votes": {},
        "night_actions": {},
        "timer_ends": None
    }
    return jsonify({"game_code": code})

@app.route("/join_game", methods=["POST"])
def join_game():
    data = request.json
    code = data["game_code"]
    name = data["player_name"]

    if code not in games:
        return jsonify({"status": "error", "message": "Game not found"})

    if name in games[code]["players"]:
        return jsonify({"status": "error", "message": "Name already taken"})

    return jsonify({"status": "success"})

# -------------------------
# Socket Events
# -------------------------

@socketio.on("join_room")
def join(data):
    code = data["game_code"]
    name = data["player"]

    join_room(code)

    game = games[code]
    game["players"][name] = {
        "alive": True,
        "role": None,
        "self_saved_last": False
    }

    if not game["host"]:
        game["host"] = name

    emit_state(code)

@socketio.on("start_game")
def start_game(data):
    code = data["game_code"]
    game = games[code]

    players = list(game["players"].keys())
    roles = (
        ["mafia"] * mafia_count(len(players)) +
        ["doctor"] +
        ["sheriff"] +
        ["villager"] * (len(players) - mafia_count(len(players)) - 2)
    )
    random.shuffle(roles)

    for p, r in zip(players, roles):
        game["players"][p]["role"] = r
        emit("private_role", {"role": r}, room=request.sid)

    game["phase"] = "day"
    game["timer_ends"] = time.time() + PHASE_TIMERS["day"]

    threading.Thread(target=timer_loop, args=(code,), daemon=True).start()
    emit_state(code)

@socketio.on("vote")
def vote(data):
    game = games[data["game_code"]]
    voter = data["player"]
    target = data["target"]

    if game["players"][voter]["alive"]:
        game["votes"][voter] = target

@socketio.on("night_action")
def night_action(data):
    game = games[data["game_code"]]
    actor = data["player"]
    target = data["target"]
    role = game["players"][actor]["role"]

    if role == "mafia":
        game["night_actions"]["mafia"].append(target)
    elif role == "doctor":
        game["night_actions"]["doctor"] = target
    elif role == "sheriff":
        result = "Mafia" if game["players"][target]["role"] == "mafia" else "Not Mafia"
        emit("action_result", {"result": result}, room=request.sid)

if __name__ == "__main__":
    socketio.run(app, debug=True)