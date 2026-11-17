"""Fixtures da área do Dono: um usuário Dono já logado e um usuário comum."""
import pytest
from django.contrib.auth.models import Group, User


@pytest.fixture
def usuario_comum(db):
    return User.objects.create_user("comum", password="senha123")


@pytest.fixture
def client_dono(db, client):
    dono = User.objects.create_user("ana", password="senha123")
    grupo, _ = Group.objects.get_or_create(name="Dono")
    dono.groups.add(grupo)
    client.force_login(dono)
    return client


@pytest.fixture
def client_equipe(client, usuario_equipe):
    client.force_login(usuario_equipe)
    return client
