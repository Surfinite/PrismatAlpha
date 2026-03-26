/**
 * status_overlay.js — Pure-function port of StatusOverlay.ts update() from <ladder>-site.
 *
 * Computes which status icons/numbers should appear on a card, without any
 * rendering. Returns a data-only description of the status overlay state.
 */

'use strict';

const { snapshotUnitToCardInstance } = require('./visual_state');

/**
 * Compute the status overlay icons for a single unit.
 *
 * @param {object} unit - Snapshot unit object
 * @param {object} cardMeta - Card metadata from cardLibrary.jso
 * @returns {object} Status overlay data
 */
function computeStatusIcons(unit, cardMeta) {
    const inst = snapshotUnitToCardInstance(unit);
    const meta = cardMeta || {};

    const variableIcons = [];
    let constructionTimer = null;

    // Construction timer takes precedence
    if (inst.constructionTime > 0 && inst.damage === 0) {
        constructionTimer = inst.constructionTime;

        // During construction, only show HP for fragile units
        if (meta.isFragile) {
            variableIcons.push({ type: 'hp', count: inst.health });
        }
    } else {
        // Normal state — show all applicable icons
        if (meta.isFrontline) {
            variableIcons.push({ type: 'frontline' });
        }
        if (meta.isFragile) {
            variableIcons.push({ type: 'hp', count: inst.health });
        }
        if (inst.delay > 0) {
            variableIcons.push({ type: 'delay', count: inst.delay });
        }
        if (inst.lifespan > 0) {
            variableIcons.push({ type: 'lifespan', count: inst.lifespan });
        }
        if (inst.charge > 0 || (meta.charge && meta.charge > 0 && inst.charge > 0)) {
            const level = Math.min(inst.charge, 3);
            variableIcons.push({ type: 'charge', count: inst.charge, level });
        }
        if (inst.disruptDamage > 0) {
            const isFull = inst.disruptDamage >= inst.health;
            variableIcons.push({
                type: 'chill',
                count: inst.disruptDamage,
                full: isFull,
            });
        }
    }

    // Fixed status icons (bottom-right corner)
    // Use unit.stats.attack (snapshot, authoritative) falling back to meta
    const attackPotential = unit.stats.attack || meta.attack || 0;
    const fixedIcons = {
        attack: attackPotential > 0 ? { value: attackPotential } : null,
        defense: null,
        spell: false,
    };

    if (!meta.isFragile) {
        if (meta.cardType === 'spell') {
            fixedIcons.spell = true;
        } else if ((meta.toughness || 0) > 0) {
            fixedIcons.defense = { value: meta.toughness };
        }
    }

    return {
        constructionTimer,
        variableIcons,
        fixedIcons,
    };
}

module.exports = { computeStatusIcons };
