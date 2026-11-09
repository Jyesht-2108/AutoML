"""
Model factory for loading and configuring PyTorch models.

This module provides functions to create pretrained models from torchvision
with custom classification heads matching the number of classes in the dataset.
"""

import torch
import torch.nn as nn
from torchvision import models
from typing import List


def get_supported_models() -> List[str]:
    """
    Return list of available model architectures.
    
    Returns:
        List of supported model architecture names
    """
    return [
        "resnet18",
        "resnet34",
        "resnet50",
        "mobilenet_v2",
        "efficientnet_b0",
        "yolov8n_cls",
        "yolov8s_cls"
    ]


# ---------------------------------------------------------------------------
# YOLOv8 Classification Modules (Pure PyTorch Implementation & Fallback)
# ---------------------------------------------------------------------------

class YOLOConv(nn.Module):
    """Standard Convolution block for YOLOv8 (Conv2d + BatchNorm2d + SiLU)."""
    def __init__(self, c1, c2, k=1, s=1, p=None, g=1):
        super().__init__()
        if p is None:
            p = (k[0] // 2, k[1] // 2) if isinstance(k, tuple) else k // 2
        self.conv = nn.Conv2d(c1, c2, k, s, p, groups=g, bias=False)
        self.bn = nn.BatchNorm2d(c2)
        self.act = nn.SiLU(inplace=True)

    def forward(self, x):
        return self.act(self.bn(self.conv(x)))


class YOLOBottleneck(nn.Module):
    """Standard Bottleneck block for YOLOv8."""
    def __init__(self, c1, c2, shortcut=True, g=1, k=((3, 3), (3, 3)), e=0.5):
        super().__init__()
        c_ = int(c2 * e)
        self.cv1 = YOLOConv(c1, c_, k[0], 1)
        self.cv2 = YOLOConv(c_, c2, k[1], 1, g=g)
        self.add = shortcut and c1 == c2

    def forward(self, x):
        return x + self.cv2(self.cv1(x)) if self.add else self.cv2(self.cv1(x))


class YOLOC2f(nn.Module):
    """CSP Bottleneck with 2 convolutions (C2f) for YOLOv8."""
    def __init__(self, c1, c2, n=1, shortcut=False, g=1, e=0.5):
        super().__init__()
        self.c = int(c2 * e)
        self.cv1 = YOLOConv(c1, 2 * self.c, 1, 1)
        self.cv2 = YOLOConv((2 + n) * self.c, c2, 1)
        self.m = nn.ModuleList(
            YOLOBottleneck(self.c, self.c, shortcut, g, k=((3, 3), (3, 3)), e=1.0) for _ in range(n)
        )

    def forward(self, x):
        y = list(self.cv1(x).chunk(2, 1))
        y.extend(m(y[-1]) for m in self.m)
        return self.cv2(torch.cat(y, 1))


class YOLOClassifyHead(nn.Module):
    """Classification Head for YOLOv8."""
    def __init__(self, c1, c2, k=1, s=1, p=None, g=1):
        super().__init__()
        c_ = 1280
        self.conv = YOLOConv(c1, c_, k, s, p, g)
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.drop = nn.Dropout(p=0.0, inplace=True)
        self.linear = nn.Linear(c_, c2)

    def forward(self, x):
        return self.linear(self.drop(self.pool(self.conv(x)).flatten(1)))


class PurePyTorchYOLOv8Cls(nn.Module):
    """Native PyTorch YOLOv8-cls implementation (no external dependencies required)."""
    def __init__(self, num_classes=1000):
        super().__init__()
        self.model = nn.Sequential(
            YOLOConv(3, 16, 3, 2),
            YOLOConv(16, 32, 3, 2),
            YOLOC2f(32, 32, 1, True),
            YOLOConv(32, 64, 3, 2),
            YOLOC2f(64, 64, 2, True),
            YOLOConv(64, 128, 3, 2),
            YOLOC2f(128, 128, 2, True),
            YOLOConv(128, 256, 3, 2),
            YOLOC2f(256, 256, 1, True),
            YOLOClassifyHead(256, num_classes)
        )
        # Expose linear head as fc for consistency with torchvision models
        self.fc = self.model[-1].linear

    def forward(self, x):
        return self.model(x)


class YOLOClassificationWrapper(nn.Module):
    """Wrapper around Ultralytics ClassificationModel to ensure clean 2D output tensor."""
    def __init__(self, base_model):
        super().__init__()
        self.base_model = base_model
        # Expose linear head as fc for compatibility
        self.fc = self.base_model.model[-1].linear

    def forward(self, x):
        out = self.base_model(x)
        if isinstance(out, (tuple, list)):
            return out[0]
        return out


def create_model(model_name: str, num_classes: int) -> nn.Module:
    """
    Load a pretrained model from torchvision and modify the final layer.
    
    This function loads a pretrained model with ImageNet weights and replaces
    the final fully connected layer with a custom layer matching num_classes.
    
    Args:
        model_name: Name of the model architecture (e.g., "resnet18", "mobilenet_v2")
        num_classes: Number of output classes for the classification task
        
    Returns:
        PyTorch model with modified final layer
        
    Raises:
        ValueError: If model_name is not supported
    """
    model_name_lower = model_name.lower()
    
    # Handle common model name variations
    model_aliases = {
        "efficientnet": "efficientnet_b0",
        "mobilenet": "mobilenet_v2",
        "resnet": "resnet18",
        "yolo": "yolov8n_cls",
        "yolov8": "yolov8n_cls",
        "yolov8n": "yolov8n_cls",
        "yolov8_cls": "yolov8n_cls",
        "yolov8s": "yolov8s_cls",
        "yolo-cls": "yolov8n_cls",
        "yolov8-cls": "yolov8n_cls"
    }
    
    if model_name_lower in model_aliases:
        model_name_lower = model_aliases[model_name_lower]
        print(f"📝 Model name '{model_name}' mapped to '{model_name_lower}'")
    
    if model_name_lower not in get_supported_models():
        raise ValueError(
            f"Unsupported model: {model_name}. "
            f"Supported models: {', '.join(get_supported_models())}"
        )
    
    # Load pretrained model based on architecture
    if model_name_lower == "resnet18":
        model = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1)
        num_features = model.fc.in_features
        model.fc = nn.Linear(num_features, num_classes)
        
    elif model_name_lower == "resnet34":
        model = models.resnet34(weights=models.ResNet34_Weights.IMAGENET1K_V1)
        num_features = model.fc.in_features
        model.fc = nn.Linear(num_features, num_classes)
        
    elif model_name_lower == "resnet50":
        model = models.resnet50(weights=models.ResNet50_Weights.IMAGENET1K_V1)
        num_features = model.fc.in_features
        model.fc = nn.Linear(num_features, num_classes)
        
    elif model_name_lower == "mobilenet_v2":
        model = models.mobilenet_v2(weights=models.MobileNet_V2_Weights.IMAGENET1K_V1)
        num_features = model.classifier[1].in_features
        model.classifier[1] = nn.Linear(num_features, num_classes)
        
    elif model_name_lower == "efficientnet_b0":
        model = models.efficientnet_b0(weights=models.EfficientNet_B0_Weights.IMAGENET1K_V1)
        num_features = model.classifier[1].in_features
        model.classifier[1] = nn.Linear(num_features, num_classes)
        
    elif model_name_lower in ("yolov8n_cls", "yolov8s_cls"):
        weight_file = "yolov8s-cls.pt" if model_name_lower == "yolov8s_cls" else "yolov8n-cls.pt"
        try:
            from ultralytics import YOLO
            yolo = YOLO(weight_file)
            base_model = yolo.model
            classify_head = base_model.model[-1]
            in_features = classify_head.linear.in_features
            classify_head.linear = nn.Linear(in_features, num_classes)
            model = YOLOClassificationWrapper(base_model)
            print(f"🚀 Initialized pretrained YOLO ({weight_file}) for {num_classes} classes")
        except Exception as e:
            print(f"⚠️ Could not load pretrained weights via ultralytics ({e}), initializing PyTorch YOLOv8Cls architecture")
            model = PurePyTorchYOLOv8Cls(num_classes=num_classes)
    
    return model
