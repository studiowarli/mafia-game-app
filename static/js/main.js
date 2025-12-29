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
      });
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
      });
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
    });

    socket.on('game_started', (data) => {
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

function updatePlayers(players, roles) {
    const playersList = document.getElementById('players-list');
    playersList.innerHTML = '';
    if (players && roles) {
        players.forEach((player, index) => {
            const role = roles[index].startsWith('dead_') ? 'dead' : roles[index];
            const icon = role === 'mafia' ? '👹' : '😇';
            playersList.innerHTML += `<div>${player} ${role === 'dead' ? '(Dead)' : ''} ${icon}</div>`;
        });
    }
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
    // Simplified phase logic (to be expanded)
    if (phase === 'night') {
        document.getElementById('action-panel').classList.remove('hidden');
    } else if (phase === 'day') {
        document.getElementById('vote-panel').classList.remove('hidden');
    }
}