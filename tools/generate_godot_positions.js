#!/usr/bin/env node
/**
 * generate_godot_positions.js
 *
 * Reads PixiJS positioning constants from the viewer source code,
 * converts all positions from PixiJS pixels (top-left origin, Y-down)
 * to Godot world coordinates (center origin, Z-down for top-down camera).
 *
 * Accounts for:
 * - PixiJS sprites use top-left anchor; Godot Sprite3D uses center
 * - StatusOverlay container offset (2, 17)
 * - Icon size (18px = STATUS_SIZE)
 * - Card size (82px = CARD_HEIGHT)
 *
 * Output: GDScript constant block ready to paste into unit_node.gd,
 * plus a human-readable position map for verification.
 */
'use strict';

// === PixiJS constants (from constants.ts) ===
const CARD_HEIGHT = 82;        // Also used as card width for square cards
const CARD_WIDTH = 83;         // Layout spacing
const ART_INSET = 5;
const ART_SIZE = 72;           // CARD_HEIGHT - 2*ART_INSET
const STATUS_SIZE = 18;        // Icon pixel size

// StatusOverlay container position (from StatusOverlay.ts line 30)
const OVERLAY_X = 2;
const OVERLAY_Y = 17;

// Fixed status positions (from constants.ts)
const FIXED_ATTACK_X = 22;
const FIXED_ATTACK_Y = 44;
const FIXED_DEFEND_X = 58;
const FIXED_DEFEND_Y = 44;

// Number offsets from icon position (from constants.ts)
const FIXED_NUM_OFFSET_X = -7;
const FIXED_NUM_OFFSET_Y = 4;
const VAR_NUM_OFFSET_X = -2;
const VAR_NUM_OFFSET_Y = 7;

// Variable icon positioning (from StatusOverlay.ts)
const VAR_ICON_X = 1;          // x position within StatusOverlay
const VAR_ICON_SPACING = 20;   // pixels between variable icon slots
const VAR_ICON_Y_BASE = 4;    // base y offset

// Name label (from UnitCard.ts)
const NAME_X = 20;
const NAME_Y = 6;

// Damage counter (from UnitCard.ts)
const DAMAGE_X = 3;
const DAMAGE_Y = 3;

// Construction timer (from StatusOverlay.ts: position.set(-1, -14) relative to overlay)
const BUILD_TIMER_X = OVERLAY_X + (-1);
const BUILD_TIMER_Y = OVERLAY_Y + (-14);

// Skull center (from UnitCard.ts)
const SKULL_CENTER_X = 41;
const SKULL_CENTER_Y = 43;
const SKULL_SIZE = 54;

// Snowflake center (from UnitCard.ts)
const SNOW_CENTER_X = 41;
const SNOW_CENTER_Y = 43;
const SNOW_SIZE = 44;

// === Conversion functions ===

/**
 * Convert PixiJS top-left pixel coordinate to Godot world coordinate (center origin).
 * Card is CARD_HEIGHT x CARD_HEIGHT pixels = 1.0 x 1.0 world units.
 *
 * Camera: screen-up = world -Z. So SWF Y=0 (top) maps to negative Z (screen top),
 * and SWF Y=82 (bottom) maps to positive Z (screen bottom).
 * Formula: world_z = py/82 - 0.5
 */
function pxToWorld(px_x, px_y) {
    return {
        x: Number((px_x / CARD_HEIGHT - 0.5).toFixed(4)),
        z: Number((px_y / CARD_HEIGHT - 0.5).toFixed(4))
    };
}

/**
 * Convert a top-left-anchored sprite position to center-anchored position.
 * Shifts by half the sprite size.
 */
function topLeftToCenter(px_x, px_y, sprite_size) {
    const half = sprite_size / 2;
    return pxToWorld(px_x + half, px_y + half);
}

/**
 * Convert a top-left-anchored text position to Godot Label3D position.
 * For left-aligned text (HORIZONTAL_ALIGNMENT_LEFT), position is left edge.
 * For center-aligned text, we'd need to know text width (skip for now).
 */
function textToWorld(px_x, px_y) {
    return pxToWorld(px_x, px_y);
}

// === Compute all positions ===

const positions = {};

// Fixed icons (absolute from card top-left)
const atkAbsX = OVERLAY_X + FIXED_ATTACK_X;
const atkAbsY = OVERLAY_Y + FIXED_ATTACK_Y;
const defAbsX = OVERLAY_X + FIXED_DEFEND_X;
const defAbsY = OVERLAY_Y + FIXED_DEFEND_Y;

positions.attack_icon = topLeftToCenter(atkAbsX, atkAbsY, STATUS_SIZE);
positions.defense_icon = topLeftToCenter(defAbsX, defAbsY, STATUS_SIZE);

// Fixed icon numbers (left-aligned text, positioned from icon top-left + offset)
const atkNumAbsX = atkAbsX + FIXED_NUM_OFFSET_X;
const atkNumAbsY = atkAbsY + FIXED_NUM_OFFSET_Y;
positions.attack_number = textToWorld(atkNumAbsX, atkNumAbsY);

const defNumAbsX = defAbsX + FIXED_NUM_OFFSET_X;
const defNumAbsY = defAbsY + FIXED_NUM_OFFSET_Y;
positions.defense_number = textToWorld(defNumAbsX, defNumAbsY);

// Variable icons (slot 0..5)
for (let i = 0; i < 6; i++) {
    const absX = OVERLAY_X + VAR_ICON_X;
    const absY = OVERLAY_Y + i * VAR_ICON_SPACING + VAR_ICON_Y_BASE;
    positions[`var_icon_${i}`] = topLeftToCenter(absX, absY, STATUS_SIZE);

    const numAbsX = absX + VAR_NUM_OFFSET_X;
    const numAbsY = absY + VAR_NUM_OFFSET_Y;
    positions[`var_number_${i}`] = textToWorld(numAbsX, numAbsY);
}

// Variable icon layout constants for Godot
const varIcon0 = positions.var_icon_0;
const varIcon1 = positions.var_icon_1;
positions.var_spacing = Number(((varIcon1.z - varIcon0.z)).toFixed(4));

// Name label (left-aligned)
positions.name_label = textToWorld(NAME_X, NAME_Y);

// Damage counter (left-aligned)
positions.damage_label = textToWorld(DAMAGE_X, DAMAGE_Y);

// Construction timer (left-aligned)
positions.build_timer = textToWorld(BUILD_TIMER_X, BUILD_TIMER_Y);

// Skull (center-anchored, already given as center coords)
positions.skull = pxToWorld(SKULL_CENTER_X, SKULL_CENTER_Y);

// Snowflake (center-anchored)
positions.snowflake = pxToWorld(SNOW_CENTER_X, SNOW_CENTER_Y);

// Card art inset
positions.card_art_topleft = pxToWorld(ART_INSET, ART_INSET);
positions.card_art_scale = Number((ART_SIZE / CARD_HEIGHT).toFixed(4));

// === Output ===

console.log('=== PixiJS → Godot Position Reference ===');
console.log(`Card: ${CARD_HEIGHT}×${CARD_HEIGHT}px = 1.0×1.0 world units`);
console.log(`Icon: ${STATUS_SIZE}×${STATUS_SIZE}px = ${(STATUS_SIZE/CARD_HEIGHT).toFixed(3)} world units`);
console.log(`StatusOverlay container: (${OVERLAY_X}, ${OVERLAY_Y})`);
console.log('');

console.log('--- Position Map (center-based for Sprite3D, left-edge for Label3D) ---');
for (const [key, val] of Object.entries(positions)) {
    if (typeof val === 'object') {
        console.log(`  ${key.padEnd(20)} x=${String(val.x).padStart(7)}  z=${String(val.z).padStart(7)}`);
    } else {
        console.log(`  ${key.padEnd(20)} = ${val}`);
    }
}

console.log('');
console.log('--- GDScript Constants Block (paste into unit_node.gd) ---');
console.log('');

const Y = '0.025';  // layer height for status icons
const Y_LABEL = '0.026';  // slightly above icons

console.log(`# Auto-generated from tools/generate_godot_positions.js`);
console.log(`# Source: PixiJS constants.ts + StatusOverlay.ts + UnitCard.ts`);
console.log(`# Card: ${CARD_HEIGHT}px = 1.0 world unit. Icon: ${STATUS_SIZE}px. Center-anchored.`);
console.log('');
console.log(`# Fixed icon positions (center of ${STATUS_SIZE}px icon, bottom area of card)`);
console.log(`const ATTACK_ICON_POS = Vector3(${positions.attack_icon.x}, ${Y}, ${positions.attack_icon.z})`);
console.log(`const DEFENSE_ICON_POS = Vector3(${positions.defense_icon.x}, ${Y}, ${positions.defense_icon.z})`);
console.log(`# Fixed icon number positions (left-aligned text)`);
console.log(`const ATTACK_NUM_POS = Vector3(${positions.attack_number.x}, ${Y_LABEL}, ${positions.attack_number.z})`);
console.log(`const DEFENSE_NUM_POS = Vector3(${positions.defense_number.x}, ${Y_LABEL}, ${positions.defense_number.z})`);
console.log('');
console.log(`# Variable icon layout (center of ${STATUS_SIZE}px icon, left side of card)`);
console.log(`const VAR_ICON_X = ${varIcon0.x}`);
console.log(`const VAR_ICON_START_Z = ${varIcon0.z}`);
console.log(`const VAR_ICON_SPACING = ${positions.var_spacing}  # ${VAR_ICON_SPACING}px / ${CARD_HEIGHT}`);
console.log(`const VAR_ICON_Y = ${Y}`);
console.log(`# Variable number offset from icon center`);
const varNumDx = Number((positions.var_number_0.x - positions.var_icon_0.x).toFixed(4));
const varNumDz = Number((positions.var_number_0.z - positions.var_icon_0.z).toFixed(4));
console.log(`const VAR_NUM_OFFSET = Vector3(${varNumDx}, 0.001, ${varNumDz})`);
console.log('');
console.log(`# Name label — SWF pixel (${NAME_X}, ${NAME_Y}), left-aligned`);
console.log(`# NameLabel transform Z = ${positions.name_label.z}, X = ${positions.name_label.x}`);
console.log('');
console.log(`# Damage counter — SWF pixel (${DAMAGE_X}, ${DAMAGE_Y}), left-aligned`);
console.log(`# DamageLabel transform Z = ${positions.damage_label.z}, X = ${positions.damage_label.x}`);
console.log('');
console.log(`# Build timer — SWF pixel (${BUILD_TIMER_X}, ${BUILD_TIMER_Y}), left-aligned`);
console.log(`# BuildTimer transform Z = ${positions.build_timer.z}, X = ${positions.build_timer.x}`);
console.log('');
console.log(`# Skull center — SWF pixel (${SKULL_CENTER_X}, ${SKULL_CENTER_Y})`);
console.log(`# Skull transform Z = ${positions.skull.z}, X = ${positions.skull.x}`);
console.log('');
console.log(`# Snowflake center — SWF pixel (${SNOW_CENTER_X}, ${SNOW_CENTER_Y})`);
console.log(`# Snowflake transform Z = ${positions.snowflake.z}, X = ${positions.snowflake.x}`);
console.log('');
console.log(`# Card art scale = ${positions.card_art_scale} (${ART_SIZE}/${CARD_HEIGHT})`);
