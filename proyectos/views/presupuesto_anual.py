"""Reparto del presupuesto del proyecto por año calendario.

Un proyecto de 36 meses no tiene un presupuesto, tiene tres: uno por año, que
es como se transfiere y como se rinde. Estas vistas son el CRUD de ese reparto
y el selector que filtra el detalle del proyecto por año.

Sigue el patrón HTMX del resto del módulo: cada mutación devuelve la lista
completa ya repintada y publica `estructuraActualizada` para que el dashboard y
los gráficos se enteren.
"""

from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from ..models import PresupuestoAnual, Proyecto
from ..numeros import pesos
from .permisos import es_jefe, usuario_es_responsable
from .utils import _to_decimal, disparar


def _puede_editar(user, proyecto):
    """El reparto anual lo carga el equipo del proyecto; la jefatura también.

    Es plata del proyecto, no de un objetivo, así que no basta con ser
    responsable de una parte: o llevas el proyecto o llevas la cartera.
    """
    return usuario_es_responsable(user, proyecto) or es_jefe(user)


def _contexto(proyecto, user, filas_en_pantalla=None, **extra):
    contexto = {
        "proyecto": proyecto,
        # Tras un error se repintan los montos que se escribieron, no los
        # guardados: ver el error junto a las cifras viejas hace pensar que se
        # está hablando de otra cosa.
        "anios": filas_en_pantalla if filas_en_pantalla is not None
        else proyecto.presupuestos_anuales.all(),
        "puede_editar": _puede_editar(user, proyecto),
    }
    contexto.update(extra)
    return contexto


def _responder(request, proyecto, **extra):
    return render(
        request,
        "proyectos/partials/presupuesto_anual.html",
        _contexto(proyecto, request.user, **extra),
    )


@login_required
def listar_presupuesto_anual(request, pk):
    proyecto = get_object_or_404(Proyecto, pk=pk)
    return _responder(request, proyecto)


@login_required
@require_POST
def crear_anio(request, pk):
    """Agrega el año siguiente al último cargado, en cero.

    Se crea vacío a propósito: el monto lo sabe el equipo del proyecto y
    proponerle una cifra repartida en partes iguales sólo lograría que la
    aceptara sin mirarla.
    """
    proyecto = get_object_or_404(Proyecto, pk=pk)
    if not _puede_editar(request.user, proyecto):
        return HttpResponseForbidden("No autorizado")

    agregados = proyecto.presupuestos_anuales.aggregate(
        n=Max("numero_anio"), c=Max("anio_calendario")
    )
    siguiente = (agregados["n"] or 0) + 1
    calendario = (
        agregados["c"] + 1 if agregados["c"] else proyecto.anio_calendario_inicial
    )

    anio = PresupuestoAnual(
        proyecto=proyecto,
        numero_anio=siguiente,
        anio_calendario=calendario,
        creado_por=request.user,
    )
    try:
        anio.full_clean()
        anio.save()
    except ValidationError as error:
        return _responder(request, proyecto, error=" ".join(
            m for msgs in error.message_dict.values() for m in msgs
        ))

    response = _responder(request, proyecto, nuevo_anio_id=anio.pk)
    return disparar(response, estructuraActualizada=True,
                    guardado=f"Año {siguiente} agregado ({calendario}).")


@login_required
@require_POST
def crear_anios_del_proyecto(request, pk):
    """Crea de una vez todos los años que le faltan al proyecto.

    Los años salen del «Año 1» que declaró quien creó el proyecto más su
    duración, no de `fecha_inicio`: el año en que llega el proyecto puede no
    ser el primero de ejecución. Sin ese dato no se propone nada, porque
    cualquier año de partida que el sistema invente se vería tan legítimo como
    uno declarado.

    Se crean en cero, igual que uno a uno: el monto lo sabe el equipo, y
    repartir en partes iguales sólo lograría que aceptaran la cifra sin mirarla.
    """
    proyecto = get_object_or_404(Proyecto, pk=pk)
    if not _puede_editar(request.user, proyecto):
        return HttpResponseForbidden("No autorizado")

    if not proyecto.anio_inicial:
        return _responder(request, proyecto, error=(
            "Para crear los años de una vez hace falta el «Año 1 del "
            "presupuesto». Cárgalo editando el proyecto."
        ))

    faltantes = proyecto.anios_faltantes
    if not faltantes:
        return _responder(request, proyecto, error=(
            f"El proyecto ya tiene sus "
            f"{proyecto.cantidad_anios_sugerida} año(s) cargados."
        ))

    siguiente = (proyecto.presupuestos_anuales.aggregate(
        n=Max("numero_anio"))["n"] or 0) + 1

    with transaction.atomic():
        for calendario in faltantes:
            anio = PresupuestoAnual(
                proyecto=proyecto,
                numero_anio=siguiente,
                anio_calendario=calendario,
                creado_por=request.user,
            )
            anio.full_clean()
            anio.save()
            siguiente += 1

    response = _responder(request, proyecto)
    return disparar(response, estructuraActualizada=True, guardado=(
        f"{len(faltantes)} año(s) creados: "
        f"{', '.join(str(a) for a in faltantes)}."
    ))


@login_required
@require_POST
def realinear_anios(request, pk):
    """Corrige el año calendario de los años ya cargados.

    Los proyectos creados antes de que el formulario pidiera el «Año 1»
    quedaron con el año en curso: un proyecto de 2024 tiene «Año 1 → 2026».
    Esto los mueve a donde corresponde.

    Se niega si algún año tiene planes de gasto. `PlanDeGasto.anio` es un año
    calendario suelto, así que mover un `PresupuestoAnual` de 2026 a 2024 no
    arrastra su POA: lo dejaría respaldando un año que ya no existe. Antes de
    realinear hay que mover esos planes a mano, que es una decisión del equipo.
    """
    proyecto = get_object_or_404(Proyecto, pk=pk)
    if not _puede_editar(request.user, proyecto):
        return HttpResponseForbidden("No autorizado")

    if not proyecto.anio_inicial:
        return _responder(request, proyecto, error=(
            "Falta el «Año 1 del presupuesto» para saber a qué años mover."
        ))

    con_poa = proyecto.anios_con_poa
    if con_poa:
        detalle = ", ".join(
            f"{a.anio_calendario} ({pesos(a.planificado)})" for a in con_poa
        )
        return _responder(request, proyecto, error=(
            f"No se puede realinear: {detalle} ya tiene planes de gasto. "
            f"Muévelos de año primero, o corrige los años uno a uno."
        ))

    filas = list(proyecto.presupuestos_anuales.order_by("numero_anio"))
    destinos = proyecto.anios_calendario_esperados[:len(filas)]

    with transaction.atomic():
        # Dos pasadas: el año calendario es único por proyecto, así que mover
        # 2026->2027 mientras 2027 todavía existe rompe la restricción. Se
        # apartan todos a un rango imposible y recién ahí se colocan.
        for indice, fila in enumerate(filas):
            fila.anio_calendario = 9000 + indice
            fila.save(update_fields=["anio_calendario"])
        for fila, destino in zip(filas, destinos):
            fila.anio_calendario = destino
            fila.actualizado_por = request.user
            fila.save(update_fields=[
                "anio_calendario", "actualizado_por", "actualizado_en"])

    response = _responder(request, proyecto)
    return disparar(response, estructuraActualizada=True, guardado=(
        f"Años realineados: {', '.join(str(a) for a in destinos)}."
    ))


def _validar_el_reparto(proyecto, filas):
    """Comprueba el reparto completo de una vez y devuelve los errores.

    No se usa `full_clean()` de cada fila porque cada una se valida contra sus
    hermanas **tal como están guardadas**, y eso hace imposible redistribuir:
    para pasar de «todo en el año 1» a «mitad y mitad» hay que bajar el año 1 y
    subir el año 2, y cualquiera de los dos pasos por separado es inválido. Al
    mirar el conjunto, esa redistribución es un solo movimiento válido.
    """
    errores = []
    for etiqueta, campo in (("corriente", "presupuesto_corriente"),
                            ("capital", "presupuesto_capital")):
        total = Decimal("0")
        for fila in filas:
            monto = getattr(fila, campo) or Decimal("0")
            if monto < 0:
                errores.append(
                    f"{fila.etiqueta}: el presupuesto {etiqueta} no puede ser negativo."
                )
                continue
            total += monto

            # Nadie puede quedar por debajo de lo que sus planes ya tomaron.
            planificado = (fila.planificado_capital if campo == "presupuesto_capital"
                           else fila.planificado_corriente)
            if monto < planificado:
                errores.append(
                    f"{fila.etiqueta}: sus planes de gasto {etiqueta} de "
                    f"{fila.anio_calendario} ya suman {pesos(planificado)}, "
                    f"así que no puede quedar en {pesos(monto)}."
                )

        del_proyecto = getattr(proyecto, campo) or Decimal("0")
        if total > del_proyecto:
            errores.append(
                f"La suma {etiqueta} de todos los años es {pesos(total)} y el "
                f"proyecto tiene {pesos(del_proyecto)}: sobran "
                f"{pesos(total - del_proyecto)}."
            )
    return errores


@login_required
@require_POST
def guardar_anios(request, pk):
    """Guarda el reparto de todos los años de una vez.

    Es la única forma de poder mover plata de un año a otro: el tope es la suma,
    así que guardar año por año obliga a pasar por un estado que la validación
    rechaza. La tabla entera se envía junta y se acepta o se rechaza junta.
    """
    proyecto = get_object_or_404(Proyecto, pk=pk)
    if not _puede_editar(request.user, proyecto):
        return HttpResponseForbidden("No autorizado")

    # Sólo se tocan los años que vinieron en el envío. Sin esto, un año que no
    # esté en el formulario —porque se creó en otra pestaña, o porque el POST
    # llega recortado— se interpretaría como «déjalo en cero» y su presupuesto
    # desaparecería sin que nadie lo pidiera.
    filas = list(proyecto.presupuestos_anuales.all())
    for fila in filas:
        if f"corriente_{fila.pk}" not in request.POST:
            continue
        fila.presupuesto_corriente = _to_decimal(request.POST[f"corriente_{fila.pk}"])
        fila.presupuesto_capital = _to_decimal(
            request.POST.get(f"capital_{fila.pk}") or 0
        )
        fila.actualizado_por = request.user

    errores = _validar_el_reparto(proyecto, filas)
    if errores:
        # Se devuelven las filas tal como las escribió el usuario, no las
        # guardadas: si se recargaran desde la base, el error hablaría de unos
        # montos y la pantalla mostraría otros.
        return _responder(request, proyecto, error=" ".join(errores),
                          filas_en_pantalla=filas)

    with transaction.atomic():
        for fila in filas:
            fila.save(update_fields=[
                "presupuesto_corriente", "presupuesto_capital",
                "actualizado_por", "actualizado_en",
            ])

    response = _responder(request, proyecto)
    return disparar(response, estructuraActualizada=True,
                    guardado="Reparto por año guardado.")


@login_required
@require_POST
def guardar_anio(request, pk):
    anio = get_object_or_404(PresupuestoAnual, pk=pk)
    proyecto = anio.proyecto
    if not _puede_editar(request.user, proyecto):
        return HttpResponseForbidden("No autorizado")

    anio.presupuesto_corriente = _to_decimal(request.POST.get("presupuesto_corriente"))
    anio.presupuesto_capital = _to_decimal(request.POST.get("presupuesto_capital"))
    if request.POST.get("anio_calendario"):
        anio.anio_calendario = int(_to_decimal(request.POST["anio_calendario"]))
    anio.actualizado_por = request.user

    try:
        anio.full_clean()
        anio.save()
    except ValidationError as error:
        # Se recarga desde la base para que la pantalla vuelva a mostrar lo que
        # está guardado y no el monto rechazado, que induce a creer que quedó.
        anio.refresh_from_db()
        return _responder(request, proyecto, error=" ".join(
            m for msgs in error.message_dict.values() for m in msgs
        ), anio_con_error=anio.pk)

    response = _responder(request, proyecto)
    return disparar(response, estructuraActualizada=True,
                    guardado=f"Presupuesto de {anio.anio_calendario} guardado.")


@login_required
@require_POST
def eliminar_anio(request, pk):
    """Borra un año y renumera los que quedan.

    Sin renumerar, borrar el Año 2 de tres deja «Año 1, Año 3» y el selector
    miente sobre cuántos años tiene el proyecto. El año calendario no se toca:
    ése es un dato, no una posición.
    """
    anio = get_object_or_404(PresupuestoAnual, pk=pk)
    proyecto = anio.proyecto
    if not _puede_editar(request.user, proyecto):
        return HttpResponseForbidden("No autorizado")

    if anio.planificado:
        return _responder(request, proyecto, error=(
            f"No se puede borrar {anio.anio_calendario}: tiene planes de gasto "
            f"cargados por {anio.planificado:,.0f}. Bórralos o muévelos primero."
        ))

    calendario = anio.anio_calendario
    anio.delete()

    for posicion, restante in enumerate(
        proyecto.presupuestos_anuales.order_by("numero_anio"), start=1
    ):
        if restante.numero_anio != posicion:
            restante.numero_anio = posicion
            restante.save(update_fields=["numero_anio"])

    response = _responder(request, proyecto)
    return disparar(response, estructuraActualizada=True,
                    guardado=f"Año {calendario} eliminado.")
