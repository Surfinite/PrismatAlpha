"""AI parameter loading and selection for PrismataAI.exe.

Loads AI parameters from SWF-extracted .bin files (plain JSON text).
Matches the AS3 logic in AIThreadHandler.as for selecting full vs short
params based on difficulty and turn number.
"""

import re

AI_NO_OPENINGS = [
    'DocileAI', 'RandomAI', 'EasyAI', 'MediumAI', 'ExpertAI', 'HardAI', 'HardestAI',
    'BL_HighEcon_Basic', 'BL_HighEcon_Adept', 'BL_HighEcon_Expert', 'BL_HighEcon_Master',
    'BL_Blue_Rusher', 'BL_Red_Rusher', 'BL_Green_Rusher',
    'BL_Red_Master', 'BL_Blue_Master', 'BL_Green_Master',
    'Mission_Giselle_Hard', 'Mission_Xelgudu1_Hard', 'Mission_Rube', 'Mission_Rube_Hard',
]


def load_params(path):
    """Load and clean AI parameters JSON string from a .bin file."""
    with open(path, 'r', encoding='utf-8') as f:
        raw = f.read()
    return re.sub(r'[\r\n\t]+', '', raw)


def select_params(difficulty, turn_number, full_params, short_params):
    """Select which AI parameters to use.

    Matches AIThreadHandler.as:297-303. AS3 uses indexOf > 0, so
    DocileAI (index 0) gets full params (reproducing the AS3 bug).
    """
    try:
        idx = AI_NO_OPENINGS.index(difficulty)
    except ValueError:
        idx = -1
    if idx > 0 or turn_number > 16:
        return short_params
    return full_params
