# Neural Network Weight Format (PNET v1)

Binary weight file format used by `NeuralNet.cpp` to load trained model weights
exported by `training/export_weights.py`.

Default path: `bin/asset/config/neural_weights.bin`

## File Structure

```
[Header]           32 bytes
[Tensors section]  variable
[Unit index]       variable
```

## Header (32 bytes, little-endian)

| Offset | Type   | Name           | Description                        |
|--------|--------|----------------|------------------------------------|
| 0      | uint32 | magic          | `0x504E4554` ("PNET" as ASCII)     |
| 4      | uint32 | version        | Format version (currently 1)       |
| 8      | uint32 | state_dim      | Input feature vector dimension     |
| 12     | uint32 | num_units      | Number of unit types in unit index |
| 16     | uint32 | hidden_dim     | Hidden layer width (e.g. 512)      |
| 20     | uint32 | num_layers     | Number of trunk residual blocks    |
| 24     | uint32 | num_tensors    | Total number of tensors that follow|
| 28     | uint32 | num_unit_names | Number of unit name entries         |

## Tensor Section

Each tensor is stored sequentially with this structure:

```
uint32  name_length     (including null terminator)
char[]  name            (null-terminated UTF-8 string)
uint32  num_dims        (number of dimensions)
uint32  shape[num_dims] (size of each dimension)
float32 data[]          (row-major, count = product of shape)
```

### Expected Tensor Order

The C++ loader (`NeuralNet::loadWeights`) expects tensors in this exact order:

1. **Input projection** (2 tensors):
   - `input_proj.weight` — shape `[hidden_dim, state_dim]`
   - `input_proj.bias` — shape `[hidden_dim]`

2. **Trunk residual blocks** (8 tensors per block, `num_layers` blocks):
   For each block `i` (0 to num_layers-1):
   - `trunk.{i}.linear1.weight` — shape `[hidden_dim, hidden_dim]`
   - `trunk.{i}.linear1.bias` — shape `[hidden_dim]`
   - `trunk.{i}.norm1.weight` — shape `[hidden_dim]` (LayerNorm gamma)
   - `trunk.{i}.norm1.bias` — shape `[hidden_dim]` (LayerNorm beta)
   - `trunk.{i}.linear2.weight` — shape `[hidden_dim, hidden_dim]`
   - `trunk.{i}.linear2.bias` — shape `[hidden_dim]`
   - `trunk.{i}.norm2.weight` — shape `[hidden_dim]` (LayerNorm gamma)
   - `trunk.{i}.norm2.bias` — shape `[hidden_dim]` (LayerNorm beta)

3. **Policy head** (4 tensors, omitted if value-only):
   - `policy.linear1.weight` — shape `[hidden_dim/2, hidden_dim]`
   - `policy.linear1.bias` — shape `[hidden_dim/2]`
   - `policy.linear2.weight` — shape `[num_units, hidden_dim/2]`
   - `policy.linear2.bias` — shape `[num_units]`

4. **Value head** (4 tensors):
   - `value.linear1.weight` — shape `[hidden_dim/4, hidden_dim]`
   - `value.linear1.bias` — shape `[hidden_dim/4]`
   - `value.linear2.weight` — shape `[1, hidden_dim/4]`
   - `value.linear2.bias` — shape `[1]`

### Total tensor count

- Policy+value mode: `2 + 8*num_layers + 4 + 4 = 10 + 8*num_layers`
- Value-only mode: `2 + 8*num_layers + 4 = 6 + 8*num_layers`

Example with 2 layers: 26 tensors (policy+value) or 22 (value-only).

## Unit Index Section

After all tensors, the unit name mapping is stored:

```
For each unit (num_unit_names entries):
  uint32  index           (0-based unit index)
  uint32  name_length     (including null terminator)
  char[]  name            (null-terminated UTF-8, display name)
```

Entries are stored in order of index (0, 1, 2, ...).

## Forward Pass (inference)

The C++ code (`NeuralNet::evaluate`) performs:

```
h = ReLU(input_proj(features))

for each trunk block:
    tmp = Linear1(h)
    tmp = LayerNorm1(tmp)
    tmp = ReLU(tmp)
    tmp = Linear2(tmp)
    tmp = LayerNorm2(tmp)
    h = h + ReLU(tmp)          # Residual connection

policy = Linear(ReLU(Linear(h)))   # policy head
value  = tanh(Linear(ReLU(Linear(h))))  # value head (tanh applied in C++)
```

Note: The Python model does NOT include `nn.Tanh()` in the value head.
The tanh activation is applied in C++ (`tanhf(rawValue)` in NeuralNet.cpp).
This design avoids gradient death through saturated tanh during training.

## PyTorch to Binary Mapping

The PyTorch `PrismataNet` uses `nn.Sequential` for trunk blocks:
```
trunk_layers[i] = Sequential(
    [0] Linear(hidden, hidden)
    [1] LayerNorm(hidden)
    [2] ReLU()
    [3] Dropout(p)
    [4] Linear(hidden, hidden)
    [5] LayerNorm(hidden)
)
```

Export maps: `[0]` -> `linear1`, `[1]` -> `norm1`, `[4]` -> `linear2`, `[5]` -> `norm2`.
Indices [2] (ReLU) and [3] (Dropout) have no learnable parameters and are skipped.

## Verification

After export, verify by:
1. Loading the binary file back in Python
2. Running forward pass on a fixed input (e.g., all-zeros)
3. Comparing outputs to the PyTorch model — max absolute difference should be < 1e-5
