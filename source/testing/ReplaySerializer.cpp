#include "ReplaySerializer.h"

namespace Prismata
{

ReplaySerializer::ReplaySerializer(const std::string & p0Name,
                                   const std::string & p1Name,
                                   const std::vector<std::string> & cardSet)
    : _p0(p0Name), _p1(p1Name), _cardSet(cardSet)
{
    _doc.SetObject();
    _states.SetArray();
    _actions.SetArray();
    _turnBoundaries.SetArray();
}

void ReplaySerializer::captureInitialState(const GameState & /*state*/)
{
    // Filled in Task 15.
}

void ReplaySerializer::captureActionApplied(const GameState & /*state*/, const Action & /*action*/)
{
    // Filled in Task 15 / 16.
}

void ReplaySerializer::recordTurnBoundary()
{
    auto & a = _doc.GetAllocator();
    _turnBoundaries.PushBack(static_cast<int>(_states.Size()), a);
}

bool ReplaySerializer::finalize(int /*winner*/, int /*turns*/,
                                const std::string & /*outDir*/, int /*gameIndex*/)
{
    // Filled in Task 18.
    return false;
}

rapidjson::Value ReplaySerializer::serializeState(const GameState & /*state*/)
{
    // Filled in Task 15.
    rapidjson::Value v(rapidjson::kObjectType);
    return v;
}

} // namespace Prismata
