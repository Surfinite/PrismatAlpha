#pragma once

#include <string>
#include <unordered_map>

namespace Prismata
{

/// Returns the internal (C++ engine) name for a given display name.
/// If the display name has no mapping (i.e., it IS the internal name), returns the input unchanged.
/// The 116-unit set is frozen and will never change.
inline const std::string & getInternalName(const std::string & displayName)
{
    // Lazy-initialized static map: display name -> internal name
    // Only entries where display != internal are listed.
    static const std::unordered_map<std::string, std::string> displayToInternal = {
        {"Aegis",               "Fragilewall"},
        {"Amporilla",           "Annihilator"},
        {"Animus",              "Academy"},
        {"Apollo",              "Flame Assassin"},
        {"Arka Sodara",         "Roshan"},
        {"Asteri Cannon",       "Giga Cannon"},
        {"Auric Impulse",       "Bond"},
        {"Auride Core",         "Hate Reactor"},
        {"Barrier",             "Sound Barrier"},
        {"Blastforge",          "Brooder"},
        {"Blood Pact",          "Unholy Barrier"},
        {"Bloodrager",          "Gnoll"},
        {"Cauterizer",          "Demolition Mech"},
        {"Centurion",           "Battalion"},
        {"Chieftain",           "Tank"},
        {"Chrono Filter",       "Electrophore"},
        {"Cluster Bolt",        "Meteor Shower"},
        {"Cryo Ray",            "Distractorod"},
        {"Cynestra",            "Marauder"},
        {"Deadeye Operative",   "Nether Warrior"},
        {"Doomed Wall",         "Doomwall"},
        {"Electrovore",         "Fickle Marine"},
        {"Endotherm Kit",       "Disruption Kit"},
        {"Energy Matrix",       "Golem"},
        {"Feral Warden",        "HPMan"},
        {"Fission Turret",      "Deconstructible Tower"},
        {"Flame Animus",        "Piranha Academy"},
        {"Forcefield",          "Blood Barrier"},
        {"Frost Brooder",       "Psychosis Cannon"},
        {"Frostbite",           "Screech Blast"},
        {"Gauss Cannon",        "Minicannon"},
        {"Gauss Charge",        "Flame Kin"},
        {"Gauss Fabricator",    "Fabricator"},
        {"Gaussite Symbiote",   "Gasplant"},
        {"Grenade Mech",        "Blade"},
        {"Grimbotch",           "Doomed Infantry"},
        {"Hannibull",           "Statue"},
        {"Hellhound",           "Grenadier"},
        {"Husk",                "House"},
        {"Iceblade Golem",      "Minimarshal"},
        {"Immolite",            "Cowardly Marine"},
        {"Infusion Grid",       "Hotel"},
        {"Iso Kronus",          "Cyclic Attacker"},
        {"Kinetic Driver",      "Arsonist"},
        {"Lucina Spinos",       "Angelic"},
        {"Mahar Rectifier",     "Viletrope"},
        {"Nivo Charge",         "Volatile Blast"},
        {"Odin",                "Furion"},
        {"Omega Splitter",      "Supertreant"},
        {"Ossified Drone",      "Neo Overlord"},
        {"Perforator",          "Trickster"},
        {"Plasmafier",          "BFD"},
        {"Plexo Cell",          "Uberdefcell"},
        {"Protoplasm",          "Pixieflower"},
        {"Redeemer",            "Rukh"},
        {"Resophore",           "Butter on Blood"},
        {"Rhino",               "Elephant"},
        {"Scorchilla",          "Rocket Artillery"},
        {"Shadowfang",          "Flame Warrior"},
        {"Shiver Yeti",         "Jester"},
        {"Shredder",            "Panther"},
        {"Steelforge",          "Conscription"},
        {"Steelsplitter",       "Treant"},
        {"Synthesizer",         "Factory"},
        {"Tarsier",             "Tesla Tower"},
        {"Tatsu Nullifier",     "Nightmare Cannon"},
        {"The Wincer",          "Beam of Wincing"},
        {"Thermite Core",       "Adrenaline Reactor"},
        {"Tia Thurnax",         "Ephemeron"},
        {"Trinity Drone",       "Machine"},
        {"Venge Cannon",        "Ion Cannon"},
        {"Xeno Guardian",       "Stone Guardian"},
        {"Zemora Voidbringer",  "NeoContraption"},
    };

    auto it = displayToInternal.find(displayName);
    if (it != displayToInternal.end())
    {
        return it->second;
    }

    // No mapping found — display name IS the internal name
    return displayName;
}

/// Returns the display (UI) name for a given internal name.
/// If the internal name has no mapping (i.e., it IS the display name), returns the input unchanged.
inline const std::string & getDisplayName(const std::string & internalName)
{
    // Lazy-initialized static map: internal name -> display name
    static const std::unordered_map<std::string, std::string> internalToDisplay = {
        {"Fragilewall",             "Aegis"},
        {"Annihilator",             "Amporilla"},
        {"Academy",                 "Animus"},
        {"Flame Assassin",          "Apollo"},
        {"Roshan",                  "Arka Sodara"},
        {"Giga Cannon",             "Asteri Cannon"},
        {"Bond",                    "Auric Impulse"},
        {"Hate Reactor",            "Auride Core"},
        {"Sound Barrier",           "Barrier"},
        {"Brooder",                 "Blastforge"},
        {"Unholy Barrier",          "Blood Pact"},
        {"Gnoll",                   "Bloodrager"},
        {"Demolition Mech",         "Cauterizer"},
        {"Battalion",               "Centurion"},
        {"Tank",                    "Chieftain"},
        {"Electrophore",            "Chrono Filter"},
        {"Meteor Shower",           "Cluster Bolt"},
        {"Distractorod",            "Cryo Ray"},
        {"Marauder",                "Cynestra"},
        {"Nether Warrior",          "Deadeye Operative"},
        {"Doomwall",                "Doomed Wall"},
        {"Fickle Marine",           "Electrovore"},
        {"Disruption Kit",          "Endotherm Kit"},
        {"Golem",                   "Energy Matrix"},
        {"HPMan",                   "Feral Warden"},
        {"Deconstructible Tower",   "Fission Turret"},
        {"Piranha Academy",         "Flame Animus"},
        {"Blood Barrier",           "Forcefield"},
        {"Psychosis Cannon",        "Frost Brooder"},
        {"Screech Blast",           "Frostbite"},
        {"Minicannon",              "Gauss Cannon"},
        {"Flame Kin",               "Gauss Charge"},
        {"Fabricator",              "Gauss Fabricator"},
        {"Gasplant",                "Gaussite Symbiote"},
        {"Blade",                   "Grenade Mech"},
        {"Doomed Infantry",         "Grimbotch"},
        {"Statue",                  "Hannibull"},
        {"Grenadier",               "Hellhound"},
        {"House",                   "Husk"},
        {"Minimarshal",             "Iceblade Golem"},
        {"Cowardly Marine",         "Immolite"},
        {"Hotel",                   "Infusion Grid"},
        {"Cyclic Attacker",         "Iso Kronus"},
        {"Arsonist",                "Kinetic Driver"},
        {"Angelic",                 "Lucina Spinos"},
        {"Viletrope",               "Mahar Rectifier"},
        {"Volatile Blast",          "Nivo Charge"},
        {"Furion",                   "Odin"},
        {"Supertreant",             "Omega Splitter"},
        {"Neo Overlord",            "Ossified Drone"},
        {"Trickster",               "Perforator"},
        {"BFD",                     "Plasmafier"},
        {"Uberdefcell",             "Plexo Cell"},
        {"Pixieflower",             "Protoplasm"},
        {"Rukh",                    "Redeemer"},
        {"Butter on Blood",         "Resophore"},
        {"Elephant",                "Rhino"},
        {"Rocket Artillery",        "Scorchilla"},
        {"Flame Warrior",           "Shadowfang"},
        {"Jester",                  "Shiver Yeti"},
        {"Panther",                 "Shredder"},
        {"Conscription",            "Steelforge"},
        {"Treant",                  "Steelsplitter"},
        {"Factory",                 "Synthesizer"},
        {"Tesla Tower",             "Tarsier"},
        {"Nightmare Cannon",        "Tatsu Nullifier"},
        {"Beam of Wincing",         "The Wincer"},
        {"Adrenaline Reactor",      "Thermite Core"},
        {"Ephemeron",               "Tia Thurnax"},
        {"Machine",                 "Trinity Drone"},
        {"Ion Cannon",              "Venge Cannon"},
        {"Stone Guardian",          "Xeno Guardian"},
        {"NeoContraption",          "Zemora Voidbringer"},
    };

    auto it = internalToDisplay.find(internalName);
    if (it != internalToDisplay.end())
    {
        return it->second;
    }

    // No mapping found — internal name IS the display name
    return internalName;
}

} // namespace Prismata
