#pragma once

#include "GUIState.h"
#include <map>
#include <memory>
#include <deque>

namespace Prismata
{
class GUIState_Menu : public GUIState
{

protected:

    std::string                 m_title;
    std::vector<std::string>    m_menuStrings;
    std::vector<std::string>    m_replayFiles;      // parallel: replay file path (empty = normal state)
    sf::Text                    m_menuText;
    size_t                      m_selectedMenuIndex = 0;

    void init(const std::string & menuConfig);
    void scanReplays();
    void loadReplay(const std::string & filepath);
    void onFrame();
    void sUserInput();
    void sRender();

public:

    GUIState_Menu(GUIEngine & game);

};
}
