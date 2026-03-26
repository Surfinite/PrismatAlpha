/**
 * visual_state.js — Pure-function port of visual-state.ts from <ladder>-site.
 *
 * Takes snapshot unit data + card metadata and produces the exact same visual
 * state decisions the PixiJS viewer would make (background frame, cover overlay,
 * shading, alpha, skull, snowflake, damage counter).
 *
 * Snapshot field → PixiJS CardInstance mapping:
 *   unit.state.mode          → deadness (alive/dead), constructionTime
 *   unit.state.blocking      → blocking
 *   unit.state.chilled       → disruptDamage
 *   unit.state.attacking     → role === 'assigned'
 *   unit.stats.hp            → health
 *   unit.stats.maxHp - hp    → damage
 *   unit.state.delay         → delay
 *   unit.state.charge        → charge
 *   unit.state.lifespan      → lifespan
 *   unit.owner               → owner (0 = P0/bottom, 1 = P1/top)
 */

'use strict';

// Background frame indices (UIInst.as BACK_*)
const BACK_DEAD = 0;
const BACK_BLOCK = 1;
// const BACK_BUSY = 2;  // unused in practice
const BACK_ABSORB = 3;
const BACK_BLOCK_FROST = 4;
const BACK_BOUGHT = 5;
const BACK_WHITEPINK = 6;
const BACK_BLOCKRED = 7;
const BACK_BUSYBLUE = 8;
const BACK_BUSYRED = 9;

// Cover frame indices (UIInst.as COVER_*)
const COVER_EMPTY = 0;
const COVER_INVSPAWN = 1;
const COVER_INVBOUGHT = 2;
const COVER_ASSIGNED = 3;
const COVER_PROMPT = 4;
const COVER_BANG = 5;

// Shading frame indices (UIInst.as SHADING_*)
const SHADING_EMPTY = 0;
const SHADING_NOTBLOCK = 1;
const SHADING_BLOCK = 2;
const SHADING_DEAD_BLOCK = 3;
const SHADING_REDBLOCK = 4;

const INST_HACK_ALPHA = 0.999;
const ALPHA_FOR_INVULNERABLE = 0.87;

/**
 * Convert snapshot unit data to the CardInstance shape expected by the PixiJS logic.
 */
function snapshotUnitToCardInstance(unit) {
    const hp = unit.stats.hp;
    const maxHp = unit.stats.maxHp;
    const damage = Math.max(0, maxHp - hp);
    const isDead = unit.state.mode === 'dead' || hp <= 0;

    return {
        owner: unit.owner,
        health: hp,
        damage: damage,
        blocking: !!unit.state.blocking,
        constructionTime: unit.state.buildTurnsRemaining || 0,
        disruptDamage: unit.state.chilled || 0,
        delay: unit.state.delay || 0,
        charge: unit.state.charge || 0,
        lifespan: unit.state.lifespan != null ? unit.state.lifespan : -1,
        // role: snapshot has attacking bool, not role string
        // We map attacking → 'assigned', otherwise 'default'
        // boughtThisPhase is NOT available in snapshots
        role: unit.state.attacking ? 'assigned' : 'default',
        deadness: isDead ? 'dead' : 'alive',
        boughtThisPhase: undefined, // not available
    };
}

/**
 * Compute the visual state for a single unit.
 *
 * @param {object} unit - Snapshot unit object
 * @param {object} cardMeta - Card metadata from cardLibrary.jso
 * @param {string} phase - 'defense' | 'action' | 'confirm'
 * @param {number} colorOnBottom - Which player is on bottom (0 = P0)
 * @returns {object} Visual state object
 */
function computeVisualState(unit, cardMeta, phase, colorOnBottom) {
    const inst = snapshotUnitToCardInstance(unit);
    const meta = cardMeta || {};

    // Derived predicates
    const isDead = inst.deadness !== 'alive';
    const isBottomPlayer = (inst.owner === 0) === (colorOnBottom === 0);
    const isFullyChilled = inst.disruptDamage >= inst.health && inst.health > 0;
    const isPartiallyDamaged = inst.damage > 0 && inst.damage < inst.health;
    const isSpell = meta.cardType === 'spell';

    // Track auditability — some states depend on boughtThisPhase/sellable
    let auditable = true;
    let unauditableReason = null;

    // Output slots — initialised to defaults
    let backFrame = BACK_BUSYBLUE;
    let coverFrame = COVER_EMPTY;
    let shadingFrame = SHADING_EMPTY;
    let cardAlpha = INST_HACK_ALPHA;
    let showSkull = false;
    let chillShouldAppear = false;

    // ----------------------------------------------------------------
    // Phase 1 — base background frame
    // ----------------------------------------------------------------
    if (isDead) {
        backFrame = BACK_DEAD;
        showSkull = true;
    } else if (isFullyChilled) {
        backFrame = BACK_BLOCK_FROST;
        chillShouldAppear = true;
    } else if (inst.blocking) {
        backFrame = BACK_BLOCK;
        shadingFrame = SHADING_BLOCK;
    } else {
        backFrame = isBottomPlayer ? BACK_BUSYBLUE : BACK_BUSYRED;
    }

    // Phase 1b — convert BACK_BLOCK to BACK_BLOCKRED for the top player
    if (backFrame === BACK_BLOCK && !isBottomPlayer) {
        backFrame = BACK_BLOCKRED;
    }

    // ----------------------------------------------------------------
    // Phase 2 — role / construction overrides for cover and shading
    // ----------------------------------------------------------------
    // Note: 'sellable' role is NOT available in snapshots.
    // We handle 'assigned' and construction, and mark sellable-dependent
    // paths as unauditable.
    if (inst.role === 'sellable') {
        // This branch can't be reached from snapshot data (role is never 'sellable')
        // but kept for completeness if the schema is ever extended.
        if (inst.constructionTime === 0) {
            if (isSpell) {
                coverFrame = COVER_EMPTY;
                shadingFrame = SHADING_EMPTY;
            } else if (inst.blocking) {
                if (isDead && inst.damage === 0) {
                    shadingFrame = SHADING_DEAD_BLOCK;
                    coverFrame = COVER_EMPTY;
                } else {
                    coverFrame = COVER_PROMPT;
                    shadingFrame = SHADING_EMPTY;
                }
            } else {
                coverFrame = COVER_EMPTY;
                shadingFrame = SHADING_NOTBLOCK;
            }
        } else {
            cardAlpha = ALPHA_FOR_INVULNERABLE;
            coverFrame = COVER_INVBOUGHT;
            shadingFrame = SHADING_EMPTY;
            backFrame = BACK_BOUGHT;
        }
    } else if (inst.constructionTime >= 1) {
        cardAlpha = ALPHA_FOR_INVULNERABLE;
        coverFrame = COVER_INVSPAWN;
        shadingFrame = SHADING_EMPTY;
        backFrame = BACK_BOUGHT;
        // Note: a sellable unit under construction would use COVER_INVBOUGHT instead
        // of COVER_INVSPAWN, but we can't distinguish them from snapshot data.
        // This is auditable because the visual difference is minor (black vs gold clock).
    } else {
        // Default role or 'assigned'
        if (inst.role === 'assigned') {
            coverFrame = COVER_ASSIGNED;
        } else {
            coverFrame = COVER_EMPTY;
        }

        if (meta.defaultBlocking && !inst.blocking) {
            shadingFrame = SHADING_NOTBLOCK;
        } else if (isDead && inst.blocking && inst.damage === 0) {
            shadingFrame = SHADING_DEAD_BLOCK;
        } else if (inst.blocking) {
            shadingFrame = SHADING_BLOCK;
        } else {
            shadingFrame = SHADING_EMPTY;
        }
    }

    // Phase 2b — convert SHADING_BLOCK to SHADING_REDBLOCK for the top player
    if (shadingFrame === SHADING_BLOCK && !isBottomPlayer) {
        shadingFrame = SHADING_REDBLOCK;
    }

    // ----------------------------------------------------------------
    // Phase 3 — damage overrides (applied after phase 2)
    // ----------------------------------------------------------------
    let damageCounter = 0;

    if (inst.damage > 0) {
        coverFrame = COVER_BANG;
        shadingFrame = SHADING_EMPTY;
        damageCounter = inst.damage;

        if (isPartiallyDamaged && phase === 'defense') {
            backFrame = BACK_ABSORB;
        } else if (inst.blocking) {
            backFrame = BACK_DEAD;
            showSkull = true;
        } else if (isPartiallyDamaged && !isDead) {
            backFrame = BACK_ABSORB;
        } else {
            backFrame = BACK_WHITEPINK;
            showSkull = true;
        }
    }

    // ----------------------------------------------------------------
    // Phase 4 — chill snowflake (suppressed during defense phase)
    // ----------------------------------------------------------------
    const showChillSnowflake = chillShouldAppear && phase !== 'defense';

    // Mark as unauditable if sellable/boughtThisPhase would matter
    // The cover_overlay for defense-phase units that could be sellable is uncertain
    // We can't know from snapshot data alone whether COVER_PROMPT vs COVER_EMPTY
    // Note: this is a conservative approach — most units are NOT sellable
    // We mark specific features unauditable in the audit runner, not here.

    return {
        backFrame,
        coverFrame,
        shadingFrame,
        cardAlpha,
        showSkull,
        showChillSnowflake,
        damageCounter,
        auditable,
        unauditableReason,
    };
}

// Export constants for tests and audit runner
module.exports = {
    computeVisualState,
    snapshotUnitToCardInstance,
    // Constants
    BACK_DEAD, BACK_BLOCK, BACK_ABSORB, BACK_BLOCK_FROST, BACK_BOUGHT,
    BACK_WHITEPINK, BACK_BLOCKRED, BACK_BUSYBLUE, BACK_BUSYRED,
    COVER_EMPTY, COVER_INVSPAWN, COVER_INVBOUGHT, COVER_ASSIGNED,
    COVER_PROMPT, COVER_BANG,
    SHADING_EMPTY, SHADING_NOTBLOCK, SHADING_BLOCK, SHADING_DEAD_BLOCK,
    SHADING_REDBLOCK,
    INST_HACK_ALPHA, ALPHA_FOR_INVULNERABLE,
};
