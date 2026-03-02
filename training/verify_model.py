"""Thorough verification of model predictions."""
import sys
sys.path.insert(0, "C:/libraries/torch_pkg")
import torch
from train import PrismataNet, compute_value_accuracy

# Load model
checkpoint = torch.load("c:/libraries/PrismataAI/training/models/best_model.pt", map_location="cpu", weights_only=True)
model = PrismataNet(checkpoint["state_dim"], checkpoint["num_units"], hidden_dim=512, num_layers=4)
model.load_state_dict(checkpoint["model_state_dict"])
model.eval()

print(f"Checkpoint epoch: {checkpoint.get('epoch', '?')}")
print(f"Val policy loss: {checkpoint.get('val_policy_loss', '?')}")
print(f"Val value loss: {checkpoint.get('val_value_loss', '?')}")

# Load val data
val = torch.load("c:/libraries/PrismataAI/training/data/val.pt", weights_only=True)
states = val["states"]
targets = val["values"]

# Run FULL model forward pass
with torch.no_grad():
    policy, value = model(states)

print(f"\nAll val examples ({len(states)}):")
print(f"  Value predictions: min={value.min():.6f}, max={value.max():.6f}, mean={value.mean():.6f}")
print(f"  Value accuracy: {compute_value_accuracy(value, targets):.4f}")
print(f"  Fraction pred > 0: {(value > 0).float().mean():.4f}")
print(f"  Fraction pred < 0: {(value < 0).float().mean():.4f}")

# Check if predictions are diverse or all the same
print(f"\nUnique prediction signs: pos={((value > 0).sum().item())}, neg={((value < 0).sum().item())}, zero={((value == 0).sum().item())}")

# Print a few examples with pos and neg targets
print("\nExamples where target = +1 (active player won):")
pos_mask = targets > 0
pos_vals = value[pos_mask][:10]
for i, v in enumerate(pos_vals):
    print(f"  pred={v.item():.6f}")

print("\nExamples where target = -1 (active player lost):")
neg_mask = targets < 0
neg_vals = value[neg_mask][:10]
for i, v in enumerate(neg_vals):
    print(f"  pred={v.item():.6f}")
