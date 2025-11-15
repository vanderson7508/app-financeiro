from flask import Flask, render_template, request, redirect, url_for
from models import db, Transacao
from datetime import datetime

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///financeiro.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# ... resto do código anterior ...


@app.route('/')
def home():
    # Buscar todas as transações
    transacoes = Transacao.query.all()

    # Calcular totais
    total_receitas = sum(t.valor for t in transacoes if t.tipo == 'Receita')
    total_despesas = sum(t.valor for t in transacoes if t.tipo == 'Despesa')
    saldo = total_receitas - total_despesas

    # Passar os valores para o template
    return render_template('index.html',
                           total_receitas=total_receitas,
                           total_despesas=total_despesas,
                           saldo=saldo)


@app.route('/transacoes')
def lista_transacoes():
    # Buscar todas as transações do banco
    transacoes = Transacao.query.all()
    return render_template('transacoes.html', transacoes=transacoes)


@app.route('/adicionar', methods=['GET', 'POST'])
def adicionar():
    if request.method == 'POST':
        # Capturar dados do formulário
        descricao = request.form.get('descricao')
        valor = float(request.form.get('valor'))
        categoria = request.form.get('categoria')
        tipo = request.form.get('tipo')
        forma_pagamento = request.form.get('forma_pagamento')
        data = datetime.strptime(request.form.get('data'), '%Y-%m-%d').date()

        # Criar nova transação
        nova_transacao = Transacao(
            descricao=descricao,
            valor=valor,
            categoria=categoria,
            tipo=tipo,
            forma_pagamento=forma_pagamento,
            data=data
        )

        # Adicionar ao banco
        db.session.add(nova_transacao)
        db.session.commit()

        # Redirecionar para a lista
        return redirect(url_for('lista_transacoes'))

    # Se for GET, apenas mostra o formulário
    return render_template('adicionar.html')


@app.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar(id):
    # Buscar a transação pelo ID
    transacao = Transacao.query.get_or_404(id)

    if request.method == 'POST':
        # Atualizar os dados
        transacao.descricao = request.form.get('descricao')
        transacao.valor = float(request.form.get('valor'))
        transacao.categoria = request.form.get('categoria')
        transacao.tipo = request.form.get('tipo')
        transacao.forma_pagamento = request.form.get('forma_pagamento')
        transacao.data = datetime.strptime(
            request.form.get('data'), '%Y-%m-%d').date()

        # Salvar no banco
        db.session.commit()

        # Redirecionar
        return redirect(url_for('lista_transacoes'))

    # Se for GET, mostra o formulário
    return render_template('editar.html', transacao=transacao)


@app.route('/deletar/<int:id>', methods=['POST'])
def deletar(id):
    # Buscar a transação
    transacao = Transacao.query.get_or_404(id)

    # Deletar do banco
    db.session.delete(transacao)
    db.session.commit()

    # Redirecionar
    return redirect(url_for('lista_transacoes'))


# Criar as tabelas na inicialização
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=False, port=5000)
