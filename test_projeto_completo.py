#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
🧪 TESTES COMPLETOS DO PROJETO FINANCEIRO
"""

from werkzeug.security import generate_password_hash
from models import (
    db, Usuario, CartaoCredito, CompraCartao, FaturaCartao,
    Transacao, Banco, Categoria, Recorrencia, MovimentacaoBanco
)
from app import app
import pytest
from datetime import date, timedelta
import sys
sys.path.insert(0, '/home/vanderson/projetos_diversos/app-financeiro')


@pytest.fixture
def app_config():
    """Configurar app para testes"""
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['WTF_CSRF_ENABLED'] = False
    return app


@pytest.fixture
def client(app_config):
    """Cliente de teste Flask"""
    with app_config.app_context():
        db.create_all()
        yield app_config.test_client()
        db.session.remove()
        db.drop_all()


usuario_counter = 0


@pytest.fixture
def usuario_teste(client):
    """Criar usuário de teste COM EMAIL ÚNICO"""
    global usuario_counter
    usuario_counter += 1

    with app.app_context():
        usuario = Usuario(
            nome=f'Teste User {usuario_counter}',
            email=f'teste{usuario_counter}@teste.com',
            senha=generate_password_hash('senha123')
        )
        db.session.add(usuario)
        db.session.commit()
        return usuario.id


# ========== TESTES DE CARTÕES ==========

class TestCartoes:
    """Testes de Cartão de Crédito"""

    def test_criar_cartao(self, usuario_teste):
        """✅ Teste: Criar cartão de crédito"""
        with app.app_context():
            cartao = CartaoCredito(
                usuario_id=usuario_teste,
                nome='Banco do Brasil',
                dia_fechamento=24,
                dia_vencimento=5
            )
            db.session.add(cartao)
            db.session.commit()

            cartao_banco = CartaoCredito.query.filter_by(
                usuario_id=usuario_teste,
                nome='Banco do Brasil'
            ).first()

            assert cartao_banco is not None
            assert cartao_banco.dia_fechamento == 24

        print("✅ Teste PASSOU: Criação de cartão")

    def test_listar_cartoes(self, usuario_teste):
        """✅ Teste: Listar cartões do usuário"""
        with app.app_context():
            for i in range(3):
                cartao = CartaoCredito(
                    usuario_id=usuario_teste,
                    nome=f'Cartão {i+1}',
                    dia_fechamento=24,
                    dia_vencimento=5
                )
                db.session.add(cartao)

            db.session.commit()

            cartoes = CartaoCredito.query.filter_by(
                usuario_id=usuario_teste).all()
            assert len(cartoes) == 3

        print("✅ Teste PASSOU: Listagem de cartões")


# ========== TESTES DE COMPRAS NO CARTÃO ==========

class TestComprasCartao:
    """Testes de Compras com Cartão de Crédito"""

    def test_criar_compra_cartao(self, usuario_teste):
        """✅ Teste: Criar compra no cartão"""
        with app.app_context():
            cartao = CartaoCredito(
                usuario_id=usuario_teste,
                nome='Banco do Brasil',
                dia_fechamento=24,
                dia_vencimento=5
            )
            db.session.add(cartao)
            db.session.flush()

            compra = CompraCartao(
                usuario_id=usuario_teste,
                cartao_id=cartao.id,
                descricao='Compra teste',
                valor_total=100.00,
                quantidade_parcelas=1,
                data_compra=date.today(),
                categoria='Testes',
                forma_pagamento='Cartão de Crédito'
            )
            db.session.add(compra)
            db.session.commit()

            compra_banco = CompraCartao.query.filter_by(
                usuario_id=usuario_teste,
                descricao='Compra teste'
            ).first()

            assert compra_banco is not None
            assert compra_banco.valor_total == 100.00

        print("✅ Teste PASSOU: Criação de compra")

    def test_compra_com_parcelas(self, usuario_teste):
        """✅ Teste: Compra parcelada"""
        with app.app_context():
            cartao = CartaoCredito(
                usuario_id=usuario_teste,
                nome='Cartão Teste',
                dia_fechamento=24,
                dia_vencimento=5
            )
            db.session.add(cartao)
            db.session.flush()

            compra = CompraCartao(
                usuario_id=usuario_teste,
                cartao_id=cartao.id,
                descricao='Compra 3x',
                valor_total=300.00,
                quantidade_parcelas=3,
                data_compra=date.today(),
                categoria='Testes',
                forma_pagamento='Cartão de Crédito'
            )
            db.session.add(compra)
            db.session.commit()

            compra_banco = CompraCartao.query.filter_by(
                usuario_id=usuario_teste,
                descricao='Compra 3x'
            ).first()

            assert compra_banco.quantidade_parcelas == 3

        print("✅ Teste PASSOU: Compra parcelada")


# ========== TESTES DE FATURAS ==========

class TestFaturas:
    """Testes de Faturas de Cartão"""

    def test_criar_fatura_antes_fechamento(self, usuario_teste):
        """✅ Teste: Fatura antes do fechamento"""
        with app.app_context():
            from app import criar_ou_atualizar_fatura

            cartao = CartaoCredito(
                usuario_id=usuario_teste,
                nome='Banco Teste',
                dia_fechamento=24,
                dia_vencimento=5
            )
            db.session.add(cartao)
            db.session.flush()

            data_compra = date(2025, 11, 18)
            fatura = criar_ou_atualizar_fatura(
                usuario_teste,
                cartao.id,
                data_compra,
                100.00
            )

            assert fatura.mes == 11
            assert fatura.ano == 2025

        print("✅ Teste PASSOU: Fatura antes do fechamento")

    def test_criar_fatura_depois_fechamento(self, usuario_teste):
        """✅ Teste: Fatura depois do fechamento"""
        with app.app_context():
            from app import criar_ou_atualizar_fatura

            cartao = CartaoCredito(
                usuario_id=usuario_teste,
                nome='Banco Teste 2',
                dia_fechamento=24,
                dia_vencimento=5
            )
            db.session.add(cartao)
            db.session.flush()

            data_compra = date(2025, 11, 25)
            fatura = criar_ou_atualizar_fatura(
                usuario_teste,
                cartao.id,
                data_compra,
                75.00
            )

            assert fatura.mes == 12
            assert fatura.ano == 2025

        print("✅ Teste PASSOU: Fatura depois do fechamento")


# ========== TESTES DE TRANSAÇÕES ==========

class TestTransacoes:
    """Testes de Transações Gerais"""

    def test_criar_transacao_despesa(self, usuario_teste):
        """✅ Teste: Criar transação de despesa"""
        with app.app_context():
            transacao = Transacao(
                usuario_id=usuario_teste,
                descricao='Despesa teste',
                valor=50.00,
                categoria='Testes',
                tipo='Despesa',
                forma_pagamento='Dinheiro',
                data=date.today()
            )
            db.session.add(transacao)
            db.session.commit()

            trans_banco = Transacao.query.filter_by(
                usuario_id=usuario_teste,
                descricao='Despesa teste'
            ).first()

            assert trans_banco is not None
            assert trans_banco.tipo == 'Despesa'

        print("✅ Teste PASSOU: Transação despesa")

    def test_criar_transacao_receita(self, usuario_teste):
        """✅ Teste: Criar transação de receita"""
        with app.app_context():
            transacao = Transacao(
                usuario_id=usuario_teste,
                descricao='Receita teste',
                valor=100.00,
                categoria='Testes',
                tipo='Receita',
                forma_pagamento='Dinheiro',
                data=date.today()
            )
            db.session.add(transacao)
            db.session.commit()

            trans_banco = Transacao.query.filter_by(
                usuario_id=usuario_teste,
                tipo='Receita'
            ).first()

            assert trans_banco.tipo == 'Receita'

        print("✅ Teste PASSOU: Transação receita")


# ========== TESTES DE BANCOS ==========

class TestBancos:
    """Testes de Contas Bancárias"""

    def test_criar_banco(self, usuario_teste):
        """✅ Teste: Criar conta bancária"""
        with app.app_context():
            banco = Banco(
                usuario_id=usuario_teste,
                nome='Banco do Brasil',
                saldo=1000.00,
                tipo='Corrente'
            )
            db.session.add(banco)
            db.session.commit()

            banco_banco = Banco.query.filter_by(
                usuario_id=usuario_teste,
                nome='Banco do Brasil'
            ).first()

            assert banco_banco is not None
            assert banco_banco.saldo == 1000.00

        print("✅ Teste PASSOU: Criação de banco")

    def test_movimentacao_banco(self, usuario_teste):
        """✅ Teste: Movimentação bancária"""
        with app.app_context():
            banco = Banco(
                usuario_id=usuario_teste,
                nome='Banco Teste',
                saldo=1000.00,
                tipo='Corrente'
            )
            db.session.add(banco)
            db.session.flush()

            movimento = MovimentacaoBanco(
                banco_id=banco.id,
                tipo_movimento='saida',
                valor=100.00,
                descricao='Saque',
                data=date.today()
            )
            db.session.add(movimento)
            banco.saldo -= 100.00
            db.session.commit()

            banco_banco = Banco.query.get(banco.id)
            assert banco_banco.saldo == 900.00

        print("✅ Teste PASSOU: Movimentação banco")


# ========== TESTES DE CATEGORIAS ==========

class TestCategorias:
    """Testes de Categorias"""

    def test_criar_categoria(self, usuario_teste):
        """✅ Teste: Criar categoria"""
        with app.app_context():
            categoria = Categoria(
                usuario_id=usuario_teste,
                nome='Categoria Teste',
                descricao='Descrição teste'
            )
            db.session.add(categoria)
            db.session.commit()

            cat_banco = Categoria.query.filter_by(
                usuario_id=usuario_teste,
                nome='Categoria Teste'
            ).first()

            assert cat_banco is not None

        print("✅ Teste PASSOU: Criação de categoria")


# ========== TESTES DE RECORRÊNCIAS ==========

class TestRecorrencias:
    """Testes de Transações Recorrentes"""

    def test_criar_recorrencia(self, usuario_teste):
        """✅ Teste: Criar transação recorrente"""
        with app.app_context():
            recorrencia = Recorrencia(
                usuario_id=usuario_teste,
                descricao='Internet mensal',
                valor=100.00,
                tipo='Despesa',
                categoria='Testes',
                forma_pagamento='Banco',
                frequencia='mensal',
                dia_vencimento=10,
                data_inicio=date.today(),
                data_fim=date.today() + timedelta(days=365),
                ativa=True
            )
            db.session.add(recorrencia)
            db.session.commit()

            rec_banco = Recorrencia.query.filter_by(
                usuario_id=usuario_teste,
                descricao='Internet mensal'
            ).first()

            assert rec_banco is not None
            assert rec_banco.frequencia == 'mensal'

        print("✅ Teste PASSOU: Criação de recorrência")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
