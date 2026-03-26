// tools/snapshot_schema.js
// Validates a BoardSnapshot object against the spec schema (Section 2).
// Returns { valid: bool, errors: string[] }

function validateSnapshot(snapshot) {
    const errors = [];

    // Required top-level fields
    if (typeof snapshot.schemaVersion !== 'number') errors.push('missing schemaVersion');
    else if (snapshot.schemaVersion !== 1) errors.push('unsupported schemaVersion: ' + snapshot.schemaVersion);

    if (typeof snapshot.seq !== 'number') errors.push('missing seq');
    if (typeof snapshot.turn !== 'number') errors.push('missing turn');
    if (!['action', 'defense', 'confirm'].includes(snapshot.phase)) {
        errors.push('invalid phase: ' + snapshot.phase);
    }
    if (![0, 1].includes(snapshot.activePlayer)) errors.push('invalid activePlayer: ' + snapshot.activePlayer);
    if (!Array.isArray(snapshot.players) || snapshot.players.length !== 2) {
        errors.push('players must be array of length 2');
    }
    if (!Array.isArray(snapshot.events)) errors.push('events must be array');

    // Validate players
    if (snapshot.players) {
        for (let p = 0; p < snapshot.players.length; p++) {
            const player = snapshot.players[p];
            if (!player) { errors.push('players[' + p + '] is null'); continue; }
            if (player.id !== p) errors.push('players[' + p + '].id should be ' + p + ', got ' + player.id);

            const res = player.resources;
            if (!res) { errors.push('players[' + p + '].resources missing'); continue; }
            for (const key of ['gold', 'green', 'blue', 'red', 'energy', 'attack']) {
                if (typeof res[key] !== 'number') errors.push('players[' + p + '].resources.' + key + ' missing');
            }

            if (!Array.isArray(player.units)) {
                errors.push('players[' + p + '].units must be array');
                continue;
            }
            for (let u = 0; u < player.units.length; u++) {
                const unit = player.units[u];
                if (typeof unit.id !== 'number') errors.push('players[' + p + '].units[' + u + '].id missing');
                if (typeof unit.cardId !== 'string') errors.push('players[' + p + '].units[' + u + '].cardId missing');
                if (typeof unit.displayName !== 'string') errors.push('players[' + p + '].units[' + u + '].displayName missing');
                if (!unit.stats) errors.push('players[' + p + '].units[' + u + '].stats missing');
                if (!unit.state) errors.push('players[' + p + '].units[' + u + '].state missing');
                if (!unit.render) errors.push('players[' + p + '].units[' + u + '].render missing');
                if (unit.render && !['front', 'middle', 'back'].includes(unit.render.row)) {
                    errors.push('players[' + p + '].units[' + u + '].render.row invalid: ' + unit.render.row);
                }
            }
        }
    }

    // Validate events
    const validEventTypes = [
        'buy', 'kill', 'sacrifice', 'assign_blocker',
        'breach_start', 'breach_kill', 'ability',
        'phase_change', 'turn_start'
    ];
    if (snapshot.events) {
        for (let e = 0; e < snapshot.events.length; e++) {
            const evt = snapshot.events[e];
            if (!validEventTypes.includes(evt.type)) {
                errors.push('events[' + e + '].type unknown: ' + evt.type);
            }
        }
    }

    return { valid: errors.length === 0, errors };
}

// CLI smoke test
if (require.main === module) {
    const good = {
        schemaVersion: 1, seq: 0, turn: 1, phase: 'action', activePlayer: 0,
        players: [
            { id: 0, resources: { gold: 6, green: 0, blue: 0, red: 0, energy: 0, attack: 0 }, units: [] },
            { id: 1, resources: { gold: 7, green: 0, blue: 0, red: 0, energy: 0, attack: 0 }, units: [] }
        ],
        events: []
    };
    const r1 = validateSnapshot(good);
    console.log('Valid snapshot:', r1.valid ? 'PASS' : 'FAIL', r1.errors);

    const bad = { seq: 0 };
    const r2 = validateSnapshot(bad);
    console.log('Invalid snapshot:', !r2.valid ? 'PASS' : 'FAIL', '(' + r2.errors.length + ' errors)');
}

module.exports = { validateSnapshot };
