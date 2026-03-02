"""Quick diagnostic: test if the trained model produces non-constant output."""
import sys
sys.path.insert(0, "C:/libraries/torch_pkg")
import torch
import json
from train import PrismataNet

# Load model
checkpoint = torch.load("models/best_model.pt", map_location="cpu", weights_only=True)
state_dim = checkpoint["state_dim"]
num_units = checkpoint["num_units"]
unit_index = checkpoint["unit_index"]

model = PrismataNet(state_dim, num_units, hidden_dim=512, num_layers=4)
model.load_state_dict(checkpoint["model_state_dict"])
model.eval()

print(f"Model loaded: state_dim={state_dim}, num_units={num_units}")
print(f"Best val policy loss: {checkpoint.get('val_policy_loss', 'N/A')}")
print(f"Best val value loss: {checkpoint.get('val_value_loss', 'N/A')}")
print(f"Saved at epoch: {checkpoint.get('epoch', 'N/A')}")

idx_to_name = {v: k for k, v in unit_index.items()}

# Test 1: all-zero input (what happens with empty features)
x_zero = torch.zeros(1, state_dim)
with torch.no_grad():
    policy_zero, value_zero = model(x_zero)
print(f"\n--- All-zero input ---")
print(f"Value: {value_zero.item():.4f}")
print(f"Policy range: [{policy_zero.min().item():.4f}, {policy_zero.max().item():.4f}]")
print(f"Policy mean: {policy_zero.mean().item():.4f}")
drone_idx = unit_index.get("Drone", -1)
if drone_idx >= 0:
    print(f"Policy[Drone]: {policy_zero[0, drone_idx].item():.4f}")

# Test 2: typical early game state
print(f"\n--- Early game (6 Drones, 2 Engineers each) ---")
x = torch.zeros(1, state_dim)
drone_idx = unit_index["Drone"]
eng_idx = unit_index["Engineer"]
wall_idx = unit_index["Wall"]
tarsier_idx = unit_index["Tarsier"]
td_idx = unit_index["Thorium Dynamo"]

# P0: 6 ready drones, 2 ready engineers
x[0, drone_idx * 11 + 0] = 6.0
x[0, eng_idx * 11 + 0] = 2.0
# P1: 6 ready drones, 2 ready engineers
x[0, drone_idx * 11 + 4] = 6.0
x[0, eng_idx * 11 + 4] = 2.0
# Supply
for name in ["Drone", "Engineer", "Wall", "Tarsier", "Thorium Dynamo"]:
    idx = unit_index[name]
    x[0, idx * 11 + 8] = 10.0
    x[0, idx * 11 + 9] = 10.0
    x[0, idx * 11 + 10] = 1.0

with torch.no_grad():
    policy, value = model(x)

print(f"Value: {value.item():.4f}")
print(f"Policy range: [{policy.min().item():.4f}, {policy.max().item():.4f}]")
top_k = torch.topk(policy[0], 15)
print("Top 15 policy outputs:")
for i in range(15):
    idx = top_k.indices[i].item()
    val = top_k.values[i].item()
    name = idx_to_name.get(idx, f"idx_{idx}")
    print(f"  {name:30s} {val:.4f}")

# Test 3: Compare with actual training data
print(f"\n--- Loading actual training sample ---")
try:
    val_data = torch.load("data/val.pt", map_location="cpu", weights_only=True)
    sample = val_data["states"][0:1]
    sample_buy = val_data["buy_targets"][0]
    sample_val = val_data["values"][0]

    print(f"Sample state non-zero features: {(sample != 0).sum().item()} / {state_dim}")
    print(f"Sample true value: {sample_val.item():.4f}")
    print(f"Sample true buys: ", end="")
    for i in range(num_units):
        if sample_buy[i] > 0:
            print(f"{idx_to_name[i]}({sample_buy[i]:.0f}) ", end="")
    print()

    with torch.no_grad():
        pred_policy, pred_value = model(sample)
    print(f"Predicted value: {pred_value.item():.4f}")
    print(f"Predicted policy range: [{pred_policy.min().item():.4f}, {pred_policy.max().item():.4f}]")
    top_k = torch.topk(pred_policy[0], 10)
    print("Top 10 predicted buys:")
    for i in range(10):
        idx = top_k.indices[i].item()
        val = top_k.values[i].item()
        name = idx_to_name.get(idx, f"idx_{idx}")
        print(f"  {name:30s} {val:.4f}")
except Exception as e:
    print(f"Could not load validation data: {e}")
