from flask import Flask, render_template, request, redirect, url_for, abort
from models import db, Transacao, Usuario, Banco, MovimentacaoBanco, CartaoCredito, CompraCartao, Categoria, Recorrencia, Orcamento
from datetime import datetime, date
from sqlalchemy import extract, func
from calendar import monthrange
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
import os
from itsdangerous import URLSafeTimedSerializer
from datetime import datetime, timedelta
import secrets
# ⭐(SendGrid):
from itsdangerous import URLSafeTimedSerializer
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content
import logging
from flask import flash

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get(
    'SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///financeiro.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ⭐ ADICIONE ISTO DEPOIS:
# ===== CONFIGURAÇÕES DO SENDGRID =====
app.config['SENDGRID_API_KEY'] = os.environ.get('SENDGRID_API_KEY', '')
app.config['SENDGRID_FROM_EMAIL'] = os.environ.get(
    'SENDGRID_FROM_EMAIL', 'noreply@financeiro.com')
app.config['SENDGRID_FROM_NAME'] = 'Controle Financeiro'

sg = SendGridAPIClient(app.config['SENDGRID_API_KEY'])
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# ===== FIM DAS CONFIGURAÇÕES =====

db.init_app(app)

mail = Mail(app)
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
# ===== FIM DO PASSO 2 =====
# Configurar LoginManager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Faça login para acessar esta página.'

# ===== FUNÇÕES DE RECUPERAÇÃO DE SENHA =====


def gerar_token_recuperacao(email):
    """Gera um token seguro para recuperação de senha"""
    return serializer.dumps(email, salt='recuperacao-senha')


def verificar_token_recuperacao(token, expiration=3600):
    """Verifica se o token é válido (padrão: 1 hora)"""
    try:
        email = serializer.loads(
            token, salt='recuperacao-senha', max_age=expiration)
        return email
    except Exception as e:
        logger.warning(f"Token inválido: {e}")
        return None


def enviar_email_recuperacao(email, nome):
    """Envia email de recuperação de senha via SendGrid"""
    try:
        if not app.config['SENDGRID_API_KEY']:
            logger.error("SendGrid API key não configurada")
            return False, "Erro ao configurar sistema de email"

        token = gerar_token_recuperacao(email)
        link_recuperacao = url_for(
            'recuperar_senha', token=token, _external=True)

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .container {{ max-width: 600px; margin: 0 auto; }}
                .header {{ background: linear-gradient(135deg, #17a2b8 0%, #20c997 100%); color: white; padding: 40px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: white; padding: 50px; border-radius: 0 0 10px 10px; }}
                .button {{ background: linear-gradient(135deg, #17a2b8 0%, #138496 100%); color: white; padding: 16px 50px; border-radius: 50px; text-decoration: none; font-weight: bold; display: inline-block; margin: 30px 0; }}
                .footer {{ text-align: center; color: #999; margin-top: 40px; padding-top: 20px; border-top: 1px solid #eee; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🔐 Recuperação de Senha</h1>
                </div>
                <div class="content">
                    <p>Olá <strong>{nome}</strong>,</p>
                    <p>Recebemos uma solicitação para recuperar sua senha.</p>
                    <p><strong>Se não foi você, ignore este email.</strong></p>

                    <center>
                        <a href="{link_recuperacao}" class="button">Redefinir Senha</a>
                    </center>

                    <p>Ou copie este link: {link_recuperacao}</p>

                    <p style="color: #999; font-size: 12px;">
                        ⏰ Este link expira em 1 hora por motivos de segurança.
                    </p>
                </div>
                <div class="footer">
                    <p>© 2025 Controle Financeiro</p>
                </div>
            </div>
        </body>
        </html>
        """

        message = Mail(
            from_email=Email(
                app.config['SENDGRID_FROM_EMAIL'], app.config['SENDGRID_FROM_NAME']),
            to_emails=To(email),
            subject='🔐 Recupere sua senha - Controle Financeiro',
            html_content=html_content
        )

        response = sg.send(message)

        if response.status_code in [200, 201]:
            logger.info(f"Email enviado para: {email}")
            return True, "Email enviado com sucesso"
        else:
            logger.error(f"Erro ao enviar: Status {response.status_code}")
            return False, "Erro ao enviar email"

    except Exception as e:
        logger.error(f"Erro: {str(e)}")
        return False, f"Erro: {str(e)}"

# ===== FIM DAS FUNÇÕES =====


@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

# ===== FUNÇÕES AUXILIARES DE SEGURANÇA =====


def verificar_propriedade_transacao(transacao_id):
    """Verifica se a transação pertence ao usuário logado"""
    transacao = Transacao.query.get_or_404(transacao_id)
    if transacao.usuario_id != current_user.id:
        abort(403)  # Forbidden
    return transacao


def verificar_propriedade_banco(banco_id):
    """Verifica se o banco pertence ao usuário logado"""
    banco = Banco.query.get_or_404(banco_id)
    if banco.usuario_id != current_user.id:
        abort(403)
    return banco


def verificar_propriedade_cartao(cartao_id):
    """Verifica se o cartão pertence ao usuário logado"""
    cartao = CartaoCredito.query.get_or_404(cartao_id)
    if cartao.usuario_id != current_user.id:
        abort(403)
    return cartao


def verificar_propriedade_compra(compra_id):
    """Verifica se a compra pertence ao usuário logado"""
    compra = CompraCartao.query.get_or_404(compra_id)
    if compra.usuario_id != current_user.id:
        abort(403)
    return compra


def verificar_propriedade_categoria(categoria_id):
    """Verifica se a categoria pertence ao usuário logado"""
    categoria = Categoria.query.get_or_404(categoria_id)
    if categoria.usuario_id != current_user.id:
        abort(403)
    return categoria


def verificar_propriedade_recorrencia(recorrencia_id):
    """Verifica se a recorrência pertence ao usuário logado"""
    recorrencia = Recorrencia.query.get_or_404(recorrencia_id)
    if recorrencia.usuario_id != current_user.id:
        abort(403)
    return recorrencia


def verificar_propriedade_orcamento(orcamento_id):
    """Verifica se o orçamento pertence ao usuário logado"""
    orcamento = Orcamento.query.get_or_404(orcamento_id)
    if orcamento.usuario_id != current_user.id:
        abort(403)
    return orcamento

# ===== ROTAS DE AUTENTICAÇÃO =====


@app.route('/registrar', methods=['GET', 'POST'])
def registrar():
    """Registrar novo usuário"""
    if request.method == 'POST':
        nome = request.form.get('nome')
        email = request.form.get('email')
        senha = request.form.get('senha')
        confirmar_senha = request.form.get('confirmar_senha')

        if not nome or not email or not senha or not confirmar_senha:
            return render_template('registrar.html', erro='Todos os campos são obrigatórios!')

        if senha != confirmar_senha:
            return render_template('registrar.html', erro='As senhas não coincidem!')

        if len(senha) < 6:
            return render_template('registrar.html', erro='A senha deve ter no mínimo 6 caracteres!')

        usuario_existente = Usuario.query.filter_by(email=email).first()
        if usuario_existente:
            return render_template('registrar.html', erro='Este email já está registrado!')

        novo_usuario = Usuario(nome=nome, email=email)
        novo_usuario.set_senha(senha)

        db.session.add(novo_usuario)
        db.session.commit()

        return redirect(url_for('login'))

    return render_template('registrar.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login do usuário"""
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')

        usuario = Usuario.query.filter_by(email=email).first()

        if usuario and usuario.verificar_senha(senha):
            login_user(usuario)
            return redirect(url_for('home'))
        else:
            return render_template('login.html', erro='Email ou senha incorretos!')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    """Logout do usuário"""
    logout_user()
    return redirect(url_for('login'))

# ===== ROTAS DE RECUPERAÇÃO DE SENHA =====


@app.route('/esqueci-senha', methods=['GET', 'POST'])
def esqueci_senha():
    """Página para solicitar recuperação de senha"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()

        if not email:
            return render_template('esqueci_senha.html', erro='Digite seu email')

        usuario = Usuario.query.filter_by(email=email).first()
        mensagem = '✅ Se esta conta existe, você receberá um email com instruções.'

        if usuario:
            enviar_email_recuperacao(email, usuario.nome)

        return render_template('esqueci_senha.html', mensagem=mensagem)

    return render_template('esqueci_senha.html')


@app.route('/recuperar-senha/<token>', methods=['GET', 'POST'])
def recuperar_senha(token):
    """Página para redefinir a senha"""
    email = verificar_token_recuperacao(token)

    if not email:
        return render_template('erro.html',
                               titulo='Link Inválido',
                               mensagem='O link expirou ou é inválido.',
                               codigo=400), 400

    usuario = Usuario.query.filter_by(email=email).first()
    if not usuario:
        return render_template('erro.html',
                               titulo='Usuário não encontrado',
                               mensagem='Este usuário não existe.',
                               codigo=404), 404

    if request.method == 'POST':
        nova_senha = request.form.get('nova_senha', '').strip()
        confirmar_senha = request.form.get('confirmar_senha', '').strip()

        if not nova_senha or not confirmar_senha:
            return render_template('recuperar_senha.html', token=token,
                                   erro='Todos os campos são obrigatórios!')

        if nova_senha != confirmar_senha:
            return render_template('recuperar_senha.html', token=token,
                                   erro='As senhas não coincidem!')

        if len(nova_senha) < 6:
            return render_template('recuperar_senha.html', token=token,
                                   erro='Mínimo 6 caracteres!')

        try:
            usuario.set_senha(nova_senha)
            db.session.commit()
            logger.info(f"Senha redefinida para: {email}")
            return render_template('recuperar_senha_sucesso.html', email=email)
        except Exception as e:
            logger.error(f"Erro: {str(e)}")
            db.session.rollback()
            return render_template('recuperar_senha.html', token=token,
                                   erro='Erro ao redefinir. Tente novamente.')

    return render_template('recuperar_senha.html', token=token)

# ===== FIM DAS ROTAS =====

# ===== ROTAS PRINCIPAIS =====


@app.route('/')
@app.route('/home', methods=['GET'])
@login_required
def home():
    """Página inicial com resumo financeiro"""
    transacoes = Transacao.query.filter_by(usuario_id=current_user.id).all()

    total_receitas = sum(t.valor for t in transacoes if t.tipo == 'Receita')
    total_despesas = sum(t.valor for t in transacoes if t.tipo == 'Despesa')

    bancos = Banco.query.filter_by(usuario_id=current_user.id).all()
    saldo_bancos = sum(banco.saldo for banco in bancos)

    transacoes_carteira = Transacao.query.filter_by(
        usuario_id=current_user.id, banco_id=None).all()
    receitas_carteira = sum(
        t.valor for t in transacoes_carteira if t.tipo == 'Receita')
    despesas_carteira = sum(
        t.valor for t in transacoes_carteira if t.tipo == 'Despesa')
    saldo_carteira = receitas_carteira - despesas_carteira

    saldo_total = saldo_bancos + saldo_carteira
    quantidade_transacoes = len(transacoes)

    return render_template('index.html',
                           total_receitas=total_receitas,
                           total_despesas=total_despesas,
                           saldo=saldo_total,
                           quantidade_transacoes=quantidade_transacoes)


@app.route('/transacoes')
@login_required
def lista_transacoes():
    transacoes = Transacao.query.filter_by(usuario_id=current_user.id).all()
    return render_template('transacoes.html', transacoes=transacoes)


@app.route('/adicionar', methods=['GET', 'POST'])
@login_required
def adicionar():
    cartoes = CartaoCredito.query.filter_by(usuario_id=current_user.id).all()
    categorias = Categoria.query.filter_by(usuario_id=current_user.id).all()
    bancos = Banco.query.filter_by(usuario_id=current_user.id).all()

    if request.method == 'POST':
        forma_pagamento = request.form.get('forma_pagamento')

        # Verificar se selecionou cartão de crédito mas não tem cartões
        if forma_pagamento == 'Cartão de Crédito' and not cartoes:
            flash('⚠️ Você precisa cadastrar um cartão de crédito primeiro!', 'warning')
            return redirect(url_for('criar_cartao'))

        # Verificar se selecionou banco mas não tem bancos
        banco_id = request.form.get('banco_id', type=int)
        if banco_id and banco_id > 0 and not bancos:
            flash('⚠️ Você precisa cadastrar um banco primeiro!', 'warning')
            return redirect(url_for('criar_banco'))

        descricao = request.form.get('descricao')
        valor_str = request.form.get('valor', '0').strip()
        valor_str = valor_str.replace('.', '').replace(',', '.')
        valor = float(valor_str)
        categoria = request.form.get('categoria')
        tipo = request.form.get('tipo')
        data = datetime.strptime(request.form.get('data'), '%Y-%m-%d').date()

        banco_id = request.form.get('banco_id', type=int)
        banco_id = banco_id if banco_id and banco_id > 0 else None

        # SEGURANÇA: Verificar se o banco pertence ao usuário
        if banco_id:
            banco = verificar_propriedade_banco(banco_id)

        eh_recorrente = request.form.get('eh_recorrente') == 'on'

        nova_transacao = Transacao(
            usuario_id=current_user.id,
            descricao=descricao,
            valor=valor,
            categoria=categoria,
            tipo=tipo,
            forma_pagamento=forma_pagamento,
            data=data,
            banco_id=banco_id
        )
        db.session.add(nova_transacao)
        db.session.commit()

        if tipo == 'Despesa' and banco_id:
            banco = Banco.query.get(banco_id)
            if banco:
                banco.saldo -= valor
                movimento = MovimentacaoBanco(
                    banco_id=banco_id,
                    tipo_movimento='saida',
                    valor=valor,
                    descricao=f'Despesa: {descricao}',
                    data=data
                )
                db.session.add(movimento)

        if tipo == 'Receita' and banco_id:
            banco = Banco.query.get(banco_id)
            if banco:
                banco.saldo += valor
                movimento = MovimentacaoBanco(
                    banco_id=banco_id,
                    tipo_movimento='entrada',
                    valor=valor,
                    descricao=f'Receita: {descricao}',
                    data=data
                )
                db.session.add(movimento)

        if eh_recorrente:
            frequencia = request.form.get('frequencia')
            dia_vencimento = request.form.get('dia_vencimento', type=int)
            data_fim_str = request.form.get('data_fim_recorrencia')
            data_fim = datetime.strptime(
                data_fim_str, '%Y-%m-%d').date() if data_fim_str else None

            nova_recorrencia = Recorrencia(
                usuario_id=current_user.id,
                descricao=descricao,
                valor=valor,
                tipo=tipo,
                categoria=categoria,
                forma_pagamento=forma_pagamento,
                frequencia=frequencia,
                dia_vencimento=dia_vencimento,
                data_inicio=data,
                data_fim=data_fim,
                ativa=True
            )
            db.session.add(nova_recorrencia)

        if forma_pagamento == 'Cartão de Crédito':
            cartao_id = request.form.get('cartao_id', type=int)

            # SEGURANÇA: Verificar se o cartão pertence ao usuário
            cartao = verificar_propriedade_cartao(cartao_id)

            quantidade_parcelas = request.form.get(
                'quantidade_parcelas', type=int, default=1)

            nova_compra = CompraCartao(
                usuario_id=current_user.id,
                cartao_id=cartao_id,
                descricao=descricao,
                valor_total=valor,
                quantidade_parcelas=quantidade_parcelas,
                data_compra=data,
                categoria=categoria,
                forma_pagamento=forma_pagamento
            )
            db.session.add(nova_compra)

        db.session.commit()
        return redirect(url_for('lista_transacoes'))

    return render_template('adicionar.html', cartoes=cartoes, categorias=categorias, bancos=bancos)


@app.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    # SEGURANÇA: Verificar propriedade
    transacao = verificar_propriedade_transacao(id)

    if request.method == 'POST':
        transacao.descricao = request.form.get('descricao')
        valor_str = request.form.get('valor', '0').strip()
        valor_str = valor_str.replace('.', '').replace(',', '.')
        valor = float(valor_str)
        transacao.categoria = request.form.get('categoria')
        transacao.tipo = request.form.get('tipo')
        transacao.forma_pagamento = request.form.get('forma_pagamento')
        transacao.data = datetime.strptime(
            request.form.get('data'), '%Y-%m-%d').date()

        db.session.commit()
        return redirect(url_for('lista_transacoes'))

    return render_template('editar.html', transacao=transacao)


@app.route('/deletar/<int:id>', methods=['POST'])
@login_required
def deletar(id):
    # SEGURANÇA: Verificar propriedade
    transacao = verificar_propriedade_transacao(id)
    db.session.delete(transacao)
    db.session.commit()
    return redirect(url_for('lista_transacoes'))

# ===== ROTAS DE RELATÓRIOS =====


@app.route('/relatorios', methods=['GET', 'POST'])
@login_required
def relatorios():
    data_inicio = request.args.get(
        'data_inicio') or request.form.get('data_inicio')
    data_fim = request.args.get('data_fim') or request.form.get('data_fim')
    categoria_filtro = request.args.get(
        'categoria') or request.form.get('categoria')
    tipo_filtro = request.args.get('tipo') or request.form.get('tipo')

    query = Transacao.query.filter_by(usuario_id=current_user.id)

    if data_inicio:
        data_inicio_obj = datetime.strptime(data_inicio, '%Y-%m-%d').date()
        query = query.filter(Transacao.data >= data_inicio_obj)

    if data_fim:
        data_fim_obj = datetime.strptime(data_fim, '%Y-%m-%d').date()
        query = query.filter(Transacao.data <= data_fim_obj)

    if categoria_filtro and categoria_filtro != 'Todas':
        query = query.filter(Transacao.categoria == categoria_filtro)

    if tipo_filtro and tipo_filtro != 'Todos':
        query = query.filter(Transacao.tipo == tipo_filtro)

    transacoes = query.order_by(Transacao.data.desc()).all()

    total_receitas = sum(t.valor for t in transacoes if t.tipo == 'Receita')
    total_despesas = sum(t.valor for t in transacoes if t.tipo == 'Despesa')
    saldo = total_receitas - total_despesas
    quantidade_transacoes = len(transacoes)

    todas_as_categorias = db.session.query(Transacao.categoria).filter_by(
        usuario_id=current_user.id).distinct().all()
    categorias = sorted([cat[0] for cat in todas_as_categorias])

    grafico_pizza = {
        'labels': ['Receitas', 'Despesas'],
        'valores': [total_receitas, total_despesas],
        'cores': ['#10b981', '#ef4444']
    }

    categoria_totais = {}
    for transacao in transacoes:
        if transacao.categoria not in categoria_totais:
            categoria_totais[transacao.categoria] = {
                'receita': 0, 'despesa': 0}

        if transacao.tipo == 'Receita':
            categoria_totais[transacao.categoria]['receita'] += transacao.valor
        else:
            categoria_totais[transacao.categoria]['despesa'] += transacao.valor

    categorias_labels = list(categoria_totais.keys())
    categorias_receitas = [categoria_totais[cat]['receita']
                           for cat in categorias_labels]
    categorias_despesas = [categoria_totais[cat]['despesa']
                           for cat in categorias_labels]

    grafico_barras = {
        'labels': categorias_labels,
        'receitas': categorias_receitas,
        'despesas': categorias_despesas
    }

    dias_totais = {}
    for transacao in transacoes:
        data_str = transacao.data.strftime('%d/%m/%Y')
        if data_str not in dias_totais:
            dias_totais[data_str] = {'receita': 0, 'despesa': 0}

        if transacao.tipo == 'Receita':
            dias_totais[data_str]['receita'] += transacao.valor
        else:
            dias_totais[data_str]['despesa'] += transacao.valor

    dias_ordenados = sorted(dias_totais.items(),
                            key=lambda x: datetime.strptime(x[0], '%d/%m/%Y'))

    dias_labels = [item[0] for item in dias_ordenados]
    dias_receitas = [item[1]['receita'] for item in dias_ordenados]
    dias_despesas = [item[1]['despesa'] for item in dias_ordenados]

    grafico_linha = {
        'labels': dias_labels,
        'receitas': dias_receitas,
        'despesas': dias_despesas
    }

    return render_template('relatorios.html',
                           transacoes=transacoes,
                           total_receitas=total_receitas,
                           total_despesas=total_despesas,
                           saldo=saldo,
                           quantidade_transacoes=quantidade_transacoes,
                           data_inicio=data_inicio,
                           data_fim=data_fim,
                           categoria_selecionada=categoria_filtro,
                           tipo_selecionado=tipo_filtro,
                           categorias=categorias,
                           grafico_pizza=grafico_pizza,
                           grafico_barras=grafico_barras,
                           grafico_linha=grafico_linha)

# ===== ROTAS DE ORÇAMENTOS =====


@app.route('/orcamentos', methods=['GET', 'POST'])
@login_required
def orcamentos():
    mes_atual = request.args.get('mes', type=int) or date.today().month
    ano_atual = request.args.get('ano', type=int) or date.today().year

    orcamentos_lista = Orcamento.query.filter_by(
        usuario_id=current_user.id, mes=mes_atual, ano=ano_atual).all()

    gastos_por_categoria = db.session.query(
        Transacao.categoria,
        func.sum(Transacao.valor)
    ).filter(
        Transacao.usuario_id == current_user.id,
        extract('month', Transacao.data) == mes_atual,
        extract('year', Transacao.data) == ano_atual,
        Transacao.tipo == 'Despesa'
    ).group_by(Transacao.categoria).all()

    gastos_dict = {cat: valor for cat, valor in gastos_por_categoria}

    orcamentos_info = []
    for orc in orcamentos_lista:
        gasto = gastos_dict.get(orc.categoria, 0)
        percentual = (gasto / orc.limite_mensal *
                      100) if orc.limite_mensal > 0 else 0
        status = 'em_dia'

        if percentual > 100:
            status = 'excedido'
        elif percentual > 80:
            status = 'alerta'

        orcamentos_info.append({
            'id': orc.id,
            'categoria': orc.categoria,
            'limite': orc.limite_mensal,
            'gasto': gasto,
            'restante': orc.limite_mensal - gasto,
            'percentual': min(percentual, 100),
            'percentual_real': percentual,
            'status': status
        })

    todas_as_categorias = db.session.query(Transacao.categoria).filter_by(
        usuario_id=current_user.id).distinct().all()
    categorias = sorted([cat[0] for cat in todas_as_categorias])

    total_limites = sum(orc['limite'] for orc in orcamentos_info)
    total_gasto = sum(orc['gasto'] for orc in orcamentos_info)
    total_restante = total_limites - total_gasto

    return render_template('orcamentos.html',
                           orcamentos_info=orcamentos_info,
                           categorias=categorias,
                           mes_selecionado=mes_atual,
                           ano_selecionado=ano_atual,
                           total_limites=total_limites,
                           total_gasto=total_gasto,
                           total_restante=total_restante)


@app.route('/orcamentos/criar', methods=['GET', 'POST'])
@login_required
def criar_orcamento():
    if request.method == 'POST':
        categoria = request.form.get('categoria')
        limite_str = request.form.get('limite', '0').strip()
        limite_str = limite_str.replace('.', '').replace(',', '.')
        limite = float(limite_str)
        mes = request.form.get('mes', type=int)
        ano = request.form.get('ano', type=int)

        orc_existente = Orcamento.query.filter_by(
            usuario_id=current_user.id, categoria=categoria, mes=mes, ano=ano).first()

        if orc_existente:
            orc_existente.limite_mensal = limite
            db.session.commit()
        else:
            novo_orcamento = Orcamento(
                usuario_id=current_user.id, categoria=categoria, limite_mensal=limite, mes=mes, ano=ano)
            db.session.add(novo_orcamento)
            db.session.commit()

        return redirect(url_for('orcamentos', mes=mes, ano=ano))

    mes_atual = date.today().month
    ano_atual = date.today().year

    todas_as_categorias = db.session.query(Transacao.categoria).filter_by(
        usuario_id=current_user.id).distinct().all()
    categorias = sorted([cat[0] for cat in todas_as_categorias])

    return render_template('criar_orcamento.html', categorias=categorias, mes_padrao=mes_atual, ano_padrao=ano_atual)


@app.route('/orcamentos/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_orcamento(id):
    # SEGURANÇA: Verificar propriedade
    orcamento = verificar_propriedade_orcamento(id)

    if request.method == 'POST':
        limite_str = request.form.get('limite', '0').strip()
        limite_str = limite_str.replace('.', '').replace(',', '.')
        limite = float(limite_str)

        orcamento.limite_mensal = limite
        db.session.commit()

        return redirect(url_for('orcamentos', mes=orcamento.mes, ano=orcamento.ano))

    return render_template('editar_orcamento.html', orcamento=orcamento)


@app.route('/orcamentos/deletar/<int:id>', methods=['POST'])
@login_required
def deletar_orcamento(id):
    # SEGURANÇA: Verificar propriedade
    orcamento = verificar_propriedade_orcamento(id)
    mes = orcamento.mes
    ano = orcamento.ano

    db.session.delete(orcamento)
    db.session.commit()

    return redirect(url_for('orcamentos', mes=mes, ano=ano))

# ===== ROTAS DE CATEGORIAS =====


@app.route('/categorias', methods=['GET'])
@login_required
def categorias():
    categorias_lista = Categoria.query.filter_by(
        usuario_id=current_user.id).all()
    return render_template('categorias.html', categorias=categorias_lista)


@app.route('/categorias/criar', methods=['GET', 'POST'])
@login_required
def criar_categoria():
    if request.method == 'POST':
        nome = request.form.get('nome')
        descricao = request.form.get('descricao', '')

        nova_categoria = Categoria(
            usuario_id=current_user.id, nome=nome, descricao=descricao)
        db.session.add(nova_categoria)
        db.session.commit()

        return redirect(url_for('categorias'))

    return render_template('criar_categoria.html')


@app.route('/categorias/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_categoria(id):
    # SEGURANÇA: Verificar propriedade
    categoria = verificar_propriedade_categoria(id)

    if request.method == 'POST':
        nome = request.form.get('nome')
        descricao = request.form.get('descricao', '')

        categoria_existente = Categoria.query.filter_by(
            usuario_id=current_user.id, nome=nome).first()
        if categoria_existente and categoria_existente.id != id:
            return render_template('editar_categoria.html', categoria=categoria, erro='Nome já existe!')

        categoria.nome = nome
        categoria.descricao = descricao

        db.session.commit()
        return redirect(url_for('categorias'))

    return render_template('editar_categoria.html', categoria=categoria)


@app.route('/categorias/deletar/<int:id>', methods=['POST'])
@login_required
def deletar_categoria(id):
    # SEGURANÇA: Verificar propriedade
    categoria = verificar_propriedade_categoria(id)

    transacoes = Transacao.query.filter_by(
        usuario_id=current_user.id, categoria=categoria.nome).first()
    compras = CompraCartao.query.filter_by(
        usuario_id=current_user.id, categoria=categoria.nome).first()
    orcamentos = Orcamento.query.filter_by(
        usuario_id=current_user.id, categoria=categoria.nome).first()

    if transacoes or compras or orcamentos:
        return redirect(url_for('categorias'))

    db.session.delete(categoria)
    db.session.commit()

    return redirect(url_for('categorias'))

# ===== ROTAS DE RECORRÊNCIAS =====


@app.route('/recorrencias', methods=['GET'])
@login_required
def recorrencias():
    recorrencias_lista = Recorrencia.query.filter_by(
        usuario_id=current_user.id, ativa=True).all()
    return render_template('recorrencias.html', recorrencias=recorrencias_lista)


@app.route('/recorrencias/criar', methods=['GET', 'POST'])
@login_required
def criar_recorrencia():
    if request.method == 'POST':
        descricao = request.form.get('descricao')
        valor_str = request.form.get('valor', '0').strip()
        valor_str = valor_str.replace('.', '').replace(',', '.')
        valor = float(valor_str)
        tipo = request.form.get('tipo')
        categoria = request.form.get('categoria')
        forma_pagamento = request.form.get('forma_pagamento')
        frequencia = request.form.get('frequencia')
        dia_vencimento = request.form.get('dia_vencimento', type=int)
        data_inicio = datetime.strptime(
            request.form.get('data_inicio'), '%Y-%m-%d').date()
        data_fim_str = request.form.get('data_fim')
        data_fim = datetime.strptime(
            data_fim_str, '%Y-%m-%d').date() if data_fim_str else None

        nova_recorrencia = Recorrencia(
            usuario_id=current_user.id,
            descricao=descricao,
            valor=valor,
            tipo=tipo,
            categoria=categoria,
            forma_pagamento=forma_pagamento,
            frequencia=frequencia,
            dia_vencimento=dia_vencimento,
            data_inicio=data_inicio,
            data_fim=data_fim,
            ativa=True
        )

        db.session.add(nova_recorrencia)
        db.session.commit()

        return redirect(url_for('recorrencias'))

    categorias = Categoria.query.filter_by(usuario_id=current_user.id).all()
    return render_template('criar_recorrencia.html', categorias=categorias)


@app.route('/recorrencias/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_recorrencia(id):
    # SEGURANÇA: Verificar propriedade
    recorrencia = verificar_propriedade_recorrencia(id)

    if request.method == 'POST':
        recorrencia.descricao = request.form.get('descricao')
        valor_str = request.form.get('valor', '0').strip()
        valor_str = valor_str.replace('.', '').replace(',', '.')
        recorrencia.valor = float(valor_str)
        recorrencia.tipo = request.form.get('tipo')
        recorrencia.categoria = request.form.get('categoria')
        recorrencia.forma_pagamento = request.form.get('forma_pagamento')
        recorrencia.frequencia = request.form.get('frequencia')
        recorrencia.dia_vencimento = request.form.get(
            'dia_vencimento', type=int)
        recorrencia.data_inicio = datetime.strptime(
            request.form.get('data_inicio'), '%Y-%m-%d').date()
        data_fim_str = request.form.get('data_fim')
        recorrencia.data_fim = datetime.strptime(
            data_fim_str, '%Y-%m-%d').date() if data_fim_str else None

        db.session.commit()

        return redirect(url_for('recorrencias'))

    categorias = Categoria.query.filter_by(usuario_id=current_user.id).all()
    return render_template('editar_recorrencia.html', recorrencia=recorrencia, categorias=categorias)


@app.route('/recorrencias/deletar/<int:id>', methods=['POST'])
@login_required
def deletar_recorrencia(id):
    # SEGURANÇA: Verificar propriedade
    recorrencia = verificar_propriedade_recorrencia(id)
    recorrencia.ativa = False
    db.session.commit()

    return redirect(url_for('recorrencias'))


@app.route('/projecao', methods=['GET'])
@login_required
def projecao():
    mes_selecionado = request.args.get('mes', type=int) or date.today().month
    ano_selecionado = request.args.get('ano', type=int) or date.today().year

    recorrencias = Recorrencia.query.filter_by(
        usuario_id=current_user.id, ativa=True).all()

    projecao_meses = {}

    for offset in range(12):
        mes_projecao = mes_selecionado + offset
        ano_projecao = ano_selecionado

        while mes_projecao > 12:
            mes_projecao -= 12
            ano_projecao += 1

        data_projecao = date(ano_projecao, mes_projecao, 1)
        chave_mes = f"{ano_projecao}-{mes_projecao:02d}"

        mes_nomes = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
                     'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']

        projecao_meses[chave_mes] = {
            'mes': mes_nomes[mes_projecao - 1],
            'ano': ano_projecao,
            'mes_numero': mes_projecao,
            'receitas': [],
            'despesas': [],
            'total_receitas': 0.0,
            'total_despesas': 0.0,
            'saldo': 0.0
        }

        for rec in recorrencias:
            if rec.data_inicio > data_projecao:
                continue
            if rec.data_fim and rec.data_fim < data_projecao:
                continue

            meses_desde_inicio = (ano_projecao - rec.data_inicio.year) * \
                12 + (mes_projecao - rec.data_inicio.month)

            ocorre = False
            if rec.frequencia == 'mensal':
                ocorre = True
            elif rec.frequencia == 'bimestral' and meses_desde_inicio % 2 == 0:
                ocorre = True
            elif rec.frequencia == 'trimestral' and meses_desde_inicio % 3 == 0:
                ocorre = True
            elif rec.frequencia == 'semestral' and meses_desde_inicio % 6 == 0:
                ocorre = True
            elif rec.frequencia == 'anual' and meses_desde_inicio % 12 == 0:
                ocorre = True

            if ocorre:
                item = {
                    'id': rec.id,
                    'descricao': rec.descricao,
                    'valor': rec.valor,
                    'categoria': rec.categoria,
                    'forma_pagamento': rec.forma_pagamento,
                    'dia_vencimento': rec.dia_vencimento
                }

                if rec.tipo == 'Receita':
                    projecao_meses[chave_mes]['receitas'].append(item)
                    projecao_meses[chave_mes]['total_receitas'] += rec.valor
                else:
                    projecao_meses[chave_mes]['despesas'].append(item)
                    projecao_meses[chave_mes]['total_despesas'] += rec.valor

        projecao_meses[chave_mes]['saldo'] = projecao_meses[chave_mes]['total_receitas'] - \
            projecao_meses[chave_mes]['total_despesas']

    chave_selecionada = f"{ano_selecionado}-{mes_selecionado:02d}"
    meses_exibicao = {}

    encontrou = False
    for chave in sorted(projecao_meses.keys()):
        if encontrou or chave == chave_selecionada:
            encontrou = True
            if len(meses_exibicao) < 4:
                meses_exibicao[chave] = projecao_meses[chave]

    return render_template('projecao.html',
                           meses=meses_exibicao,
                           mes_selecionado=mes_selecionado,
                           ano_selecionado=ano_selecionado)

# ===== ROTAS DE BANCOS =====


@app.route('/bancos', methods=['GET'])
@login_required
def bancos():
    bancos_lista = Banco.query.filter_by(usuario_id=current_user.id).all()
    total_geral = sum(banco.saldo for banco in bancos_lista)

    return render_template('bancos.html', bancos=bancos_lista, total_geral=total_geral)


@app.route('/bancos/criar', methods=['GET', 'POST'])
@login_required
def criar_banco():
    if request.method == 'POST':
        nome = request.form.get('nome')
        saldo_str = request.form.get('saldo', '0').strip()
        saldo_str = saldo_str.replace('.', '').replace(',', '.')
        saldo = float(saldo_str)
        tipo = request.form.get('tipo')
        descricao = request.form.get('descricao', '')

        novo_banco = Banco(usuario_id=current_user.id, nome=nome,
                           saldo=saldo, tipo=tipo, descricao=descricao)

        if saldo > 0:
            movimento = MovimentacaoBanco(
                banco_id=None,
                tipo_movimento='entrada',
                valor=saldo,
                descricao='Saldo inicial',
                data=date.today()
            )
            db.session.add(novo_banco)
            db.session.flush()
            movimento.banco_id = novo_banco.id
            db.session.add(movimento)
        else:
            db.session.add(novo_banco)

        db.session.commit()
        return redirect(url_for('bancos'))

    return render_template('criar_banco.html')


@app.route('/bancos/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_banco(id):
    # SEGURANÇA: Verificar propriedade
    banco = verificar_propriedade_banco(id)

    if request.method == 'POST':
        banco.nome = request.form.get('nome')
        banco.tipo = request.form.get('tipo')
        banco.descricao = request.form.get('descricao', '')

        db.session.commit()
        return redirect(url_for('bancos'))

    return render_template('editar_banco.html', banco=banco)


@app.route('/bancos/deletar/<int:id>', methods=['POST'])
@login_required
def deletar_banco(id):
    # SEGURANÇA: Verificar propriedade
    banco = verificar_propriedade_banco(id)

    if banco.movimentacoes:
        return redirect(url_for('bancos'))

    db.session.delete(banco)
    db.session.commit()

    return redirect(url_for('bancos'))


@app.route('/bancos/<int:id>/movimentacoes', methods=['GET'])
@login_required
def movimentacoes_banco(id):
    # SEGURANÇA: Verificar propriedade
    banco = verificar_propriedade_banco(id)
    movimentacoes = MovimentacaoBanco.query.filter_by(
        banco_id=id).order_by(MovimentacaoBanco.data.desc()).all()

    return render_template('movimentacoes_banco.html', banco=banco, movimentacoes=movimentacoes)


@app.route('/bancos/<int:id>/adicionar-saldo', methods=['GET', 'POST'])
@login_required
def adicionar_saldo(id):
    # SEGURANÇA: Verificar propriedade
    banco = verificar_propriedade_banco(id)

    if request.method == 'POST':
        valor_str = request.form.get('valor', '0').strip()
        valor_str = valor_str.replace('.', '').replace(',', '.')
        valor = float(valor_str)
        descricao = request.form.get('descricao')
        data = datetime.strptime(request.form.get('data'), '%Y-%m-%d').date()

        banco.saldo += valor

        movimento = MovimentacaoBanco(
            banco_id=id,
            tipo_movimento='entrada',
            valor=valor,
            descricao=descricao,
            data=data
        )

        db.session.add(movimento)
        db.session.commit()

        return redirect(url_for('movimentacoes_banco', id=id))

    return render_template('adicionar_saldo.html', banco=banco)


@app.route('/bancos/<int:id>/sacar-saldo', methods=['GET', 'POST'])
@login_required
def sacar_saldo(id):
    # SEGURANÇA: Verificar propriedade
    banco = verificar_propriedade_banco(id)

    if request.method == 'POST':
        valor_str = request.form.get('valor', '0').strip()
        valor_str = valor_str.replace('.', '').replace(',', '.')
        valor = float(valor_str)
        descricao = request.form.get('descricao')
        data = datetime.strptime(request.form.get('data'), '%Y-%m-%d').date()

        if banco.saldo < valor:
            return render_template('sacar_saldo.html', banco=banco, erro='Saldo insuficiente!')

        banco.saldo -= valor

        movimento = MovimentacaoBanco(
            banco_id=id,
            tipo_movimento='saida',
            valor=valor,
            descricao=descricao,
            data=data
        )

        db.session.add(movimento)
        db.session.commit()

        return redirect(url_for('movimentacoes_banco', id=id))

    return render_template('sacar_saldo.html', banco=banco)


@app.route('/bancos/transferencia', methods=['GET', 'POST'])
@login_required
def transferencia():
    if request.method == 'POST':
        banco_origem_id = request.form.get('banco_origem', type=int)
        banco_destino_id = request.form.get('banco_destino', type=int)

        # SEGURANÇA: Verificar propriedade
        banco_origem = verificar_propriedade_banco(banco_origem_id)
        banco_destino = verificar_propriedade_banco(banco_destino_id)

        valor_str = request.form.get('valor', '0').strip()
        valor_str = valor_str.replace('.', '').replace(',', '.')
        valor = float(valor_str)
        descricao = request.form.get('descricao')
        data = datetime.strptime(request.form.get('data'), '%Y-%m-%d').date()

        if banco_origem.saldo < valor:
            bancos_lista = Banco.query.filter_by(
                usuario_id=current_user.id).all()
            return render_template('transferencia.html', bancos=bancos_lista, erro='Saldo insuficiente!')

        banco_origem.saldo -= valor
        banco_destino.saldo += valor

        movimento_saida = MovimentacaoBanco(
            banco_id=banco_origem_id,
            tipo_movimento='saida',
            valor=valor,
            descricao=f'Transferência para {banco_destino.nome}',
            data=data
        )

        movimento_entrada = MovimentacaoBanco(
            banco_id=banco_destino_id,
            tipo_movimento='entrada',
            valor=valor,
            descricao=f'Transferência de {banco_origem.nome}',
            data=data
        )

        db.session.add(movimento_saida)
        db.session.add(movimento_entrada)
        db.session.commit()

        return redirect(url_for('bancos'))

    bancos_lista = Banco.query.filter_by(usuario_id=current_user.id).all()

    # Verificar se tem pelo menos 2 bancos
    if len(bancos_lista) < 2:
        flash('⚠️ Você precisa ter pelo menos 2 bancos cadastrados para fazer transferência!', 'warning')
        return redirect(url_for('bancos'))

    return render_template('transferencia.html', bancos=bancos_lista)

# ===== ROTAS DE CARTÃO DE CRÉDITO =====


@app.route('/cartoes', methods=['GET'])
@login_required
def cartoes():
    cartoes_lista = CartaoCredito.query.filter_by(
        usuario_id=current_user.id).all()
    return render_template('cartoes.html', cartoes=cartoes_lista)


@app.route('/cartoes/criar', methods=['GET', 'POST'])
@login_required
def criar_cartao():
    if request.method == 'POST':
        nome = request.form.get('nome')
        dia_fechamento = request.form.get('dia_fechamento', type=int)
        dia_vencimento = request.form.get('dia_vencimento', type=int)

        novo_cartao = CartaoCredito(usuario_id=current_user.id, nome=nome,
                                    dia_fechamento=dia_fechamento, dia_vencimento=dia_vencimento)

        db.session.add(novo_cartao)
        db.session.commit()

        return redirect(url_for('cartoes'))

    return render_template('criar_cartao.html')


@app.route('/cartoes/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_cartao(id):
    # SEGURANÇA: Verificar propriedade
    cartao = verificar_propriedade_cartao(id)

    if request.method == 'POST':
        cartao.nome = request.form.get('nome')
        cartao.dia_fechamento = request.form.get('dia_fechamento', type=int)
        cartao.dia_vencimento = request.form.get('dia_vencimento', type=int)

        db.session.commit()

        return redirect(url_for('cartoes'))

    return render_template('editar_cartao.html', cartao=cartao)


@app.route('/cartoes/deletar/<int:id>', methods=['POST'])
@login_required
def deletar_cartao(id):
    # SEGURANÇA: Verificar propriedade
    cartao = verificar_propriedade_cartao(id)

    compras = CompraCartao.query.filter_by(cartao_id=id).first()
    if compras:
        return redirect(url_for('cartoes'))

    db.session.delete(cartao)
    db.session.commit()

    return redirect(url_for('cartoes'))


@app.route('/compras-cartao', methods=['GET'])
@login_required
def compras_cartao():
    compras = CompraCartao.query.filter_by(usuario_id=current_user.id).all()

    compras_por_cartao = {}
    for compra in compras:
        if compra.cartao.id not in compras_por_cartao:
            compras_por_cartao[compra.cartao.id] = {
                'cartao': compra.cartao,
                'compras': []
            }

        valor_parcela = compra.valor_total / compra.quantidade_parcelas

        compras_por_cartao[compra.cartao.id]['compras'].append({
            'id': compra.id,
            'descricao': compra.descricao,
            'valor_total': compra.valor_total,
            'quantidade_parcelas': compra.quantidade_parcelas,
            'valor_parcela': valor_parcela,
            'data_compra': compra.data_compra,
            'categoria': compra.categoria,
            'status': compra.status
        })

    return render_template('compras_cartao.html', compras_por_cartao=compras_por_cartao)


@app.route('/compras-cartao/criar', methods=['GET', 'POST'])
@login_required
def criar_compra_cartao():
    from flask import flash

    cartoes = CartaoCredito.query.filter_by(usuario_id=current_user.id).all()
    categorias = Categoria.query.filter_by(usuario_id=current_user.id).all()

    # Verificar se tem cartões cadastrados
    if not cartoes:
        flash('⚠️ Você precisa cadastrar um cartão de crédito primeiro!', 'warning')
        return redirect(url_for('criar_cartao'))

    if request.method == 'POST':
        cartao_id = request.form.get('cartao_id', type=int)

        # SEGURANÇA: Verificar propriedade
        cartao = verificar_propriedade_cartao(cartao_id)

        descricao = request.form.get('descricao')
        valor_str = request.form.get('valor', '0').strip()
        valor_str = valor_str.replace('.', '').replace(',', '.')
        valor_total = float(valor_str)
        quantidade_parcelas = request.form.get(
            'quantidade_parcelas', type=int, default=1)
        categoria = request.form.get('categoria')
        data_compra = datetime.strptime(
            request.form.get('data_compra'), '%Y-%m-%d').date()

        nova_compra = CompraCartao(
            usuario_id=current_user.id,
            cartao_id=cartao_id,
            descricao=descricao,
            valor_total=valor_total,
            quantidade_parcelas=quantidade_parcelas,
            data_compra=data_compra,
            categoria=categoria,
            forma_pagamento='Cartão de Crédito'
        )

        db.session.add(nova_compra)
        db.session.commit()

        return redirect(url_for('compras_cartao'))

    return render_template('criar_compra_cartao.html', cartoes=cartoes, categorias=categorias)


@app.route('/compras-cartao/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_compra_cartao(id):
    # SEGURANÇA: Verificar propriedade
    compra = verificar_propriedade_compra(id)

    if request.method == 'POST':
        compra.descricao = request.form.get('descricao')
        valor_str = request.form.get('valor', '0').strip()
        valor_str = valor_str.replace('.', '').replace(',', '.')
        compra.valor_total = float(valor_str)
        compra.quantidade_parcelas = request.form.get(
            'quantidade_parcelas', type=int)
        compra.categoria = request.form.get('categoria')
        compra.data_compra = datetime.strptime(
            request.form.get('data_compra'), '%Y-%m-%d').date()

        db.session.commit()

        return redirect(url_for('compras_cartao'))

    cartoes = CartaoCredito.query.filter_by(usuario_id=current_user.id).all()
    categorias = Categoria.query.filter_by(usuario_id=current_user.id).all()

    return render_template('editar_compra_cartao.html', compra=compra, cartoes=cartoes, categorias=categorias)


@app.route('/compras-cartao/deletar/<int:id>', methods=['POST'])
@login_required
def deletar_compra_cartao(id):
    # SEGURANÇA: Verificar propriedade
    compra = verificar_propriedade_compra(id)
    db.session.delete(compra)
    db.session.commit()

    return redirect(url_for('compras_cartao'))


@app.route('/dividas-parceladas', methods=['GET'])
@login_required
def dividas_parceladas():
    mes_selecionado = request.args.get('mes', type=int) or date.today().month
    ano_selecionado = request.args.get('ano', type=int) or date.today().year

    compras = CompraCartao.query.filter_by(
        usuario_id=current_user.id, status='aberta').all()

    # Verificar se tem dívidas parceladas
    if not compras:
        flash('ℹ️ Você não tem dívidas parceladas no momento.', 'info')
        return redirect(url_for('cartoes'))

    dividas_por_mes = {}

    for compra in compras:
        if compra.quantidade_parcelas == 1:
            continue

        cartao = compra.cartao
        valor_parcela = compra.valor_total / compra.quantidade_parcelas

        for num_parcela in range(1, compra.quantidade_parcelas + 1):
            meses_adiante = num_parcela

            ano_parcela = compra.data_compra.year
            mes_parcela = compra.data_compra.month + meses_adiante

            while mes_parcela > 12:
                mes_parcela -= 12
                ano_parcela += 1

            dia_fechamento = cartao.dia_fechamento
            _, ultimo_dia_mes = monthrange(ano_parcela, mes_parcela)
            dia_fechamento = min(dia_fechamento, ultimo_dia_mes)

            dia_vencimento = cartao.dia_vencimento
            dia_vencimento = min(dia_vencimento, ultimo_dia_mes)

            data_fechamento = date(ano_parcela, mes_parcela, dia_fechamento)
            data_vencimento = date(ano_parcela, mes_parcela, dia_vencimento)

            chave_mes = f"{ano_parcela}-{mes_parcela:02d}"
            mes_nomes = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
                         'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
            mes_nome = mes_nomes[mes_parcela - 1]

            if chave_mes not in dividas_por_mes:
                dividas_por_mes[chave_mes] = {
                    'mes': mes_nome,
                    'mes_numero': mes_parcela,
                    'ano': ano_parcela,
                    'data_fechamento': data_fechamento,
                    'data_vencimento': data_vencimento,
                    'parcelas': [],
                    'total_mes': 0
                }

            divida = {
                'id': compra.id,
                'descricao': compra.descricao,
                'cartao': compra.cartao.nome,
                'numero_parcela': num_parcela,
                'quantidade_parcelas': compra.quantidade_parcelas,
                'parcelas_faltando': compra.quantidade_parcelas - num_parcela,
                'valor_parcela': valor_parcela,
                'data_compra': compra.data_compra,
                'categoria': compra.categoria,
                'data_fechamento': data_fechamento,
                'data_vencimento': data_vencimento
            }

            dividas_por_mes[chave_mes]['parcelas'].append(divida)
            dividas_por_mes[chave_mes]['total_mes'] += valor_parcela

    chave_selecionada = f"{ano_selecionado}-{mes_selecionado:02d}"
    mes_selecionado_data = dividas_por_mes.get(chave_selecionada, None)

    if mes_selecionado_data:
        total_dividas = mes_selecionado_data['total_mes']
        total_parcelas = len(mes_selecionado_data['parcelas'])
    else:
        total_dividas = 0
        total_parcelas = 0

    meses_disponiveis = sorted(dividas_por_mes.keys())

    return render_template('dividas_parceladas.html',
                           mes_selecionado_data=mes_selecionado_data,
                           meses_disponiveis=meses_disponiveis,
                           mes_selecionado=mes_selecionado,
                           ano_selecionado=ano_selecionado,
                           total_dividas=total_dividas,
                           total_parcelas=total_parcelas)

# ===== ERROR HANDLERS =====


@app.errorhandler(403)
def acesso_negado(e):
    """Erro 403 - Acesso Negado"""
    return render_template('erro.html',
                           titulo='Acesso Negado',
                           mensagem='Você não tem permissão para acessar este recurso.',
                           codigo=403), 403


@app.errorhandler(404)
def pagina_nao_encontrada(e):
    """Erro 404 - Página não encontrada"""
    return render_template('erro.html',
                           titulo='Página não encontrada',
                           mensagem='A página que você procura não existe.',
                           codigo=404), 404


@app.errorhandler(500)
def erro_interno(e):
    """Erro 500 - Erro interno do servidor"""
    db.session.rollback()
    return render_template('erro.html',
                           titulo='Erro interno',
                           mensagem='Ocorreu um erro no servidor. Tente novamente mais tarde.',
                           codigo=500), 500


# Criar as tabelas na inicialização
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=False, port=5000)
