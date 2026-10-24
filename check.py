import torch
print("Torch version:", torch.__version__)
print("Torch CUDA available:", torch.cuda.is_available())
print("Torch build:", torch.version.cuda)
print("Device count:", torch.cuda.device_count())