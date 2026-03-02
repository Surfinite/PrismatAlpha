"""Check value accuracy across all checkpoints."""
import sys
sys.path.insert(0, "C:/libraries/torch_pkg")
import torch
from train import PrismataNet, compute_value_accuracy

# Load val data
val = torch.load("c:/libraries/PrismataAI/training/data/val.pt", weights_only=True)
states = val["states"]
targets = val["values"]

checkpoints = [
    "best_model.pt",
    "checkpoint_ep10.pt",
    "checkpoint_ep20.pt",
    "checkpoint_ep30.pt",
    "checkpoint_ep40.pt",
    "checkpoint_ep50.pt",
]

for cp_name in checkpoints:
    cp = torch.load(f"c:/libraries/PrismataAI/training/models/{cp_name}", map_location="cpu", weights_only=True)
    model = PrismataNet(cp["state_dim"], cp["num_units"], hidden_dim=512, num_layers=4)
    model.load_state_dict(cp["model_state_dict"])
    model.eval()

    with torch.no_grad():
        _, value = model(states)

    acc = compute_value_accuracy(value, targets)
    pos_frac = (value > 0).float().mean().item()
    neg_frac = (value < 0).float().mean().item()
    val_min = value.min().item()
    val_max = value.max().item()
    val_mean = value.mean().item()

    epoch = cp.get("epoch", "?")
    print(f"{cp_name:25s} ep={epoch:>3} acc={acc:.4f} mean={val_mean:+.4f} min={val_min:+.6f} max={val_max:+.6f} pos%={pos_frac:.3f} neg%={neg_frac:.3f}")
