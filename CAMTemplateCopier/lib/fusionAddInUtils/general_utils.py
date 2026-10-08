import adsk.core

_app = adsk.core.Application.get()


def add_handler(event, handler, handler_list):
    """Connect an event handler and keep a reference so it is not garbage collected."""
    event.add(handler)
    handler_list.append(handler)


def log(message):
    """Write a line to the Fusion TEXT COMMANDS window."""
    _app.log(f"[CAMTemplateCopier] {message}")


def find_template_folder(project_name, folder_path):
    """Walk from a project name and a list of folder names to a DataFolder.

    Returns (folder, '') on success, or (None, message) when the hub, the
    project or one of the folders cannot be found."""
    app = adsk.core.Application.get()
    hub = app.data.activeHub
    if not hub:
        return None, "No active hub found. Please sign in to Fusion."

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
    """The .f3d DataFiles in the folder (may be empty)."""
    templates = []
    for data_file in template_folder.dataFiles.asArray():
        if data_file.fileExtension == "f3d":
            templates.append(data_file)
    return templates
