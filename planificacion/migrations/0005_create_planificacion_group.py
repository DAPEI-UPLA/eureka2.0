from django.db import migrations


def crear_grupo_planificacion(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')

    grupo, created = Group.objects.get_or_create(name='Planificacion')

    # Permisos del modelo Indicador
    permisos = Permission.objects.filter(
        content_type__app_label='planificacion',
        content_type__model__in=['indicador', 'programa']
    )

    grupo.permissions.set(permisos)


class Migration(migrations.Migration):

    dependencies = [
        ('planificacion', '0004_alter_indicador_options'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(crear_grupo_planificacion),
    ]