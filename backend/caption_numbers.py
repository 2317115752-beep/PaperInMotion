"""Format spoken Chinese quantities for display in subtitles."""
import re

DIGITS = dict(zip('零〇一二两三四五六七八九', '001223456789'))
SMALL_UNITS = {'十': 10, '百': 100, '千': 1000}
LARGE_UNITS = {'万': 10_000, '亿': 100_000_000}
DIGIT_CHARS = ''.join(DIGITS)
INTEGER_CHARS = DIGIT_CHARS + '十百千万亿'
INTEGER = rf'[{INTEGER_CHARS}]+'
DECIMAL = rf'(?:{INTEGER}|[0-9]+)点[{DIGIT_CHARS}0-9]+'
SIGN = r'(?:[−+-]|(?<![担背肩辜自])负)?'
NUMBER = rf'{SIGN}(?:{DECIMAL}|{INTEGER}|[0-9]+(?:\.[0-9]+)?)'
BOUNDARY = rf'(?![{INTEGER_CHARS}0-9.])'

# Small-unit groups are evaluated from high to low. A missing digit at the
# end of a hundreds/thousands group is ambiguous without an explicit 零.
def integer_value(text):
    if len(text) > 32:
        return None
    if text.isascii() and text.isdigit():
        return int(text)
    if all(c in DIGITS for c in text):
        return int(''.join(DIGITS[c] for c in text))

    total, group, digit = 0, 0, None
    small_limit, large_limit = 10_000, float('inf')
    zero = False
    for index, char in enumerate(text):
        if char in DIGITS:
            if digit is not None:
                return None
            digit = int(DIGITS[char])
            zero = digit == 0 or zero
            if digit == 0:
                digit = None
        elif char in SMALL_UNITS:
            unit = SMALL_UNITS[char]
            if unit >= small_limit or (digit is None and not (unit == 10 and index == 0)):
                return None
            group += (digit if digit is not None else 1) * unit
            small_limit, digit, zero = unit, None, False
        else:
            unit = LARGE_UNITS[char]
            value = group + (digit or 0)
            if unit >= large_limit or not value or (digit is not None and 10 < small_limit < 10_000 and not zero):
                return None
            total += value * unit
            large_limit, small_limit, group, digit, zero = unit, 10_000, 0, None, False
    if digit is not None and not zero and (10 < small_limit < 10_000 or total and not group):
        return None
    return total + group + (digit or 0)


def display_number(text):
    sign = {'负': '−', '-': '−', '−': '−', '+': '+'}.get(text[0], '')
    value = text[1:] if sign else text
    if re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', value):
        return sign + value
    whole, point, decimal = value.partition('点')
    number = integer_value(whole)
    if number is None:
        return None
    fraction = ''.join(DIGITS.get(c, c) for c in decimal)
    return sign + str(number) + ('.' + fraction if point else '')


def replace_numbers(text, pattern, replacement):
    def format_match(match):
        numbers = [display_number(value) for value in match.groups()]
        return replacement(*numbers) if all(number is not None for number in numbers) else match[0]
    return re.sub(pattern, format_match, text)


def format_math_numbers(text):
    # Match mathematical phrases before individual measurements and decimals.
    text = replace_numbers(text, rf'百分之({NUMBER}){BOUNDARY}', lambda n: n + '%')
    text = replace_numbers(text, rf'({NUMBER})分之({NUMBER}){BOUNDARY}', lambda d, n: f'{n}/{d}')
    text = replace_numbers(text, rf'({NUMBER})\s*乘(?:以)?\s*({NUMBER}){BOUNDARY}(?!方)', lambda a, b: f'{a}×{b}')
    text = replace_numbers(text, rf'(?<![{INTEGER_CHARS}])({SIGN}{DECIMAL}){BOUNDARY}', lambda n: n)
    text = replace_numbers(
        text, rf'(?<![A-Za-z0-9.])({NUMBER})(?=毫米|厘米|微米|纳米|千米|米[。，、；）]|毫秒|微秒|秒|像素|赫兹|个分量|倍|次方)',
        lambda n: n,
    )
    text = replace_numbers(
        text, rf'(?<![{INTEGER_CHARS}0-9.])({SIGN}[0-9]+(?:\.[0-9]+)?|负{INTEGER}|[零〇二三四五六七八九十][{INTEGER_CHARS}]*|一[{INTEGER_CHARS}]+)度(?!量|数)',
        lambda n: f'{n}°',
    )
    text = replace_numbers(
        text, rf'(?<![A-Za-z0-9.{INTEGER_CHARS}])({INTEGER}|[0-9]+)维'
              r'(?=数组|向量|矩阵|空间|数据|张量|点|关键点|关节|重投影|特征|图像|模型|坐标)',
        lambda n: f'{n}D ',
    )
    for name in ('公式', '方程', '图', '表'):
        text = replace_numbers(
            text, rf'{name}({INTEGER})(?=$|[（(。，、；：中把将给可得所用的修])',
            lambda n: f'{name}{n}',
        )
    text = replace_numbers(
        text, rf'输出({NUMBER})和({NUMBER})(?=的结果|[。，；：])', lambda a, b: f'输出{a}和{b}',
    )
    for operator, symbol in (('加上?', '+'), ('减去?', '−'), ('除以', '÷')):
        text = replace_numbers(
            text, rf'({NUMBER}){operator}({NUMBER}){BOUNDARY}', lambda a, b: f'{a}{symbol}{b}',
        )
    for verb in ('等于', '约为', '降到', '降至', '升到', '升至', '结果是'):
        text = replace_numbers(
            text, rf'{verb}({NUMBER})(?=$|[。，“”！？、；：）]|时)',
            lambda n: f'{verb}{n}',
        )
    return text
