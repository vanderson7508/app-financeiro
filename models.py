from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date

db = SQLAlchemy()

class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuarios'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha = db.Column(db.String(255), nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamentos
    transacoes = db.relationship('Transacao', backref='usuario', lazy=True, cascade='all, delete-orphan')
    bancos = db.relationship('Banco', backref='usuario', lazy=True, cascade='all, delete-orphan')
    cartoes = db.relationship('CartaoCredito', backref='usuario', lazy=True, cascade='all, delete-orphan')
    compras_cartao = db.relationship('CompraCartao', backref='usuario', lazy=True, cascade='all, delete-orphan')
    categorias = db.relationship('Categoria', backref='usuario', lazy=True, cascade='all, delete-orphan')
    recorrencias = db.relationship('Recorrencia', backref='usuario', lazy=True, cascade='all, delete-orphan')
    orcamentos = db.relationship('Orcamento', backref='usuario', lazy=True, cascade='all, delete-orphan')
    faturas = db.relationship('FaturaCartao', backref='usuario', lazy=True, cascade='all, delete-orphan')

    def set_senha(self, senha):
        self.senha = generate_password_hash(senha)

    def verificar_senha(self, senha):
        return check_password_hash(self.senha, senha)

class Transacao(db.Model):
    __tablename__ = 'transacoes'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    descricao = db.Column(db.String(200), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    categoria = db.Column(db.String(100), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # Receita ou Despesa
    forma_pagamento = db.Column(db.String(50), nullable=False)
    data = db.Column(db.Date, nullable=False)
    banco_id = db.Column(db.Integer, db.ForeignKey('bancos.id'), nullable=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamento
    banco = db.relationship('Banco', backref='transacoes')

class Banco(db.Model):
    __tablename__ = 'bancos'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    saldo = db.Column(db.Float, default=0.0)
    tipo = db.Column(db.String(50), nullable=False)  # Conta Corrente, Poupança, etc
    descricao = db.Column(db.String(200), nullable=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamentos
    movimentacoes = db.relationship('MovimentacaoBanco', backref='banco', lazy=True, cascade='all, delete-orphan')

class MovimentacaoBanco(db.Model):
    __tablename__ = 'movimentacoes_banco'

    id = db.Column(db.Integer, primary_key=True)
    banco_id = db.Column(db.Integer, db.ForeignKey('bancos.id'), nullable=False)
    tipo_movimento = db.Column(db.String(20), nullable=False)  # entrada ou saida
    valor = db.Column(db.Float, nullable=False)
    descricao = db.Column(db.String(200), nullable=False)
    data = db.Column(db.Date, nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

class CartaoCredito(db.Model):
    __tablename__ = 'cartoes_credito'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    dia_fechamento = db.Column(db.Integer, nullable=False)  # Dia do fechamento da fatura
    dia_vencimento = db.Column(db.Integer, nullable=False)  # Dia do vencimento
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamentos
    compras = db.relationship('CompraCartao', backref='cartao', lazy=True, cascade='all, delete-orphan')
    faturas = db.relationship('FaturaCartao', backref='cartao', lazy=True, cascade='all, delete-orphan')

class CompraCartao(db.Model):
    __tablename__ = 'compras_cartao'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    cartao_id = db.Column(db.Integer, db.ForeignKey('cartoes_credito.id'), nullable=False)
    descricao = db.Column(db.String(200), nullable=False)
    valor_total = db.Column(db.Float, nullable=False)
    quantidade_parcelas = db.Column(db.Integer, default=1)
    data_compra = db.Column(db.Date, nullable=False)
    categoria = db.Column(db.String(100), nullable=False)
    forma_pagamento = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default='aberta')  # aberta ou fechada
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

class FaturaCartao(db.Model):
    """
    Modelo para controlar as faturas do cartão de crédito.
    Uma fatura é gerada para cada mês/ano do cartão.
    """
    __tablename__ = 'faturas_cartao'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    cartao_id = db.Column(db.Integer, db.ForeignKey('cartoes_credito.id'), nullable=False)

    # Data da fatura
    mes = db.Column(db.Integer, nullable=False)  # 1-12
    ano = db.Column(db.Integer, nullable=False)

    # Valores
    valor_total = db.Column(db.Float, default=0.0)
    valor_pago = db.Column(db.Float, default=0.0)
    valor_restante = db.Column(db.Float, default=0.0)

    # Datas importantes
    data_fechamento = db.Column(db.Date, nullable=False)
    data_vencimento = db.Column(db.Date, nullable=False)
    data_pagamento = db.Column(db.Date, nullable=True)

    # Status
    status = db.Column(db.String(20), default='aberta')  # aberta, paga, atrasada

    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamento
    transacoes_fatura = db.relationship('TransacaoFatura', backref='fatura', lazy=True, cascade='all, delete-orphan')
    pagamentos = db.relationship('PagamentoFatura', backref='fatura', lazy=True, cascade='all, delete-orphan')

class TransacaoFatura(db.Model):
    """
    Relaciona cada transação de cartão de crédito com a fatura correspondente.
    """
    __tablename__ = 'transacoes_fatura'

    id = db.Column(db.Integer, primary_key=True)
    fatura_id = db.Column(db.Integer, db.ForeignKey('faturas_cartao.id'), nullable=False)
    compra_cartao_id = db.Column(db.Integer, db.ForeignKey('compras_cartao.id'), nullable=False)

    # Parcela
    numero_parcela = db.Column(db.Integer, default=1)
    valor_parcela = db.Column(db.Float, nullable=False)

    # Relacionamentos
    compra = db.relationship('CompraCartao', backref='parcelas_fatura')

class PagamentoFatura(db.Model):
    """
    Registra os pagamentos das faturas.
    """
    __tablename__ = 'pagamentos_fatura'

    id = db.Column(db.Integer, primary_key=True)
    fatura_id = db.Column(db.Integer, db.ForeignKey('faturas_cartao.id'), nullable=False)

    valor = db.Column(db.Float, nullable=False)
    data_pagamento = db.Column(db.Date, nullable=False)
    forma_pagamento = db.Column(db.String(50), nullable=False)
    descricao = db.Column(db.String(200), nullable=True)

    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

class Categoria(db.Model):
    __tablename__ = 'categorias'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.String(200), nullable=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

class Recorrencia(db.Model):
    __tablename__ = 'recorrencias'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    descricao = db.Column(db.String(200), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # Receita ou Despesa
    categoria = db.Column(db.String(100), nullable=False)
    forma_pagamento = db.Column(db.String(50), nullable=False)
    banco_id = db.Column(db.Integer, db.ForeignKey('bancos.id'), nullable=True)  # ✅ NOVO
    cartao_id = db.Column(db.Integer, db.ForeignKey('cartoes_credito.id'), nullable=True)  # ✅ NOVO
    frequencia = db.Column(db.String(20), nullable=False)  # mensal, bimestral, etc
    dia_vencimento = db.Column(db.Integer, nullable=False)
    data_inicio = db.Column(db.Date, nullable=False)
    data_fim = db.Column(db.Date, nullable=True)
    ativa = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

class Orcamento(db.Model):
    __tablename__ = 'orcamentos'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    categoria = db.Column(db.String(100), nullable=False)
    limite_mensal = db.Column(db.Float, nullable=False)
    mes = db.Column(db.Integer, nullable=False)
    ano = db.Column(db.Integer, nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
