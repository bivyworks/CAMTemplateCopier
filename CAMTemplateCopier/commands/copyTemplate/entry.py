import adsk.core
import adsk.fusion
import traceback
import os
import sys

# Add the add-in root to the path so we can import config and lib
_addin_dir = os.path.join(os.path.dirname(__file__), "..", "..")
if _addin_dir not in sys.path:
    sys.path.insert(0, _addin_dir)

import config
from lib.fusionAddInUtils import add_handler, log, find_template_folder, get_template_files

_app = adsk.core.Application.get()
_ui = _app.userInterface

# Global handler list to prevent garbage collection
_handlers = []

# Cached template data
_template_files_cache = {}  # name -> DataFile


def _get_or_create_panel(workspace_id, tab_id, panel_id, panel_name):
    """Get or create a custom toolbar panel in a workspace.

    Returns the panel, or None if the workspace/tab isn't found.
    """
    workspace = _ui.workspaces.itemById(workspace_id)
    if not workspace:
        log(f"Workspace '{workspace_id}' not found.")
        return None

    # Get or find the tab
    toolbar_tabs = workspace.toolbarTabs
    tab = toolbar_tabs.itemById(tab_id)
    if not tab:
        # Use the first available tab as fallback
        if toolbar_tabs.count > 0:
            tab = toolbar_tabs.item(0)
        else:
            log(f"No tabs in workspace '{workspace_id}'.")
            return None

    # Check if our custom panel already exists
    panel = tab.toolbarPanels.itemById(panel_id)
    if not panel:
        panel = tab.toolbarPanels.add(panel_id, panel_name)

    return panel


def start(handlers_global):
    """Create the command definition and add it to both DESIGN and MANUFACTURE toolbars."""
    try:
        cmd_def = _ui.commandDefinitions.itemById(config.ADDIN_COMMAND_ID)
        if cmd_def:
            cmd_def.deleteMe()

        resource_dir = os.path.join(os.path.dirname(__file__), "resources")
        cmd_def = _ui.commandDefinitions.addButtonDefinition(
            config.ADDIN_COMMAND_ID,
            config.ADDIN_COMMAND_NAME,
            config.ADDIN_COMMAND_DESCRIPTION,
            resource_dir,
        )

        on_created = CommandCreatedHandler()
        add_handler(cmd_def.commandCreated, on_created, handlers_global)

        # Add the button to custom panels in both MANUFACTURE and DESIGN workspaces
        panels_added = []
        workspace_configs = [
            ("CAMEnvironment", "CAMTab", "CAMTemplateCopierPanel", "CAM Templates"),
            ("FusionSolidEnvironment", "SolidTab", "CAMTemplateCopierPanelDesign", "CAM Templates"),
        ]

        for ws_id, tab_id, panel_id, panel_name in workspace_configs:
            panel = _get_or_create_panel(ws_id, tab_id, panel_id, panel_name)
            if panel:
                existing = panel.controls.itemById(config.ADDIN_COMMAND_ID)
                if not existing:
                    panel.controls.addCommand(cmd_def)
                panels_added.append(f"{ws_id} ({panel.id})")
                log(f"Button added to workspace: {ws_id}, panel: {panel.id}")

        if not panels_added:
            # Fallback: add to whatever add-ins panel exists
            for fallback_id in [config.ADDIN_PANEL_ID, config.ADDIN_PANEL_ID_FALLBACK, "ToolsScriptsAddinsPanel"]:
                panel = _ui.allToolbarPanels.itemById(fallback_id)
                if panel:
                    existing = panel.controls.itemById(config.ADDIN_COMMAND_ID)
                    if not existing:
                        panel.controls.addCommand(cmd_def)
                    panels_added.append(fallback_id)
                    log(f"Button added to fallback panel: {fallback_id}")
                    break

        if not panels_added:
            log("Warning: Could not find any toolbar panel.")
            _ui.messageBox(
                "CAMTemplateCopier: Could not add the button to any toolbar.\n"
                "You can run it from the Scripts and Add-Ins dialog (Shift+S)."
            )

        log("Command registered successfully.")

    except:
        log(f"Failed to start command:\n{traceback.format_exc()}")
        _ui.messageBox(f"CAMTemplateCopier failed to start:\n{traceback.format_exc()}")


def stop():
    """Remove the command from all toolbars and delete the command definition."""
    try:
        # Remove from all panels we may have added to
        panel_ids = [
            "CAMTemplateCopierPanel",
            "CAMTemplateCopierPanelDesign",
            config.ADDIN_PANEL_ID,
            config.ADDIN_PANEL_ID_FALLBACK,
            "ToolsScriptsAddinsPanel",
        ]
        for panel_id in panel_ids:
            panel = _ui.allToolbarPanels.itemById(panel_id)
            if panel:
                ctrl = panel.controls.itemById(config.ADDIN_COMMAND_ID)
                if ctrl:
                    ctrl.deleteMe()
                # Delete custom panels we created (only ours)
                if panel_id in ("CAMTemplateCopierPanel", "CAMTemplateCopierPanelDesign"):
                    if panel.controls.count == 0:
                        panel.deleteMe()

        cmd_def = _ui.commandDefinitions.itemById(config.ADDIN_COMMAND_ID)
        if cmd_def:
            cmd_def.deleteMe()

        _template_files_cache.clear()
        log("Command cleaned up.")

    except:
        log(f"Failed to stop command:\n{traceback.format_exc()}")


class CommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            cmd = args.command
            inputs = cmd.commandInputs

            # --- Validate preconditions ---
            active_doc = _app.activeDocument
            if not active_doc:
                _ui.messageBox(
                    "No document is open.\n\n"
                    "Please open a document before using Copy CAM Template."
                )
                # Cancel the command by setting isCancelButtonVisible and
                # not adding any inputs — user will see the message box above.
                cmd.isOKButtonVisible = False
                return

            if not active_doc.isSaved:
                _ui.messageBox(
                    "The current document has not been saved yet.\n\n"
                    "Please save the document first so the add-in knows "
                    "which folder to copy the template into."
                )
                cmd.isOKButtonVisible = False
                return

            # --- Find template folder and list templates ---
            template_folder, error_msg = find_template_folder(
                config.TEMPLATE_PROJECT_NAME, config.TEMPLATE_FOLDER_PATH
            )
            if not template_folder:
                _ui.messageBox(f"Template folder not found:\n\n{error_msg}")
                cmd.isOKButtonVisible = False
                return

            template_files = get_template_files(template_folder)
            if not template_files:
                path_str = " / ".join(config.TEMPLATE_FOLDER_PATH)
                _ui.messageBox(
                    f'No .f3d template files found in "{path_str}".\n\n'
                    f"Add template documents to this folder in the Data Panel."
                )
                cmd.isOKButtonVisible = False
                return

            # --- Cache template DataFile objects ---
            _template_files_cache.clear()
            for tf in template_files:
                _template_files_cache[tf.name] = tf

            # --- Build the dialog ---
            # Template dropdown
            dropdown = inputs.addDropDownCommandInput(
                "templateSelect",
                "Template",
                adsk.core.DropDownStyles.TextListDropDownStyle,
            )
            first = True
            for name in sorted(_template_files_cache.keys()):
                dropdown.listItems.add(name, first)
                first = False

            # File name defaults to "MFG <active document name>"
            doc_name = active_doc.name
            # Remove version suffix like " v3" that Fusion appends
            if " v" in doc_name:
                doc_name = doc_name[:doc_name.rfind(" v")]
            default_name = f"MFG {doc_name}"
            inputs.addStringValueInput("fileName", "New File Name", default_name)

            # Checkbox to insert the original component into the template
            inputs.addBoolValueInput("insertComponent", "Insert component into template", True, "", True)

            # --- Connect execute and input-changed handlers ---
            add_handler(cmd.execute, CommandExecuteHandler(), _handlers)
            add_handler(cmd.inputChanged, InputChangedHandler(), _handlers)
            add_handler(cmd.destroy, CommandDestroyHandler(), _handlers)

        except:
            _ui.messageBox(
                f"CAMTemplateCopier error:\n{traceback.format_exc()}"
            )


class InputChangedHandler(adsk.core.InputChangedEventHandler):
    """Update the file name field when the user picks a different template."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            # Template selection change no longer overwrites the file name,
            # since the default name is based on the active document, not the template.
            pass
        except:
            log(f"InputChanged error:\n{traceback.format_exc()}")


class CommandExecuteHandler(adsk.core.CommandEventHandler):
    """Fires when the user clicks OK. We cannot saveAs here, so fire a custom event."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            inputs = args.command.commandInputs
            dropdown = inputs.itemById("templateSelect")
            name_input = inputs.itemById("fileName")
            insert_checkbox = inputs.itemById("insertComponent")

            template_name = dropdown.selectedItem.name
            new_name = name_input.value.strip()
            insert_component = insert_checkbox.value if insert_checkbox else True

            if not new_name:
                _ui.messageBox("Please enter a file name.")
                return

            # Validate the template is still in cache
            if template_name not in _template_files_cache:
                _ui.messageBox(
                    f'Template "{template_name}" not found in cache.\n'
                    f"Try reopening the command."
                )
                return

            # Check for duplicate file name in target folder
            active_doc = _app.activeDocument
            if not active_doc or not active_doc.isSaved:
                _ui.messageBox("The active document is not saved. Cannot determine target folder.")
                return

            target_folder = active_doc.dataFile.parentFolder
            for existing_file in target_folder.dataFiles.asArray():
                if existing_file.name == new_name:
                    _ui.messageBox(
                        f'A file named "{new_name}" already exists in the target folder.\n\n'
                        f"Please choose a different name."
                    )
                    return

            # Fire the custom event to do the actual copy outside the command transaction
            import json

            event_data = json.dumps(
                {"template": template_name, "newName": new_name, "insertComponent": insert_component}
            )
            custom_event = _app.fireCustomEvent(config.CUSTOM_EVENT_ID, event_data)
            log(f"Copy requested: '{template_name}' -> '{new_name}'")

        except:
            _ui.messageBox(
                f"CAMTemplateCopier execute error:\n{traceback.format_exc()}"
            )


class CommandDestroyHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        _handlers.clear()
