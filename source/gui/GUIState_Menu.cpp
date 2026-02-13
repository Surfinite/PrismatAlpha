#include "GUIState_Menu.h"
#include "GUIState_Play.h"

#include "Prismata.h"
#include "PrismataAI.h"
#include "Assets.h"
#include "GUIEngine.h"

#include <filesystem>
#include <fstream>
#include <iostream>
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
        m_replayFiles.push_back("");  // not a replay
    }

    scanReplays();

    m_menuText.setFont(Assets::Instance().getFont("Consolas"));
    m_menuText.setCharacterSize(16);
}

void GUIState_Menu::scanReplays()
{
    const std::string replayDir = "asset/replays";
    if (!std::filesystem::exists(replayDir)) return;

    for (auto & entry : std::filesystem::recursive_directory_iterator(replayDir))
    {
        if (!entry.is_regular_file()) continue;
        if (entry.path().extension() != ".json") continue;

        // Build a display name from the path: "Replay: folder/game_0001"
        auto relPath = std::filesystem::relative(entry.path(), replayDir);
        std::string displayName = "Replay: " + relPath.stem().string();

        // Include parent folder name if it exists
        if (relPath.has_parent_path() && relPath.parent_path() != ".")
        {
            displayName = "Replay: " + relPath.parent_path().string() + "/" + relPath.stem().string();
        }

        m_menuStrings.push_back(displayName);
        m_replayFiles.push_back(entry.path().string());
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

    m_game.pushState(std::make_shared<GUIState_Play>(m_game, replayStates, p0, p1, winner));
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
        // this event is triggered when a key is pressed
        if (event.type == sf::Event::KeyPressed)
        {
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
                    if (m_selectedMenuIndex > 0) { m_selectedMenuIndex--; }
                    else { m_selectedMenuIndex = m_menuStrings.size() - 1; }
                    break;
                }
                case sf::Keyboard::S:
                case sf::Keyboard::Down:
                {
                    m_selectedMenuIndex = (m_selectedMenuIndex + 1) % m_menuStrings.size();
                    break;
                }
                case sf::Keyboard::D:
                case sf::Keyboard::Return:
                {
                    if (!m_replayFiles[m_selectedMenuIndex].empty())
                    {
                        loadReplay(m_replayFiles[m_selectedMenuIndex]);
                    }
                    else
                    {
                        auto & stateName = m_menuStrings[m_selectedMenuIndex];
                        m_game.pushState(std::make_shared<GUIState_Play>(m_game, AIParameters::Instance().getState(stateName)));
                    }
                    break;
                }
                default: break;
            }
        }
    }
}

void GUIState_Menu::sRender()
{
    // clear the window to a blue
    m_game.window().setView(m_game.window().getDefaultView());
    m_game.window().clear(sf::Color(0, 0, 0));

    // draw the game title in the top-left of the screen
    m_menuText.setCharacterSize(32);
    m_menuText.setString(m_title);
    m_menuText.setFillColor(sf::Color::White);
    m_menuText.setPosition(sf::Vector2f(12, 5));
    m_game.window().draw(m_menuText);

    m_menuText.setCharacterSize(32);
    const int filesPerLine = 38;
    // draw all of the menu options
    for (size_t i = 0; i < m_menuStrings.size(); i++)
    {
        m_menuText.setString(m_menuStrings[i]);
        bool isReplay = !m_replayFiles[i].empty();
        if (i == m_selectedMenuIndex)
            m_menuText.setFillColor(sf::Color::Yellow);
        else if (isReplay)
            m_menuText.setFillColor(sf::Color(100, 200, 100));  // green tint for replays
        else
            m_menuText.setFillColor(sf::Color(127, 127, 127));
        m_menuText.setPosition(sf::Vector2f(32.0f + (float)(i/filesPerLine)*450, 50.0f + (i%filesPerLine) * (float)m_menuText.getCharacterSize()+2));
        m_game.window().draw(m_menuText);
    }

    // draw the controls in the bottom-left
    m_menuText.setCharacterSize(32);
    m_menuText.setFillColor(sf::Color::Yellow);
    m_menuText.setString("up: w/up   down: s/down   run: d/enter   back: esc");
    m_menuText.setPosition(sf::Vector2f(15, m_game.window().getSize().y - 50));
    m_game.window().draw(m_menuText);

    m_game.window().display();
}
