# CAMTemplateCopier - Fusion add-in entry point.
#
# Fusion calls run() when the add-in loads and stop() when it unloads. The
# command (toolbar button and dialog) lives in commands/copyTemplate/entry.py.
# This file owns the two application-level events the copy needs:
#
#   1. a custom event, fired from the dialog's OK handler, in which the
#      template is opened invisibly, saved under the new name into the active
#      document's folder and closed. Saving or closing a document is not
#      allowed inside a command event, so it has to happen afterwards;
#   2. the dataFileComplete event, which fires when the cloud upload of the
#      new file has finished. The new file is opened there and the original
#      part is inserted into it.
#
# The add-in's own modules are dropped from sys.modules and imported again on
# every run(), so Stop / Run in the Scripts and Add-Ins dialog picks up edited
# files without restarting Fusion. Fusion's loader leaves __package__ unset,
# so the package name is resolved the way a relative import resolves it.

import importlib
import json
import sys
import traceback
from pathlib import Path

import adsk.core
import adsk.fusion

_ROOT = Path(__file__).resolve().parent
_OWN = ('commands', 'lib', 'config.py')

_app = adsk.core.Application.get()
_ui = _app.userInterface

config = None               # the add-in's config module, set by _load_fresh()
copy_template_cmd = None    # commands/copyTemplate/entry.py
_log = None

_handlers = []              # keeps event handlers alive
_custom_event = None
_data_file_complete_handler = None

# State of the copy in flight: the name we are waiting for the cloud to
# report as uploaded, and the part to insert into it once it is open.
_pending_open_name = None
_source_data_file = None


# ------------------------------------------------------------------ module loading

def _package_name() -> str:
    g = globals()
    if g.get('__package__'):
        return g['__package__']
    spec = g.get('__spec__')
    if spec is not None and getattr(spec, 'parent', None):
        return spec.parent
    name = g.get('__name__') or ''
    return name if '__path__' in g else name.rpartition('.')[0]


def _is_own(module) -> bool:
    """Is this module one of the add-in's own (under commands/, lib/, or config.py)?"""
    paths = []
    try:
        f = getattr(module, '__file__', None)
        if f:
            paths.append(f)
        paths.extend(str(p) for p in (getattr(module, '__path__', None) or []))
    except Exception:
        return False
    for p in paths:
        try:
            rel = Path(p).resolve().relative_to(_ROOT)
        except (ValueError, OSError):
            continue
        if rel.parts and rel.parts[0] in _OWN:
            return True
    return False


def _drop_stale_modules() -> None:
    stale = [name for name, module in list(sys.modules.items())
             if module is not None and name != __name__ and _is_own(module)]
    for name in stale:
        sys.modules.pop(name, None)


def _load_fresh() -> None:
    global config, copy_template_cmd, _log
    pkg = _package_name()
    if not pkg:
        raise ImportError('cannot resolve the add-in package name (no __package__, __spec__ or __path__)')
    _drop_stale_modules()
    config = importlib.import_module(pkg + '.config')
    utils = importlib.import_module(pkg + '.lib.fusionAddInUtils')
    copy_template_cmd = importlib.import_module(pkg + '.commands.copyTemplate.entry')
    _log = utils.log


def _report(what: str) -> None:
    """Log a failure and show it, whatever state the add-in is in."""
    error_msg = traceback.format_exc()
    try:
        if _log is not None:
            _log(f'{what} failed:\n{error_msg}')
    except Exception:
        pass
    try:
        _ui.messageBox(f'CAMTemplateCopier {what} failed:\n{error_msg}')
    except Exception:
        pass


# ------------------------------------------------------------------ events

class CopyEventHandler(adsk.core.CustomEventHandler):
    """The deferred copy, outside the command transaction: open the template
    invisibly, save it under the new name into the target folder, close it.
    The upload then completes in the background (see DataFileCompleteHandler)."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        global _pending_open_name, _source_data_file
        template_doc = None
        try:
            event_data = json.loads(args.additionalInfo)
            template_name = event_data['template']
            new_name = event_data['newName']
            _log(f"Starting copy: '{template_name}' -> '{new_name}'")

            template_file = copy_template_cmd.cached_template(template_name)
            if template_file is None:
                _ui.messageBox(f'Template "{template_name}" is no longer available.\nPlease run the command again.')
                return

            active_doc = _app.activeDocument
            if not active_doc or not active_doc.isSaved:
                _ui.messageBox('Cannot determine the target folder.\nMake sure a saved document is open.')
                return
            target_folder = active_doc.dataFile.parentFolder

            # The part to insert later, only when asked for.
            _source_data_file = active_doc.dataFile if event_data.get('insertComponent', True) else None

            _log('Opening the template (invisible)...')
            template_doc = _app.documents.open(template_file, False)
            if not template_doc:
                _ui.messageBox('Fusion could not open the template document.')
                return

            _log(f"Saving as '{new_name}' into '{target_folder.name}'...")
            _pending_open_name = new_name
            if not template_doc.saveAs(new_name, target_folder, '', ''):
                _pending_open_name = None
                _source_data_file = None
                _ui.messageBox(f'Fusion could not save "{new_name}" into "{target_folder.name}".')
                return
            _log('Saved. Waiting for the cloud upload to complete...')
        except Exception:
            _pending_open_name = None
            _source_data_file = None
            _report('copy')
        finally:
            # Never leave an invisible document open, whatever happened above.
            if template_doc is not None:
                try:
                    template_doc.close(False)
                except Exception:
                    _log('Closing the template document raised an exception.')


class DataFileCompleteHandler(adsk.core.DataEventHandler):
    """Fires when a cloud upload has completed. When it is the file we just
    saved, open it and insert the original part."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        global _pending_open_name, _source_data_file
        try:
            if not _pending_open_name:
                return
            completed_file = args.file
            if completed_file is None or completed_file.name != _pending_open_name:
                return
            _log(f"Upload of '{_pending_open_name}' complete. Opening...")
            new_doc = _app.documents.open(completed_file, True)
            if not new_doc:
                _ui.messageBox(f'"{_pending_open_name}" was saved but Fusion could not open it.')
                return
            _log('New document opened.')

            if _source_data_file is not None:
                try:
                    _insert_part(new_doc, _source_data_file)
                except Exception:
                    error_msg = traceback.format_exc()
                    _log(f'Component insert failed:\n{error_msg}')
                    _ui.messageBox(f'The template was copied and opened, but inserting the part failed:\n{error_msg}')
        except Exception:
            _report('open after upload')
        finally:
            _pending_open_name = None
            _source_data_file = None


def _insert_part(new_doc, data_file) -> None:
    """Insert the part into the newly opened copy at the origin, as a linked
    reference when configured (Occurrences.addByInsert with
    isReferencedComponent=True; Fusion returns None when the two files are
    not in the same project), else as an embedded copy."""
    design = adsk.fusion.Design.cast(new_doc.products.itemByProductType('DesignProductType'))
    if not design:
        _log('No design in the new document; the part was not inserted.')
        return
    occurrences = design.rootComponent.occurrences
    transform = adsk.core.Matrix3D.create()          # identity: at the origin
    want_link = bool(getattr(config, 'INSERT_AS_REFERENCE', True))
    occ = occurrences.addByInsert(data_file, transform, want_link) if want_link else None
    if occ is not None:
        linked = False
        try:
            linked = bool(occ.isReferencedComponent)
        except Exception:
            pass
        _log(f"Inserted '{data_file.name}' as a {'linked reference' if linked else 'component'}.")
        return
    if want_link:
        _log(f"Fusion refused to link '{data_file.name}' (the part and the copy must be in the same project); "
             f"inserting an embedded copy instead.")
    occ = occurrences.addByInsert(data_file, transform, False)
    if occ is None:
        raise RuntimeError(f"Occurrences.addByInsert returned None for '{data_file.name}'.")
    _log(f"Inserted '{data_file.name}' as an embedded copy.")
    if want_link:
        _ui.messageBox(f'"{data_file.name}" was inserted as an embedded copy, not a linked reference: Fusion '
                       f'only links files from the same project.')


# ------------------------------------------------------------------ add-in lifecycle

def run(context):
    global _custom_event, _data_file_complete_handler
    try:
        _load_fresh()
        _log('Starting CAMTemplateCopier add-in...')

        # A previous load that did not stop cleanly leaves the id registered,
        # and registerCustomEvent then returns None.
        try:
            _app.unregisterCustomEvent(config.CUSTOM_EVENT_ID)
        except Exception:
            pass
        custom_event = _app.registerCustomEvent(config.CUSTOM_EVENT_ID)
        if custom_event is None:
            raise RuntimeError(f'registerCustomEvent({config.CUSTOM_EVENT_ID!r}) returned None')
        copy_handler = CopyEventHandler()
        custom_event.add(copy_handler)
        _handlers.append(copy_handler)
        _custom_event = custom_event

        dfc_handler = DataFileCompleteHandler()
        _app.dataFileComplete.add(dfc_handler)
        _handlers.append(dfc_handler)
        _data_file_complete_handler = dfc_handler

        copy_template_cmd.start(_handlers)
        _log('CAMTemplateCopier add-in started.')
    except Exception:
        _report('run')


def stop(context):
    global _custom_event, _data_file_complete_handler, _pending_open_name, _source_data_file
    try:
        if copy_template_cmd is None:        # run() never got that far
            return
        _log('Stopping CAMTemplateCopier add-in...')
        copy_template_cmd.stop()
        if _custom_event is not None:
            _app.unregisterCustomEvent(config.CUSTOM_EVENT_ID)
            _custom_event = None
        if _data_file_complete_handler is not None:
            _app.dataFileComplete.remove(_data_file_complete_handler)
            _data_file_complete_handler = None
        _handlers.clear()
        _pending_open_name = None
        _source_data_file = None
        _log('CAMTemplateCopier add-in stopped.')
    except Exception:
        _report('stop')
