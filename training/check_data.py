"""Check training data distribution."""
import sys
sys.path.insert(0, "C:/libraries/torch_pkg")
import torch

train = torch.load("c:/libraries/PrismataAI/training/data/train.pt", weights_only=True)
val = torch.load("c:/libraries/PrismataAI/training/data/val.pt", weights_only=True)

for name, data in [("Train", train), ("Val", val)]:
    values = data["values"]
    pos = (values > 0).sum().item()
    neg = (values < 0).sum().item()
    zero = (values == 0).sum().item()
    total = len(values)
    print(f"{name}: {total} examples")
    print(f"  +1 (active won): {pos} ({pos/total*100:.1f}%)")
    print(f"  -1 (active lost): {neg} ({neg/total*100:.1f}%)")
    print(f"  0 (draw): {zero} ({zero/total*100:.1f}%)")
    print()
