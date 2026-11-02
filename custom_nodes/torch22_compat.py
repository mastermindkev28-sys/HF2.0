"""Compatibility shim for PyTorch 2.2 (the last build for Intel Macs).

ComfyUI calls torch.compiler.is_compiling(), added in PyTorch 2.3. Without this,
CLIPTextEncode fails with "module 'torch.compiler' has no attribute 'is_compiling'".
Installed only on Intel Macs by scripts/install.sh.
"""
import torch

if not hasattr(torch.compiler, "is_compiling"):
    try:
        from torch._dynamo import is_compiling as _is_compiling
    except Exception:  # pragma: no cover
        def _is_compiling() -> bool:
            return False
    torch.compiler.is_compiling = _is_compiling

NODE_CLASS_MAPPINGS: dict = {}
NODE_DISPLAY_NAME_MAPPINGS: dict = {}
