"""Tests that run without Fusion: the template folder lookup, the file
filter, the suggested file name, and the add-in's module loading the way
Fusion performs it.

Run from the repository root:  python3 -m unittest discover -s tests
"""

import sys
import types
import unittest
import warnings
from pathlib import Path

HERE = Path(__file__).resolve().parent
ADDIN = HERE.parent / 'CAMTemplateCopier'
sys.path.insert(0, str(HERE))

import fake_adsk  # noqa: E402

app = fake_adsk.install()

# Import the add-in folder as the package Fusion makes of it.
if 'CAMTemplateCopier' not in sys.modules:
    _pkg = types.ModuleType('CAMTemplateCopier')
    _pkg.__path__ = [str(ADDIN)]
    _pkg.__package__ = 'CAMTemplateCopier'
    sys.modules['CAMTemplateCopier'] = _pkg

from CAMTemplateCopier import config  # noqa: E402
from CAMTemplateCopier.lib.fusionAddInUtils import find_template_folder, get_template_files  # noqa: E402
from CAMTemplateCopier.commands.copyTemplate import entry  # noqa: E402


def make_hub():
    templates = fake_adsk.DataFolder('CAM Templates', files=[
        fake_adsk.DataFile('Vise Template'), fake_adsk.DataFile('Notes', 'txt'), fake_adsk.DataFile('Fixture Plate'),
    ])
    resources = fake_adsk.DataFolder('Resources', folders=[templates])
    root = fake_adsk.DataFolder('root', folders=[templates, resources])
    other = fake_adsk.DataFolder('root')
    return fake_adsk._Hub([fake_adsk.DataProject('Customer Parts', other), fake_adsk.DataProject('Workholding', root)])


class TemplateFolder(unittest.TestCase):
    def setUp(self):
        app.data.activeHub = make_hub()

    def test_finds_nested_folder(self):
        folder, err = find_template_folder('Workholding', ['Resources', 'CAM Templates'])
        self.assertEqual(err, '')
        self.assertEqual(folder.name, 'CAM Templates')
        folder, err = find_template_folder('Workholding', ['CAM Templates'])
        self.assertEqual(folder.name, 'CAM Templates')

    def test_missing_project_and_folder(self):
        folder, err = find_template_folder('Nope', ['CAM Templates'])
        self.assertIsNone(folder)
        self.assertIn('TEMPLATE_PROJECT_NAME', err)
        folder, err = find_template_folder('Workholding', ['Resources', 'Missing'])
        self.assertIsNone(folder)
        self.assertIn('"Missing"', err)
        self.assertIn('Resources / Missing', err)

    def test_no_hub(self):
        app.data.activeHub = None
        folder, err = find_template_folder('Workholding', ['CAM Templates'])
        self.assertIsNone(folder)
        self.assertIn('sign in', err)

    def test_only_f3d_files(self):
        folder, _ = find_template_folder('Workholding', ['CAM Templates'])
        self.assertEqual([f.name for f in get_template_files(folder)], ['Vise Template', 'Fixture Plate'])

    def test_default_config_path_resolves(self):
        folder, err = find_template_folder(config.TEMPLATE_PROJECT_NAME, config.TEMPLATE_FOLDER_PATH)
        self.assertEqual(err, '')


class DefaultName(unittest.TestCase):
    def test_uses_the_data_file_name(self):
        doc = types.SimpleNamespace(name='Bracket v7', dataFile=types.SimpleNamespace(name='Bracket'))
        self.assertEqual(entry.default_new_name(doc), 'MFG Bracket')

    def test_strips_the_version_suffix_without_a_data_file(self):
        doc = types.SimpleNamespace(name='Side vent v12', dataFile=None)
        self.assertEqual(entry.default_new_name(doc), 'MFG Side vent')
        doc = types.SimpleNamespace(name='Vise jaw', dataFile=None)
        self.assertEqual(entry.default_new_name(doc), 'MFG Vise jaw')


class MainModule(unittest.TestCase):
    def test_loads_fresh_modules_the_way_fusion_runs_it(self):
        """Fusion executes the main file in a module with __path__ set and no
        __package__; two runs must each import fresh modules."""
        saved = {n: m for n, m in sys.modules.items() if n == 'CAMTemplateCopier' or n.startswith('CAMTemplateCopier.')}
        try:
            for n in saved:
                del sys.modules[n]
            mod = types.ModuleType('CAMTemplateCopier')
            mod.__file__ = str(ADDIN / 'CAMTemplateCopier.py')
            mod.__path__ = [str(ADDIN)]
            mod.__package__ = None
            mod.__spec__ = None
            sys.modules['CAMTemplateCopier'] = mod
            code = compile((ADDIN / 'CAMTemplateCopier.py').read_text(encoding='utf-8'), mod.__file__, 'exec')
            exec(code, mod.__dict__)
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', ImportWarning)
                self.assertEqual(mod._package_name(), 'CAMTemplateCopier')
                mod._load_fresh()
                first = mod.copy_template_cmd
                mod._load_fresh()
            self.assertIsNotNone(first)
            self.assertIsNot(first, mod.copy_template_cmd)
            self.assertEqual(mod.config.ADDIN_COMMAND_ID, config.ADDIN_COMMAND_ID)
            self.assertTrue(callable(mod.copy_template_cmd.start))
            self.assertIn(__name__, sys.modules)        # only the add-in's own modules are dropped
        finally:
            for n in [n for n in sys.modules if n == 'CAMTemplateCopier' or n.startswith('CAMTemplateCopier.')]:
                del sys.modules[n]
            sys.modules.update(saved)


if __name__ == '__main__':
    unittest.main()
