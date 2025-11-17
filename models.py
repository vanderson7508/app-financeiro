from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

db = SQLAlchemy()


class Transacao(db.Model):
    __tablename__ = 'transacao'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey(
        'usuario.id'), nullable=False)
    descricao = db.Column(db.String(100), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    categoria = db.Column(db.String(50), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # 'Receita' ou 'Despesa'
    forma_pagamento = db.Column(db.String(50), nullable=False)
    data = db.Column(db.Date, nullable=False, default=date.today)
    banco_id = db.Column(db.Integer, db.ForeignKey('banco.id'), nullable=True)
    data_criacao = db.Column(db.DateTime, nullable=False, default=datetime.now)

    banco = db.relationship('Banco', backref='transacoes')

    def __repr__(self):
        return f'<Transacao {self.descricao} - R${self.valor}>'


class Orcamento(db.Model):
    __tablename__ = 'orcamento'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey(
        'usuario.id'), nullable=False)
    categoria = db.Column(db.String(50), nullable=False)
    limite_mensal = db.Column(db.Float, nullable=False)
    mes = db.Column(db.Integer, nullable=False)  # 1 a 12
    ano = db.Column(db.Integer, nullable=False)
    data_criacao = db.Column(db.DateTime, nullable=False, default=datetime.now)

    def __repr__(self):
        return f'<Orcamento {self.categoria} - R${self.limite_mensal}>'


class CartaoCredito(db.Model):
    __tablename__ = 'cartao_credito'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey(
        'usuario.id'), nullable=False)
    nome = db.Column(db.String(100), nullable=False)  # ex: "Nubank", "Itaú"
    dia_fechamento = db.Column(db.Integer, nullable=False)  # 1-31
    dia_vencimento = db.Column(db.Integer, nullable=False)  # 1-31
    data_criacao = db.Column(db.DateTime, nullable=False, default=datetime.now)

    def __repr__(self):
        return f'<CartaoCredito {self.nome}>'


class CompraCartao(db.Model):
    __tablename__ = 'compra_cartao'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey(
        'usuario.id'), nullable=False)
    cartao_id = db.Column(db.Integer, db.ForeignKey(
        'cartao_credito.id'), nullable=False)
    descricao = db.Column(db.String(100), nullable=False)
    valor_total = db.Column(db.Float, nullable=False)
    quantidade_parcelas = db.Column(db.Integer, nullable=False, default=1)
    data_compra = db.Column(db.Date, nullable=False)
    categoria = db.Column(db.String(50), nullable=False)
    forma_pagamento = db.Column(
        db.String(20), nullable=False, default='Cartão')
    status = db.Column(db.String(20), nullable=False,
                       default='aberta')  # 'aberta', 'quitada'
    data_criacao = db.Column(db.DateTime, nullable=False, default=datetime.now)

    cartao = db.relationship('CartaoCredito', backref='compras')

    def __repr__(self):
        return f'<CompraCartao {self.descricao} - R${self.valor_total}>'


class Categoria(db.Model):
    __tablename__ = 'categoria'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey(
        'usuario.id'), nullable=False)
    nome = db.Column(db.String(50), nullable=False)
    descricao = db.Column(db.String(200))
    data_criacao = db.Column(db.DateTime, nullable=False, default=datetime.now)

    def __repr__(self):
        return f'<Categoria {self.nome}>'


class Recorrencia(db.Model):
    __tablename__ = 'recorrencia'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey(
        'usuario.id'), nullable=False)
    descricao = db.Column(db.String(100), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # 'Receita' ou 'Despesa'
    categoria = db.Column(db.String(50), nullable=False)
    forma_pagamento = db.Column(db.String(20), nullable=False)
    # 'mensal', 'bimestral', etc
    frequencia = db.Column(db.String(20), nullable=False)
    dia_vencimento = db.Column(db.Integer, nullable=False)  # Dia do mês (1-31)
    data_inicio = db.Column(db.Date, nullable=False)
    data_fim = db.Column(db.Date)  # None = indefinida
    ativa = db.Column(db.Boolean, nullable=False, default=True)
    data_criacao = db.Column(db.DateTime, nullable=False, default=datetime.now)

    def __repr__(self):
        return f'<Recorrencia {self.descricao} - R${self.valor}>'


class Banco(db.Model):
    __tablename__ = 'banco'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey(
        'usuario.id'), nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    saldo = db.Column(db.Float, nullable=False, default=0.0)
    # 'Conta Corrente', 'Poupança', etc
    tipo = db.Column(db.String(50), nullable=False)
    descricao = db.Column(db.String(200))
    data_criacao = db.Column(db.DateTime, nullable=False, default=datetime.now)

    def __repr__(self):
        return f'<Banco {self.nome} - R${self.saldo}>'


class MovimentacaoBanco(db.Model):
    __tablename__ = 'movimentacao_banco'

    id = db.Column(db.Integer, primary_key=True)
    banco_id = db.Column(db.Integer, db.ForeignKey('banco.id'), nullable=False)
    tipo_movimento = db.Column(
        db.String(20), nullable=False)  # 'entrada', 'saida'
    valor = db.Column(db.Float, nullable=False)
    descricao = db.Column(db.String(100), nullable=False)
    data = db.Column(db.Date, nullable=False)
    data_criacao = db.Column(db.DateTime, nullable=False, default=datetime.now)

    banco = db.relationship('Banco', backref='movimentacoes')

    def __repr__(self):
        return f'<Movimentacao {self.descricao} - R${self.valor}>'


class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)

    def set_senha(self, senha):
        self.senha_hash = generate_password_hash(senha)

    def verificar_senha(self, senha):
        return check_password_hash(self.senha_hash, senha)
