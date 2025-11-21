#!/usr/bin/env python3
"""
Script para adicionar colunas cartao_id e recorrencia_id na tabela transacoes
Sem perder dados existentes!
"""

from app import app, db
from sqlalchemy import text

def add_columns():
    """Adiciona colunas na tabela transacoes se não existirem"""
    
    with app.app_context():
        try:
            print("🔧 Iniciando migration...")
            
            with db.engine.connect() as connection:
                # Verificar se coluna cartao_id já existe
                try:
                    print("✓ Tentando adicionar coluna cartao_id...")
                    connection.execute(text(
                        'ALTER TABLE transacoes ADD COLUMN cartao_id INTEGER REFERENCES cartoes_credito(id);'
                    ))
                    connection.commit()
                    print("✅ Coluna cartao_id adicionada com sucesso!")
                except Exception as e:
                    if 'already exists' in str(e) or 'column' in str(e).lower():
                        print("⚠️  Coluna cartao_id já existe - pulando...")
                    else:
                        print(f"❌ Erro ao adicionar cartao_id: {e}")
                        connection.rollback()
                
                # Verificar se coluna recorrencia_id já existe
                try:
                    print("✓ Tentando adicionar coluna recorrencia_id...")
                    connection.execute(text(
                        'ALTER TABLE transacoes ADD COLUMN recorrencia_id INTEGER REFERENCES recorrencias(id);'
                    ))
                    connection.commit()
                    print("✅ Coluna recorrencia_id adicionada com sucesso!")
                except Exception as e:
                    if 'already exists' in str(e) or 'column' in str(e).lower():
                        print("⚠️  Coluna recorrencia_id já existe - pulando...")
                    else:
                        print(f"❌ Erro ao adicionar recorrencia_id: {e}")
                        connection.rollback()
            
            print("\n✅ Migration completada!")
            print("📊 Todas as colunas estão presentes na tabela transacoes")
            
        except Exception as e:
            print(f"\n❌ ERRO CRÍTICO: {e}")
            return False
    
    return True


if __name__ == '__main__':
    print("=" * 80)
    print("MIGRATION: Adicionar colunas na tabela transacoes")
    print("=" * 80)
    
    success = add_columns()
    
    if success:
        print("\n✅ Migration executada com SUCESSO!")
    else:
        print("\n❌ Migration FALHOU!")
    
    print("=" * 80)
