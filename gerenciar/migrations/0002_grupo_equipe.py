"""Cria o grupo "Equipe" (atendentes do painel de pedidos; não mexem no cardápio)."""
from django.db import migrations


def criar_grupo(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name="Equipe")


class Migration(migrations.Migration):
    dependencies = [("gerenciar", "0001_grupo_dono")]
    operations = [migrations.RunPython(criar_grupo, migrations.RunPython.noop)]
