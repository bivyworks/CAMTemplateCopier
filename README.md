# CAM Template Copier

A small Fusion add-in for shops that keep their CAM setups as template files.
One click copies a chosen template next to the part you are working on,
opens the copy, and drops the part into it, so a new manufacturing model
starts from your machine, stock and tool settings instead of from scratch.

Standard library and the Fusion API only. Nothing to install besides the
add-in.

## What it does

1. You have a part open and saved, say `Bracket`.
2. **Copy CAM Template** lists the `.f3d` files in your template folder.
3. You pick one, keep or edit the suggested name (`MFG Bracket`), and leave
   *Insert this part into the template* ticked.
4. The add-in saves a copy of the template into the same folder as `Bracket`,
   waits for the cloud upload to finish, opens the copy and inserts `Bracket`
   at the origin as a component.

Nothing in the template or in the part is modified.

## Requirements

- Autodesk Fusion with the Python API, on macOS or Windows.
- Templates stored in a Fusion project (cloud data), not on the local disk.

## Install

1. Clone or download this repository somewhere permanent.
2. In Fusion: **Utilities → Add-Ins → Scripts and Add-Ins → Add-Ins tab → +**
   (the green plus) and pick the `CAMTemplateCopier` folder.
3. Tick *Run on Startup* if Fusion did not already.
4. A **CAM Templates** panel with the **Copy CAM Template** button appears on
   the MANUFACTURE tab and on the DESIGN tab.

After updating the files, Stop and Run the add-in in the Scripts and Add-Ins
dialog, or restart Fusion.

## Configure

Open `CAMTemplateCopier/config.py` and set two values:

```python
TEMPLATE_PROJECT_NAME = "Workholding"       # the project in your Data Panel
TEMPLATE_FOLDER_PATH = ["CAM Templates"]    # folder path inside that project, one entry per level
```

`NEW_NAME_PREFIX` ("MFG ") is what goes in front of the part name in the
suggested file name. The messages the add-in shows when the project or a
folder cannot be found name the setting to check.

## Notes

- The part is inserted as an embedded copy, not as a linked reference. Edit
  the `False` in the `addByInsert` call in `CAMTemplateCopier.py` to `True`
  for a linked reference; Fusion then requires the part and the copy to be in
  the same project.
- The copy is refused when a file with the same name already exists in the
  target folder.
- Progress and errors go to the **TEXT COMMANDS** window, prefixed with
  `[CAMTemplateCopier]`.

## How it works

Fusion does not allow saving, opening or closing documents while a command
dialog is active, so the OK button only validates the inputs and fires a
custom event. The event handler opens the template invisibly, saves it
under the new name into the target folder and closes it. The upload to the
cloud then finishes in the background; the add-in listens for Fusion's
`dataFileComplete` event, and when the file with the new name reports
complete it opens it and inserts the part.

## Development

```
python3 -m unittest discover -s tests
python3 -m pyflakes CAMTemplateCopier tests
```

The tests run without Fusion through a small stand-in for the parts of the
API the add-in touches at import time and in its data helpers. They cover
the template folder lookup and its error messages, the file filter, the
suggested name, and the module loading the way Fusion performs it (the
add-in reloads its own modules on every Run, so edits are picked up by
Stop / Run without restarting Fusion). GitHub Actions runs them on Ubuntu
and Windows with Python 3.12 and 3.14.

## License

MIT, see [LICENSE](LICENSE).
