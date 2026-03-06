#pragma once

#include "GUIState.h"
#include <map>
#include <memory>
#include <deque>
#include <string>
#include <vector>

namespace Prismata
{

struct ReplayFileInfo
{
    std::string path;
    std::string displayName;
};

struct ReplayFolderInfo
{
    std::string folderName;
    std::vector<ReplayFileInfo> files;
};

class GUIState_Menu : public GUIState
{

protected:

    std::string                 m_title;
    std::vector<std::string>    m_menuStrings;
    sf::Text                    m_menuText;
    size_t                      m_selectedMenuIndex = 0;

    // Replay browser
    std::vector<ReplayFolderInfo> m_replayFolders;
    size_t                      m_separatorIndex = 0;
    bool                        m_inReplayFolder = false;
    size_t                      m_selectedReplayFolder = 0;
    size_t                      m_selectedReplayFile = 0;
    int                         m_menuScrollOffset = 0;
    int                         m_replayScrollOffset = 0;

    void init(const std::string & menuConfig);
    void onFrame();
    void sUserInput();
    void sRender();
    void scanReplayFolders();
    void loadReplay(const std::string & filepath);

public:

    GUIState_Menu(GUIEngine & game);

};
}