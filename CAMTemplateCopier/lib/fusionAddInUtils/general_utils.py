import adsk.core
import traceback

_app = adsk.core.Application.get()


def add_handler(event, handler, handler_list):
    """Connect an event handler and keep a reference to prevent garbage collection."""
    event.add(handler)
    handler_list.append(handler)


def log(message):
    """Log a message to the Fusion 360 Text Commands palette."""
    _app.log(f"[CAMTemplateCopier] {message}")


def find_template_folder(project_name, folder_path):
    """Navigate from a project name and folder path list to a DataFolder.

    Args:
        project_name: Name of the Fusion 360 project (e.g. "Bivy Works")
        folder_path: List of subfolder names from the project root
                     (e.g. ["CAM Templates"])

    Returns:
        The DataFolder if found, or None.
        Also returns an error message string (empty on success).
    """
    app = adsk.core.Application.get()
    hub = app.data.activeHub
    if not hub:
        return None, "No active hub found. Please sign in to Fusion 360."

    # Find the project
    target_project = None
    for proj in hub.dataProjects:
        if proj.name == project_name:
            target_project = proj
            break

    if not target_project:
        return None, (
            f'Project "{project_name}" not found in the active hub.\n'
            f"Check TEMPLATE_PROJECT_NAME in config.py."
        )

    # Walk the folder path
    current_folder = target_project.rootFolder
    for folder_name in folder_path:
        next_folder = current_folder.dataFolders.itemByName(folder_name)
        if not next_folder:
            built_path = " / ".join(folder_path)
            return None, (
                f'Folder "{folder_name}" not found in path "{built_path}".\n'
                f"Check TEMPLATE_FOLDER_PATH in config.py."
            )
        current_folder = next_folder

    return current_folder, ""


def get_template_files(template_folder):
    """Return a list of DataFile objects for .f3d files in the given folder.

    Returns:
        A list of DataFile objects (may be empty).
    """
    templates = []
    for data_file in template_folder.dataFiles.asArray():
        if data_file.fileExtension == "f3d":
            templates.append(data_file)
    return templates
