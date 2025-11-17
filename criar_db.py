#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
sys.path.insert(0, '/home/vanderson/Projects/meu_app_financeiro')

from app import app, db

print("🔄 Criando banco de dados...")

with app.app_context():
    db.create_all()
    print("✅ Banco de dados criado com sucesso!")
    print("📊 Tabelas criadas:")
    print("  - usuario")
    print("  - transacao")
    print("  - orcamento")
    print("  - cartao_credito")
    print("  - compra_cartao")
    print("  - categoria")
    print("  - recorrencia")
    print("  - banco")
    print("  - movimentacao_banco")
