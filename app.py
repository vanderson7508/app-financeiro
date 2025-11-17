"""
Controle Financeiro - App Principal
Versão: 2.0 com SendGrid
"""

# ===== IMPORTS =====
from flask import Flask, render_template, request, redirect, url_for, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, Usuario, Transacao, Banco, MovimentacaoBanco, CartaoCredito, CompraCartao, Categoria, Recorrencia, Orcamento
from datetime import datetime, date, timedelta
from sqlalchemy import extract, func
from calendar import monthrange
import os
import logging

# SendGrid
from itsdangerous import URLSafeTimedSerializer
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content
from dotenv import load_dotenv

# ===== CARREGAR VARIÁVEIS DE AMBIENTE =====
load_dotenv()

# ===== CONFIGURAR APP =====
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get(
    'SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///financeiro.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ===== CONFIGURAÇÕES DO SENDGRID =====
app.config['SENDGRID_API_KEY'] = os.environ.get('SENDGRID_API_KEY', '')
app.config['SENDGRID_FROM_EMAIL'] = os.environ.get(
    'SENDGRID_FROM_EMAIL', 'noreply@financeiro.com')
app.config['SENDGRID_FROM_NAME'] = 'Controle Financeiro'

# Inicializar SendGrid
sg = SendGridAPIClient(app.config['SENDGRID_API_KEY'])
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

# Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== INICIALIZAR BANCO DE DADOS (APENAS UMA VEZ!) =====
db.init_app(app)

# ===== CONFIGURAR LOGIN MANAGER =====
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Faça login para acessar esta página.'


@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

# ===== FUNÇÕES DE SEGURANÇA =====


def verificar_propriedade_transacao(transacao_id):
    """Verifica se a transação pertence ao usuário logado"""
    transacao = Transacao.query.get_or_404(transacao_id)
    if transacao.usuario_id != current_user.id:
        abort(403)
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
            <meta charset="UTF-8">
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f5f7fa; }}
                .container {{ max-width: 600px; margin: 0 auto; }}
                .header {{ background: linear-gradient(135deg, #17a2b8 0%, #20c997 100%); color: white; padding: 40px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: white; padding: 50px; border-radius: 0 0 10px 10px; line-height: 1.8; }}
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
                        <a href="{link_recuperacao}" class="button">🔄 Redefinir Senha</a>
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


# ===== CRIAR TABELAS NA INICIALIZAÇÃO =====
with app.app_context():
    db.create_all()
    logger.info("✅ Banco de dados inicializado")

# ===== EXECUTAR =====
if __name__ == '__main__':
    app.run(debug=True, port=5000)
