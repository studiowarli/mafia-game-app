const socket = io();

function createGame() {
    const playerName = document.getElementById('player_name').value;
    fetch('/create_game', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ player_name: playerName })
    }).then(response => response.json())
      .then(data => {
          window.location.href = `/game?code=${data.game_code}&player=${playerName}`;
      }).catch(error => console.error('Error creating game:', error));
}

function joinGame() {
    const gameCode = document.getElementById('game_code').value;
    const playerName = document.getElementById('join_player_name').value;
    fetch('/join_game', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ game_code: gameCode, player_name: playerName })
    }).then(response => response.json())
      .then(data => {
          if (data.status === 'success') {
              window.location.href = `/game?code=${gameCode}&player=${playerName}`;
          } else {
              alert(data.message);
          }
      }).catch(error => console.error('Error joining game:', error));
}

socket.on('connect', () => {
    const urlParams = new URLSearchParams(window.location.search);
    const gameCode = urlParams.get('code');
    const playerName = urlParams.get('player');
    socket.emit('join_room', { game_code: gameCode });
    document.getElementById('code-display').textContent = gameCode;

    socket.on('game_state', (data) => {
        updatePlayers(data.players, data.roles);
        updatePhase(data.phase, data.timer);
        const startBtnContainer = document.getElementById('start-btn-container');
        startBtnContainer.innerHTML = '';  // Clear previous content
        if (data.phase === 'lobby' && data.players[0] === playerName) {
            if (data.players.length >= 5) {
                startBtnContainer.innerHTML = '<button id="start-game-btn" class="mt-4 bg-red-600 text-white p-2 rounded w-full" onclick="startGame()">Start Game</button>';
            } else {
                startBtnContainer.innerHTML = '<p class="mt-4 text-gray-600">Waiting for more players (need at least 5 to start).</p>';
            }
        }
    });

    socket.on('player_joined', (data) => {
        updatePlayers(data.players, []);  // Update player list without roles (lobby phase)
    });

    socket.on('game_started', (data) => {
        updatePlayers(data.players, data.roles);  // Update with roles on start
        updatePhase(data.phase, 60);
    });

    socket.on('action_result', (data) => {
        console.log(`${data.player} action result: ${data.result}`);
    });

    socket.on('elimination', (data) => {
        alert(`${data.player} was eliminated! Role: ${data.role}`);
        updatePlayers(); // Refresh player list
    });
});

function startGame() {
    const urlParams = new URLSearchParams(window.location.search);
    const gameCode = urlParams.get('code');
    socket.emit('start_game', { game_code: gameCode });
}

function updatePlayers(players, roles) {
    const playersList = document.getElementById('players-list');
    playersList.innerHTML = '';
    if (players && roles && roles.length > 0) {
        players.forEach((player, index) => {
            const role = roles[index] ? (roles[index].startsWith('dead_') ?