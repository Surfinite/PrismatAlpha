#pragma once

#include "GUIState.h"
#include <map>
#include <memory>
#include <deque>
#include <vector>
#include <string>

namespace Prismata
{

enum MenuItemType { ITEM_HEADER, ITEM_STATE, ITEM_FOLDER };
enum MenuView { VIEW_MAIN, VIEW_FOLDER };

struct ReplayFolder
{
    std::string displayName;    // "BlendQuick_10 (16 games)  Feb 13"
    std::string folderPath;
    std::string p0Name;
    std::string p1Name;
    std::string dateStr;        // "Feb 13"
    std::vector<std::string> gameFiles;  // sorted full paths
};

struct ReplayGameInfo
{
    std::string filePath;
    std::string displayName;    // "Game 001   42 turns   P0 wins"
    int turns = 0;
    int winner = -1;
    std::string winnerName;
};

struct MenuItem
{
    std::string displayText;
    MenuItemType type = ITEM_STATE;
    std::string stateName;      // for ITEM_STATE
    size_t folderIndex = 0;     // for ITEM_FOLDER (index into m_replayFolders)
};

class GUIState_Menu : public GUIState
{

protected:

    sf::Text                    m_menuText;

    // Main view
    std::vector<MenuItem>       m_menuItems;
    std::vector<ReplayFolder>   m_replayFolders;
    size_t                      m_selectedMenuIndex = 0;

    // Folder view
    MenuView                    m_viewMode = VIEW_MAIN;
    size_t                      m_activeFolderIndex = 0;
    std::vector<ReplayGameInfo> m_folderGames;
    size_t                      m_folderSelectedIndex = 0;

    // Scrolling
    size_t                      m_scrollOffset = 0;

    void init(const std::string & menuConfig);
    void scanReplays();
    void loadReplay(const std::string & filepath);
    void enterFolder(size_t folderIdx);
    size_t nextSelectable(size_t from, int direction) const;
    void onFrame();
    void sUserInput();
    void sRender();

public:

    GUIState_Menu(GUIEngine & game);

};
}
