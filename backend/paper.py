"""Extract layout blocks and source-located visual material from a PDF."""
import base64
import re

import pymupdf as fitz

CAPTION = re.compile(r'^\s*(?:fig(?:ure)?\.?|table)\s*\d+\b|^\s*[图表]\s*\d+', re.I)
TABLE_CAPTION = re.compile(
    r'^\s*table\s*\d+\b(?!\s+(?:compares|shows|presents|illustrates|reports|lists|provides|summarizes)\b)'
    r'|^\s*表\s*\d+', re.I,
)
EQUATION = re.compile(r'(?:[=≈≤≥∑∫])')
MAX_ASSETS = 12


def save_crop(page, rect, path, max_size=1500):
    scale = min(max_size / max(rect.width, rect.height), 2.5)
    page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=rect, alpha=False).save(str(path))


def caption_column(bounds, label):
    midpoint = bounds.x0 + bounds.width * .5
    margin = bounds.width * .035
    left, right = bounds.x0 + margin, bounds.x1 - margin
    if label.width < bounds.width * .49:
        if label.x0 >= midpoint - bounds.width * .02:
            left = min(label.x0, midpoint)
        elif label.x1 < midpoint + bounds.width * .04:
            right = max(label.x1, midpoint + bounds.width * .01)
    return left, right


def figure_crop(bounds, label, text_blocks, image_rects, drawing_rects):
    left, right = caption_column(bounds, label)
    column_width = right - left
    preceding = [
        rect.y1 for rect, text in text_blocks
        if rect.y1 <= label.y0 and rect.x1 > label.x0 and rect.x0 < label.x1
        and (CAPTION.match(text) or (len(text) >= 100 and rect.width >= column_width * .32)
             or (rect.y1 < bounds.y0 + bounds.height * .14 and rect.height < 15
                 and re.search(r'^(?:\d{1,3}\s+)|(?:\s+\d{1,3})$', text)))
    ]
    top = max([bounds.y0, label.y0 - bounds.height * .67] + preceding)
    images = [rect for rect in image_rects if rect.y0 >= top and rect.y1 <= label.y0 + 1]
    anchors = [
        rect for rect in images if rect.width >= 55 and rect.height >= 40
        and label.y0 - rect.y1 <= 145 and rect.x1 > label.x0 and rect.x0 < label.x1
    ]
    # The caption limits neighboring panels. An aligned full-width image may itself
    # extend beyond that footprint when the caption is only one line long.
    left = min([left] + [rect.x0 for rect in anchors])
    right = max([right] + [rect.x1 for rect in anchors])
    components = [
        rect for rect in images + drawing_rects
        if rect.y0 >= top and rect.y1 <= label.y0 + 1 and rect.x0 >= left - 4 and rect.x1 <= right + 4
    ]
    if not anchors and components:
        anchor = max(components, key=lambda rect: rect.y1)
        if label.y0 - anchor.y1 <= 75:
            anchors = [anchor]
    if anchors:
        crop = fitz.Rect(max(anchors, key=lambda rect: rect.y1))
        gap = 35
        while True:
            vicinity = crop + (-gap, -gap, gap, gap)
            expanded = fitz.Rect(crop)
            for part in components:
                if vicinity.intersects(part):
                    expanded.include_rect(part)
            if expanded == crop:
                break
            crop = expanded
        if crop.width >= 55 and crop.height >= 40:
            # Keep short panel labels beside a graphic while excluding prose and captions.
            label_area = crop + (-12, -9, 12, 20)
            for rect, text in text_blocks:
                if (top <= rect.y0 and rect.y1 < label.y0 and len(text) < 100
                        and not CAPTION.match(text) and rect.x0 >= left and rect.x1 <= right
                        and (rect.width < column_width * .4 or (rect.height <= 24
                            and rect.x0 >= crop.x0 - 5 and rect.x1 <= crop.x1 + 5))
                        and label_area.intersects(rect)):
                    crop.include_rect(rect)
            return (crop + (-2, -2, 2, 2)) & fitz.Rect(left - 4, top, right + 4, label.y0 - 1)

    # Captions next to figures drawn as text can still use the intervening column.
    return fitz.Rect(left, max(top, label.y0 - 220) + 3, right, label.y0 - 2)


def horizontal_overlap(first, second):
    return min(first.x1, second.x1) - max(first.x0, second.x0)


def aligned_columns(first, second):
    return horizontal_overlap(first, second) >= min(first.width, second.width) * .6


def vertical_gap(first, second):
    return max(first.y0 - second.y1, second.y0 - first.y1)


def match_tables(tables, captions, bounds):
    pairs = []
    candidates = []
    for table in tables:
        rect = fitz.Rect(table.bbox) & bounds
        if rect.width < 55 or rect.height < 40 or rect.get_area() > bounds.get_area() * .85:
            continue
        cells = table.extract()
        if sum(sum(bool(cell and cell.strip()) for cell in row) >= 2 for row in cells) >= 2:
            candidates.append((rect, cells))
    for label_index, (label, caption) in enumerate(captions):
        if not TABLE_CAPTION.match(caption):
            continue
        for table_index, (rect, _cells) in enumerate(candidates):
            if not aligned_columns(rect, label):
                continue
            gap = vertical_gap(rect, label)
            if not -2 <= gap <= 60:
                continue
            between_top = min(rect.y1, label.y1)
            between_bottom = max(rect.y0, label.y0)
            if any(between_top <= other.y0 and other.y1 <= between_bottom
                   and aligned_columns(rect, other)
                   for other, _ in captions):
                continue
            if any(not TABLE_CAPTION.match(text) and aligned_columns(rect, other)
                   and vertical_gap(rect, other) < gap
                   for other, text in captions):
                continue
            center_offset = abs(rect.x0 + rect.x1 - label.x0 - label.x1)
            pairs.append((max(0, gap), center_offset, label_index, table_index))
    matches, used_tables = {}, set()
    # Pair the closest edges first and only assign each grid once.
    for _, _, label_index, table_index in sorted(pairs):
        if label_index not in matches and table_index not in used_tables:
            matches[label_index] = candidates[table_index]
            used_tables.add(table_index)
    return matches


def extract_assets(page, number, folder, remaining):
    if remaining <= 0:
        return []
    bounds = page.rect
    text_blocks = [(fitz.Rect(block[:4]), ' '.join(block[4].split()))
                   for block in page.get_text('blocks', sort=True) if block[6] == 0]
    captions = [(label, text) for label, text in text_blocks
                if CAPTION.match(text) and len(text) <= 550 and label.width >= 35
                and (not text.lower().startswith(('table', '表')) or TABLE_CAPTION.match(text))]
    has_tables = any(TABLE_CAPTION.match(text) for _, text in captions)
    table_matches = match_tables(page.find_tables().tables, captions, bounds) if has_tables else {}
    image_rects = []
    drawing_rects = []
    graphics_loaded = False
    assets = []
    for index, (label, caption) in enumerate(captions):
        is_table = bool(TABLE_CAPTION.match(caption))
        if not is_table:
            if not graphics_loaded:
                image_rects = [fitz.Rect(item['bbox']) for item in page.get_image_info()]
                image_rects = [rect for rect in image_rects if rect.width >= 8 and rect.height >= 6]
                drawing_rects = [item['rect'] for item in page.get_drawings(extended=False)]
                # Horizontal or vertical connectors can have zero area in a PDF.
                drawing_rects = [rect + (-1, -1, 1, 1) for rect in drawing_rects if max(rect.width, rect.height) >= 8]
                graphics_loaded = True
            rect = figure_crop(bounds, label, text_blocks, image_rects, drawing_rects)
        else:
            if index not in table_matches:
                continue
            rect, cells = table_matches[index]
        rect = rect & bounds
        if rect.width < 55 or rect.height < 40 or rect.get_area() > bounds.get_area() * .85:
            continue
        kind = 'table' if is_table else 'figure'
        visual_id = f'p{number}-{kind}{len(assets)+1}'
        filename = f'assets/{visual_id}.png'
        save_crop(page, rect, folder/filename)
        asset = {'id': visual_id, 'kind': kind, 'caption': caption, 'bbox': list(rect), 'file': filename}
        if is_table:
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
