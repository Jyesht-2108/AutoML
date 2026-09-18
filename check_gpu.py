#!/usr/bin/env python3
"""
Quick script to verify GPU (MPS) is available and working
"""
import torch
import time

print("="*60)
print("GPU/MPS Verification for M3 MacBook")
print("="*60)

# Check MPS availability
print(f"\n1. MPS Built: {torch.backends.mps.is_built()}")
print(f"2. MPS Available: {torch.backends.mps.is_available()}")

if torch.backends.mps.is_available():
    print("\n✅ Apple Silicon GPU (MPS) is available!")
    
    # Test MPS performance
    print("\n3. Running performance test...")
    device = torch.device("mps")
    
    # Create a large tensor and do some operations
    size = 5000
    x = torch.randn(size, size, device=device)
    y = torch.randn(size, size, device=device)
    
    start = time.time()
    for _ in range(10):
        z = torch.matmul(x, y)
    torch.mps.synchronize()  # Wait for GPU to finish
    gpu_time = time.time() - start
    
    print(f"   GPU Time: {gpu_time:.3f}s")
    
    # Compare with CPU
    x_cpu = x.cpu()
    y_cpu = y.cpu()
    
    start = time.time()
    for _ in range(10):
        z_cpu = torch.matmul(x_cpu, y_cpu)
    cpu_time = time.time() - start
    
    print(f"   CPU Time: {cpu_time:.3f}s")
    print(f"   Speedup: {cpu_time/gpu_time:.2f}x faster on GPU")
    
    if gpu_time < cpu_time:
        print("\n✅ GPU is working correctly and faster than CPU!")
    else:
        print("\n⚠️  GPU is slower than CPU - this is unusual")
        
else:
    print("\n❌ MPS is not available")
    print("\nTroubleshooting:")
    print("1. Make sure you're on Apple Silicon (M1/M2/M3)")
    print("2. Update PyTorch: pip install --upgrade torch torchvision")
    print("3. Check macOS version (requires macOS 12.3+)")

print("\n" + "="*60)
