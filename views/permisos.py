def es_jefe(user):
    return user.groups.filter(name='JefeProyectos').exists()


def es_encargada(user):
    return user.groups.filter(name='EncargadaProyectos').exists()


def usuario_es_responsable(user, proyecto):
    return user == proyecto.responsable
