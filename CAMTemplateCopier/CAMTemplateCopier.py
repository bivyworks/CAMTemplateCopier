import adsk.core
import adsk.fusion
import traceback
import json
import os
import sys

# Ensure the add-in root is on the path
_addin_dir = os.path.dirname(os.path.abspath(__file__))
if _addin_dir not in sys.path:
    sys.path.insert(0, _addin_dir)

import config
from commands.copyTemplate import entry as copy_template_cmd
from lib.fusionAddInUtils import log

_app = adsk.core.Application.get()
_ui = _app.userInterface

# Global references to prevent garbage collection
_handlers = []
_custom_event = None
_data_file_complete_handler = None

# State for tracking the async save and component insert
_pending_open_name = None
_source_data_file = None  # The original part's DataFile to insert after template opens


class CopyEventHandler(adsk.core.CustomEventHandler):
    """Handles the deferred copy operation outside the command transaction.

    This is where the actual open-template -> saveAs -> close sequence happens.
    """

    def __init__(self):
        super().__init__()

    def notify(self, args):
        global _pending_open_name, _source_data_file
        try:
            event_data = json.loads(args.additionalInfo)
            template_name = event_data["template"]
            new_name = event_data["newName"]

            log(f"Starting copy: '{template_name}' -> '{new_name}'")

            # Get the cached template DataFile
            from commands.copyTemplate.entry import _template_files_cache

            template_file = _template_files_cache.get(template_name)
            if not template_file:
                _ui.messageBox(
                    f'Template "{template_name}" not found in cache.\n'
                    f"Please try again."
                )
                return

            # Get the target folder and save source file ref for later insertion
            active_doc = _app.activeDocument
            if not active_doc or not active_doc.isSaved:
                _ui.messageBox(
                    "Cannot determine target folder.\n"
                    "Make sure a saved document is open."
                )
                return
            target_folder = active_doc.dataFile.parentFolder

            # Only store the source file if the user wants to insert the component
            if event_data.get("insertComponent", True):
                _source_data_file = active_doc.dataFile
            else:
                _source_data_file = None

            # Open the template invisibly
            log("Opening template document (invisible)...")
            template_doc = _app.documents.open(template_file, False)
            if not template_doc:
                _ui.messageBox("Failed to open the template document.")
                return

            # Save as new name into the target folder
            log(f"Saving as '{new_name}' into '{target_folder.name}'...")
            _pending_open_name = new_name
            template_doc.saveAs(new_name, target_folder, "", "")

            # Close the invisible template document without saving
            template_doc.close(False)
            log("Template document closed. Waiting for cloud save to complete...")

        except:
            error_msg = traceback.format_exc()
            log(f"Copy failed:\n{error_msg}")
            _ui.messageBox(f"CAMTemplateCopier copy failed:\n{error_msg}")


class DataFileCompleteHandler(adsk.core.DataEventHandler):
    """Fires when a cloud file save completes.

    We use this to open the newly saved copy once it's available.
    """

    def __init__(self):
        super().__init__()

    def notify(self, args):
        global _pending_open_name, _source_data_file
        try:
            if not _pending_open_name:
                return

            completed_file = args.file
            if completed_file and completed_file.name == _pending_open_name:
                log(f"Cloud save complete for '{_pending_open_name}'. Opening...")
                new_doc = _app.documents.open(completed_file, True)
                log("New document opened successfully.")

                # Insert the original part as a component
                if _source_data_file and new_doc:
                    try:
                        design = adsk.fusion.Design.cast(new_doc.products.itemByProductType("DesignProductType"))
                        if design:
                            root_comp = design.rootComponent
                            transform = adsk.core.Matrix3D.create()  # identity — origin
                            root_comp.occurrences.addByInsert(
                                _source_data_file, transform, False
                            )
                            log(f"Inserted component '{_source_data_file.name}' into template.")
                        else:
                            log("Warning: No design found in new document. Component not inserted.")
                    except:
                        error_msg = traceback.format_exc()
                        log(f"Component insert failed:\n{error_msg}")
                        _ui.messageBox(
                            f"Template copied and opened, but component insert failed:\n{error_msg}"
                        )

                _pending_open_name = None
                _source_data_file = None

        except:
            error_msg = traceback.format_exc()
            log(f"DataFileComplete handler error:\n{error_msg}")
            _pending_open_name = None
            _source_data_file = None


def run(context):
    global _custom_event, _data_file_complete_handler
    try:
        log("Starting CAMTemplateCopier add-in...")

        # Register the custom event for deferred save operations
        custom_event = _app.registerCustomEvent(config.CUSTOM_EVENT_ID)
        copy_handler = CopyEventHandler()
        custom_event.add(copy_handler)
        _handlers.append(copy_handler)
        _custom_event = custom_event

        # Register the dataFileComplete event to know when cloud saves finish
        dfc_handler = DataFileCompleteHandler()
        _app.dataFileComplete.add(dfc_handler)
        _handlers.append(dfc_handler)
        _data_file_complete_handler = dfc_handler

        # Start the command (creates the toolbar button)
        copy_template_cmd.start(_handlers)

        log("CAMTemplateCopier add-in started.")

    except:
        error_msg = traceback.format_exc()
        log(f"CAMTemplateCopier run failed:\n{error_msg}")
        if _ui:
            _ui.messageBox(f"CAMTemplateCopier failed to start:\n{error_msg}")


def stop(context):
    global _custom_event, _data_file_complete_handler, _pending_open_name
    try:
        log("Stopping CAMTemplateCopier add-in...")

        # Stop the command (removes toolbar button)
        copy_template_cmd.stop()

        # Unregister the custom event
        if _custom_event:
            _app.unregisterCustomEvent(config.CUSTOM_EVENT_ID)
            _custom_event = None

        # Clean up the dataFileComplete handler
        if _data_file_complete_handler:
            _app.dataFileComplete.remove(_data_file_complete_handler)
            _data_file_complete_handler = None

        _handlers.clear()
        _pending_open_name = None
        _source_data_file = None

        log("CAMTemplateCopier add-in stopped.")

    except:
        error_msg = traceback.format_exc()
        log(f"CAMTemplateCopier stop failed:\n{error_msg}")
        if _ui:
            _ui.messageBox(f"CAMTemplateCopier failed to stop:\n{error_msg}")
