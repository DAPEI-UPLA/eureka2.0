"""Helpers compartidos por views y templatetags de planificacion."""
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.core.exceptions import PermissionDenied


# =============================================================
# PERMISOS
# =============================================================

def es_planificacion(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name="Planificacion").exists()


def planificacion_required(view_func):
    """Decorador: exige login + grupo Planificacion (o superuser)."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.shortcuts import redirect
            return redirect("login")
        if not es_planificacion(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapper


def get_user_role(request):
    """Devuelve dict con flags útiles, cacheado por request."""
    cache_key = "_planificacion_role"
    if hasattr(request, cache_key):
        return getattr(request, cache_key)

    user = request.user
    role = {
        "es_planificacion": es_planificacion(user),
        "es_anonimo": not user.is_authenticated,
    }
    setattr(request, cache_key, role)
    return role


# =============================================================
# DECIMAL UTILS
# =============================================================

def parse_decimal(raw):
    """Convierte un string (formato cl o estándar) a Decimal o None."""
    if raw is None:
        return None
    if isinstance(raw, Decimal):
        return raw
    txt = str(raw).strip()
    if not txt:
        return None
    txt = txt.replace(".", "").replace(",", ".") if txt.count(",") == 1 and txt.count(".") > 1 \
        else txt.replace(",", ".")
    try:
        return Decimal(txt)
    except InvalidOperation:
        return None


# =============================================================
# CÁLCULO DE AVANCE
# =============================================================

def calcular_avance(valor, meta, calculo_invertido=False):
    """Devuelve el % de avance, sin tope superior, o None.

    Reglas:
      - meta = 0  -> None (no es divisible).
      - valor = 0 -> 0% (rojo), también en cálculo invertido.
      - normal:    (valor/meta) * 100
      - invertido: (meta/valor) * 100
    """
    if valor is None or meta is None:
        return None
    try:
        v = Decimal(str(valor))
        m = Decimal(str(meta))
    except InvalidOperation:
        return None

    if m == 0:
        return None

    if v == 0:
        return 0.0

    if calculo_invertido:
        ratio = (m / v) * Decimal(100)
    else:
        ratio = (v / m) * Decimal(100)

    pct = float(ratio)
    return max(0.0, pct)


def color_avance(avance):
    """Devuelve clase CSS según umbrales 0-69, 70-89, 90+ (porcentaje)."""
    if avance is None:
        return "neutro"
    if avance < 70:
        return "rojo"
    if avance < 90:
        return "amarillo"
    return "verde"


def hex_color_avance(avance):
    if avance is None:
        return "#9ca3af"
    if avance < 70:
        return "#ef4444"
    if avance < 90:
        return "#f59e0b"
    return "#16a34a"


def acumular_valores(seguimientos_qs, hasta_anio, hasta_semestre):
    """Suma valores de seguimientos hasta el (año, semestre) dado, inclusive."""
    total = Decimal(0)
    for s in seguimientos_qs:
        if s.anio < hasta_anio or (s.anio == hasta_anio and s.semestre <= hasta_semestre):
            if s.valor is not None:
                total += s.valor
    return total


def avance_indicador(programa_indicador, anio, semestre, hasta_acumulado=False):
    """
    Calcula avance para un (programa_indicador, anio, semestre).
    Si el indicador es acumulativo, suma los valores hasta el período pedido.
    Retorna dict: {valor, meta, avance, color, estado_medicion, estado_meta, valor_display, meta_display}.
    """
    indicador = programa_indicador.indicador

    seguimientos = list(programa_indicador.seguimientos.all())
    actual = next(
        (s for s in seguimientos if s.anio == anio and s.semestre == semestre),
        None,
    )

    estado_medicion = "VALOR"
    valor_display = None

    if actual is not None:
        estado_medicion = actual.estado
        if actual.estado == "SM":
            valor_display = "S/M"
        elif actual.estado == "NA":
            valor_display = "N/A"
        else:
            valor_display = actual.valor

    if indicador.acumulativo:
        # Solo suma valores numéricos válidos
        numericos = [s for s in seguimientos if s.estado == "VALOR" and s.valor is not None]
        valor = acumular_valores(numericos, anio, semestre)
        if valor == 0 and actual is None:
            valor = None
    else:
        valor = actual.valor if (actual and actual.estado == "VALOR") else None

    meta_info = programa_indicador.meta_para(anio)
    meta_estado = meta_info.get("estado", "VALOR")
    meta_valor = meta_info.get("valor")
    meta_display = meta_info.get("display")
    if meta_estado == "SM":
        meta_display = "S/M"
    elif meta_estado == "NA":
        meta_display = "N/A"

    # No calcular avance si meta o valor están en estado especial
    if estado_medicion != "VALOR" or meta_estado != "VALOR":
        avance = None
    else:
        avance = calcular_avance(valor, meta_valor, indicador.calculo_invertido)

    return {
        "seguimiento": actual,
        "valor": valor,
        "valor_display": valor_display,
        "estado_medicion": estado_medicion,
        "meta": meta_valor,
        "meta_display": meta_display,
        "estado_meta": meta_estado,
        "avance": avance,
        "color": color_avance(avance),
        "color_hex": hex_color_avance(avance),
    }


def avance_global_ponderado(items):
    """items = lista de dicts con 'avance' y 'peso' Decimal."""
    suma_pesos = Decimal(0)
    suma_ponderada = Decimal(0)
    for it in items:
        if it.get("avance") is None:
            continue
        peso = it.get("peso") or Decimal(1)
        suma_pesos += peso
        suma_ponderada += Decimal(str(it["avance"])) * peso
    if suma_pesos == 0:
        return None
    return float(suma_ponderada / suma_pesos)


def score_color(color):
    """Verde=1, amarillo=0.7, rojo=0. Neutro/sin datos = None (se excluye)."""
    if color == "verde":
        return Decimal("1.0")
    if color == "amarillo":
        return Decimal("0.7")
    if color == "rojo":
        return Decimal("0.0")
    return None


def grado_cumplimiento_plan(items):
    """
    Calcula grado de cumplimiento del plan según la regla institucional:
        Cálculo_i = peso_i * score_i  (verde=1, amarillo=0.7, rojo=0)
        Grado     = Σ Cálculo_i / Σ peso_i  * 100

    Los indicadores en S/M (Sin Medición) o sin meta NO se incluyen ni
    en el numerador ni en el denominador — coincide con la planilla
    institucional, que descuenta esos pesos del total cuando un
    indicador no aplica al período.

    items: lista de dicts con 'color' y 'peso' (Decimal).
    """
    suma_calculo = Decimal(0)
    suma_pesos = Decimal(0)
    for it in items:
        score = score_color(it.get("color"))
        if score is None:
            continue
        peso = it.get("peso") or Decimal(1)
        suma_calculo += peso * score
        suma_pesos += peso
    if suma_pesos == 0:
        return None
    return float(suma_calculo / suma_pesos * Decimal(100))


# =============================================================
# AÑO / SEMESTRE
# =============================================================

DEFAULT_ANIOS = list(range(2024, 2031))


def _safe_int(raw, default):
    """int() tolerando espacios, NBSP y separadores de miles."""
    if raw is None:
        return default
    txt = str(raw).strip().replace("\xa0", "").replace(" ", "").replace(".", "").replace(",", "")
    if not txt:
        return default
    try:
        return int(txt)
    except ValueError:
        return default


def parse_anio_semestre(request, default_anio=None, default_sem=2):
    anio = _safe_int(request.GET.get("anio"), default_anio or DEFAULT_ANIOS[0])
    sem = _safe_int(request.GET.get("semestre"), default_sem)
    if sem not in (1, 2):
        sem = default_sem
    return anio, sem
