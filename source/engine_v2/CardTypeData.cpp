#include "CardTypeData.h"
#include "CardTypes.h"
#include "FileUtils.h"

using namespace Prismata;

CardTypeData::CardTypeData()
{

}

CardTypeData & CardTypeData::Instance()
{
    static CardTypeData params;
    return params;
}

void CardTypeData::ProcessPostInit()
{
    for (size_t type(0); type < m_allCardTypeInfo.size(); ++type)
    {
        CardTypeInfo & data = m_allCardTypeInfo[type];
        data.attackGivenToEnemy = 0;

        // calculate how much attack buying this card gives to the enemy
        data.attackGivenToEnemy += data.buyScript.getEffect().getGive().amountOf(Resources::Attack);

        const std::vector<CreateDescription> & created = data.buyScript.getEffect().getCreate();
        for (size_t c(0); c < created.size(); ++c)
        {
            // if we give this to the enemy
            if (!created[c].getOwn())
            {
                const CardTypeInfo CardTypeInfo = GetCardTypeInfoByName(created[c].getCardName());

                data.attackGivenToEnemy += CardTypeInfo.attack * (HealthType)created[c].getMultiple();
            }
        }
        
        // process resonate to and resonate from
        if (data.beginOwnTurnScript.hasResonate())
        {
            CardID resonateFromID = GetCardTypeInfoByName(data.beginOwnTurnScript.getResonateEffect().getResonateTypeName()).typeID;
            data.resonatesFromIDs.push_back(resonateFromID);
            m_allCardTypeInfo[resonateFromID].resonatesToIDs.push_back(type);
        }
    }
}
const CardTypeInfo & CardTypeData::getCardTypeInfo(const CardID id)
{
    PRISMATA_ASSERT(id < m_allCardTypeInfo.size(), "Card ID not known: %d", id);

    return m_allCardTypeInfo[id];
}

const CardTypeInfo & CardTypeData::GetCardTypeInfoByName(const std::string & name)
{
    for (CardID c(0); c<m_allCardTypeInfo.size(); ++c)
    {
        if (m_allCardTypeInfo[c].cardName.compare(name) == 0)
        {
            return m_allCardTypeInfo[c];
        }
    }

    return m_allCardTypeInfo[0];
}

std::string CardTypeData::getVariableName(const std::string & str)
{
    char temp[256];
    size_t ind = 0;
    for (size_t i(0); i < str.size(); ++i)
    {
        if (str[i] == ' ')
        {
            if (ind > 0 && temp[ind - 1] != '_')
            {
                temp[ind++] = '_';
            }
        }
        else if (str[i] == '-')
        {

        }
        else
        {
            temp[ind++] = str[i];
        }
    }

    temp[ind] = '\0';
    return std::string(temp);
}

size_t CardTypeData::numCardTypes()
{
    return m_allCardTypeInfo.size();
}

void CardTypeData::ResetData()
{
    m_allCardTypeInfo.clear();
}

void CardTypeData::InitFromMergedDeckJSON(const rapidjson::Value & mergedDeck)
{
    Instance() = CardTypeData();

    m_allCardTypeInfo.push_back(CardTypeInfo());
    m_allCardTypeInfo.push_back(CardTypeInfo());

    PRISMATA_ASSERT(mergedDeck.IsArray(), "Input 'mergedDeck' JSON Value is not an Array");
    
    for (rapidjson::SizeType i=0; i<mergedDeck.Size(); ++i)
    {
        PRISMATA_ASSERT(mergedDeck[i].HasMember("name"), "Deck element has no name field");

        const std::string &         name = mergedDeck[i]["name"].GetString();
        const rapidjson::Value &    val  = mergedDeck[i];

        m_allCardTypeInfo.push_back(CardTypeInfo(m_allCardTypeInfo.size(), name, val));
    }

    ProcessPostInit();

}

void CardTypeData::InitFromCardLibraryFile(const std::string & jsonGameStateCardData)
{
    Instance() = CardTypeData();

    m_allCardTypeInfo.push_back(CardTypeInfo());
    m_allCardTypeInfo.push_back(CardTypeInfo());

    rapidjson::Document document;

    // Exactly the 105 competitive ranked units (by internal name, alphabetized)
    const std::string dominionNames[] =
    {
        "Adrenaline Reactor", "Angelic", "Annihilator", "Antima Comet", "Arms Race", "Arsonist", "Battalion", "BFD", "Beam of Wincing", "Blade",
        "Blood Phage", "Bombarder", "Bond", "Borehole Patroller", "Butter on Blood", "Centrifuge", "Colossus", "Conscription", "Corpus", "Cowardly Marine",
        "Cyclic Attacker", "Deconstructible Tower", "Defense Grid", "Demolition Mech", "Disruption Kit", "Distractorod", "Doomed Drone", "Doomed Infantry", "Doomed Mech", "Doomwall",
        "Drake", "Ebb Turbine", "Electrophore", "Ephemeron", "Fabricator", "Factory", "Ferritin Sac", "Fickle Marine", "Flame Assassin", "Flame Kin",
        "Flame Warrior", "Fragilewall", "Furion", "Galvani Drone", "Gasplant", "Giga Cannon", "Gnoll", "Golem", "Grenadier", "HPMan",
        "Hate Reactor", "Hotel", "House", "Innervi Field", "Ion Cannon", "Jester", "Lancetooth", "Machine", "Manticore", "Marauder",
        "Mega Drone", "Meteor Shower", "Militia", "Minimarshal", "Mobile Animus", "Neo Overlord", "NeoContraption", "Nether Warrior", "Nightmare Cannon", "Nitrocybe",
        "Oxide Mixer", "Panther", "Photonic Fibroid", "Piranha Academy", "Pixie", "Pixieflower", "Polywall", "Psychosis Cannon", "Rocket Artillery", "Roshan",
        "Rukh", "Savior", "Screech Blast", "Sentinel", "Sound Barrier", "Statue", "Stone Guardian", "Supertreant", "Tank", "Tantalum Ray",
        "Tesla Coil", "Thorium Dynamo", "Thunderhead", "Trickster", "Tyranno Smorcus", "Uberdefcell", "Unholy Barrier", "Urban Sentry", "Vai Mauronax", "Valkyrion",
        "Viletrope", "Vivid Drone", "Volatile Blast", "Wild Drone", "Xaetron"
    };

    bool parsingFailed = document.Parse(FileUtils::ReadFile(jsonGameStateCardData).c_str()).HasParseError();

    PRISMATA_ASSERT(!parsingFailed, "Couldn't parse card library file");

    for (rapidjson::Value::ConstMemberIterator itr = document.MemberBegin(); itr != document.MemberEnd(); ++itr)
    {
        const std::string &         name = itr->name.GetString();
        const rapidjson::Value &    val  = itr->value;

        bool isBaseSet = val.HasMember("baseSet") && val["baseSet"].IsInt() && (val["baseSet"].GetInt() == 1);
        bool isDominionSet = std::find(std::begin(dominionNames), std::end(dominionNames), name) != std::end(dominionNames);
               
        if (isBaseSet || isDominionSet)
        {
            m_allCardTypeInfo.push_back(CardTypeInfo(m_allCardTypeInfo.size(), name, val));
        }
    }

    ProcessPostInit();
}

void CardTypeData::printCardTypeVariableNames()
{
    for (size_t i(0); i < m_allCardTypeInfo.size(); ++i)
    {
        const CardTypeInfo & typeData = m_allCardTypeInfo[i];
        std::cout << "CardType " << getVariableName(typeData.cardName) << "(" << typeData.typeID << ");" << std::endl;
        
    }

    for (size_t i(0); i < m_allCardTypeInfo.size(); ++i)
    {
        const CardTypeInfo & typeData = m_allCardTypeInfo[i];
        std::cout << "extern CardType " << getVariableName(typeData.cardName) << ";" << std::endl;
    }
}
