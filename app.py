from flask import Flask, render_template, request, redirect, url_for, abort
from models import db, Transacao, Usuario, Banco, MovimentacaoBanco, CartaoCredito, CompraCartao, Categoria, Recorrencia, Orcamento, FaturaCartao, TransacaoFatura, PagamentoFatura
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
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
# ===== FUNÇÃO PARA CONVERTER VALORES COM VÍRGULA OU PONTO =====

def parse_valor(valor_str):
    """Converte string com vírgula ou ponto para float"""
    if not valor_str or not str(valor_str).strip():
        return 0.0

    valor_str = str(valor_str).strip()

    # Se tem vírgula, substitui por ponto
    # Se tem ponto antes de vírgula, remove o ponto
    if ',' in valor_str:
        # Formato: 250,99 ou 1.250,99
        valor_str = valor_str.replace('.', '').replace(',', '.')
    else:
        # Formato: 250.99 ou 250
        valor_str = valor_str.replace(',', '')

    try:
        return float(valor_str)
    except ValueError:
        return 0.0

# ===== FIM DA FUNÇÃO =====

# ===== FUNÇÃO PARA GERENCIAR FATURAS =====


def criar_ou_atualizar_fatura(usuario_id, cartao_id, data_compra, valor):
    """
    Cria ou atualiza a fatura do cartão.

    LÓGICA CORRIGIDA (FINAL):
    - Compra ANTES do dia de fechamento (dia 24) → Entra na fatura de ESTE MÊS
    - Compra DEPOIS do dia de fechamento (dia 24) → Entra na fatura do PRÓXIMO MÊS

    Exemplo com fechamento dia 24:
    - Compra em 18/11 (ANTES) → Fatura de NOVEMBRO (fecha 24/11, vence 05/12)
    - Compra em 25/11 (DEPOIS) → Fatura de DEZEMBRO (fecha 24/12, vence 05/01)
    """
    cartao = CartaoCredito.query.get(cartao_id)

    if not cartao:
        print(f"❌ Cartão com ID {cartao_id} não encontrado!")
        return None

    # ✅ LÓGICA CORRIGIDA FINAL:
    # Se compra é ANTES ou NO dia de fechamento = fatura DESTE MÊS
    # Se compra é DEPOIS do dia de fechamento = fatura do PRÓXIMO MÊS
    if data_compra.day <= cartao.dia_fechamento:
        # Compra ANTES ou NO fechamento = fatura DESTE MÊS
        mes = data_compra.month
        ano = data_compra.year
    else:
        # Compra DEPOIS do fechamento = fatura do PRÓXIMO MÊS
        proximo_mes = data_compra + relativedelta(months=1)
        mes = proximo_mes.month
        ano = proximo_mes.year

    # Calcular datas da fatura
    _, ultimo_dia = monthrange(ano, mes)
    dia_fechamento = min(cartao.dia_fechamento, ultimo_dia)

    data_fechamento = date(ano, mes, dia_fechamento)

    # ✅ Data de vencimento = MÊS SEGUINTE após o fechamento
    # Exemplo: Se fecha em 24/11, vence em 05/12
    mes_vencimento = mes + 1 if mes < 12 else 1
    ano_vencimento = ano if mes < 12 else ano + 1
    _, ultimo_dia_venc = monthrange(ano_vencimento, mes_vencimento)
    dia_vencimento_calc = min(cartao.dia_vencimento, ultimo_dia_venc)
    data_vencimento = date(ano_vencimento, mes_vencimento, dia_vencimento_calc)

    print(f"DEBUG: Fatura {mes}/{ano}")
    print(f"       Fecha: {data_fechamento}")
    print(
        f"       Vence em: {mes_vencimento}/{ano_vencimento}, dia {dia_vencimento_calc}")
    print(f"       Data Vencimento: {data_vencimento}")

    # Procurar ou criar fatura
    fatura = FaturaCartao.query.filter_by(
        usuario_id=usuario_id,
        cartao_id=cartao_id,
        mes=mes,
        ano=ano
    ).first()

    if not fatura:
        # ✅ Criar nova fatura
        fatura = FaturaCartao(
            usuario_id=usuario_id,
            cartao_id=cartao_id,
            mes=mes,
            ano=ano,
            data_fechamento=data_fechamento,
            data_vencimento=data_vencimento,
            valor_total=valor,
            valor_pago=0,
            valor_restante=valor,
            status='aberta'
        )
        db.session.add(fatura)
        db.session.flush()
        print(f"✅ Fatura criada: {mes:02d}/{ano}")
        print(f"   Fecha: {data_fechamento.strftime('%d/%m/%Y')}")
        print(f"   Vence: {data_vencimento.strftime('%d/%m/%Y')}")
        print(f"   Valor: R$ {valor}")
    else:
        # Atualizar valores da fatura existente
        fatura.valor_total += valor
        fatura.valor_restante = fatura.valor_total - fatura.valor_pago
        print(f"✅ Fatura atualizada: {mes:02d}/{ano}")
        print(f"   Total: R$ {fatura.valor_total}")

    # Verificar se está atrasada
    if fatura.data_vencimento < date.today() and fatura.status == 'aberta':
        fatura.status = 'atrasada'
        print(f"⚠️  Fatura {mes:02d}/{ano} marcada como ATRASADA")

    try:
        db.session.commit()
        print(f"✅ Fatura {mes:02d}/{ano} salva com sucesso!")
        return fatura
    except Exception as e:
        print(f"❌ Erro ao salvar fatura: {e}")
        db.session.rollback()
        return None


def pagar_fatura(fatura_id, valor_pagamento, banco_id):
    """
    Registra o pagamento de uma fatura.
    """
    fatura = FaturaCartao.query.get(fatura_id)
    banco = Banco.query.get(banco_id)

    if not fatura or not banco:
        return False, "Fatura ou banco não encontrado"

    if banco.saldo < valor_pagamento:
        return False, "Saldo insuficiente no banco"

    # Descontar do banco
    banco.saldo -= valor_pagamento

    # Registrar movimentação
    movimento = MovimentacaoBanco(
        banco_id=banco_id,
        tipo_movimento='saida',
        valor=valor_pagamento,
        descricao=f'Pagamento fatura {fatura.cartao.nome} {fatura.mes}/{fatura.ano}',
        data=date.today()
    )
    db.session.add(movimento)

    # Registrar pagamento
    pagamento = PagamentoFatura(
        fatura_id=fatura_id,
        valor=valor_pagamento,
        data_pagamento=date.today(),
        forma_pagamento='Transferência Bancária'
    )
    db.session.add(pagamento)

    # Atualizar fatura
    fatura.valor_pago += valor_pagamento
    fatura.valor_restante = fatura.valor_total - fatura.valor_pago

    if fatura.valor_restante <= 0:
        fatura.status = 'paga'
        fatura.data_pagamento = date.today()

    db.session.commit()

    return True, "Pagamento registrado com sucesso"

# ===== FIM DAS FUNÇÕES DE FATURA =====

# Filtro para formatar valores monetários


@app.template_filter('format_decimal')
def format_decimal(value):
    if value is None:
        return '0.00'
    try:
        return "{:.2f}".format(float(value)).replace('.', ',')
    except (ValueError, TypeError):
        return '0.00'

# Filtro para converter para valor correto


@app.context_processor
def inject_utils():
    return dict(parse_value=parse_valor)


app.config['SECRET_KEY'] = os.environ.get(
    'SECRET_KEY', 'dev-secret-key-change-in-production')

# Configurar banco de dados
if os.environ.get('DATABASE_URL'):
    # Produção - PostgreSQL no Railway
    database_url = os.environ.get('DATABASE_URL')
    # Fix para PostgreSQL
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    # Desenvolvimento - SQLite local
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
def processar_recorrencias():
    """
    ✅ Processa recorrências e gera transações automaticamente
    Esta função deve ser chamada regularmente (diariamente recomendado)
    """
    from datetime import date, timedelta

    recorrencias_ativas = Recorrencia.query.filter_by(ativa=True).all()
    hoje = date.today()

    for rec in recorrencias_ativas:
        # ✅ Verificar se a recorrência deve gerar transação hoje
        # Regra simples: se o dia do vencimento é hoje ou passou

        # Se data_fim existe e já passou, não processar
        if rec.data_fim and hoje > rec.data_fim:
            continue

        # Se data_inicio ainda não chegou, não processar
        if hoje < rec.data_inicio:
            continue

        # Verificar se a transação já foi criada hoje
        transacao_hoje = Transacao.query.filter_by(
            usuario_id=rec.usuario_id,
            descricao=f"[REC] {rec.descricao}",
            data=hoje
        ).first()

        if transacao_hoje:
            continue  # Já foi processada hoje

        # Verificar frequência e se deve gerar transação
        dias_desde_inicio = (hoje - rec.data_inicio).days

        deve_processar = False
        if rec.frequencia == 'Diária':
            deve_processar = True
        elif rec.frequencia == 'Semanal':
            deve_processar = dias_desde_inicio % 7 == 0
        elif rec.frequencia == 'Quinzenal':
            deve_processar = dias_desde_inicio % 15 == 0
        elif rec.frequencia == 'Mensal':
            deve_processar = hoje.day == rec.dia_vencimento
        elif rec.frequencia == 'Bimestral':
            meses_desde = (hoje.year - rec.data_inicio.year) * \
                12 + (hoje.month - rec.data_inicio.month)
            deve_processar = meses_desde % 2 == 0 and hoje.day == rec.dia_vencimento
        elif rec.frequencia == 'Trimestral':
            meses_desde = (hoje.year - rec.data_inicio.year) * \
                12 + (hoje.month - rec.data_inicio.month)
            deve_processar = meses_desde % 3 == 0 and hoje.day == rec.dia_vencimento
        elif rec.frequencia == 'Semestral':
            meses_desde = (hoje.year - rec.data_inicio.year) * \
                12 + (hoje.month - rec.data_inicio.month)
            deve_processar = meses_desde % 6 == 0 and hoje.day == rec.dia_vencimento
        elif rec.frequencia == 'Anual':
            deve_processar = (hoje.month == rec.data_inicio.month and
                              hoje.day == rec.dia_vencimento)

        if deve_processar:
            # ✅ Criar transação automática
            nova_transacao = Transacao(
                usuario_id=rec.usuario_id,
                descricao=f"[REC] {rec.descricao}",  # Marca como recorrência
                valor=rec.valor,
                tipo=rec.tipo,
                categoria=rec.categoria,
                forma_pagamento=rec.forma_pagamento,
                banco_id=rec.banco_id,  # Usa o banco da recorrência
                data=hoje,
                data_criacao=datetime.utcnow()
            )

            db.session.add(nova_transacao)
            print(f"✅ Recorrência processada: {rec.descricao} ({hoje})")

    db.session.commit()


@app.route('/home', methods=['GET'])
@login_required
def home():
    """Página inicial com resumo financeiro"""

    # ✅ Processar recorrências antes de mostrar o dashboard
    processar_recorrencias()

    transacoes = Transacao.query.filter_by(usuario_id=current_user.id).all()

    # ✅ BUG 4 FIX: NÃO contar transações de CARTÃO no total de receitas/despesas
    # Apenas contar transações de BANCO
    total_receitas = sum(t.valor for t in transacoes if t.tipo ==
                         'Receita' and t.forma_pagamento != 'Cartão de Crédito')
    total_despesas = sum(t.valor for t in transacoes if t.tipo ==
                         'Despesa' and t.forma_pagamento != 'Cartão de Crédito')

    bancos = Banco.query.filter_by(usuario_id=current_user.id).all()
    saldo_bancos = sum(banco.saldo for banco in bancos)

    # ✅ BUG 4 FIX: Carteira = apenas transações sem banco_id E que NÃO sejam cartão
    transacoes_carteira = Transacao.query.filter_by(
        usuario_id=current_user.id, banco_id=None).all()
    # Excluir transações de CARTÃO DE CRÉDITO
    transacoes_carteira = [
        t for t in transacoes_carteira if t.forma_pagamento != 'Cartão de Crédito']

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
        valor = parse_valor(request.form.get('valor', '0'))
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
            db.session.flush()  # ✅ Garantir que a compra seja salva

            # ✅ CRIAR/ATUALIZAR A FATURA
            fatura = criar_ou_atualizar_fatura(
                usuario_id=current_user.id,
                cartao_id=cartao_id,
                data_compra=data,
                valor=valor
            )

            if fatura:
                print(
                    f"✅ Fatura criada para compra: {fatura.mes:02d}/{fatura.ano}")
            else:
                print(f"❌ Erro ao criar fatura para a compra!")

        db.session.commit()
        return redirect(url_for('lista_transacoes'))

    return render_template('adicionar.html', cartoes=cartoes, categorias=categorias, bancos=bancos)


@app.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    # SEGURANÇA: Verificar propriedade
    transacao = verificar_propriedade_transacao(id)

    if request.method == 'POST':
        try:
            # ✅ Guardar valores antigos para sincronização
            valor_antigo = transacao.valor
            forma_pagamento_antiga = transacao.forma_pagamento
            data_antiga = transacao.data

            # Atualizar transação
            transacao.descricao = request.form.get('descricao')
            valor_novo = parse_valor(request.form.get('valor', '0'))
            transacao.valor = valor_novo
            transacao.categoria = request.form.get('categoria')
            transacao.tipo = request.form.get('tipo')
            transacao.forma_pagamento = request.form.get('forma_pagamento')
            transacao.data = datetime.strptime(
                request.form.get('data'), '%Y-%m-%d').date()

            # ✅ Se for CARTÃO DE CRÉDITO, banco_id DEVE ser None!
            if transacao.forma_pagamento == 'Cartão de Crédito':
                transacao.banco_id = None

            db.session.commit()

            # ✅ SINCRONIZAÇÃO: Se mudou a forma de pagamento
            if forma_pagamento_antiga != transacao.forma_pagamento:
                print(f"🔄 Mudança de forma de pagamento detectada!")
                print(f"   De: {forma_pagamento_antiga}")
                print(f"   Para: {transacao.forma_pagamento}")

                # Se ERA cartão e DEIXOU de ser cartão → DELETAR de CompraCartao
                if forma_pagamento_antiga == 'Cartão de Crédito' and transacao.forma_pagamento != 'Cartão de Crédito':
                    print(f"   ❌ Removendo de Compras do Cartão...")

                    compra = CompraCartao.query.filter_by(
                        usuario_id=transacao.usuario_id,
                        descricao=transacao.descricao,
                        data_compra=data_antiga
                    ).first()

                    if compra:
                        print(f"   ✅ Compra encontrada, deletando...")
                        valor_compra = compra.valor_total
                        cartao_id = compra.cartao_id

                        # Atualizar fatura
                        cartao = CartaoCredito.query.get(cartao_id)
                        if cartao:
                            if compra.data_compra.day <= cartao.dia_fechamento:
                                mes_fatura = compra.data_compra.month
                                ano_fatura = compra.data_compra.year
                            else:
                                if compra.data_compra.month == 12:
                                    mes_fatura = 1
                                    ano_fatura = compra.data_compra.year + 1
                                else:
                                    mes_fatura = compra.data_compra.month + 1
                                    ano_fatura = compra.data_compra.year

                            fatura = FaturaCartao.query.filter_by(
                                usuario_id=transacao.usuario_id,
                                cartao_id=cartao_id,
                                mes=mes_fatura,
                                ano=ano_fatura
                            ).first()

                            if fatura:
                                fatura.valor_total -= valor_compra
                                fatura.valor_restante = fatura.valor_total - fatura.valor_pago

                                if fatura.valor_total <= 0:
                                    db.session.delete(fatura)

                                db.session.commit()
                                print(f"   ✅ Fatura atualizada!")

                        db.session.delete(compra)
                        db.session.commit()
                        flash(
                            f'✅ Transação movida para {transacao.forma_pagamento}! Removida de Compras do Cartão.', 'success')

                # Se NÃO ERA cartão e PASSOU a ser cartão → CRIAR em CompraCartao
                elif forma_pagamento_antiga != 'Cartão de Crédito' and transacao.forma_pagamento == 'Cartão de Crédito':
                    print(f"   ✅ Adicionando a Compras do Cartão...")

                    # Encontrar qual cartão usar (o primeiro ou de uma forma definida)
                    cartoes = CartaoCredito.query.filter_by(
                        usuario_id=transacao.usuario_id).all()
                    if cartoes:
                        cartao = cartoes[0]  # Usar o primeiro cartão

                        # Criar CompraCartao
                        nova_compra = CompraCartao(
                            usuario_id=transacao.usuario_id,
                            cartao_id=cartao.id,
                            descricao=transacao.descricao,
                            valor_total=transacao.valor,
                            quantidade_parcelas=1,
                            categoria=transacao.categoria,
                            data_compra=transacao.data,
                            forma_pagamento='Cartão de Crédito',  # ✅ ADICIONAR FORMA DE PAGAMENTO!
                            status='pendente'
                        )
                        db.session.add(nova_compra)
                        db.session.commit()

                        # Atualizar/Criar fatura
                        if transacao.data.day <= cartao.dia_fechamento:
                            mes_fatura = transacao.data.month
                            ano_fatura = transacao.data.year
                        else:
                            if transacao.data.month == 12:
                                mes_fatura = 1
                                ano_fatura = transacao.data.year + 1
                            else:
                                mes_fatura = transacao.data.month + 1
                                ano_fatura = transacao.data.year

                        fatura = FaturaCartao.query.filter_by(
                            usuario_id=transacao.usuario_id,
                            cartao_id=cartao.id,
                            mes=mes_fatura,
                            ano=ano_fatura
                        ).first()

                        if not fatura:
                            # ✅ Calcular data de fechamento baseada no cartão
                            if mes_fatura == 12:
                                proximo_mes = 1
                                proximo_ano = ano_fatura + 1
                            else:
                                proximo_mes = mes_fatura + 1
                                proximo_ano = ano_fatura

                            try:
                                data_fechamento = datetime(
                                    proximo_ano, proximo_mes, cartao.dia_fechamento).date()
                            except:
                                # Se dia não existe no mês, usar último dia do mês
                                if proximo_mes == 2:
                                    data_fechamento = datetime(
                                        proximo_ano, 3, 1).date() - timedelta(days=1)
                                else:
                                    data_fechamento = datetime(
                                        proximo_ano, proximo_mes + 1, 1).date() - timedelta(days=1)

                            fatura = FaturaCartao(
                                usuario_id=transacao.usuario_id,
                                cartao_id=cartao.id,
                                mes=mes_fatura,
                                ano=ano_fatura,
                                valor_total=transacao.valor,
                                valor_pago=0,
                                valor_restante=transacao.valor,
                                data_fechamento=data_fechamento,
                                data_vencimento=data_fechamento +
                                # Vencimento 10 dias depois
                                timedelta(days=10),
                                status='aberta'
                            )
                            db.session.add(fatura)
                        else:
                            fatura.valor_total += transacao.valor
                            fatura.valor_restante = fatura.valor_total - fatura.valor_pago

                        db.session.commit()
                        print(f"   ✅ Compra criada e fatura atualizada!")
                        flash(
                            f'✅ Transação movida para Cartão de Crédito! Adicionada em Compras do Cartão.', 'success')
                    else:
                        flash(
                            f'⚠️ Nenhum cartão cadastrado para adicionar esta transação.', 'warning')

            # ✅ Se continua sendo cartão, atualizar fatura com diferença
            elif (transacao.forma_pagamento == 'Cartão de Crédito' and
                  forma_pagamento_antiga == 'Cartão de Crédito'):

                diferenca = valor_novo - valor_antigo

                if diferenca != 0:
                    print(
                        f"✏️ Editando transação de cartão: {transacao.descricao}")
                    print(f"   Diferença: R$ {diferenca:.2f}")

                    compra = CompraCartao.query.filter_by(
                        usuario_id=transacao.usuario_id,
                        descricao=transacao.descricao,
                        data_compra=data_antiga
                    ).first()

                    if compra:
                        compra.valor_total = valor_novo
                        compra.data_compra = transacao.data
                        db.session.commit()

                        cartao = CartaoCredito.query.get(compra.cartao_id)

                        if cartao:
                            if compra.data_compra.day <= cartao.dia_fechamento:
                                mes_fatura = compra.data_compra.month
                                ano_fatura = compra.data_compra.year
                            else:
                                if compra.data_compra.month == 12:
                                    mes_fatura = 1
                                    ano_fatura = compra.data_compra.year + 1
                                else:
                                    mes_fatura = compra.data_compra.month + 1
                                    ano_fatura = compra.data_compra.year

                            fatura = FaturaCartao.query.filter_by(
                                usuario_id=transacao.usuario_id,
                                cartao_id=compra.cartao_id,
                                mes=mes_fatura,
                                ano=ano_fatura
                            ).first()

                            if fatura:
                                fatura.valor_total += diferenca
                                fatura.valor_restante = fatura.valor_total - fatura.valor_pago
                                db.session.commit()
                                print(f"✅ Fatura atualizada!")

            return redirect(url_for('lista_transacoes'))

        except Exception as e:
            print(f"❌ ERRO ao editar transação: {e}")
            import traceback
            traceback.print_exc()
            db.session.rollback()
            flash(f'❌ Erro ao editar: {str(e)}', 'danger')
            return redirect(url_for('lista_transacoes'))

    categorias = Categoria.query.filter_by(usuario_id=current_user.id).all()
    return render_template('editar.html', transacao=transacao, categorias=categorias)


@app.route('/deletar/<int:id>', methods=['POST'])
@login_required
def deletar(id):
    # SEGURANÇA: Verificar propriedade
    transacao = verificar_propriedade_transacao(id)

    # ✅ SE FOR CARTÃO DE CRÉDITO, ATUALIZAR FATURA
    if transacao.forma_pagamento == 'Cartão de Crédito':
        print(f"🗑️ Deletando transação cartão: {transacao.descricao}")

        # Procurar a CompraCartao relacionada
        compra = CompraCartao.query.filter_by(
            usuario_id=transacao.usuario_id,
            descricao=transacao.descricao,
            valor_total=transacao.valor,
            data_compra=transacao.data
        ).first()

        if compra:
            print(f"✅ Compra encontrada, atualizando fatura...")
            valor_compra = compra.valor_total
            cartao_id = compra.cartao_id

            # ✅ ATUALIZAR A FATURA
            cartao = CartaoCredito.query.get(cartao_id)

            if cartao:
                if compra.data_compra.day <= cartao.dia_fechamento:
                    mes_fatura = compra.data_compra.month
                    ano_fatura = compra.data_compra.year
                else:
                    if compra.data_compra.month == 12:
                        mes_fatura = 1
                        ano_fatura = compra.data_compra.year + 1
                    else:
                        mes_fatura = compra.data_compra.month + 1
                        ano_fatura = compra.data_compra.year

                # Procurar a fatura
                fatura = FaturaCartao.query.filter_by(
                    usuario_id=transacao.usuario_id,
                    cartao_id=cartao_id,
                    mes=mes_fatura,
                    ano=ano_fatura
                ).first()

                if fatura:
                    print(
                        f"✅ Fatura encontrada: {mes_fatura:02d}/{ano_fatura}")
                    print(f"   Valor anterior: R$ {fatura.valor_total}")

                    # SUBTRAIR O VALOR DA FATURA
                    fatura.valor_total -= valor_compra
                    fatura.valor_restante = fatura.valor_total - fatura.valor_pago

                    print(f"   Valor novo: R$ {fatura.valor_total}")

                    # SE FATURA FICAR COM VALOR 0, DELETAR
                    if fatura.valor_total <= 0:
                        print(f"   Fatura com valor 0, deletando...")
                        db.session.delete(fatura)

                    print(f"✅ Fatura atualizada!")

            # DELETAR A COMPRA
            db.session.delete(compra)

    # DELETAR A TRANSAÇÃO
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
        limite = parse_valor(request.form.get('limite', '0'))
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

    # ✅ CORREÇÃO: Buscar categorias do modelo + transações
    categorias_modelo = Categoria.query.filter_by(
        usuario_id=current_user.id).all()
    categorias_modelo_nomes = [cat.nome for cat in categorias_modelo]

    # Adicionar também categorias de transações já criadas
    categorias_transacao = db.session.query(Transacao.categoria).filter_by(
        usuario_id=current_user.id).distinct().all()
    categorias_transacao_nomes = [cat[0]
                                  for cat in categorias_transacao if cat[0]]

    # Combinar e remover duplicatas
    todas_categorias = sorted(
        set(categorias_modelo_nomes + categorias_transacao_nomes))

    return render_template('criar_orcamento.html', categorias=todas_categorias, mes_padrao=mes_atual, ano_padrao=ano_atual)


@app.route('/orcamentos/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_orcamento(id):
    # SEGURANÇA: Verificar propriedade
    orcamento = verificar_propriedade_orcamento(id)

    if request.method == 'POST':
        limite = parse_valor(request.form.get('limite', '0'))

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
        valor = parse_valor(request.form.get('valor', '0'))
        tipo = request.form.get('tipo')
        categoria = request.form.get('categoria')
        forma_pagamento = request.form.get('forma_pagamento')
        banco_id_str = request.form.get('banco_id')
        banco_id = int(
            banco_id_str) if banco_id_str and banco_id_str != '' else None
        cartao_id_str = request.form.get('cartao_id')
        cartao_id = int(
            cartao_id_str) if cartao_id_str and cartao_id_str != '' else None
        frequencia = request.form.get('frequencia')
        dia_vencimento = request.form.get('dia_vencimento', type=int)
        data_inicio = datetime.strptime(
            request.form.get('data_inicio'), '%Y-%m-%d').date()
        data_fim_str = request.form.get('data_fim')
        data_fim = datetime.strptime(
            data_fim_str, '%Y-%m-%d').date() if data_fim_str else None

        # ✅ Se banco_id foi selecionado, verificar propriedade
        if banco_id:
            banco = verificar_propriedade_banco(banco_id)

        # ✅ Se cartao_id foi selecionado, verificar propriedade
        if cartao_id:
            cartao = CartaoCredito.query.get_or_404(cartao_id)
            if cartao.usuario_id != current_user.id:
                flash('❌ Acesso negado!', 'danger')
                return redirect(url_for('criar_recorrencia'))

        nova_recorrencia = Recorrencia(
            usuario_id=current_user.id,
            descricao=descricao,
            valor=valor,
            tipo=tipo,
            categoria=categoria,
            forma_pagamento=forma_pagamento,
            banco_id=banco_id,  # ✅ Agora aceita banco_id
            cartao_id=cartao_id,  # ✅ Agora aceita cartao_id
            frequencia=frequencia,
            dia_vencimento=dia_vencimento,
            data_inicio=data_inicio,
            data_fim=data_fim,
            ativa=True
        )

        db.session.add(nova_recorrencia)
        db.session.commit()

        flash(f'✅ Recorrência "{descricao}" criada com sucesso!', 'success')
        return redirect(url_for('recorrencias'))

    categorias = Categoria.query.filter_by(usuario_id=current_user.id).all()
    bancos = Banco.query.filter_by(usuario_id=current_user.id).all()
    cartoes = CartaoCredito.query.filter_by(usuario_id=current_user.id).all()

    return render_template('criar_recorrencia.html',
                           categorias=categorias,
                           bancos=bancos,
                           cartoes=cartoes)


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
            # ✅ CORRIGIR: Comparar data_inicio com o primeiro dia do mês
            # Se data_inicio é depois do primeiro dia deste mês, não mostrar
            if rec.data_inicio.year > ano_projecao or \
               (rec.data_inicio.year == ano_projecao and rec.data_inicio.month > mes_projecao):
                continue  # Ainda não chegou nesse mês

            # Se data_fim passou, não mostrar mais
            if rec.data_fim and (rec.data_fim.year < ano_projecao or
               (rec.data_fim.year == ano_projecao and rec.data_fim.month < mes_projecao)):
                continue  # Já terminou essa recorrência

            meses_desde_inicio = (ano_projecao - rec.data_inicio.year) * \
                12 + (mes_projecao - rec.data_inicio.month)

            ocorre = False
            freq_lower = rec.frequencia.lower()  # ✅ Converter para minúscula para comparar

            if freq_lower == 'mensal':  # ✅ Mensal aparece todo mês
                ocorre = True
            elif freq_lower == 'diária':  # ✅ Diária aparece todo mês
                ocorre = True
            elif freq_lower == 'bimestral' and meses_desde_inicio >= 0 and meses_desde_inicio % 2 == 0:
                ocorre = True
            elif freq_lower == 'trimestral' and meses_desde_inicio >= 0 and meses_desde_inicio % 3 == 0:
                ocorre = True
            elif freq_lower == 'semestral' and meses_desde_inicio >= 0 and meses_desde_inicio % 6 == 0:
                ocorre = True
            elif freq_lower == 'anual' and meses_desde_inicio >= 0 and meses_desde_inicio % 12 == 0:
                ocorre = True
            elif freq_lower == 'semanal':  # ✅ Semanal: mostrar no mês de início
                if meses_desde_inicio == 0:
                    ocorre = True
            elif freq_lower == 'quinzenal':  # ✅ Quinzenal: mostrar no mês de início
                if meses_desde_inicio == 0:
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
                           ano_selecionado=ano_selecionado,
                           abs=abs)  # ✅ Adicionar função abs

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
        saldo = parse_valor(request.form.get('saldo', '0'))
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

        # Editar saldo se foi fornecido
        saldo_str = request.form.get('saldo', '').strip()
        if saldo_str:
            novo_saldo = parse_valor(saldo_str)

            # Calcular diferença
            diferenca = novo_saldo - banco.saldo

            if diferenca != 0:
                # Atualizar saldo
                banco.saldo = novo_saldo

                # Registrar movimentação
                tipo_movimento = 'entrada' if diferenca > 0 else 'saida'
                descricao = request.form.get(
                    'descricao_ajuste', 'Ajuste de saldo')

                # Pegar a data, ou usar data de hoje se não preencheu
                data_ajuste_str = request.form.get('data_ajuste', '').strip()
                if data_ajuste_str:
                    data = datetime.strptime(
                        data_ajuste_str, '%Y-%m-%d').date()
                else:
                    data = date.today()

                movimento = MovimentacaoBanco(
                    banco_id=id,
                    tipo_movimento=tipo_movimento,
                    valor=abs(diferenca),
                    descricao=descricao,
                    data=data
                )
                db.session.add(movimento)

        db.session.commit()
        flash(f'✅ Banco {banco.nome} atualizado com sucesso!', 'success')
        return redirect(url_for('bancos'))

    return render_template('editar_banco.html', banco=banco)


@app.route('/bancos/deletar/<int:id>', methods=['POST'])
@login_required
def deletar_banco(id):
    # SEGURANÇA: Verificar propriedade
    banco = verificar_propriedade_banco(id)

    # Deletar todas as movimentações do banco
    MovimentacaoBanco.query.filter_by(banco_id=id).delete()

    db.session.delete(banco)
    db.session.commit()

    flash('✅ Banco deletado com sucesso!', 'success')
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
        valor = parse_valor(request.form.get('valor', '0'))
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
        valor = parse_valor(request.form.get('valor', '0'))
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

        valor = parse_valor(request.form.get('valor', '0'))
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


@app.route('/carteira/editar', methods=['GET', 'POST'])
@login_required
def editar_carteira():
    """Editar saldo da carteira (dinheiro físico)"""

    # Pegar saldo atual da carteira de transações
    transacoes_carteira = Transacao.query.filter_by(
        usuario_id=current_user.id, banco_id=None).all()
    transacoes_carteira = [
        t for t in transacoes_carteira if t.forma_pagamento != 'Cartão de Crédito']

    receitas_carteira = sum(
        t.valor for t in transacoes_carteira if t.tipo == 'Receita')
    despesas_carteira = sum(
        t.valor for t in transacoes_carteira if t.tipo == 'Despesa')
    saldo_por_transacoes = receitas_carteira - despesas_carteira

    if request.method == 'POST':
        try:
            novo_saldo = parse_valor(request.form.get('novo_saldo', '0'))
            motivo = request.form.get('motivo', 'Ajuste de saldo da carteira')

            # Calcular a diferença
            diferenca = novo_saldo - saldo_por_transacoes

            if diferenca == 0:
                flash('✅ Saldo já está correto!', 'info')
                return redirect(url_for('editar_carteira'))

            # Criar transação de ajuste APENAS se houver diferença
            if diferenca > 0:
                # Se novo saldo é maior, adicionar receita
                transacao = Transacao(
                    usuario_id=current_user.id,
                    descricao=f'🔧 Ajuste carteira: {motivo}',
                    valor=diferenca,
                    categoria='Ajuste',
                    tipo='Receita',
                    forma_pagamento='Dinheiro',
                    data=date.today(),
                    banco_id=None
                )
                print(f"💰 Adicionando R$ {diferenca:.2f} à carteira")
                flash(
                    f'✅ Carteira ajustada! Adicionado R$ {diferenca:.2f}', 'success')
            else:
                # Se novo saldo é menor, adicionar despesa
                transacao = Transacao(
                    usuario_id=current_user.id,
                    descricao=f'🔧 Ajuste carteira: {motivo}',
                    valor=abs(diferenca),
                    categoria='Ajuste',
                    tipo='Despesa',
                    forma_pagamento='Dinheiro',
                    data=date.today(),
                    banco_id=None
                )
                print(f"💸 Removendo R$ {abs(diferenca):.2f} da carteira")
                flash(
                    f'✅ Carteira ajustada! Removido R$ {abs(diferenca):.2f}', 'success')

            db.session.add(transacao)
            db.session.commit()

            return redirect(url_for('editar_carteira'))

        except Exception as e:
            print(f"❌ ERRO ao editar carteira: {e}")
            import traceback
            traceback.print_exc()
            db.session.rollback()
            flash(f'❌ Erro ao editar carteira: {str(e)}', 'danger')
            return redirect(url_for('editar_carteira'))

    return render_template('editar_carteira.html', saldo_atual=saldo_por_transacoes)


@app.route('/carteira/transferir', methods=['GET', 'POST'])
@login_required
def transferir_carteira():
    """Transferir saldo da carteira para um banco"""

    # ✅ Pegar saldo da carteira - MESMO CÁLCULO DE editar_carteira()
    transacoes_carteira = Transacao.query.filter_by(
        usuario_id=current_user.id, banco_id=None).all()
    # ✅ IMPORTANTE: Excluir transações de CARTÃO DE CRÉDITO!
    transacoes_carteira = [
        t for t in transacoes_carteira if t.forma_pagamento != 'Cartão de Crédito']

    receitas_carteira = sum(
        t.valor for t in transacoes_carteira if t.tipo == 'Receita')
    despesas_carteira = sum(
        t.valor for t in transacoes_carteira if t.tipo == 'Despesa')
    saldo_carteira = receitas_carteira - despesas_carteira

    bancos = Banco.query.filter_by(usuario_id=current_user.id).all()

    # Verificar se tem bancos
    if not bancos:
        flash('⚠️ Você precisa cadastrar um banco primeiro!', 'warning')
        return redirect(url_for('criar_banco'))

    if request.method == 'POST':
        banco_id = request.form.get('banco_id', type=int)
        valor = parse_valor(request.form.get('valor', '0'))
        descricao = request.form.get('descricao', 'Transferência da carteira')
        data = datetime.strptime(request.form.get('data'), '%Y-%m-%d').date()

        # SEGURANÇA: Verificar propriedade do banco
        banco = verificar_propriedade_banco(banco_id)

        # Validar saldo
        if valor > saldo_carteira:
            flash('❌ Saldo insuficiente na carteira!', 'danger')
            return redirect(url_for('transferir_carteira'))

        # Criar transação de saída na carteira
        transacao_saida = Transacao(
            usuario_id=current_user.id,
            descricao=f'Transferência para {banco.nome}',
            valor=valor,
            categoria='Transferência',
            tipo='Despesa',
            forma_pagamento='Transferência',
            data=data,
            banco_id=None  # Sai da carteira
        )
        db.session.add(transacao_saida)

        # Criar transação de entrada no banco
        transacao_entrada = Transacao(
            usuario_id=current_user.id,
            descricao=f'Transferência da carteira',
            valor=valor,
            categoria='Transferência',
            tipo='Receita',
            forma_pagamento='Transferência',
            data=data,
            banco_id=banco_id  # Entra no banco
        )
        db.session.add(transacao_entrada)

        # Atualizar saldo do banco
        banco.saldo += valor

        # Criar movimento do banco
        movimento = MovimentacaoBanco(
            banco_id=banco_id,
            tipo_movimento='entrada',
            valor=valor,
            descricao=descricao,
            data=data
        )
        db.session.add(movimento)

        db.session.commit()

        flash(
            f'✅ Transferência de R$ {valor:.2f} realizada com sucesso!', 'success')
        return redirect(url_for('home'))

    return render_template('transferir_carteira.html',
                           saldo_carteira=saldo_carteira,
                           bancos=bancos)

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
        try:
            cartao_id = request.form.get('cartao_id', type=int)

            # SEGURANÇA: Verificar propriedade
            cartao = verificar_propriedade_cartao(cartao_id)

            descricao = request.form.get('descricao')
            valor_total = parse_valor(request.form.get('valor', '0'))
            quantidade_parcelas = request.form.get(
                'quantidade_parcelas', type=int, default=1)
            categoria = request.form.get('categoria')
            data_compra = datetime.strptime(
                request.form.get('data_compra'), '%Y-%m-%d').date()

            # ✅ CRIAR A COMPRA
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
            db.session.flush()  # ✅ Garantir que a compra seja salva antes da fatura

            print(f"✅ Compra criada: {descricao} - R$ {valor_total}")

            # ✅ CRIAR/ATUALIZAR A FATURA
            fatura = criar_ou_atualizar_fatura(
                usuario_id=current_user.id,
                cartao_id=cartao_id,
                data_compra=data_compra,
                valor=valor_total
            )

            if fatura:
                print(
                    f"✅ Fatura criada/atualizada: {fatura.mes}/{fatura.ano} - R$ {fatura.valor_total}")
                db.session.commit()
                flash(
                    f'✅ Compra lançada com sucesso! Fatura criada para {fatura.mes}/{fatura.ano}', 'success')
            else:
                print(f"❌ Erro ao criar fatura!")
                db.session.rollback()
                flash('❌ Erro ao criar fatura!', 'danger')
                return render_template('criar_compra_cartao.html', cartoes=cartoes, categorias=categorias)

            return redirect(url_for('compras_cartao'))

        except Exception as e:
            print(f"❌ ERRO ao lançar compra: {e}")
            import traceback
            traceback.print_exc()
            db.session.rollback()
            flash(f'❌ Erro ao lançar compra: {str(e)}', 'danger')
            return render_template('criar_compra_cartao.html', cartoes=cartoes, categorias=categorias)

    return render_template('criar_compra_cartao.html', cartoes=cartoes, categorias=categorias)


@app.route('/compras-cartao/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_compra_cartao(id):
    # SEGURANÇA: Verificar propriedade
    compra = verificar_propriedade_compra(id)

    if request.method == 'POST':
        try:
            # ✅ Guardar valores antigos ANTES de mudar
            valor_antigo = compra.valor_total
            data_antiga = compra.data_compra
            descricao_antiga = compra.descricao

            # Atualizar compra
            compra.descricao = request.form.get('descricao')
            valor_novo = parse_valor(request.form.get('valor', '0'))
            compra.valor_total = valor_novo
            compra.quantidade_parcelas = request.form.get(
                'quantidade_parcelas', type=int)
            compra.categoria = request.form.get('categoria')
            compra.data_compra = datetime.strptime(
                request.form.get('data_compra'), '%Y-%m-%d').date()

            db.session.commit()

            # ✅ SINCRONIZAÇÃO BIDIRECIONAL: Atualizar também em Minhas Transações
            transacao = Transacao.query.filter_by(
                usuario_id=current_user.id,
                descricao=descricao_antiga,
                data=data_antiga,
                forma_pagamento='Cartão de Crédito'
            ).first()

            if transacao:
                print(f"🔄 Sincronizando com Minhas Transações...")
                transacao.descricao = compra.descricao
                transacao.valor = valor_novo
                transacao.categoria = compra.categoria
                transacao.data = compra.data_compra
                db.session.commit()
                print(f"✅ Transação sincronizada!")

            # ✅ Calcular diferença e atualizar fatura
            diferenca = valor_novo - valor_antigo

            if diferenca != 0:  # Só atualizar se o valor mudou
                print(f"✏️ Editando compra de cartão: {compra.descricao}")
                print(f"   Valor anterior: R$ {valor_antigo:.2f}")
                print(f"   Valor novo: R$ {valor_novo:.2f}")
                print(f"   Diferença: R$ {diferenca:.2f}")

                # Procurar a fatura do cartão
                cartao = CartaoCredito.query.get(compra.cartao_id)

                if cartao:
                    # Determinar qual mês a compra pertence
                    if compra.data_compra.day <= cartao.dia_fechamento:
                        mes_fatura = compra.data_compra.month
                        ano_fatura = compra.data_compra.year
                    else:
                        if compra.data_compra.month == 12:
                            mes_fatura = 1
                            ano_fatura = compra.data_compra.year + 1
                        else:
                            mes_fatura = compra.data_compra.month + 1
                            ano_fatura = compra.data_compra.year

                    # Procurar a fatura
                    fatura = FaturaCartao.query.filter_by(
                        usuario_id=current_user.id,
                        cartao_id=compra.cartao_id,
                        mes=mes_fatura,
                        ano=ano_fatura
                    ).first()

                    if fatura:
                        print(
                            f"✅ Fatura encontrada: {mes_fatura:02d}/{ano_fatura}")
                        print(
                            f"   Fatura anterior: R$ {fatura.valor_total:.2f}")

                        # ✅ Atualizar fatura com a diferença
                        fatura.valor_total += diferenca
                        fatura.valor_restante = fatura.valor_total - fatura.valor_pago

                        print(f"   Fatura nova: R$ {fatura.valor_total:.2f}")

                        db.session.commit()
                        print(f"✅ Fatura atualizada!")
                        flash(
                            f'✅ Compra editada! Minhas Transações sincronizadas! Fatura atualizada para R$ {fatura.valor_total:.2f}', 'success')
                    else:
                        print(
                            f"⚠️ Fatura não encontrada para {mes_fatura:02d}/{ano_fatura}")
                        flash(
                            f'✅ Compra editada e sincronizada mas fatura não encontrada', 'info')
                else:
                    print(f"⚠️ Cartão não encontrado")
            else:
                flash(f'✅ Compra editada e sincronizada com sucesso!', 'success')

            return redirect(url_for('compras_cartao'))

        except Exception as e:
            print(f"❌ ERRO ao editar compra: {e}")
            import traceback
            traceback.print_exc()
            db.session.rollback()
            flash(f'❌ Erro ao editar compra: {str(e)}', 'danger')
            return redirect(url_for('compras_cartao'))

    cartoes = CartaoCredito.query.filter_by(usuario_id=current_user.id).all()
    categorias = Categoria.query.filter_by(usuario_id=current_user.id).all()

    return render_template('editar_compra_cartao.html', compra=compra, cartoes=cartoes, categorias=categorias)


@app.route('/compras-cartao/deletar/<int:id>', methods=['POST'])
@login_required
def deletar_compra_cartao(id):
    # SEGURANÇA: Verificar propriedade
    compra = verificar_propriedade_compra(id)

    print(f"🗑️ Deletando compra cartão: {compra.descricao}")

    valor_compra = compra.valor_total
    cartao_id = compra.cartao_id
    data_compra = compra.data_compra
    usuario_id = compra.usuario_id

    # ✅ ATUALIZAR A FATURA ANTES DE DELETAR
    cartao = CartaoCredito.query.get(cartao_id)

    if cartao:
        # Determinar qual mês a compra pertencia
        if data_compra.day <= cartao.dia_fechamento:
            mes_fatura = data_compra.month
            ano_fatura = data_compra.year
        else:
            if data_compra.month == 12:
                mes_fatura = 1
                ano_fatura = data_compra.year + 1
            else:
                mes_fatura = data_compra.month + 1
                ano_fatura = data_compra.year

        # Procurar a fatura
        fatura = FaturaCartao.query.filter_by(
            usuario_id=usuario_id,
            cartao_id=cartao_id,
            mes=mes_fatura,
            ano=ano_fatura
        ).first()

        if fatura:
            print(f"✅ Fatura encontrada: {mes_fatura:02d}/{ano_fatura}")
            print(f"   Valor anterior: R$ {fatura.valor_total}")

            # SUBTRAIR O VALOR DA FATURA
            fatura.valor_total -= valor_compra
            fatura.valor_restante = fatura.valor_total - fatura.valor_pago

            print(f"   Valor novo: R$ {fatura.valor_total}")

            # SE FATURA FICAR COM VALOR 0, DELETAR
            if fatura.valor_total <= 0:
                print(f"   Fatura com valor 0, deletando...")
                db.session.delete(fatura)

            print(f"✅ Fatura atualizada!")

    # DELETAR A COMPRA
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

# ===== ROTAS DE FATURAS =====


@app.route('/faturas', methods=['GET'])
@login_required
def listar_faturas():
    """Lista todas as faturas do usuário"""
    cartoes = CartaoCredito.query.filter_by(usuario_id=current_user.id).all()

    faturas_por_cartao = {}

    for cartao in cartoes:
        faturas = FaturaCartao.query.filter_by(
            usuario_id=current_user.id,
            cartao_id=cartao.id
        ).order_by(FaturaCartao.ano.desc(), FaturaCartao.mes.desc()).all()

        if faturas:
            faturas_por_cartao[cartao.id] = {
                'cartao': cartao,
                'faturas': faturas
            }

    # Resumo
    total_em_aberto = sum(
        f.valor_restante for f in FaturaCartao.query.filter_by(
            usuario_id=current_user.id,
            status='aberta'
        ).all()
    )

    total_atrasado = sum(
        f.valor_restante for f in FaturaCartao.query.filter_by(
            usuario_id=current_user.id,
            status='atrasada'
        ).all()
    )

    return render_template(
        'faturas.html',
        faturas_por_cartao=faturas_por_cartao,
        total_em_aberto=total_em_aberto,
        total_atrasado=total_atrasado
    )


@app.route('/faturas/<int:fatura_id>', methods=['GET'])
@login_required
def detalhar_fatura(fatura_id):
    """Mostra detalhes da fatura"""
    fatura = FaturaCartao.query.get_or_404(fatura_id)

    if fatura.usuario_id != current_user.id:
        abort(403)

    # Pegar transações da fatura
    transacoes = TransacaoFatura.query.filter_by(fatura_id=fatura_id).all()

    # Pegar pagamentos registrados
    pagamentos = PagamentoFatura.query.filter_by(fatura_id=fatura_id).all()

    # Bancos disponíveis para pagamento
    bancos = Banco.query.filter_by(usuario_id=current_user.id).all()

    return render_template(
        'detalhar_fatura.html',
        fatura=fatura,
        transacoes=transacoes,
        pagamentos=pagamentos,
        bancos=bancos
    )


@app.route('/faturas/<int:fatura_id>/pagar', methods=['POST'])
@login_required
def pagar_fatura_route(fatura_id):
    """Processa o pagamento de uma fatura"""
    fatura = FaturaCartao.query.get_or_404(fatura_id)

    if fatura.usuario_id != current_user.id:
        abort(403)

    valor = parse_valor(request.form.get('valor', '0'))
    banco_id = request.form.get('banco_id', type=int)

    if valor <= 0 or valor > fatura.valor_restante:
        flash('❌ Valor de pagamento inválido!', 'danger')
        return redirect(url_for('detalhar_fatura', fatura_id=fatura_id))

    sucesso, mensagem = pagar_fatura(fatura_id, valor, banco_id)

    if sucesso:
        flash(f'✅ {mensagem}', 'success')
    else:
        flash(f'❌ {mensagem}', 'danger')

    return redirect(url_for('detalhar_fatura', fatura_id=fatura_id))

# ===== FIM DAS ROTAS DE FATURAS =====


# Criar as tabelas na inicialização
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=False, port=5000)
