#!/usr/bin/env bash
# ComfyFlow — Install & Patch SaveAndLoadPromptCondition custom node
# Usage: bash install_custom_nodes.sh /path/to/ComfyUI
# (Run this on the machine hosting ComfyUI)

set -euo pipefail

COMFYUI_DIR="${1:-${COMFYUI_PATH:-.}}"
NODE_DIR="$COMFYUI_DIR/custom_nodes/ComfyUI-SaveAndLoadPromptCondition"

echo "[ComfyFlow] Installing SaveAndLoadPromptCondition..."

if [ ! -d "$NODE_DIR" ]; then
    git clone https://github.com/endman100/ComfyUI-SaveAndLoadPromptCondition.git "$NODE_DIR"
    echo "[ComfyFlow] Cloned to $NODE_DIR"
else
    echo "[ComfyFlow] Already exists at $NODE_DIR, updating..."
    cd "$NODE_DIR" && git pull
fi

# Patch nodes.py — add filename input, remove hardcoded timestamp
cat > "$NODE_DIR/nodes.py" << 'PYEOF'
import os
import folder_paths
import torch
import hashlib
from comfy.cli_args import args
from pathlib import Path

if args.base_directory:
    base_path = os.path.join(Path(os.path.abspath(args.base_directory)).parent.parent, "models")
else:
    base_path = os.path.join(Path(os.path.dirname(os.path.realpath(__file__))).parent.parent, "models")

os.makedirs(os.path.join(base_path, "conditionings"), exist_ok=True)
folder_paths.folder_names_and_paths["conditionings"] = ([os.path.join(base_path, "conditionings")], [".bin"])

class SaveConditioning:
    def __init__(self):
        self.output_dir = os.path.join(base_path, "conditionings")

    @classmethod
    def INPUT_TYPES(s):
        return {"required":
                    {"conditionings": ("CONDITIONING", ),
                     "filename": ("STRING", {"default": "conditioning"})},
                }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("saved_filename",)
    FUNCTION = "save_conditioning"
    OUTPUT_NODE = True
    CATEGORY = "endman100"

    def save_conditioning(self, conditionings, filename):
        file_name = f"{filename}_conditionings.bin"
        results = list()
        for (batch_number, conditioning) in enumerate(conditionings):
            save_path = os.path.join(self.output_dir, file_name)
            print(f"[SaveConditioning] Saving to: {save_path}")
            torch.save(conditioning, save_path)
            results.append(file_name)
        return {"ui": {"conditionings": results}, "result": (file_name,)}

class LoadContditioning():
    @classmethod
    def INPUT_TYPES(s):
        return {"required": { "conditioning": (folder_paths.get_filename_list("conditionings"), )}}

    CATEGORY = "endman100"
    RETURN_TYPES = ("CONDITIONING", )
    FUNCTION = "load_conditioning"

    def load_conditioning(self, conditioning):
        conditioning_path = folder_paths.get_full_path("conditionings", conditioning)
        conditioning_list = torch.load(conditioning_path)
        conditioning_list[0] = conditioning_list[0].cpu()
        for key, value in conditioning_list[1].items():
            if(type(value) == torch.Tensor):
                conditioning_list[1][key] = value.cpu()
        if(hasattr(conditioning_list[0], "addit_embeds")):
            for key, value in conditioning_list[0].addit_embeds.items():
                if(type(value) == torch.Tensor):
                    conditioning_list[0].addit_embeds[key] = value.cpu()
        return ([conditioning_list], )

    @classmethod
    def IS_CHANGED(s, conditioning):
        conditioning_path = folder_paths.get_full_path("conditionings", conditioning)
        m = hashlib.sha256()
        with open(conditioning_path, 'rb') as f:
            m.update(f.read())
        return m.digest().hex()

    @classmethod
    def VALIDATE_INPUTS(s, conditioning):
        conditioning_path = folder_paths.get_full_path("conditionings", conditioning)
        if not os.path.exists(conditioning_path):
            return "Invalid conditioning file: {}".format(conditioning_path)
        return True

NODE_CLASS_MAPPINGS = {
    "SaveConditioning": SaveConditioning,
    "LoadContditioning": LoadContditioning,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "Save Conditioning": "SaveConditioning",
    "Load Contditioning": "LoadContditioning"
}
PYEOF

echo "[ComfyFlow] Patched nodes.py v2.0"
echo "[ComfyFlow] Done. Restart ComfyUI to load the updated node."
