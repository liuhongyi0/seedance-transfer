# ComfyUI Seedance Wizard
# AI-powered video creation wizard for ComfyUI
# License: MIT
# Copyright (c) 2025 Seedance Wizard Contributors

from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

# ComfyUI uses this to serve static files from the web/ directory.
# All .js files in this directory are automatically injected into the frontend.
# HTML/CSS files are accessible at /extensions/comfyui-seedance-wizard/<filename>
WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
