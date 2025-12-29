const socket = io();

function createGame() {
    const playerName = document.getElementById('player_name').value;
    if (!playerName) {
        alert('Please enter a player name');
        return;
    }
    fetch('/create_game', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ player_name: playerName })
    }).then(response => {
        if (!response.ok) {
            throw new Error('Failed to create game');
        }
        return response.json();
    }).then(data => {
        window.location.href = `/game?code=${data.game_code}&player=${playerName}`;
    }).catch(error => {
        console.error('Error creating game:', error);
        alert('Error creating game: ' + error.message);
    });
}

function joinGame() {
    const gameCode = document.getElementById('game_code').value;
    const playerName = document.getElementById('join_player_name').value;
    if (!gameCode || !playerName) {
        alert('Please enter both game code and player name');
        return;
    }
    fetch('/join_game', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ game_code: gameCode, player_name: playerName })
    }).then(response => {
        if (!response.ok) {
            throw new Error('Failed to join game');
        }
        return response.json();
    }).then(data => {
        if (data.status === 'success') {
            window.location.href = `/game?code=${gameCode}&player=${playerName}`;
        } else {
            alert(data.message);
        }
    }).catch(error => {
        console.error('Error joining game:', error);
        alert('Error joining game: ' + error.message);
    });
}

socket.on('connect', () => {
    const urlParams = new URLSearchParams(window.location.search);
    const gameCode = urlParams.get('code');
    const playerName = urlParams.get('player');
    socket.emit('join_room', { game_code: gameCode, player: playerName });
    document.getElementById('code-display').textContent = gameCode;

    socket.on('game_state', (data) => {
        updatePlayers(data.players, []);  // Public list without roles
        updatePhase(data.phase, data.timer);
        updateStartButton(data.phase, data.players, playerName);
    });

    socket.on('player_joined', (data) => {
        updatePlayers(data.players, []);
        updateStartButton(data.phase, data.players, playerName);
    });

    socket.on('game_started', (data) => {
        updatePlayers(data.players, []);  // Public list
        updatePhase(data.phase, 60);
        const startBtnContainer = document.getElementById('start-btn-container');
        startBtnContainer.innerHTML = '';
        updateStartButton(data.phase, data.players, playerName);  // Show restart if host
    });

    socket.on('private_role', (data) => {
        alert(`Your role: ${data.role}`);  // Private role notification; expand to UI element
    });

    socket.on('action_result', (data) => {
        alert(`Action result: ${data.result}`);  // Private result
    });

    socket.on('elimination', (data) => {
        alert(`${data.player} was eliminated! Role: ${data.role}`);
    });

    socket.on('game_restarted', (data) => {
        updatePlayers(data.players, []);
        updatePhase(data.phase, 0);
        updateStartButton(data.phase, data.players, playerName);
    });
});

function startGame() {
    const urlParams = new URLSearchParams(window.location.search);
    const gameCode = urlParams.get('code');
    socket.emit('start_game', { game_code: gameCode });
}

function restartGame() {
    const urlParams = new URLSearchParams(window.location.search);
    const gameCode = urlParams.get('code');
    socket.emit('restart_game', { game_code: gameCode });
}

function submitAction() {
    const urlParams = new URLSearchParams(window.location.search);
    const gameCode = urlParams.get('code');
    const playerName = urlParams.get('player');
    const target = document.getElementById('target-select').value;
    if (!target) {
        alert('Select a target');
        return;
    }
    socket.emit('night_action', { game_code: gameCode, player_name: playerName, action: 'check', target: target });  // Example action; adjust per role
}

function updatePlayers(players, roles) {
    const playersList = document.getElementById('players-list');
    playersList.innerHTML = '';
    players.forEach(player => {
        playersList.innerHTML += `<div>${player}</div>`;  // Public list, no roles/icons
    });
}

function updatePhase(phase, timer) {
    const phaseInfo = document.getElementById('phase-info');
    phaseInfo.textContent = `Phase: ${phase}`;
    const timerDisplay = document.getElementById('timer');
    timerDisplay.textContent = `Time left: ${timer}s`;
    if (timer > 0) {
        let timeLeft = timer;
        const interval = setInterval(() => {
            timeLeft--;
            timerDisplay.textContent = `Time left: ${timeLeft}s`;
            if (timeLeft <= 0) clearInterval(interval);
        }, 1000);
    }
    document.getElementById('action-panel').classList.toggle('hidden', phase !== 'night');
    document.getElementById('vote-panel').classList.toggle('hidden', phase !== 'day');
    if (phase === 'night') {
        document.getElementById('action-btn').onclick = submitAction;  // Wire up button
    }
}

function updateStartButton(phase, players, playerName) {
    const startBtnContainer = document.getElementById('start-btn-container');
    startBtnContainer.innerHTML = '';
    if (phase === 'lobby' && players[0] === playerName) {
        if (players.length >= 5) {
            startBtnContainer.innerHTML = '<button id="start-game-btn" class="mt-4 bg-red-600 text-white p-2 rounded w-full" onclick="startGame()">Start Game</button>';
        } else {
            startBtnContainer.innerHTML = '<p class="mt-4 text-gray-600">Waiting for more players (need at least 5 to start).</p>';
        }
    } else if (phase !== 'lobby' && players[0] === playerName) {
        startBtnContainer.innerHTML = '<button id="restart-game-btn" class="mt-4 bg-gray-600 text-white p-2 rounded w-full" onclick="restartGame()">Restart Game</button>';
    }
}