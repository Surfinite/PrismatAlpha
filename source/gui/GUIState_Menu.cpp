#include "GUIState_Menu.h"
#include "GUIState_Play.h"

#include "Prismata.h"
#include "PrismataAI.h"
#include "Assets.h"
#include "GUIEngine.h"

#include <filesystem>
#include <fstream>
#include <algorithm>

#include "rapidjson/document.h"

using namespace Prismata;

GUIState_Menu::GUIState_Menu(GUIEngine & game)
    : GUIState(game)
{
    init("");
}

void GUIState_Menu::init(const std::string & menuConfig)
{
    m_title = "Prismata AI: Select Starting State";

    for (auto & stateName : AIParameters::Instance().getStateNames())
    {
        m_menuStrings.push_back(stateName);
    }

    // Separator between states and replay folders
    m_separatorIndex = m_menuStrings.size();
    m_menuStrings.push_back("----------------------------");

    scanReplayFolders();

    m_menuText.setFont(Assets::Instance().getFont("Consolas"));
    m_menuText.setCharacterSize(16);
}

void GUIState_Menu::scanReplayFolders()
{
    m_replayFolders.clear();

    const std::string replayDir = "asset/replays";
    if (!std::filesystem::exists(replayDir) || !std::filesystem::is_directory(replayDir))
    {
        return;
    }

    // Collect subdirectories
    std::vector<std::string> folderNames;
    for (auto & entry : std::filesystem::directory_iterator(replayDir))
    {
        if (!entry.is_directory()) continue;
        folderNames.push_back(entry.path().filename().string());
    }
    std::sort(folderNames.begin(), folderNames.end());

    for (auto & folderName : folderNames)
    {
        ReplayFolderInfo folder;
        folder.folderName = folderName;

        std::string folderPath = replayDir + "/" + folderName;
        std::vector<std::string> jsonFiles;
        for (auto & fileEntry : std::filesystem::directory_iterator(folderPath))
        {
            if (!fileEntry.is_regular_file()) continue;
            if (fileEntry.path().extension() != ".json") continue;
            jsonFiles.push_back(fileEntry.path().filename().string());
        }
        std::sort(jsonFiles.begin(), jsonFiles.end());

        for (auto & fileName : jsonFiles)
        {
            ReplayFileInfo fi;
            fi.path = folderPath + "/" + fileName;
            // Strip .json extension for display
            fi.displayName = fileName.substr(0, fileName.size() - 5);
            folder.files.push_back(fi);
        }

        if (!folder.files.empty())
        {
            std::string label = folderName + " (" + std::to_string(folder.files.size()) + " games)";
            m_menuStrings.push_back(label);
            m_replayFolders.push_back(folder);
        }
    }
}

void GUIState_Menu::loadReplay(const std::string & filepath)
{
    std::ifstream file(filepath);
    if (!file.is_open())
    {
        std::cout << "Failed to open replay: " << filepath << std::endl;
        return;
    }

    std::string content((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
    file.close();

    rapidjson::Document doc;
    doc.Parse(content.c_str());

    if (doc.HasParseError() || !doc.HasMember("states") || !doc["states"].IsArray())
    {
        std::cout << "Invalid replay file: " << filepath << std::endl;
        return;
    }

    std::string p0 = doc.HasMember("p0") ? doc["p0"].GetString() : "Player 0";
    std::string p1 = doc.HasMember("p1") ? doc["p1"].GetString() : "Player 1";
    int winner = doc.HasMember("winner") ? doc["winner"].GetInt() : -1;

    const auto & states = doc["states"];
    std::vector<GameState> replayStates;
    replayStates.reserve(states.Size());

    for (rapidjson::SizeType i = 0; i < states.Size(); ++i)
    {
        replayStates.push_back(GameState(states[i]));
    }

    if (replayStates.empty())
    {
        std::cout << "Replay has no states: " << filepath << std::endl;
        return;
    }

    // Parse optional per-action replay metadata
    std::vector<std::string> actionLabels;
    std::vector<size_t> turnBoundaries;
    int totalTurns = 0;

    if (doc.HasMember("actions") && doc["actions"].IsArray())
    {
        const auto & actions = doc["actions"];
        actionLabels.reserve(actions.Size());
        for (rapidjson::SizeType i = 0; i < actions.Size(); ++i)
        {
            actionLabels.push_back(actions[i].GetString());
        }
    }

    if (doc.HasMember("turnBoundaries") && doc["turnBoundaries"].IsArray())
    {
        const auto & boundaries = doc["turnBoundaries"];
        turnBoundaries.reserve(boundaries.Size());
        for (rapidjson::SizeType i = 0; i < boundaries.Size(); ++i)
        {
            turnBoundaries.push_back(static_cast<size_t>(boundaries[i].GetUint64()));
        }
    }

    if (doc.HasMember("turns") && doc["turns"].IsInt())
    {
        totalTurns = doc["turns"].GetInt();
    }

    m_game.pushState(std::make_shared<GUIState_Play>(m_game, std::move(replayStates), p0, p1, winner,
                                                      std::move(actionLabels), std::move(turnBoundaries), totalTurns));
}

void GUIState_Menu::onFrame()
{
    sUserInput();
    sRender();
}

void GUIState_Menu::sUserInput()
{
    sf::Event event;
    while (m_game.window().pollEvent(event))
    {
        if (event.type == sf::Event::Closed)
        {
            m_game.quit();
        }

        if (event.type == sf::Event::KeyPressed)
        {
            if (m_inReplayFolder)
            {
                // Inside a replay folder — navigate files
                auto & folder = m_replayFolders[m_selectedReplayFolder];
                switch (event.key.code)
                {
                    case sf::Keyboard::Escape:
                    {
                        m_inReplayFolder = false;
                        break;
                    }
                    case sf::Keyboard::W:
                    case sf::Keyboard::Up:
                    {
                        if (m_selectedReplayFile > 0) { m_selectedReplayFile--; }
                        else { m_selectedReplayFile = folder.files.size() - 1; }
                        break;
                    }
                    case sf::Keyboard::S:
                    case sf::Keyboard::Down:
                    {
                        m_selectedReplayFile = (m_selectedReplayFile + 1) % folder.files.size();
                        break;
                    }
                    case sf::Keyboard::D:
                    case sf::Keyboard::Return:
                    {
                        loadReplay(folder.files[m_selectedReplayFile].path);
                        break;
                    }
                    default: break;
                }
            }
            else
            {
                // Main menu navigation
                switch (event.key.code)
                {
                    case sf::Keyboard::Escape:
                    {
                        m_game.quit();
                        break;
                    }
                    case sf::Keyboard::W:
                    case sf::Keyboard::Up:
                    {
                        if (m_selectedMenuIndex > 0)
                        {
                            m_selectedMenuIndex--;
                            // Skip separator
                            if (m_selectedMenuIndex == m_separatorIndex)
                            {
                                if (m_separatorIndex > 0) { m_selectedMenuIndex--; }
                                else { m_selectedMenuIndex = m_menuStrings.size() - 1; }
                            }
                        }
                        else
                        {
                            m_selectedMenuIndex = m_menuStrings.size() - 1;
                        }
                        break;
                    }
                    case sf::Keyboard::S:
                    case sf::Keyboard::Down:
                    {
                        m_selectedMenuIndex = (m_selectedMenuIndex + 1) % m_menuStrings.size();
                        // Skip separator
                        if (m_selectedMenuIndex == m_separatorIndex)
                        {
                            m_selectedMenuIndex = (m_selectedMenuIndex + 1) % m_menuStrings.size();
                        }
                        break;
                    }
                    case sf::Keyboard::D:
                    case sf::Keyboard::Return:
                    {
                        if (m_selectedMenuIndex < m_separatorIndex)
                        {
                            // State item — existing behavior
                            auto & stateName = m_menuStrings[m_selectedMenuIndex];
                            m_game.pushState(std::make_shared<GUIState_Play>(m_game, AIParameters::Instance().getState(stateName)));
                        }
                        else if (m_selectedMenuIndex > m_separatorIndex)
                        {
                            // Replay folder
                            m_selectedReplayFolder = m_selectedMenuIndex - m_separatorIndex - 1;
                            m_selectedReplayFile = 0;
                            m_replayScrollOffset = 0;
                            m_inReplayFolder = true;
                        }
                        break;
                    }
                    default: break;
                }
            }
        }
    }
}

void GUIState_Menu::sRender()
{
    m_game.window().setView(m_game.window().getDefaultView());
    m_game.window().clear(sf::Color(0, 0, 0));

    if (m_inReplayFolder)
    {
        // Render file list for selected folder
        auto & folder = m_replayFolders[m_selectedReplayFolder];

        m_menuText.setCharacterSize(32);
        m_menuText.setString("Replays: " + folder.folderName);
        m_menuText.setFillColor(sf::Color::White);
        m_menuText.setPosition(sf::Vector2f(12, 5));
        m_game.window().draw(m_menuText);

        m_menuText.setCharacterSize(32);
        const float itemHeight = 34.0f;
        const float topY = 50.0f;
        const float bottomY = (float)m_game.window().getSize().y - 60.0f;
        int visibleItems = std::max(1, (int)((bottomY - topY) / itemHeight));

        // Auto-scroll to keep selection visible
        if ((int)m_selectedReplayFile < m_replayScrollOffset)
            m_replayScrollOffset = (int)m_selectedReplayFile;
        if ((int)m_selectedReplayFile >= m_replayScrollOffset + visibleItems)
            m_replayScrollOffset = (int)m_selectedReplayFile - visibleItems + 1;

        for (size_t i = 0; i < folder.files.size(); i++)
        {
            float y = topY + ((int)i - m_replayScrollOffset) * itemHeight;
            if (y < topY - itemHeight || y > bottomY) continue;

            m_menuText.setString(folder.files[i].displayName);
            m_menuText.setFillColor(i == m_selectedReplayFile ? sf::Color::Yellow : sf::Color(127, 127, 127));
            m_menuText.setPosition(sf::Vector2f(32.0f, y));
            m_game.window().draw(m_menuText);
        }

        m_menuText.setCharacterSize(32);
        m_menuText.setFillColor(sf::Color::Yellow);
        m_menuText.setString("up: w/up   down: s/down   load: d/enter   back: esc");
        m_menuText.setPosition(sf::Vector2f(15, m_game.window().getSize().y - 50));
        m_game.window().draw(m_menuText);
    }
    else
    {
        // Render main menu
        m_menuText.setCharacterSize(32);
        m_menuText.setString(m_title);
        m_menuText.setFillColor(sf::Color::White);
        m_menuText.setPosition(sf::Vector2f(12, 5));
        m_game.window().draw(m_menuText);

        m_menuText.setCharacterSize(32);
        const float menuItemHeight = (float)m_menuText.getCharacterSize() + 2;
        const float menuTopY = 50.0f;
        const float menuBottomY = (float)m_game.window().getSize().y - 60.0f;
        int menuVisibleItems = std::max(1, (int)((menuBottomY - menuTopY) / menuItemHeight));

        // Auto-scroll to keep selection visible
        if ((int)m_selectedMenuIndex < m_menuScrollOffset)
            m_menuScrollOffset = (int)m_selectedMenuIndex;
        if ((int)m_selectedMenuIndex >= m_menuScrollOffset + menuVisibleItems)
            m_menuScrollOffset = (int)m_selectedMenuIndex - menuVisibleItems + 1;

        for (size_t i = 0; i < m_menuStrings.size(); i++)
        {
            float y = menuTopY + ((int)i - m_menuScrollOffset) * menuItemHeight;
            if (y < menuTopY - menuItemHeight || y > menuBottomY) continue;

            m_menuText.setString(m_menuStrings[i]);

            if (i == m_separatorIndex)
            {
                m_menuText.setFillColor(sf::Color(80, 80, 80));
            }
            else if (i > m_separatorIndex)
            {
                m_menuText.setFillColor(i == m_selectedMenuIndex ? sf::Color::Yellow : sf::Color(100, 200, 200));
            }
            else
            {
                m_menuText.setFillColor(i == m_selectedMenuIndex ? sf::Color::Yellow : sf::Color(127, 127, 127));
            }

            m_menuText.setPosition(sf::Vector2f(32.0f, y));
            m_game.window().draw(m_menuText);
        }

        m_menuText.setCharacterSize(32);
        m_menuText.setFillColor(sf::Color::Yellow);
        m_menuText.setString("up: w/up   down: s/down   run: d/enter   back: esc");
        m_menuText.setPosition(sf::Vector2f(15, m_game.window().getSize().y - 50));
        m_game.window().draw(m_menuText);
    }

    m_game.window().display();
}
