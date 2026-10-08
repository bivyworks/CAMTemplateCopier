"""A tiny stand-in for the ``adsk`` package so the add-in's modules can be
imported and its pure helpers exercised outside Fusion.

It models only what the import-time code and the data helpers touch: the
application singleton with its log, user interface and data hub, projects,
folders and files, the handler base classes the command subclasses, and the
drop-down style enum. ``install()`` registers it in ``sys.modules``."""

import sys
import types
from typing import List, Optional


class _Handler:
    def __init__(self):
        pass


class CustomEventHandler(_Handler):
    pass


class DataEventHandler(_Handler):
    pass


class CommandCreatedEventHandler(_Handler):
    pass


class CommandEventHandler(_Handler):
    pass


class InputChangedEventHandler(_Handler):
    pass


class DropDownStyles:
    TextListDropDownStyle = 0


class DataFile:
    def __init__(self, name: str, ext: str = 'f3d'):
        self.name = name
        self.fileExtension = ext


class _DataFiles:
    def __init__(self, files):
        self._files = list(files)

    def asArray(self):
        return list(self._files)


class _DataFolders:
    def __init__(self, folders):
        self._folders = list(folders)

    def itemByName(self, name):
        for f in self._folders:
            if f.name == name:
                return f
        return None


class DataFolder:
    def __init__(self, name: str, folders=(), files=()):
        self.name = name
        self.dataFolders = _DataFolders(folders)
        self.dataFiles = _DataFiles(files)


class DataProject:
    def __init__(self, name: str, root: DataFolder):
        self.name = name
        self.rootFolder = root


class _Hub:
    def __init__(self, projects):
        self.dataProjects = list(projects)


class _Data:
    def __init__(self):
        self.activeHub: Optional[_Hub] = None


class FakeUI:
    def __init__(self):
        self.messages: List[str] = []

    def messageBox(self, text, *args):
        self.messages.append(text)
        return 0


class FakeApp:
    _instance = None

    def __init__(self):
        self.userInterface = FakeUI()
        self.data = _Data()
        self.log_lines: List[str] = []

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def log(self, message, *args):
        self.log_lines.append(message)


def install() -> FakeApp:
    if 'adsk' in sys.modules and getattr(sys.modules['adsk'], '_fake', False):
        return FakeApp.get()
    adsk = types.ModuleType('adsk')
    adsk._fake = True
    core = types.ModuleType('adsk.core')
    fusion = types.ModuleType('adsk.fusion')
    for name, obj in list(globals().items()):
        if isinstance(obj, type):
            setattr(core, name, obj)
    core.Application = FakeApp
    adsk.core, adsk.fusion = core, fusion
    sys.modules['adsk'] = adsk
    sys.modules['adsk.core'] = core
    sys.modules['adsk.fusion'] = fusion
    return FakeApp.get()
