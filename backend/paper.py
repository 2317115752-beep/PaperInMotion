"""Extract layout blocks and source-located visual material from a PDF."""
import base64
import re

import pymupdf as fitz

CAPTION = re.compile(r'^\s*(?:fig(?:ure)?\.?|table)\s*\d+\b|^\s*[图表]\s*\d+', re.I)
EQUATION = re.compile(r'(?:[=≈≤≥∑∫])')
MAX_ASSETS = 12


def save_crop(page, rect, path, max_size=1500):
    scale = min(max_size / max(rect.width, rect.height), 2.5)
    page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=rect, alpha=False).save(str(path))


def extract_assets(page, number, folder, remaining):
    if remaining <= 0:
        return []
    bounds = page.rect
    blocks = page.get_text('blocks', sort=True)
    image_rects = [fitz.Rect(item['bbox']) for item in page.get_image_info()
                   if (item['bbox'][2] - item['bbox'][0]) >= 55 and (item['bbox'][3] - item['bbox'][1]) >= 45]
    assets = []
    for block in blocks:
        caption = ' '.join(block[4].split())
        if not CAPTION.match(caption):
            continue
        label = fitz.Rect(block[:4])
        if len(caption) > 550 or label.width < 35:
            continue
        is_table = caption.lower().startswith(('table', '表'))
        if not is_table:
            nearby = [r for r in image_rects if abs(r.y1 - label.y0) < 145 and r.x1 > label.x0 and r.x0 < label.x1]
            if nearby:
                rect = fitz.Rect(nearby[0])
                for part in nearby[1:]:
                    rect.include_rect(part)
            else:
                preceding = [fitz.Rect(b[:4]) for b in blocks if fitz.Rect(b[:4]).y1 < label.y0 - 30
                             and fitz.Rect(b[:4]).x1 > label.x0 and fitz.Rect(b[:4]).x0 < label.x1]
                top = max([b.y1 for b in preceding] + [label.y0 - 220])
                margins = (.035 * bounds.width, bounds.width * .035)
                # Preserve the whole column even when the caption occupies only one short line.
                single_column = label.width < bounds.width * .49 and (
                    label.x0 >= bounds.width * .48 or label.x1 < bounds.width * .54)
                left = bounds.width * .5 if single_column and label.x0 >= bounds.width * .48 else margins[0]
                right = (bounds.width * .51 if single_column and left == margins[0] else bounds.width - margins[1])
                rect = fitz.Rect(left, max(bounds.y0, top + 3), right, label.y0 - 2)
        else:
            table_candidates = [table for table in page.find_tables().tables
                                if abs(table.bbox[1] - label.y1) < 150]
            if not table_candidates:
                continue
            table = min(table_candidates, key=lambda item: abs(item.bbox[1] - label.y1))
            rect = fitz.Rect(table.bbox)
        rect = rect & bounds
        if rect.width < 55 or rect.height < 40 or rect.get_area() > bounds.get_area() * .85:
            continue
        kind = 'table' if is_table else 'figure'
        visual_id = f'p{number}-{kind}{len(assets)+1}'
        filename = f'assets/{visual_id}.png'
        save_crop(page, rect, folder/filename)
        asset = {'id': visual_id, 'kind': kind, 'caption': caption, 'bbox': list(rect), 'file': filename}
        if is_table:
            cells = table.extract()
            if 2 <= len(cells) <= 10 and 2 <= len(cells[0]) <= 5:
                asset['table'] = {'headers': [str(cell or '')[:50] for cell in cells[0]],
                                  'rows': [[str(cell or '')[:65] for cell in row] for row in cells[1:]]}
        assets.append(asset)
        if len(assets) >= remaining:
            break
    return assets


def read_document(path, folder=None, *, name='Paper', page_offset=0, max_images=4):
    pages, images, warnings = [], [], []
    if folder:
        (folder/'assets').mkdir(exist_ok=True)
    with fitz.open(path) as doc:
        if not doc.is_pdf or doc.needs_pass:
            raise ValueError('Upload an unencrypted PDF.')
        if not 1 <= len(doc) <= 80:
            raise ValueError('Each PDF must have 1–80 pages.')
        remaining, assets_left, candidates = 100_000, MAX_ASSETS, []
        for index, page in enumerate(doc):
            number = index + 1 + page_offset
            # Layout blocks preserve reading units. Plain extraction preserves column order
            # on authored scientific PDFs where sorting by rows would interleave columns.
            text = page.get_text('text').strip()[:min(12_000, remaining)]
            assets = extract_assets(page, number, folder, assets_left) if folder else []
            assets_left -= len(assets)
            equations = []
            for block in page.get_text('blocks'):
                line = ' '.join(block[4].split())
                if 4 <= len(line) <= 160 and EQUATION.search(line) and len(equations) < 5:
                    equations.append({'text': line, 'bbox': list(block[:4])})
            if text or assets:
                pages.append({'page': number, 'text': text, 'document': name, 'physical_page': index + 1,
                              'assets': assets, 'equations': equations})
            remaining -= len(text)
            if index == 0 or assets or re.search(r'figure|architecture|framework|图\s*\d', text, re.I):
                candidates.append((0 if assets else 1, index, number))
            if remaining <= 0:
                warnings.append(f'{name}: text truncated at 100,000 characters.')
                break
        if sum(len(p['text']) for p in pages) < 200 and page_offset == 0:
            raise ValueError('Too little selectable text. Upload a text-based PDF.')
        for _, index, number in sorted(candidates)[:max_images]:
            page = doc[index]
            scale = min(1200 / max(page.rect.width, page.rect.height), 2)
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            images.append({'page': number, 'data': base64.b64encode(pix.tobytes('png')).decode()})
    return pages, images, warnings
