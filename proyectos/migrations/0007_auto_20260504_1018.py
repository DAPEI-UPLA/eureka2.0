from django.db import migrations

CATALOGO = {
    "Corriente": {
        "Personal": {
            "Relativo a personal": [
                "Honorarios",
                "Remuneraciones",
                "Transferencia a estudiantes",
                "Transferencias postdoctorales",
                "Viáticos/Manutención"
            ]
        },
        "Operación": {
            "Relativos a bienes y servicios de consumo": [
                "Arriendo de equipamiento y vehículos",
                "Arriendo de espacios",
                "Consultoría",
                "Material pedagógico y académico",
                "Materiales e insumos",
                "Movilización/Traslado",
                "Seguros bienes",
                "Seguros personal",
                "Servicio de correspondencia",
                "Servicios básicos",
                "Servicio de alimentación",
                "Servicios de acreditación",
                "Servicios de apoyo académico y de capacitación",
                "Servicios audiovisuales y de comunicación",
                "Servicios de mantenimiento y reparación",
                "Servicios de suscripción y acceso",
                "Servicios y productos de difusión",
                "Tasas y Patentes"
            ]
        }
    },
    "Capital": {
        "Inversiones": {
            "Bienes": [
                "Bienes inmuebles y terrenos",
                "Desarrollo de softwares",
                "Equipamiento audiovisual, computacional y de información",
                "Equipamiento e instrumental de apoyo",
                "Mobiliario y Alhajamiento menor",
                "Soporte informático y bases de datos",
                "Vehículos"
            ],
            "Obras": [
                "Obra nueva",
                "Ampliación",
                "Alteración",
                "Estudios prefactibilidad y diseño"
            ]
        }
    }
}


def cargar_catalogo(apps, schema_editor):
    Transferencia = apps.get_model('proyectos', 'Transferencia')
    TipoGasto = apps.get_model('proyectos', 'TipoGasto')
    Gasto = apps.get_model('proyectos', 'Gasto')
    GastoElegible = apps.get_model('proyectos', 'GastoElegible')

    for nombre_transferencia, tipos in CATALOGO.items():
        transferencia, _ = Transferencia.objects.get_or_create(
            nombre=nombre_transferencia
        )

        for nombre_tipo, gastos in tipos.items():
            tipo_gasto, _ = TipoGasto.objects.get_or_create(
                transferencia=transferencia,
                nombre=nombre_tipo
            )

            for nombre_gasto, elegibles in gastos.items():
                gasto, _ = Gasto.objects.get_or_create(
                    tipo_gasto=tipo_gasto,
                    nombre=nombre_gasto
                )

                for nombre_elegible in elegibles:
                    GastoElegible.objects.get_or_create(
                        gasto=gasto,
                        nombre=nombre_elegible
                    )


class Migration(migrations.Migration):

    dependencies = [
        ('proyectos', '0006_unidad_alter_plandegasto_options_and_more'),
    ]

    operations = [
        migrations.RunPython(cargar_catalogo),
    ]