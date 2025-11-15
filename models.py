from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Transacao(db.Model):
    __tablename__ = 'transacao'  # Nome da tabela no banco

    # Aqui você define cada coluna
    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(100), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    categoria = db.Column(db.String(50), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # 'Despesa' ou 'Receita'
    forma_pagamento = db.Column(db.String(20), nullable=False)  # 'Dinheiro', 'Débito', 'Crédito'
    data = db.Column(db.Date, nullable=False)

    # Método para representar o objeto (útil para debug)
    def __repr__(self):
        return f'<Transacao {self.descricao} - R${self.valor}>'
