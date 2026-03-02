"""Quick verification: what does the Python model output for various inputs?"""
import sys
sys.path.insert(0, "C:/libraries/torch_pkg")
import torch
from train import PrismataNet

# Load model
checkpoint = torch.load("c:/libraries/PrismataAI/training/models/best_model.pt", map_location="cpu", weights_only=True)
model = PrismataNet(checkpoint["state_dim"], checkpoint["num_units"], hidden_dim=512, num_layers=4)
model.load_state_dict(checkpoint["model_state_dict"])
model.eval()

state_dim = checkpoint["state_dim"]
print(f"State dim: {state_dim}")

# Test 1: All zeros
x = torch.zeros(1, state_dim)
with torch.no_grad():
    # Manual forward pass to see intermediate values
    h = torch.relu(model.input_proj(x))
    print(f"After input_proj: mean={h.mean():.4f}, std={h.std():.4f}, min={h.min():.4f}, max={h.max():.4f}")

    for i, layer in enumerate(model.trunk_layers):
        block_out = layer(h)
        relu_block = torch.relu(block_out)
        h = h + relu_block
        print(f"After trunk block {i}: mean={h.mean():.4f}, std={h.std():.4f}, min={h.min():.4f}, max={h.max():.4f}")

    # Value head
    vh = model.value_head[0](h)  # Linear
    vh = model.value_head[1](vh) # ReLU
    raw = model.value_head[2](vh) # Linear (scalar)
    val = model.value_head[3](raw) # Tanh
    print(f"\nValue head: raw={raw.item():.4f}, tanh={val.item():.4f}")

# Test 2: Random features (mimicking a real game state)
print("\n--- Random features ---")
x2 = torch.zeros(1, state_dim)
# Set some features: 6 drones for P0, 3 drones for P1 (just example values)
x2[0, 0] = 6.0  # Some unit ready count
x2[0, 4] = 3.0  # Opponent unit count
with torch.no_grad():
    policy, value = model(x2)
    print(f"Value: {value.item():.4f}")

# Test 3: Load actual training data and check a few
print("\n--- Actual training data ---")
train_data = torch.load("c:/libraries/PrismataAI/training/data/val.pt", weights_only=True)
states = train_data["states"][:10]
values_target = train_data["values"][:10]

with torch.no_grad():
    # Manual forward to get raw values
    h = torch.relu(model.input_proj(states))
    for layer in model.trunk_layers:
        h = h + torch.relu(layer(h))

    vh = model.value_head[0](h)
    vh = model.value_head[1](vh)
    raw = model.value_head[2](vh)
    pred = model.value_head[3](raw)

    for i in range(10):
        nz = (states[i] != 0).sum().item()
        print(f"  Example {i}: raw={raw[i].item():.4f}, tanh={pred[i].item():.4f}, target={values_target[i].item():.1f}, nonzero_feat={nz}")
