#include "GUIState_Menu.h"
#include "GUIState_Play.h"
#include "GUIState_WatchTraining.h"

#include "Prismata.h"
#include "PrismataAI.h"
#include "Assets.h"
#include "GUIEngine.h"

#include <filesystem>
#include <fstream>
#include <iostream>
#include <algorithm>
#include <sstream>
#include <iomanip>
#include "rapidjson/document.h"

using namespace Prismata;

static const char * MONTH_NAMES[] = { "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec" };

// Try to strip "_YYYY-MM-DD_HH-MM-SS" from end of folder name.
// Returns the stripped name and sets dateStr to "Mon DD" (e.g. "Feb 13").
// If no timestamp found, returns the original name and empty dateStr.
static std::string stripTimestamp(const std::string & folderName, std::string & dateStr)
{
    // Pattern: _YYYY-MM-DD_HH-MM-SS (20 chars)
    // Look for _20 near end
    dateStr.clear();
    if (folderName.size() < 21) return folderName;

    size_t pos = folderName.rfind("_20");
    if (pos == std::string::npos || pos + 20 > folderName.size()) return folderName;

    // Validate format: _YYYY-MM-DD_HH-MM-SS
    std::string tail = folderName.substr(pos);
    if (tail.size() < 20) return folderName;
    // Check: _YYYY-MM-DD_HH-MM-SS
    if (tail[0] != '_' || tail[5] != '-' || tail[8] != '-' || tail[11] != '_'
        || tail[14] != '-' || tail[17] != '-')
        return folderName;

    // Extract month and day
    int month = std::atoi(tail.substr(6, 2).c_str());
    int day = std::atoi(tail.substr(9, 2).c_str());
    if (month >= 1 && month <= 12)
    {
        dateStr = std::string(MONTH_NAMES[month]) + " " + std::to_string(day);
    }

    return folderName.substr(0, pos);
}

// Read p0/p1 names from a replay JSON file (reads only metadata, not full states).
static bool readReplayMetadata(const std::string & filepath, std::string & p0, std::string & p1)
{
    std::ifstream file(filepath);
    if (!file.is_open()) return false;

    std::string content((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
    file.close();

    rapidjson::Document doc;
    doc.Parse(content.c_str());
    if (doc.HasParseError()) return false;

    p0 = doc.HasMember("p0") ? doc["p0"].GetString() : "Player 0";
    p1 = doc.HasMember("p1") ? doc["p1"].GetString() : "Player 1";
    return true;
}

GUIState_Menu::GUIState_Menu(GUIEngine & game)
    : GUIState(game)
{
    init("");
}

void GUIState_Menu::init(const std::string & menuConfig)
{
    m_menuText.setFont(Assets::Instance().getFont("Consolas"));
    m_menuText.setCharacterSize(32);

    // Section: New Game
    MenuItem header;
    header.displayText = "New Game";
    header.type = ITEM_HEADER;
    m_menuItems.push_back(header);

    for (auto & stateName : AIParameters::Instance().getStateNames())
    {
        MenuItem item;
        item.displayText = stateName;
        item.type = ITEM_STATE;
        item.stateName = stateName;
        m_menuItems.push_back(item);
    }

    // Watch Training item
    {
        MenuItem watchItem;
        watchItem.displayText = "Watch Training (Self-Play)";
        watchItem.type = ITEM_WATCH_TRAINING;
        m_menuItems.push_back(watchItem);
    }

    // Watch Eval item
    {
        MenuItem evalItem;
        evalItem.displayText = "Watch Eval (Neural vs Hardest)";
        evalItem.type = ITEM_WATCH_EVAL;
        m_menuItems.push_back(evalItem);
    }

    scanReplays();

    // Set initial selection to first selectable item
    m_selectedMenuIndex = 0;
    if (!m_menuItems.empty() && m_menuItems[0].type == ITEM_HEADER)
    {
        m_selectedMenuIndex = nextSelectable(0, 1);
    }
}

void GUIState_Menu::scanReplays()
{
    const std::string replayDir = "asset/replays";
    if (!std::filesystem::exists(replayDir)) return;

    // Collect folders
    for (auto & entry : std::filesystem::directory_iterator(replayDir))
    {
        if (!entry.is_directory()) continue;

        // Collect .json files in this folder
        std::vector<std::string> jsonFiles;
        for (auto & fileEntry : std::filesystem::directory_iterator(entry.path()))
        {
            if (!fileEntry.is_regular_file()) continue;
            if (fileEntry.path().extension() != ".json") continue;
            jsonFiles.push_back(fileEntry.path().string());
        }

        if (jsonFiles.empty()) continue;

        std::sort(jsonFiles.begin(), jsonFiles.end());

        ReplayFolder folder;
        folder.folderPath = entry.path().string();
        folder.gameFiles = jsonFiles;

        // Strip timestamp and extract date
        std::string folderName = entry.path().filename().string();
        std::string baseName = stripTimestamp(folderName, folder.dateStr);

        // Read first game for player names
        readReplayMetadata(jsonFiles[0], folder.p0Name, folder.p1Name);

        // Build display name: "BaseName (N games)"
        folder.displayName = baseName + " (" + std::to_string(jsonFiles.size()) + ")";

        m_replayFolders.push_back(folder);
    }

    if (m_replayFolders.empty()) return;

    // Sort newest-first by folder name (timestamps sort lexicographically)
    std::sort(m_replayFolders.begin(), m_replayFolders.end(),
        [](const ReplayFolder & a, const ReplayFolder & b)
        {
            // Compare the full folder path — timestamps in folder names sort correctly
            return a.folderPath > b.folderPath;
        });

    // Add replay section header
    MenuItem replayHeader;
    replayHeader.displayText = "Saved Replays";
    replayHeader.type = ITEM_HEADER;
    m_menuItems.push_back(replayHeader);

    // Add folder entries
    for (size_t i = 0; i < m_replayFolders.size(); i++)
    {
        auto & folder = m_replayFolders[i];

        MenuItem item;
        item.type = ITEM_FOLDER;
        item.folderIndex = i;

        // Build display: "Name (N)  P0 vs P1  Date"
        std::string display = folder.displayName;
        if (!folder.p0Name.empty() && !folder.p1Name.empty())
        {
            display += "  " + folder.p0Name + " vs " + folder.p1Name;
        }
        if (!folder.dateStr.empty())
        {
            display += "  " + folder.dateStr;
        }
        item.displayText = display;

        m_menuItems.push_back(item);
    }
}

void GUIState_Menu::enterFolder(size_t folderIdx)
{
    if (folderIdx >= m_replayFolders.size()) return;

    m_viewMode = VIEW_FOLDER;
    m_activeFolderIndex = folderIdx;
    m_folderGames.clear();
    m_folderSelectedIndex = 0;
    m_scrollOffset = 0;

    auto & folder = m_replayFolders[folderIdx];

    for (size_t i = 0; i < folder.gameFiles.size(); i++)
    {
        ReplayGameInfo info;
        info.filePath = folder.gameFiles[i];

        // Format game number
        std::ostringstream oss;
        oss << "Game " << std::setfill('0') << std::setw(3) << (i + 1);

        // Try to read metadata
        std::ifstream file(folder.gameFiles[i]);
        if (file.is_open())
        {
            std::string content((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
            file.close();

            rapidjson::Document doc;
            doc.Parse(content.c_str());

            if (!doc.HasParseError())
            {
                info.turns = doc.HasMember("turns") ? doc["turns"].GetInt() : 0;
                info.winner = doc.HasMember("winner") ? doc["winner"].GetInt() : -1;
                info.winnerName = doc.HasMember("winnerName") ? doc["winnerName"].GetString() : "";

                oss << "   " << info.turns << " turns";

                if (info.winner == 0)
                    oss << "   P0 wins";
                else if (info.winner == 1)
                    oss << "   P1 wins";
                else
                    oss << "   Draw";
            }
            else
            {
                oss << "   (error loading)";
            }
        }
        else
        {
            oss << "   (error loading)";
        }

        info.displayName = oss.str();
        m_folderGames.push_back(info);
    }
}

size_t GUIState_Menu::nextSelectable(size_t from, int direction) const
{
    if (m_menuItems.empty()) return 0;

    size_t idx = from;
    size_t count = m_menuItems.size();

    for (size_t attempt = 0; attempt < count; attempt++)
    {
        if (direction > 0)
            idx = (idx + 1) % count;
        else if (idx > 0)
            idx--;
        else
            idx = count - 1;

        if (m_menuItems[idx].type != ITEM_HEADER)
            return idx;
    }

    return from; // all headers somehow, stay put
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
            return;
        }

        if (event.type != sf::Event::KeyPressed) continue;

        if (m_viewMode == VIEW_MAIN)
        {
            size_t itemCount = m_menuItems.size();
            if (itemCount == 0) continue;

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
                    size_t prev = m_selectedMenuIndex;
                    if (prev > 0)
                        prev--;
                    else
                        prev = itemCount - 1;

                    // Skip headers
                    if (m_menuItems[prev].type == ITEM_HEADER)
                    {
                        if (prev > 0)
                            prev = nextSelectable(prev, -1);
                        else
                            prev = nextSelectable(prev, -1);
                    }
                    m_selectedMenuIndex = prev;
                    break;
                }
                case sf::Keyboard::S:
                case sf::Keyboard::Down:
                {
                    size_t next = (m_selectedMenuIndex + 1) % itemCount;

                    // Skip headers
                    if (m_menuItems[next].type == ITEM_HEADER)
                        next = nextSelectable(next, 1);

                    m_selectedMenuIndex = next;
                    break;
                }
                case sf::Keyboard::D:
                case sf::Keyboard::Return:
                {
                    auto & item = m_menuItems[m_selectedMenuIndex];
                    if (item.type == ITEM_STATE)
                    {
                        m_game.pushState(std::make_shared<GUIState_Play>(
                            m_game, AIParameters::Instance().getState(item.stateName)));
                    }
                    else if (item.type == ITEM_FOLDER)
                    {
                        enterFolder(item.folderIndex);
                    }
                    else if (item.type == ITEM_WATCH_TRAINING)
                    {
                        m_game.pushState(std::make_shared<GUIState_WatchTraining>(m_game));
                    }
                    else if (item.type == ITEM_WATCH_EVAL)
                    {
                        m_game.pushState(std::make_shared<GUIState_WatchTraining>(
                            m_game, "PrismatAI_AB_Legacy", "OriginalHardestAI",
                            true, "WATCH EVAL"));
                    }
                    break;
                }
                default: break;
            }

            // Update scroll for main view
            unsigned int windowH = m_game.window().getSize().y;
            size_t visibleItems = (windowH - 120) / 34;
            if (visibleItems < 1) visibleItems = 1;

            if (m_selectedMenuIndex >= m_scrollOffset + visibleItems)
                m_scrollOffset = m_selectedMenuIndex - visibleItems + 1;
            if (m_selectedMenuIndex < m_scrollOffset)
                m_scrollOffset = m_selectedMenuIndex;
        }
        else // VIEW_FOLDER
        {
            size_t itemCount = m_folderGames.size();
            if (itemCount == 0 && event.key.code != sf::Keyboard::Escape)
                continue;

            switch (event.key.code)
            {
                case sf::Keyboard::Escape:
                {
                    m_viewMode = VIEW_MAIN;
                    m_scrollOffset = 0;
                    // Recalculate scroll for main view
                    unsigned int windowH = m_game.window().getSize().y;
                    size_t visibleItems = (windowH - 120) / 34;
                    if (visibleItems < 1) visibleItems = 1;
                    if (m_selectedMenuIndex >= visibleItems)
                        m_scrollOffset = m_selectedMenuIndex - visibleItems + 1;
                    break;
                }
                case sf::Keyboard::W:
                case sf::Keyboard::Up:
                {
                    if (m_folderSelectedIndex > 0)
                        m_folderSelectedIndex--;
                    else
                        m_folderSelectedIndex = itemCount - 1;
                    break;
                }
                case sf::Keyboard::S:
                case sf::Keyboard::Down:
                {
                    m_folderSelectedIndex = (m_folderSelectedIndex + 1) % itemCount;
                    break;
                }
                case sf::Keyboard::D:
                case sf::Keyboard::Return:
                {
                    if (m_folderSelectedIndex < m_folderGames.size())
                    {
                        loadReplay(m_folderGames[m_folderSelectedIndex].filePath);
                    }
                    break;
                }
                default: break;
            }

            // Update scroll for folder view
            unsigned int windowH = m_game.window().getSize().y;
            size_t visibleItems = (windowH - 120) / 34;
            if (visibleItems < 1) visibleItems = 1;

            if (m_folderSelectedIndex >= m_scrollOffset + visibleItems)
                m_scrollOffset = m_folderSelectedIndex - visibleItems + 1;
            if (m_folderSelectedIndex < m_scrollOffset)
                m_scrollOffset = m_folderSelectedIndex;
        }
    }
}

void GUIState_Menu::sRender()
{
    m_game.window().setView(m_game.window().getDefaultView());
    m_game.window().clear(sf::Color(0, 0, 0));

    unsigned int windowH = m_game.window().getSize().y;
    size_t visibleItems = (windowH - 120) / 34;
    if (visibleItems < 1) visibleItems = 1;

    m_menuText.setCharacterSize(32);

    if (m_viewMode == VIEW_MAIN)
    {
        // Title
        m_menuText.setString("Prismata AI");
        m_menuText.setFillColor(sf::Color::White);
        m_menuText.setPosition(sf::Vector2f(12, 5));
        m_game.window().draw(m_menuText);

        // Menu items
        float y = 50.0f;
        for (size_t i = m_scrollOffset; i < m_menuItems.size() && (i - m_scrollOffset) < visibleItems; i++)
        {
            auto & item = m_menuItems[i];
            float drawY = y + (float)(i - m_scrollOffset) * 34.0f;

            if (item.type == ITEM_HEADER)
            {
                // Draw section header with line decoration
                std::string headerText = "-- " + item.displayText + " --------------------------------------";
                m_menuText.setString(headerText);
                m_menuText.setFillColor(sf::Color(80, 160, 160));
                m_menuText.setPosition(sf::Vector2f(20, drawY));
            }
            else
            {
                m_menuText.setString("  " + item.displayText);

                if (i == m_selectedMenuIndex)
                    m_menuText.setFillColor(sf::Color::Yellow);
                else if (item.type == ITEM_WATCH_TRAINING)
                    m_menuText.setFillColor(sf::Color(100, 220, 220));
                else if (item.type == ITEM_WATCH_EVAL)
                    m_menuText.setFillColor(sf::Color(220, 160, 100));
                else if (item.type == ITEM_FOLDER)
                    m_menuText.setFillColor(sf::Color(100, 200, 100));
                else
                    m_menuText.setFillColor(sf::Color(200, 200, 200));

                m_menuText.setPosition(sf::Vector2f(20, drawY));
            }

            m_game.window().draw(m_menuText);
        }

        // Scroll indicators
        if (m_scrollOffset > 0)
        {
            m_menuText.setString("  ...");
            m_menuText.setFillColor(sf::Color(100, 100, 100));
            m_menuText.setPosition(sf::Vector2f(20, y - 10));
            m_game.window().draw(m_menuText);
        }
        if (m_scrollOffset + visibleItems < m_menuItems.size())
        {
            m_menuText.setString("  ...");
            m_menuText.setFillColor(sf::Color(100, 100, 100));
            m_menuText.setPosition(sf::Vector2f(20, y + visibleItems * 34.0f));
            m_game.window().draw(m_menuText);
        }

        // Controls
        m_menuText.setFillColor(sf::Color::Yellow);
        m_menuText.setString("up: w/up   down: s/down   select: d/enter   quit: esc");
        m_menuText.setPosition(sf::Vector2f(15, (float)windowH - 50));
        m_game.window().draw(m_menuText);
    }
    else // VIEW_FOLDER
    {
        auto & folder = m_replayFolders[m_activeFolderIndex];

        // Title: folder name + players
        std::string title = folder.displayName + "  " + folder.p0Name + " vs " + folder.p1Name;
        m_menuText.setString(title);
        m_menuText.setFillColor(sf::Color::White);
        m_menuText.setPosition(sf::Vector2f(12, 5));
        m_game.window().draw(m_menuText);

        // Game list
        float y = 50.0f;
        for (size_t i = m_scrollOffset; i < m_folderGames.size() && (i - m_scrollOffset) < visibleItems; i++)
        {
            auto & game = m_folderGames[i];
            float drawY = y + (float)(i - m_scrollOffset) * 34.0f;

            m_menuText.setString("  " + game.displayName);

            if (i == m_folderSelectedIndex)
                m_menuText.setFillColor(sf::Color::Yellow);
            else
                m_menuText.setFillColor(sf::Color(100, 200, 100));

            m_menuText.setPosition(sf::Vector2f(20, drawY));
            m_game.window().draw(m_menuText);
        }

        // Scroll indicators
        if (m_scrollOffset > 0)
        {
            m_menuText.setString("  ...");
            m_menuText.setFillColor(sf::Color(100, 100, 100));
            m_menuText.setPosition(sf::Vector2f(20, y - 10));
            m_game.window().draw(m_menuText);
        }
        if (m_scrollOffset + visibleItems < m_folderGames.size())
        {
            m_menuText.setString("  ...");
            m_menuText.setFillColor(sf::Color(100, 100, 100));
            m_menuText.setPosition(sf::Vector2f(20, y + visibleItems * 34.0f));
            m_game.window().draw(m_menuText);
        }

        // Controls
        m_menuText.setFillColor(sf::Color::Yellow);
        m_menuText.setString("up: w/up   down: s/down   play: d/enter   back: esc");
        m_menuText.setPosition(sf::Vector2f(15, (float)windowH - 50));
        m_game.window().draw(m_menuText);
    }

    m_game.window().display();
}
