# M3 MacBook Training Optimization Guide

## Current Optimizations (Already Implemented)

✅ **MPS Device Detection**: Automatically uses Apple Silicon GPU
✅ **Batch Size**: Set to 128 for better GPU utilization
✅ **Data Loading**: 6 parallel workers to prevent GPU starvation
✅ **Prefetching**: 2 batches prefetched per worker
✅ **Persistent Workers**: Workers stay alive between epochs
✅ **Data Augmentation**: Optimized transforms for better accuracy

## Performance Tips

### 1. Monitor GPU Usage
```bash
# Check if MPS is being used
python3 -c "import torch; print('MPS available:', torch.backends.mps.is_available())"

# Monitor GPU usage during training
sudo powermetrics --samplers gpu_power -i 1000
```

### 2. Increase Batch Size (if you have 16GB+ RAM)
Edit `.env` file:
```
BATCH_SIZE=256  # For M3 Pro/Max with 18GB+ unified memory
```

### 3. Use Smaller Models for Faster Training
- `resnet18`: Fastest, good for simple tasks (default)
- `resnet34`: Balanced speed/accuracy
- `resnet50`: Slower but more accurate
- `efficientnet_b0`: Best accuracy/speed tradeoff

### 4. Reduce Epochs for Testing
Edit `.env`:
```
DEFAULT_EPOCHS=5  # Quick test
DEFAULT_EPOCHS=15  # Production (current default)
DEFAULT_EPOCHS=25  # Maximum accuracy
```

### 5. Expected Training Times on M3

| Model | Dataset Size | Epochs | Approx Time |
|-------|-------------|--------|-------------|
| ResNet18 | 1000 images | 10 | 2-5 min |
| ResNet18 | 10000 images | 10 | 15-30 min |
| ResNet50 | 10000 images | 10 | 30-60 min |

## Troubleshooting

### Training is using CPU instead of GPU
```bash
# Check PyTorch MPS support
python3 -c "import torch; print(torch.backends.mps.is_built())"
```

If False, reinstall PyTorch:
```bash
pip install --upgrade torch torchvision
```

### Out of Memory Errors
Reduce batch size in `.env`:
```
BATCH_SIZE=64  # or even 32
```

### Slow Data Loading
The bottleneck might be disk I/O, not GPU. Consider:
- Using SSD storage
- Reducing image resolution
- Fewer data augmentation transforms
