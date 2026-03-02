from django.contrib.auth.models import Group
from django.db.models.signals import post_migrate
from django.dispatch import receiver


@receiver(post_migrate)
def crear_grupo_aprobadores(sender, **kwargs):
    if sender.name == 'oct':
        Group.objects.get_or_create(name='Aprobadores de Iniciativas')