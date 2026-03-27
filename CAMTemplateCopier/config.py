# CAMTemplateCopier Configuration
# Edit these values to match your Fusion 360 project structure.

# The name of the Fusion 360 project that contains your CAM templates.
TEMPLATE_PROJECT_NAME = "Workholding"

# Path from the project root folder to the templates folder.
# This MUST be a Python list of strings — keep the brackets and quotes!
# Examples:
#   ["CAM Templates"]              — for: Project Root > CAM Templates
#   ["Resources", "CAM Templates"] — for: Project Root > Resources > CAM Templates
TEMPLATE_FOLDER_PATH = ["CAM Templates"]

# Add-in UI identifiers (no need to change these)
ADDIN_COMMAND_ID = "CAMTemplateCopierCmd"
ADDIN_COMMAND_NAME = "Copy CAM Template"
ADDIN_COMMAND_DESCRIPTION = "Copy a CAM template into the current folder and open it"

# Custom event ID for deferred save operations
CUSTOM_EVENT_ID = "CAMTemplateCopyEvent"

# Toolbar panel — place the button in the MANUFACTURE workspace Add-Ins panel
ADDIN_PANEL_ID = "CAMScriptsAddinsPanel"
# Fallback panel if the above doesn't exist
ADDIN_PANEL_ID_FALLBACK = "SolidScriptsAddinsPanel"
