"""The Copy CAM Template command: toolbar button, dialog and OK handler.

The dialog lists the .f3d files of the configured template folder, suggests
a name for the copy and asks whether to insert the active part into it. OK
only validates and fires the custom event; the copy itself runs in
CAMTemplateCopier.py after the command has closed.
"""

import json
import os
import re
import traceback

import adsk.core

from ... import config
from ...lib.fusionAddInUtils import add_handler, log, find_template_folder, get_template_files

_app = adsk.core.Application.get()
_ui = _app.userInterface

_handlers = []                  # per-dialog handlers, cleared on destroy
_template_files_cache = {}      # template name -> DataFile, filled when the dialog opens

PANEL_NAME = "CAM Templates"
OWN_PANELS = (
    ("CAMEnvironment", "CAMTab", "CAMTemplateCopierPanel"),
    ("FusionSolidEnvironment", "SolidTab", "CAMTemplateCopierPanelDesign"),
)


def cached_template(name):
    """The DataFile of a template listed by the last dialog, or None."""
    return _template_files_cache.get(name)


def default_new_name(active_doc) -> str:
    """The suggested name of the copy: the prefix plus the document's name
    without the ' vN' version suffix Fusion shows in the title."""
    name = ""
    try:
        name = active_doc.dataFile.name or ""
    except Exception:
        name = ""
    if not name:
        try:
            name = re.sub(r"\s+v\d+$", "", active_doc.name or "")
        except Exception:
            name = ""
    return f"{config.NEW_NAME_PREFIX}{name}".strip()


# ------------------------------------------------------------------ toolbar

def _get_or_create_panel(workspace_id, tab_id, panel_id, panel_name):
    """Our own panel on the given tab, created when missing. None when the
    workspace has no tabs at all."""
    workspace = _ui.workspaces.itemById(workspace_id)
    if not workspace:
        log(f"Workspace '{workspace_id}' not found.")
        return None
    toolbar_tabs = workspace.toolbarTabs
    tab = toolbar_tabs.itemById(tab_id)
    if not tab:
        if toolbar_tabs.count == 0:
            log(f"No tabs in workspace '{workspace_id}'.")
            return None
        tab = toolbar_tabs.item(0)
    panel = tab.toolbarPanels.itemById(panel_id)
    if not panel:
        panel = tab.toolbarPanels.add(panel_id, panel_name)
    return panel


def start(handlers_global):
    """Create the command definition and put its button on the MANUFACTURE and
    DESIGN toolbars (or on an add-ins panel when neither workspace exists)."""
    try:
        cmd_def = _ui.commandDefinitions.itemById(config.ADDIN_COMMAND_ID)
        if cmd_def:
            # Left behind by a load that did not stop cleanly: remove its
            # buttons before the definition they are bound to.
            _remove_controls()
            cmd_def.deleteMe()

        resource_dir = os.path.join(os.path.dirname(__file__), "resources")
        cmd_def = _ui.commandDefinitions.addButtonDefinition(
            config.ADDIN_COMMAND_ID, config.ADDIN_COMMAND_NAME, config.ADDIN_COMMAND_DESCRIPTION, resource_dir
        )
        add_handler(cmd_def.commandCreated, CommandCreatedHandler(), handlers_global)

        panels_added = []
        for ws_id, tab_id, panel_id in OWN_PANELS:
            panel = _get_or_create_panel(ws_id, tab_id, panel_id, PANEL_NAME)
            if panel:
                if not panel.controls.itemById(config.ADDIN_COMMAND_ID):
                    panel.controls.addCommand(cmd_def)
                panels_added.append(f"{ws_id} ({panel.id})")
                log(f"Button added to workspace {ws_id}, panel {panel.id}")

        if not panels_added:
            for fallback_id in (config.ADDIN_PANEL_ID, config.ADDIN_PANEL_ID_FALLBACK, "ToolsScriptsAddinsPanel"):
                panel = _ui.allToolbarPanels.itemById(fallback_id)
                if panel:
                    if not panel.controls.itemById(config.ADDIN_COMMAND_ID):
                        panel.controls.addCommand(cmd_def)
                    panels_added.append(fallback_id)
                    log(f"Button added to fallback panel {fallback_id}")
                    break

        if not panels_added:
            log("Warning: no toolbar panel found for the button.")
            _ui.messageBox(
                "CAMTemplateCopier: the button could not be added to any toolbar.\n"
                "You can still run it from the Scripts and Add-Ins dialog (Shift+S)."
            )
        log("Command registered.")
    except Exception:
        log(f"Failed to start the command:\n{traceback.format_exc()}")
        _ui.messageBox(f"CAMTemplateCopier failed to start:\n{traceback.format_exc()}")


def _remove_controls():
    """Remove our button from every panel it may be on, and our own panels
    when they are empty."""
    own_ids = {panel_id for _, _, panel_id in OWN_PANELS}
    for panel_id in list(own_ids) + [config.ADDIN_PANEL_ID, config.ADDIN_PANEL_ID_FALLBACK, "ToolsScriptsAddinsPanel"]:
        panel = _ui.allToolbarPanels.itemById(panel_id)
        if not panel:
            continue
        ctrl = panel.controls.itemById(config.ADDIN_COMMAND_ID)
        if ctrl:
            ctrl.deleteMe()
        if panel_id in own_ids and panel.controls.count == 0:
            panel.deleteMe()


def stop():
    """Remove the button(s) and the command definition."""
    try:
        _remove_controls()
        cmd_def = _ui.commandDefinitions.itemById(config.ADDIN_COMMAND_ID)
        if cmd_def:
            cmd_def.deleteMe()
        _template_files_cache.clear()
        log("Command cleaned up.")
    except Exception:
        log(f"Failed to stop the command:\n{traceback.format_exc()}")


# ------------------------------------------------------------------ dialog

def _cannot_run(cmd, message: str) -> None:
    """Show why the command cannot run: a message box, and the same text in
    the dialog, which keeps only a Close button."""
    _ui.messageBox(message)
    try:
        box = cmd.commandInputs.addTextBoxCommandInput("reason", "", message.replace("\n", "<br/>"), 4, True)
        box.isFullWidth = True
    except Exception:
        pass
    cmd.isOKButtonVisible = False


class CommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            cmd = args.command
            inputs = cmd.commandInputs

            active_doc = _app.activeDocument
            if not active_doc:
                _cannot_run(cmd, "No document is open.\n\nOpen the part you want to machine before using Copy CAM Template.")
                return
            if not active_doc.isSaved:
                _cannot_run(cmd, "The current document has not been saved yet.\n\n"
                                 "Save it first so the add-in knows which folder to copy the template into.")
                return

            template_folder, error_msg = find_template_folder(config.TEMPLATE_PROJECT_NAME, config.TEMPLATE_FOLDER_PATH)
            if not template_folder:
                _cannot_run(cmd, f"Template folder not found:\n\n{error_msg}")
                return
            template_files = get_template_files(template_folder)
            if not template_files:
                path_str = " / ".join(config.TEMPLATE_FOLDER_PATH)
                _cannot_run(cmd, f'No .f3d template files found in "{path_str}".\n\n'
                                 f"Add template documents to this folder in the Data Panel.")
                return

            _template_files_cache.clear()
            for tf in template_files:
                _template_files_cache[tf.name] = tf

            dropdown = inputs.addDropDownCommandInput("templateSelect", "Template", adsk.core.DropDownStyles.TextListDropDownStyle)
            first = True
            for name in sorted(_template_files_cache):
                dropdown.listItems.add(name, first)
                first = False
            inputs.addStringValueInput("fileName", "New file name", default_new_name(active_doc))
            inputs.addBoolValueInput("insertComponent", "Insert this part into the template", True, "", True)

            add_handler(cmd.execute, CommandExecuteHandler(), _handlers)
            add_handler(cmd.destroy, CommandDestroyHandler(), _handlers)
        except Exception:
            _ui.messageBox(f"CAMTemplateCopier error:\n{traceback.format_exc()}")


class CommandExecuteHandler(adsk.core.CommandEventHandler):
    """OK: validate, then hand the copy to the custom event (a document cannot
    be saved inside a command event)."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            inputs = args.command.commandInputs
            dropdown = inputs.itemById("templateSelect")
            name_input = inputs.itemById("fileName")
            insert_checkbox = inputs.itemById("insertComponent")

            template_name = dropdown.selectedItem.name if dropdown and dropdown.selectedItem else ""
            new_name = (name_input.value or "").strip() if name_input else ""
            insert_component = bool(insert_checkbox.value) if insert_checkbox else True

            if not new_name:
                _ui.messageBox("Please enter a file name.")
                return
            if template_name not in _template_files_cache:
                _ui.messageBox(f'Template "{template_name}" is no longer available.\nPlease run the command again.')
                return

            active_doc = _app.activeDocument
            if not active_doc or not active_doc.isSaved:
                _ui.messageBox("The active document is not saved, so the target folder is unknown.")
                return
            target_folder = active_doc.dataFile.parentFolder
            for existing_file in target_folder.dataFiles.asArray():
                if existing_file.name == new_name:
                    _ui.messageBox(f'A file named "{new_name}" already exists in this folder.\n\nPlease choose a different name.')
                    return

            event_data = json.dumps({"template": template_name, "newName": new_name, "insertComponent": insert_component})
            _app.fireCustomEvent(config.CUSTOM_EVENT_ID, event_data)
            log(f"Copy requested: '{template_name}' -> '{new_name}'")
        except Exception:
            _ui.messageBox(f"CAMTemplateCopier execute error:\n{traceback.format_exc()}")


class CommandDestroyHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        _handlers.clear()
