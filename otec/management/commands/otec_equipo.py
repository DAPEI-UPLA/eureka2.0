"""Muestra y arma el equipo OTEC.

Los grupos «Encargado OTEC» y «Profesional OTEC» definen quién aparece en la
carga laboral. Este comando solo asigna **usuarios que ya existen**: crear
cuentas es una decisión de acceso y se hace desde el administrador de Django.

    python manage.py otec_equipo
    python manage.py otec_equipo --agregar pflores --rol encargado
    python manage.py otec_equipo --quitar pflores
"""

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand, CommandError

from otec.models import (
    GRUPO_ENCARGADO,
    GRUPO_PROFESIONAL,
    Actividad,
    equipo_otec,
    rol_otec,
)

ROLES = {
    "encargado": GRUPO_ENCARGADO,
    "profesional": GRUPO_PROFESIONAL,
}


class Command(BaseCommand):
    help = "Lista el equipo OTEC y asigna usuarios a sus grupos."

    def add_arguments(self, parser):
        parser.add_argument("--agregar", metavar="USUARIO")
        parser.add_argument("--quitar", metavar="USUARIO")
        parser.add_argument(
            "--rol", choices=sorted(ROLES), help="Requerido junto con --agregar."
        )

    def handle(self, *args, **options):
        for nombre in (GRUPO_ENCARGADO, GRUPO_PROFESIONAL):
            Group.objects.get_or_create(name=nombre)

        if options["agregar"]:
            if not options["rol"]:
                raise CommandError("Indique el rol con --rol encargado|profesional.")
            usuario = self._usuario(options["agregar"])
            grupo = Group.objects.get(name=ROLES[options["rol"]])
            # Una persona tiene un solo rol: se quita del otro grupo.
            for otro in (GRUPO_ENCARGADO, GRUPO_PROFESIONAL):
                if otro != grupo.name:
                    usuario.groups.remove(Group.objects.get(name=otro))
            usuario.groups.add(grupo)
            self.stdout.write(self.style.SUCCESS(
                f"{usuario.username} quedó en «{grupo.name}»."
            ))

        if options["quitar"]:
            usuario = self._usuario(options["quitar"])
            for nombre in (GRUPO_ENCARGADO, GRUPO_PROFESIONAL):
                usuario.groups.remove(Group.objects.get(name=nombre))
            self.stdout.write(self.style.SUCCESS(
                f"{usuario.username} salió del equipo OTEC."
            ))

        self._listar()

    def _usuario(self, username):
        usuario = User.objects.filter(username=username).first()
        if usuario is None:
            existentes = ", ".join(
                User.objects.order_by("username").values_list("username", flat=True)[:15]
            )
            raise CommandError(
                f"No existe el usuario «{username}». Créelo primero en el "
                f"administrador de Django. Usuarios actuales: {existentes}"
            )
        return usuario

    def _listar(self):
        equipo = list(equipo_otec())
        self.stdout.write("")
        self.stdout.write(f"EQUIPO OTEC ({len(equipo)})")
        if not equipo:
            self.stdout.write(
                "  (vacío — la carga laboral no mostrará a nadie hasta que "
                "haya usuarios en los grupos)"
            )
        for u in equipo:
            n = u.actividades_otec.count()
            self.stdout.write(
                f"  {u.username:<20} {u.get_full_name() or '(sin nombre)':<28} "
                f"{rol_otec(u):<12} {n} actividades"
            )

        # Nombres que la planilla menciona y no calzan con nadie del equipo.
        from otec.importador import clave

        conocidos = set()
        for u in equipo:
            for etiqueta in (u.get_full_name(), u.first_name, u.username):
                if etiqueta:
                    conocidos.add(clave(etiqueta))

        pendientes = {}
        for a in Actividad.objects.all():
            for nombre in a.responsable_seguimiento.split("/"):
                nombre = nombre.strip()
                if nombre and clave(nombre) not in conocidos:
                    pendientes[nombre] = pendientes.get(nombre, 0) + 1

        if pendientes:
            self.stdout.write("")
            self.stdout.write("NOMBRES EN LA PLANILLA SIN USUARIO EN EL EQUIPO")
            for nombre, n in sorted(pendientes.items(), key=lambda x: -x[1]):
                self.stdout.write(f"  {nombre:<24} en {n} actividades")
