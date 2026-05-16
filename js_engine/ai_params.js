'use strict';

const fs = require('fs');
const path = require('path');

/**
 * ai_params.js — Load AI parameters from SWF-extracted .bin files.
 *
 * These are plain JSON text despite the .bin extension (extracted via JPEXS FFDec).
 *
 * Routing is by aiDifficulty (primary) and turn number (fallback). See
 * selectParams() and AS3 AIThreadHandler.as:297 / :340.
 *
 *   - Full params (148_*.bin): the default. Defines 105 opening books totalling
 *     988 entries, including 98 unit-specific R_*OB books (R_AmporillaOB, ...).
 *   - Short params (93_*.bin): used when aiDifficulty is in AI_NO_OPENINGS
 *     (HardestAI, HardAI, ExpertAI, the BL_HighEcon_* family, the rusher
 *     variants, mission bots) OR when turnNumber > 16. Defines 7 generic
 *     opening books totalling 120 entries — DefaultOpeningBook2 (50),
 *     FastimusOpeningBook (17), BlueTurnTwoOpeningBook (17), Xelgudu1OpeningBook
 *     (13), ConduitOpeningBook (11), OpeningBook_HighEcon (8),
 *     DefaultOpeningBook (4). The 98 per-unit R_*OB books are dropped.
 *
 * AI_NO_OPENINGS is therefore a misleading name: AIs in that list still get
 * the generic OBs through the short blob (e.g. HardestAI's NewIterator_Root
 * portfolio consumes DefaultOpeningBook2 via ACAvoidBreach_ChillSolver2 and
 * DefaultOpeningBook via the other four ChillSolver branches). They just lose
 * the per-unit R_*OB books that bot-league/random-set players reach for.
 *
 * The AS3 code (AIThreadHandler.as:203-209) strips all whitespace [\r\n\t]
 * before sending to MCDSAI.
 */

const FULL_PARAMS_PATH = path.resolve(__dirname,
    '../tmp_swf_extract/148_AI.AIThreadHandler_aiParamTextLoad.bin');
const SHORT_PARAMS_PATH = path.resolve(__dirname,
    '../tmp_swf_extract/93_AI.AIThreadHandler_aiParam_shortTextLoad.bin');

/**
 * Load and clean AI parameters JSON string.
 * Strips whitespace to match AS3 behavior (AIThreadHandler.as:206).
 *
 * @param {string} [filePath] - Override path
 * @returns {string} Cleaned JSON string (NOT parsed — sent raw to MCDSAI)
 */
function loadFullParams(filePath) {
    filePath = filePath || FULL_PARAMS_PATH;
    const raw = fs.readFileSync(filePath, 'utf-8');
    // AS3: aiParameters = aiParamString.toString().replace(/[\r\n\t]+/g, "")
    return raw.replace(/[\r\n\t]+/g, '');
}

/**
 * Load short params (used after turn 16).
 * @param {string} [filePath] - Override path
 * @returns {string} Cleaned JSON string
 */
function loadShortParams(filePath) {
    filePath = filePath || SHORT_PARAMS_PATH;
    const raw = fs.readFileSync(filePath, 'utf-8');
    return raw.replace(/[\r\n\t]+/g, '');
}

/**
 * AI names that should NOT use opening books (use short params).
 * From AIThreadHandler.as:110.
 */
const AI_NO_OPENINGS = [
    'DocileAI', 'RandomAI', 'EasyAI', 'MediumAI', 'ExpertAI', 'HardAI', 'HardestAI',
    'BL_HighEcon_Basic', 'BL_HighEcon_Adept', 'BL_HighEcon_Expert', 'BL_HighEcon_Master',
    'BL_Blue_Rusher', 'BL_Red_Rusher', 'BL_Green_Rusher',
    'BL_Red_Master', 'BL_Blue_Master', 'BL_Green_Master',
    'Mission_Giselle_Hard', 'Mission_Xelgudu1_Hard', 'Mission_Rube', 'Mission_Rube_Hard'
];

/**
 * Select which AI parameters to use based on difficulty and turn number.
 * Matches AIThreadHandler.as:297-303 and :340-347 logic.
 */
function selectParams(aiDifficulty, turnNumber, fullParams, shortParams) {
    // NOTE: AS3 source (AIThreadHandler.as:297,340) uses `> 0`, not `!== -1`.
    // This means DocileAI (index 0) incorrectly gets full params in the live game.
    // We reproduce this exact behavior for faithfulness.
    if (AI_NO_OPENINGS.indexOf(aiDifficulty) > 0 || turnNumber > 16) {
        return shortParams;
    }
    return fullParams;
}

module.exports = {
    loadFullParams,
    loadShortParams,
    selectParams,
    AI_NO_OPENINGS,
    FULL_PARAMS_PATH,
    SHORT_PARAMS_PATH
};
