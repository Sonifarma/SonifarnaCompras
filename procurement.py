"""Conservative buying rules shared by comparison, selection and drafts."""
import calendar
from datetime import date, datetime
import math
import re
import unicodedata
from zoneinfo import ZoneInfo


def normalize(value):
    value = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode().upper()
    return re.sub(r'[^A-Z0-9]+', ' ', value).strip()


def today():
    return datetime.now(ZoneInfo('America/Sao_Paulo')).date()


def parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    value = str(value or '').strip()
    for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d %H:%M:%S', '%m/%Y', '%Y-%m']:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def is_capsule(product):
    return bool(re.search(r'CAPSUL|\bCAPS?\b|VCAPS|DRCAPS|TAPIOCAPS', normalize(product)))


def unit(value, product=''):
    value = normalize(value)
    if value in {'G', 'GR', 'GRAMA', 'GRAMAS'}:
        return 'g', 1
    if value in {'KG', 'QUILO', 'QUILOS', 'QUILOGRAMA', 'QUILOGRAMAS'}:
        return 'g', 1000
    if value in {'MG', 'MILIGRAMA', 'MILIGRAMAS'}:
        return 'g', .001
    if value in {'MIL', 'MILH', 'MI', 'MH', 'MILHEIRO', 'MILHEIROS', '1000 UN', '1000 UNIDADES'}:
        return 'milheiro', 1
    if value in {'CAP', 'CAPS', 'CAPSULA', 'CAPSULAS'}:
        return 'milheiro', .001
    if value in {'UN', 'UND', 'UNID', 'UNIDADE', 'UNIDADES'} and is_capsule(product):
        return 'milheiro', .001
    return None, None


def positive(value):
    return isinstance(value, (int, float)) and math.isfinite(value) and value > 0


def evaluate(need, quote, delivery=None):
    delivery = parse_date(delivery) or today()
    cutoff = date(delivery.year + 1, delivery.month,
                  min(delivery.day, calendar.monthrange(delivery.year + 1, delivery.month)[1]))
    warnings = []
    if quote.get('import_warning'):warnings.append('Conferir extração: '+quote['import_warning'])
    name = need.get('name', '')
    base, factor = unit(need.get('unit'), name)
    quote_base, quote_factor = unit(quote.get('base_unit'), quote.get('product', name))
    if is_capsule(name) and base != 'milheiro':
        warnings.append('Cápsulas exigem quantidade em milheiros ou unidades contáveis')
    qty = need.get('qty')
    quantity = qty * factor if positive(qty) and factor else None
    cost = quote.get('unit_cost')
    price = cost / quote_factor if isinstance(cost, (float, int)) and math.isfinite(cost) and cost >= 0 and quote_factor else None
    if not base or quote_base != base or quantity is None or price is None:
        warnings.append('Quantidade, preço ou unidade sem conversão segura (g ou milheiro)')
        price = None
    pack_qty = quote.get('base_qty')
    package = pack_qty * quote_factor if positive(pack_qty) and quote_factor else None
    # Parse only simple quantities, never infer a pack from ambiguous multi-pack text.
    match = re.fullmatch(r'\s*(\d+(?:[.,]\d+)?)\s*([A-Za-zÀ-ÿ]+)\s*', str(quote.get('pack') or ''))
    if package is None and match:
        parsed_base, parsed_factor = unit(match[2], quote.get('product', name))
        if parsed_base == base:
            package = float(match[1].replace(',', '.')) * parsed_factor
    if not positive(package):
        package = None
        warnings.append('Quantidade da embalagem não informada')
    expiry = parse_date(quote.get('expiry'))
    if expiry is None:
        warnings.append('Validade não informada ou não reconhecida')
    elif expiry <= cutoff:
        warnings.append('Validade não supera 1 ano na entrega prevista')
    previous_base, previous_factor = unit(need.get('last_pack_unit'), name)
    previous = need.get('last_pack_qty')
    previous = previous * previous_factor if positive(previous) and previous_factor and previous_base == base else None
    ratio = package / previous if package and previous else None
    if previous is None:
        warnings.append('Embalagem da última compra não informada')
    elif ratio and ratio > 1 + 1e-9:
        warnings.append(f'Embalagem {ratio:.2f} vezes a última compra — exige aprovação')
    packs = max(1, math.ceil(quantity / package - 1e-10)) if quantity and package and price is not None else None
    purchased = packs * package if packs else None
    spend = round(purchased * price, 2) if purchased is not None else None
    surplus = round(max(0, purchased - quantity), 6) if purchased is not None else None
    return {'unit': base, 'quantity': quantity, 'unit_price': price, 'package_qty': package,
            'last_package_qty': previous, 'package_ratio': ratio, 'packages': packs,
            'purchase_qty': purchased, 'surplus_qty': surplus, 'purchase_total': spend,
            'expiry_date': expiry.isoformat() if expiry else None, 'expiry_after': cutoff.isoformat(),
            'warnings': warnings, 'eligible': not warnings}


def commercial(subtotal, terms, pending=0):
    minimum = terms.get('minimum_order', 700)
    threshold = terms.get('free_shipping_from', 2000)
    confirmed = bool(terms.get('confirmed', False))
    free = subtotal >= threshold
    freight = 0 if free else terms.get('freight')
    return {**terms, 'minimum_order': minimum, 'free_shipping_from': threshold,
            'confirmed': confirmed, 'subtotal': round(subtotal, 2),
            'missing_minimum': round(max(0, minimum - subtotal), 2),
            'missing_free_shipping': round(max(0, threshold - subtotal), 2),
            'free_shipping': free, 'freight_applied': freight,
            'landed_total': round(subtotal + freight, 2) if freight is not None and confirmed else None,
            'ready': confirmed and pending == 0 and subtotal >= minimum and freight is not None}
