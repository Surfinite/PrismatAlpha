#include "PrismataAI.h"
#include "GUIEngine.h"
#include "NeuralNet.h"

#include <cstdlib>
#include <ctime>

using namespace Prismata;

int main(int argc, char *argv[])
{
    srand((unsigned int)time(NULL));

    // Initialize the Prismata Card Library from the JSON library file
    Prismata::InitFromCardLibrary("asset/config/cardLibrary.jso");

    // Load neural network weights for AI evaluation
    if (NeuralNet::Instance().loadWeights("asset/config/neural_weights.bin"))
    {
        NeuralNet::Instance().buildCardTypeMapping();
    }

    // Parse the AI Parameters from the AI config file
    Prismata::AIParameters::Instance().parseFile("asset/config/config.txt");

    // Construct the GUIEngine object and run the game
    GUIEngine g;
    g.run();

    return 0;
}
