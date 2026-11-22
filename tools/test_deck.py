import io
import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import check
import deck


CASE = Path(__file__).resolve().parents[1] / 'demo/family/first-run'


class DeckTests(unittest.TestCase):
    def test_entire_sample_is_reproducible_and_new_text_is_escaped(self):
        spec = json.loads((CASE / 'presentation.json').read_text())
        self.assertEqual(deck.render(spec), (CASE / 'decision-brief.pptx').read_bytes())
        spec['slides'][0]['title'] = 'Условия A & B < 4'
        with ZipFile(io.BytesIO(deck.render(spec))) as archive:
            xml = ET.fromstring(archive.read('ppt/slides/slide1.xml'))
            self.assertIn('Условия A & B < 4', list(xml.itertext()))
            self.assertIn(spec['slides'][0]['notes'], ' '.join(ET.fromstring(archive.read('ppt/notesSlides/notesSlide1.xml')).itertext()))
        spec['slides'][0]['title'] = 'text\ufffeend'
        with self.assertRaises(ValueError):
            deck.render(spec)
        spec['slides'][0]['title'] = 'Заголовок'
        del spec['slides'][0]['notes']
        with self.assertRaisesRegex(ValueError, 'notes'):
            deck.render(spec)

    def test_completion_requires_valid_deck_for_new_cases_and_reads_old_cases(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            state = json.loads((CASE / 'state.json').read_text())
            state.update(stage='complete', output='result.md', decision={'option_id':'close','quote':'Закрыть.'})
            (root / 'result.md').write_text('Решение')
            path = root / 'state.json'
            for name in (None, '../other.pptx', 'broken.pptx'):
                state['presentation'] = name
                (root / 'broken.pptx').write_text('ошибка')
                path.write_text(json.dumps(state))
                with self.assertRaises(ValueError):
                    check.read_state(path)
            del state['presentation']
            path.write_text(json.dumps(state))
            self.assertEqual(check.read_state(path)['stage'], 'complete')
            state['format_version'] = 2
            path.write_text(json.dumps(state))
            with self.assertRaisesRegex(ValueError, 'presentation'):
                check.read_state(path)

    def test_depth_modes_have_valid_order_and_reproducible_case_files(self):
        spec = json.loads((CASE / 'presentation.json').read_text())
        for mode, expected, filename in (('quick',4,'strategy-quick.pptx'),('standard',6,'decision-brief.pptx'),('deep',len(spec['investment']['pages']),'strategy-deep.pptx')):
            spec['level'] = mode
            output = deck.render(spec)
            self.assertEqual((CASE / filename).read_bytes(), output)
            with ZipFile(io.BytesIO(output)) as archive:
                ids = ET.fromstring(archive.read('ppt/presentation.xml')).findall('{*}sldIdLst/{*}sldId')
                self.assertEqual(len(ids), expected)
                if mode == 'deep':
                    overrides = {n.get('PartName') for n in ET.fromstring(archive.read('[Content_Types].xml')).findall('{*}Override')}
                    for slide in range(7,expected+1):
                        self.assertIn(f'/ppt/slides/slide{slide}.xml', overrides)
                        self.assertIn(f'/ppt/notesSlides/notesSlide{slide}.xml', overrides)
        del spec['investment']
        with ZipFile(io.BytesIO(deck.render(spec))) as legacy:
            ids = ET.fromstring(legacy.read('ppt/presentation.xml')).findall('{*}sldIdLst/{*}sldId')
            self.assertEqual(len(ids),10)
        del spec['appendix']
        with self.assertRaisesRegex(ValueError, 'приложения'):
            deck.render(spec)
