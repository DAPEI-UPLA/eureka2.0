from .actividades import (
    crear_actividad,
    crear_actividad_form,
    editar_actividad,
    editar_actividad_form,
    eliminar_actividad,
    guardar_actividad,
    listar_actividades,
)
from .catalogo import (
    cargar_actividades,
    cargar_gastos,
    cargar_gastos_elegibles,
    cargar_resultados,
    cargar_tipos_gasto,
)
from .objetivos import (
    crear_objetivo,
    editar_objetivo_form,
    editar_presupuesto_objetivo,
    eliminar_objetivo,
    guardar_objetivo,
    listar_objetivos,
    meta_objetivo,
)
from .orden import mover_actividad, mover_objetivo, mover_resultado
from .graficos import graficos_proyecto, graficos_proyectos
from .exportar import (
    exportar_cartera_excel,
    exportar_proyecto_excel,
    informe_proyecto,
)
from .permisos import es_encargada, es_jefe, usuario_es_responsable
from .presupuesto_resultado import (
    guardar_presupuesto_resultado_anual,
    presupuesto_resultado_anual,
)
from .presupuesto_objetivo import (
    guardar_presupuesto_objetivo_anual,
    presupuesto_objetivo_anual,
)
from .presupuesto_anual import (
    crear_anio,
    eliminar_anio,
    guardar_anio,
    listar_presupuesto_anual,
)
from .planes_gasto import (
    crear_plan_gasto,
    crear_plan_gasto_form,
    editar_plan_gasto,
    editar_plan_gasto_form,
    eliminar_plan_gasto,
    listar_planes_actividad,
    listar_planes_gasto,
)
from .egresos import (
    crear_egreso,
    crear_egreso_form,
    editar_egreso,
    editar_egreso_form,
    elegibles_por_subtipo,
    eliminar_egreso,
    listar_egresos,
    pagar_cuota,
    pagar_impuesto,
    plan_detalle,
    planes_por_elegible,
)
from .proyectos import (
    dashboard_proyecto,
    detalle_proyecto,
    editar_proyecto,
    eliminar_proyecto,
    lista_proyectos,
    mis_proyectos,
    proyectos_por_tipo,
    tablero_proyecto,
)
from .resultados import (
    crear_resultado,
    detalle_presupuesto_resultado,
    editar_resultado_form,
    eliminar_resultado,
    fila_resultado,
    form_asignar_presupuesto,
    guardar_presupuesto,
    guardar_resultado,
    listar_resultados,
)

# alias para retrocompat
actualizar_presupuesto_objetivo = editar_presupuesto_objetivo
