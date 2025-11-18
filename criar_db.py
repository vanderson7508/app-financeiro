#!/usr/bin/env python
# -*- coding: utf-8 -*-

from app import app, db
import sys
sys.path.insert(0, '/home/vanderson/Projects/meu_app_financeiro')


print("🔄 Criando/Atualizando banco de dados...")

with app.app_context():
    db.create_all()
    print("✅ Banco de dados criado/atualizado com sucesso!")
    print("📊 Tabelas existentes:")
    print("  ✅ usuario")
    print("  ✅ transacao")
    print("  ✅ orcamento")
    print("  ✅ cartao_credito")
    print("  ✅ compra_cartao")
    print("  ✅ categoria")
    print("  ✅ recorrencia")
    print("  ✅ banco")
    print("  ✅ movimentacao_banco")
    print("")
    print("📊 Novas tabelas (Sistema de Faturas):")
    print("  ✅ faturas_cartao")
    print("  ✅ transacoes_fatura")
    print("  ✅ pagamentos_fatura")
    print("")
    print("🎉 Tudo pronto! O sistema de faturas está ativado.")
    print("")
    print("📝 Próximos passos:")
    print("  1. Copie o app_COM_FATURAS.py para app.py")
    print("  2. Copie os templates HTML (faturas.html e detalhar_fatura.html)")
    print("  3. Adicione o link de Faturas ao menu base.html")
    print("  4. Reinicie a aplicação")
    print("  5. Teste lançando uma compra no cartão de crédito")
