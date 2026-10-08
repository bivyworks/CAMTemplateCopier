# CAMTemplateCopier configuration.
# Edit these values to match your Fusion project structure.

# The name of the Fusion project that holds your CAM templates (as shown in
# the Data Panel). The example below is a project named "Workholding".
TEMPLATE_PROJECT_NAME = "Workholding"

# Path from that project's root folder to the folder with the template files.
# This must be a Python list of strings, one entry per folder level:
#   ["CAM Templates"]              for  Project root > CAM Templates
#   ["Resources", "CAM Templates"] for  Project root > Resources > CAM Templates
TEMPLATE_FOLDER_PATH = ["CAM Templates"]

# Prefix put in front of the active document's name to suggest the new file
# name, e.g. "MFG Bracket" for a document named "Bracket".
NEW_NAME_PREFIX = "MFG "

# Insert the part into the copy as a linked reference (True), so that later
# changes to the part flow into the manufacturing model, or as an embedded
# copy (False). A link requires the part and the copy to be in the same
# project, which is always the case here because the copy is saved into the
# part's own folder; if Fusion still refuses the link, the add-in falls back
# to an embedded copy and says so.
INSERT_AS_REFERENCE = True

# Add-in UI identifiers (no need to change these).
ADDIN_COMMAND_ID = "CAMTemplateCopierCmd"
ADDIN_COMMAND_NAME = "Copy CAM Template"
ADDIN_COMMAND_DESCRIPTION = "Copy a CAM template into the current folder and open it"

# Custom event id for the deferred save.
CUSTOM_EVENT_ID = "CAMTemplateCopyEvent"

# The button goes into a "CAM Templates" panel on the MANUFACTURE and DESIGN
# toolbars. If neither workspace can be found, one of these add-ins panels is
# used instead.
ADDIN_PANEL_ID = "CAMScriptsAddinsPanel"
ADDIN_PANEL_ID_FALLBACK = "SolidScriptsAddinsPanel"
