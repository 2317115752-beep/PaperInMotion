from pathlib import Path
import tempfile
import unittest

import pymupdf as fitz

from backend.paper import extract_assets


class PdfFigureTests(unittest.TestCase):
    def test_table_captions_match_the_nearest_aligned_table_on_either_side(self):
        with tempfile.TemporaryDirectory() as temporary, fitz.open() as document:
            folder = Path(temporary)
            (folder/'assets').mkdir()
            page = document.new_page(width=600, height=800)

            def draw_table(left, top, headers):
                for x in (left, left + 60, left + 120):
                    page.draw_line((x, top), (x, top + 104))
                for y in range(top, top + 105, 26):
                    page.draw_line((left, y), (left + 120, y))
                for row, fields in enumerate((headers, ('One', '21'), ('Two', '43'), ('Three', '10'))):
                    for column, field in enumerate(fields):
                        page.insert_text((left + 4 + column * 60, top + 17 + row * 26), field, fontsize=8)

            draw_table(70, 75, ('Baseline', 'Accuracy'))
            draw_table(70, 207, ('Method', 'Validation'))
            draw_table(350, 100, ('Other', 'Column'))
            draw_table(70, 365, ('System', 'Test'))
            page.insert_text((58, 191), 'Table 1. Baseline evaluation.', fontsize=10)
            page.insert_text((58, 323), 'Table 2. Validation evaluation.', fontsize=10)
            page.insert_text((58, 353), 'Table 3. Test evaluation.', fontsize=10)

            tables = extract_assets(page, 1, folder, remaining=3)
            self.assertEqual([asset['caption'].split('.')[0] for asset in tables],
                             ['Table 1', 'Table 2', 'Table 3'])
            self.assertEqual([asset['table']['headers'] for asset in tables],
                             [['Baseline', 'Accuracy'], ['Method', 'Validation'], ['System', 'Test']])
            for asset, top in zip(tables, (75, 207, 365)):
                self.assertAlmostEqual(asset['bbox'][1], top, delta=2)

    def test_composite_figure_preserves_panels_and_labels_inside_its_column(self):
        with tempfile.TemporaryDirectory() as temporary, fitz.open() as document:
            folder = Path(temporary)
            (folder/'assets').mkdir()
            page = document.new_page(width=600, height=800)
            pixel = fitz.Pixmap(fitz.csRGB, 1, 1, bytes((50, 120, 200)), False)

            page.insert_image(fitz.Rect(45, 95, 145, 156), pixmap=pixel, keep_proportion=False)
            page.insert_image(fitz.Rect(166, 102, 198, 129), pixmap=pixel, keep_proportion=False)
            page.insert_image(fitz.Rect(214, 104, 232, 125), pixmap=pixel, keep_proportion=False)
            page.draw_rect(fitz.Rect(245, 101, 277, 128))
            page.insert_text((248, 145), 'Panel D', fontsize=8)
            page.insert_image(fitz.Rect(314, 98, 520, 158), pixmap=pixel, keep_proportion=False)
            page.insert_text((42, 187), 'Fig. 1. Four panels compare the inputs and outputs.', fontsize=9)
            page.insert_text((42, 210), 'A new paragraph starts below the figure.', fontsize=9)

            asset, = extract_assets(page, 1, folder, remaining=1)
            left, top, right, bottom = asset['bbox']
            self.assertLessEqual(left, 45)
            self.assertLessEqual(top, 95)
            self.assertGreaterEqual(right, 277)
            self.assertLess(right, 314)
            self.assertGreaterEqual(bottom, 156)
            self.assertLess(bottom, 173)
            self.assertTrue((folder/asset['file']).is_file())

    def test_grid_of_small_panels_keeps_its_shared_labels(self):
        with tempfile.TemporaryDirectory() as temporary, fitz.open() as document:
            folder = Path(temporary)
            (folder/'assets').mkdir()
            page = document.new_page(width=600, height=800)
            pixel = fitz.Pixmap(fitz.csRGB, 1, 1, bytes((50, 120, 200)), False)
            for top in (98, 133, 168):
                for left in (126, 182, 238, 294, 350, 406):
                    page.insert_image(fitz.Rect(left, top, left + 52, top + 32), pixmap=pixel, keep_proportion=False)
            page.insert_text((129, 213), 'Input Image         Front View         Side View         Input Image'
                             '         Front View         Side View', fontsize=7)
            page.insert_text((125, 245), 'Fig. 2. The first and second set of panels show different examples'
                             ' using the same three kinds of information.', fontsize=7)

            asset, = extract_assets(page, 1, folder, remaining=1)
            left, top, right, bottom = asset['bbox']
            self.assertLessEqual(left, 126)
            self.assertLessEqual(top, 98)
            self.assertGreaterEqual(right, 458)
            self.assertGreaterEqual(bottom, 213)
            self.assertLess(bottom, 235)
