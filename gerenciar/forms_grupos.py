"""Formulários dos grupos de opção (ex.: "Adicionais", "Ponto da carne") e das opções de cada um."""
from decimal import Decimal

from django import forms
from django.utils.text import slugify

from cardapio.models import GrupoOpcao, Opcao
from cardapio.disponibilidade import capacidade_grupo

from .forms import ler_preco


class GrupoForm(forms.ModelForm):
    """Dados do grupo. O `codigo` é gerado sozinho e nunca muda depois."""

    class Meta:
        model = GrupoOpcao
        fields = ["nome", "tipo", "minimo", "maximo", "obrigatorio"]
        labels = {
            "nome": "Nome do grupo",
            "tipo": "Como o cliente escolhe",
            "minimo": "Mínimo de escolhas",
            "maximo": "Máximo de escolhas",
            "obrigatorio": "Obrigatório (o cliente precisa escolher)",
        }
        help_texts = {"minimo": "Só vale se o grupo for obrigatório; em grupo opcional o mínimo vira 0."}
        widgets = {
            "nome": forms.TextInput(attrs={"class": "input", "placeholder": "Ex.: Adicionais"}),
            "tipo": forms.Select(attrs={"class": "input"}),
            "minimo": forms.NumberInput(attrs={"class": "input", "min": 0, "inputmode": "numeric"}),
            "maximo": forms.NumberInput(attrs={"class": "input", "min": 1, "inputmode": "numeric"}),
        }
        error_messages = {
            "nome": {"required": "Digite o nome do grupo."},
            "minimo": {"required": "Informe o mínimo (pode ser 0).", "invalid": "Digite um número inteiro."},
            "maximo": {"required": "Informe o máximo.", "invalid": "Digite um número inteiro."},
        }

    def clean(self):
        dados = super().clean()
        if dados.get("tipo") == GrupoOpcao.UNICA:  # escolha única: só dá para escolher 1
            dados["maximo"] = 1
            self.errors.pop("maximo", None)
        minimo, maximo = dados.get("minimo"), dados.get("maximo")
        if minimo is not None and maximo is not None:
            if maximo < 1:
                self.add_error("maximo", "O máximo precisa ser pelo menos 1.")
            elif minimo > maximo:
                self.add_error("minimo", "O mínimo não pode ser maior que o máximo.")
            if dados.get("obrigatorio") and minimo < 1:
                self.add_error("minimo", "Grupo obrigatório precisa de mínimo 1 ou mais.")
        return dados

    def _codigo_livre(self, nome):
        """Gera o código a partir do nome; se já existe, acrescenta -2, -3..."""
        base = slugify(nome)[:50] or "grupo"
        codigo, n = base, 2
        while GrupoOpcao.objects.filter(codigo=codigo).exists():
            codigo = f"{base}-{n}"
            n += 1
        return codigo

    def validar_capacidade(self, opcoes):
        """Valida os limites contra as opções já limpas pelo formset, sem esgotamentos."""
        dados = self.cleaned_data
        capacidade = capacidade_grupo(dados["tipo"], opcoes)
        if dados["obrigatorio"] and max(dados["minimo"], 1) > capacidade:
            self.add_error("minimo", f"O mínimo excede a capacidade das opções ({capacidade}).")
        if dados["maximo"] > capacidade:
            self.add_error("maximo", f"O máximo excede a capacidade das opções ({capacidade}).")
        return not self.errors

    def save(self, commit=True):
        grupo = super().save(commit=False)
        if not grupo.codigo:  # só grupo novo (os importados mantêm o código original)
            grupo.codigo = self._codigo_livre(grupo.nome)
        if grupo.tipo == GrupoOpcao.UNICA:
            grupo.maximo = 1
        if not grupo.obrigatorio:  # grupo opcional não tem mínimo: zera para não confundir
            grupo.minimo = 0
        if commit:
            grupo.save()
        return grupo


class OpcaoForm(forms.ModelForm):
    """Uma linha do grupo: nome, preço (formato brasileiro), quantidade máxima e ordem."""

    preco = forms.CharField(
        label="Preço (R$)", required=False,
        widget=forms.TextInput(attrs={"class": "input", "inputmode": "decimal", "placeholder": "0,00"}),
    )
    ordem = forms.IntegerField(
        label="Ordem", required=False, min_value=0,
        widget=forms.NumberInput(attrs={"class": "input ger-ordem", "inputmode": "numeric"}),
        error_messages={"invalid": "Digite um número inteiro."},
    )

    class Meta:
        model = Opcao
        fields = ["nome", "preco", "qtd_maxima", "ordem"]
        widgets = {
            "nome": forms.TextInput(attrs={"class": "input", "placeholder": "Ex.: Bacon"}),
            "qtd_maxima": forms.NumberInput(attrs={"class": "input", "min": 1, "inputmode": "numeric"}),
        }
        labels = {"nome": "Nome da opção", "qtd_maxima": "Qtd. máxima"}
        error_messages = {
            "nome": {"required": "Digite o nome da opção."},
            "qtd_maxima": {"required": "Informe a quantidade máxima.", "invalid": "Digite um número inteiro."},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:  # mostra o preço no formato brasileiro
            self.initial["preco"] = f"{self.instance.preco:.2f}".replace(".", ",")

    def clean_preco(self):
        texto = self.cleaned_data.get("preco") or ""
        if not texto.strip():
            return Decimal("0.00")
        try:
            valor = ler_preco(texto)
        except ValueError:
            raise forms.ValidationError("Digite o preço em reais, por exemplo 2,50 (ou 0 se for grátis).")
        if valor >= Decimal("100000"):
            raise forms.ValidationError("Esse preço é alto demais. Confira o valor.")
        return valor

    def clean_qtd_maxima(self):
        valor = self.cleaned_data["qtd_maxima"]
        if valor < 1:
            raise forms.ValidationError("A quantidade máxima precisa ser pelo menos 1.")
        return valor

    def clean_ordem(self):
        return self.cleaned_data.get("ordem") or 0


class BaseOpcaoFormSet(forms.BaseInlineFormSet):
    """Exige pelo menos uma opção que não esteja marcada para remover."""

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        vivas = [f for f in self.forms if f.cleaned_data and not f.cleaned_data.get("DELETE")]
        if not vivas:
            raise forms.ValidationError("Cadastre pelo menos uma opção no grupo.")

    def opcoes_ativas(self):
        """Instâncias validadas que serão salvas, excluindo linhas vazias e removidas."""
        return [f.instance for f in self.forms if f.cleaned_data and not f.cleaned_data.get("DELETE")]


OpcaoFormSet = forms.inlineformset_factory(
    GrupoOpcao, Opcao, form=OpcaoForm, formset=BaseOpcaoFormSet,
    extra=0, can_delete=True,
)
