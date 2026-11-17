"""Formulários da configuração da loja: dados gerais, horários, bairros e formas de pagamento."""
import re
from decimal import Decimal

from django import forms

from loja.models import Bairro, Configuracao, FormaPagamento, Horario

from .forms import ler_preco


class CampoReais(forms.CharField):
    """Campo de texto que entende "5", "5,00" ou "R$ 5,50" e devolve Decimal. Aceita 0, recusa negativo."""

    def __init__(self, *, maximo=Decimal("100000"), erro="Digite um valor em reais, por exemplo 5,00.", **kwargs):
        self.maximo, self.erro = maximo, erro
        kwargs.setdefault("widget", forms.TextInput(attrs={"class": "input", "inputmode": "decimal", "placeholder": "0,00"}))
        super().__init__(**kwargs)

    def prepare_value(self, value):
        """Mostra o número com vírgula (5,00) ao abrir o formulário."""
        if isinstance(value, Decimal):
            return f"{value:.2f}".replace(".", ",")
        return value

    def clean(self, value):
        texto = super().clean(value)
        if texto in (None, ""):
            return None
        try:
            valor = ler_preco(texto)
        except ValueError:
            raise forms.ValidationError(self.erro)
        if valor >= self.maximo:
            raise forms.ValidationError("Esse valor é alto demais. Confira.")
        return valor


def limpar_whatsapp(texto):
    """Guarda só os dígitos, com 55 na frente: "(81) 99000-1234" vira "5581990001234". Vazio é permitido."""
    digitos = re.sub(r"\D", "", texto or "")
    if not digitos:
        if (texto or "").strip():  # digitou algo, mas sem nenhum número
            raise forms.ValidationError("WhatsApp inválido. Digite com DDD, por exemplo (81) 99000-1234.")
        return ""
    if len(digitos) in (10, 11):  # veio sem o 55: completa
        digitos = "55" + digitos
    if len(digitos) not in (12, 13) or not digitos.startswith("55"):
        raise forms.ValidationError("WhatsApp inválido. Digite com DDD, por exemplo (81) 99000-1234.")
    return digitos


class LojaForm(forms.ModelForm):
    """Dados da loja que aparecem para o cliente (o modo aberta/fechada tem botões próprios)."""

    pedido_minimo = CampoReais(label="Pedido mínimo no delivery (R$)", erro="Digite o pedido mínimo em reais, por exemplo 10,00.")

    class Meta:
        model = Configuracao
        fields = ["nome", "slogan", "endereco", "whatsapp", "instagram", "chave_pix", "pix_titular", "pix_banco", "prazo", "pedido_minimo", "vias_padrao", "entrada_pedidos"]
        labels = {"whatsapp": "WhatsApp da loja", "vias_padrao": "Vias da comanda (impressão)", "prazo": "Prazo de entrega"}
        help_texts = {"whatsapp": "Com DDD. Ex.: (81) 99000-1234", "instagram": "Só o nome, sem @.", "prazo": "Ex.: 15 - 80 min"}
        widgets = {
            campo: forms.TextInput(attrs={"class": "input"})
            for campo in ["nome", "slogan", "endereco", "instagram", "chave_pix", "pix_titular", "pix_banco", "prazo"]
        }
        widgets["whatsapp"] = forms.TextInput(attrs={"class": "input", "inputmode": "tel", "placeholder": "(81) 99000-1234"})
        widgets["entrada_pedidos"] = forms.RadioSelect
        widgets["vias_padrao"] = forms.NumberInput(attrs={"class": "input", "min": 1, "max": 5, "inputmode": "numeric"})
        error_messages = {
            "nome": {"required": "Digite o nome da loja."},
            "prazo": {"required": "Digite o prazo de entrega."},
            "vias_padrao": {"required": "Informe as vias.", "invalid": "Digite um número inteiro."},
        }

    def clean_whatsapp(self):
        return limpar_whatsapp(self.cleaned_data.get("whatsapp"))

    def clean_vias_padrao(self):
        vias = self.cleaned_data["vias_padrao"]
        if not 1 <= vias <= 5:
            raise forms.ValidationError("Use de 1 a 5 vias.")
        return vias


class HorarioForm(forms.ModelForm):
    """Uma linha da semana: abre neste dia?, hora de abrir e de fechar."""

    abre = forms.TimeField(label="Abre", widget=forms.TimeInput(attrs={"class": "input", "type": "time"}, format="%H:%M"),
                           error_messages={"invalid": "Hora inválida.", "required": "Informe a hora de abrir."})
    fecha = forms.TimeField(label="Fecha", widget=forms.TimeInput(attrs={"class": "input", "type": "time"}, format="%H:%M"),
                            error_messages={"invalid": "Hora inválida.", "required": "Informe a hora de fechar."})

    class Meta:
        model = Horario
        fields = ["ativo", "abre", "fecha"]

    def clean(self):
        dados = super().clean()
        # dia fechado: as horas não importam, então não reclama delas
        if not dados.get("ativo"):
            for campo in ("abre", "fecha"):
                self.errors.pop(campo, None)
                dados[campo] = getattr(self.instance, campo)
            return dados
        abre, fecha = dados.get("abre"), dados.get("fecha")
        if abre and fecha and fecha <= abre:
            self.add_error("fecha", "O horário de fechar precisa ser depois do de abrir.")
        return dados


HorarioFormSet = forms.modelformset_factory(Horario, form=HorarioForm, extra=0)


class BairroForm(forms.ModelForm):
    """Nome do bairro e a taxa de entrega em reais (0 = entrega grátis)."""

    taxa = CampoReais(label="Taxa (R$)", maximo=Decimal("1000"), erro="Digite a taxa em reais, por exemplo 5,00 (ou 0 se for grátis).")

    class Meta:
        model = Bairro
        fields = ["nome", "taxa", "ativo"]
        labels = {"nome": "Bairro", "ativo": "Entrega neste bairro"}
        widgets = {"nome": forms.TextInput(attrs={"class": "input", "placeholder": "Ex.: Paratibe"})}
        error_messages = {"nome": {"required": "Digite o nome do bairro."}}

    def clean_nome(self):
        nome = self.cleaned_data["nome"].strip()
        outros = Bairro.objects.filter(nome__iexact=nome).exclude(pk=self.instance.pk)
        if outros.exists():
            raise forms.ValidationError("Já existe um bairro com esse nome.")
        return nome

    def validate_unique(self):
        """A conferência de nome repetido já é feita (sem diferenciar maiúscula) em clean_nome."""


class PagamentoForm(forms.ModelForm):
    """Acréscimo (%) e onde cada forma de pagamento vale. Nome e código não mudam."""

    acrescimo_pct = CampoReais(label="Acréscimo (%)", maximo=Decimal("100"), erro="Digite o acréscimo em %, por exemplo 4 ou 4,5 (0 = sem acréscimo).")

    class Meta:
        model = FormaPagamento
        fields = ["acrescimo_pct", "aceita_delivery", "aceita_retirada", "aceita_local"]
        labels = {"aceita_delivery": "Delivery", "aceita_retirada": "Retirada", "aceita_local": "No local"}


PagamentoFormSet = forms.modelformset_factory(FormaPagamento, form=PagamentoForm, extra=0)
