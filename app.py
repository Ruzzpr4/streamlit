import streamlit as st
import duckdb
import pandas as pd
import time
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

st.set_page_config(
    page_title="Consulta CNPJ com base no CNAE",
    layout="wide"
)

CAMINHO_DADOS = "dados_app_todas_empresas/*.parquet"

try:
    EMAIL_REMETENTE = st.secrets["email"]["usuario"]
    EMAIL_SENHA = st.secrets["email"]["senha"]
except FileNotFoundError:
    st.error("Erro: Arquivo não encontrado.")
    st.stop()
except KeyError:
    st.error("Erro: As chaves de e-mail não foram configuradas.")
    st.stop()

TEMPLATES = {
    "Apresentação Comercial": {
        "assunto": "Parceria com a {EMPRESA}",
        "corpo": """
        <div style="font-family: Arial, color: #333;">
            <p>Olá, equipe <strong>{EMPRESA}</strong>,</p>
            <p>Vi que vocês atuam em {CIDADE} e gostaria de apresentar uma solução que pode ajudar na sua operação.</p>
            <p>Podemos agendar uma breve conversa?</p>
            <p>Atenciosamente,</p>
            <p><strong>Seu Nome</strong></p>
        </div>
        """
    },
    "Contato Simples": {
        "assunto": "Contato referente à {EMPRESA}",
        "corpo": """
        <p>Olá,</p>
        <p>Gostaria de falar com o responsável pela <strong>{EMPRESA}</strong>.</p>
        <p>Tenho uma proposta comercial.</p>
        <p>Obrigado.</p>
        """
    }
}

def formatar_moeda(valor):
    if pd.isna(valor): return "R$ 0,00"
    try:
        return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return str(valor)

def enviar_email(destinatario, assunto, corpo_html):
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_REMETENTE
        msg['To'] = destinatario
        msg['Subject'] = assunto
        msg.attach(MIMEText(corpo_html, 'html'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_REMETENTE, EMAIL_SENHA)
        server.sendmail(EMAIL_REMETENTE, destinatario, msg.as_string())
        server.quit()
        return True, "OK"
    except Exception as e:
        return False, str(e)

st.sidebar.header("Filtros de Pesquisa")

st.sidebar.markdown("### Atividade Econômica")
cnae_input = st.sidebar.text_input("CNAE (Apenas números)", help="Exemplo: 4120400")

escopo_cnae = st.sidebar.radio(
    "Escopo da busca",
    options=["Principal e Secundário", "Apenas Principal"]
)

st.sidebar.markdown("---")
st.sidebar.markdown("### Dados Financeiros")

capital_min = st.sidebar.number_input(
    "Capital Social Mínimo",
    min_value=0.0,
    value=0.0,
    step=10000.0,
    format="%.2f"
)
st.sidebar.text(f"Filtro: {formatar_moeda(capital_min)}")

st.sidebar.markdown("---")
st.sidebar.markdown("### Características")

tipo_unidade = st.sidebar.radio(
    "Tipo de Unidade",
    options=["Todas", "Apenas Matriz", "Apenas Filial"],
    index=0
)

col_porte, col_ativa = st.sidebar.columns(2)
filtro_porte = col_porte.checkbox("Excluir ME/EPP", value=True)
apenas_ativas = col_ativa.checkbox("Apenas Ativas", value=True)

ufs = st.sidebar.multiselect(
    "Estados (UF)",
    options=['AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA','PB','PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO'],
    default=[]
)

limitador_linhas = st.sidebar.slider("Limite de visualização (Tela)", 100, 50000, 1000)

st.sidebar.markdown("---")
st.sidebar.markdown("### Estatísticas")
if st.sidebar.button("Verificar Total de Registros"):
    try:
        if os.path.exists("dados_app_todas_empresas"):
            con_count = duckdb.connect(database=':memory:')
            total_banco = con_count.execute(f"SELECT count(*) FROM '{CAMINHO_DADOS}'").fetchone()[0]
            total_fmt = f"{total_banco:,.0f}".replace(",", ".")
            st.sidebar.info(f"Total no Banco: {total_fmt} empresas")
        else:
            st.sidebar.error("Banco de dados não encontrado.")
    except Exception as e:
        st.sidebar.error(f"Erro ao ler banco: {e}")

st.title("Base de Dados EMPRESAS - Consulta por CNAE v1.1")
st.text("Desenvolvido por Raul Stefani - Última atualização: 05/02")

tab1, tab2 = st.tabs(["Busca e Filtros", "Envio de E-mails"])

with tab1:
    if not os.path.exists("dados_app_todas_empresas"):
        st.error("Diretório de dados não encontrado.")
        st.stop()

    if st.button("Pesquisar", type="primary"):
        
        if not cnae_input:
            st.warning("Informe o código CNAE.")
        else:
            cnae_limpo = "".join(filter(str.isdigit, cnae_input))
            start_time = time.time()
            
            query = f"""
            SELECT 
                cnpj_basico || cnpj_ordem || cnpj_dv as CNPJ,
                razao_social as 'RAZAO SOCIAL',
                nome_fantasia as 'NOME FANTASIA',
                capital_social as 'CAPITAL SOCIAL',
                cnae_fiscal_principal as 'CNAE PRINCIPAL',
                uf as UF,
                municipio as MUNICIPIO,
                bairro as BAIRRO,
                logradouro as LOGRADOURO,
                numero as NUMERO,
                ddd_1 || ' ' || telefone_1 as TELEFONE,
                correio_eletronico as EMAIL,
                identificador_matriz_filial
            FROM '{CAMINHO_DADOS}'
            WHERE capital_social >= {capital_min}
            """
            
            params = []
            
            if escopo_cnae == "Apenas Principal":
                query += " AND cnae_fiscal_principal = ?"
                params.append(cnae_limpo)
            else:
                query += " AND (cnae_fiscal_principal = ? OR contains(cnae_fiscal_secundaria, ?))"
                params.append(cnae_limpo)
                params.append(cnae_limpo)

            if apenas_ativas:
                query += " AND situacao_cadastral = '02'"
                
            if filtro_porte:
                query += " AND porte_empresa = '05'"

            if tipo_unidade == "Apenas Matriz":
                query += " AND identificador_matriz_filial = '1'"
            elif tipo_unidade == "Apenas Filial":
                query += " AND identificador_matriz_filial = '2'"
                
            if ufs:
                lista_ufs = ", ".join([f"'{u}'" for u in ufs])
                query += f" AND uf IN ({lista_ufs})"
                
            query += " ORDER BY capital_social DESC"

            try:
                con = duckdb.connect(database=':memory:')
                df_final = con.execute(query, params).df()
                
                st.session_state['df_leads'] = df_final
                
                total_rows = len(df_final)
                tempo_total = time.time() - start_time
                
                if total_rows > 0:
                    st.success(f"Consulta finalizada. {total_rows} registros encontrados em {tempo_total:.2f}s")
                    st.divider()

                    m1, m2, m3 = st.columns(3)
                    m1.metric("Total de Registros", total_rows)
                    m2.metric("Maior Capital Social", formatar_moeda(df_final['CAPITAL SOCIAL'].max()))
                    
                    try:
                        qtd_matriz = len(df_final[df_final['identificador_matriz_filial'].astype(str) == '1'])
                    except:
                        qtd_matriz = 0
                        
                    m3.metric("Distribuição", f"{qtd_matriz} Matrizes / {total_rows - qtd_matriz} Filiais")

                    st.write(f"### Visualização ({limitador_linhas} linhas)")
                    
                    st.dataframe(
                        df_final.head(limitador_linhas),
                        column_config={
                            "CAPITAL SOCIAL": st.column_config.NumberColumn("Capital Social", format="R$ %.2f"),
                            "CNPJ": st.column_config.TextColumn("CNPJ"),
                        },
                        width="stretch",
                        height=500,
                        hide_index=True
                    )

                    nome_arquivo = f"exportacao_cnae{cnae_limpo}.csv"
                    csv = df_final.to_csv(index=False, sep=';', encoding='utf-8-sig').encode('utf-8-sig')
                    st.download_button("Baixar CSV", csv, nome_arquivo, "text/csv", type="primary", use_container_width=True)

                else:
                    st.info("Nenhum registro encontrado com os critérios selecionados.")
                    
            except Exception as e:
                st.error(f"Erro na execução da consulta: {e}")

with tab2:
    st.header("Disparo de E-mails")
    
    if 'df_leads' not in st.session_state or st.session_state['df_leads'] is None:
        st.warning("Realize uma pesquisa na aba 'Busca e Filtros' primeiro para carregar os dados.")
    else:
        df = st.session_state['df_leads']
 
        df_emails_raw = df[df['EMAIL'].notna() & (df['EMAIL'] != '')].copy()
        total_emails = len(df_emails_raw)
        
        st.info(f"Leads com e-mail válido disponíveis: {total_emails}")
        
        if total_emails > 0:
            col_esq, col_dir = st.columns([1, 1])
            
            with col_esq:
                st.subheader("Configuração da Mensagem")
                template_name = st.selectbox("Modelo", list(TEMPLATES.keys()))
                template = TEMPLATES[template_name]
                
                assunto_input = st.text_input("Assunto", value=template['assunto'])
                corpo_input = st.text_area("Corpo (HTML)", value=template['corpo'], height=250)
                
                st.markdown("<small>Variáveis: `{EMPRESA}`, `{CIDADE}`, `{UF}`</small>", unsafe_allow_html=True)
                
                st.divider()
                st.subheader("Seleção de Destinatários")
                
                modo_envio = st.radio(
                    "Modo de Seleção",
                    options=["Envio Sequencial (Top X)", "Seleção Manual na Lista"]
                )
                
                df_para_envio = pd.DataFrame()
                
                if modo_envio == "Envio Sequencial (Top X)":
                    qtd_envio = st.slider("Quantidade a enviar", 1, total_emails, min(10, total_emails))
                    df_para_envio = df_emails_raw.head(qtd_envio)
                    st.caption(f"Serão enviados e-mails para os primeiros {qtd_envio} leads da lista.")
                
                else: 
                    st.write("Selecione os destinatários abaixo:")
                    if "selecao" not in df_emails_raw.columns:
                        df_emails_raw.insert(0, "Selecionar", False)

                    df_editado = st.data_editor(
                        
                        df_emails_raw[["Selecionar", "RAZAO SOCIAL" , "CAPITAL SOCIAL" , "EMAIL", "MUNICIPIO", "UF"]],
                        column_config={
                            "Selecionar": st.column_config.CheckboxColumn(
                                "Enviar?",
                                help="Marque para enviar e-mail",
                                default=False,
                            ),
                            "CAPITAL SOCIAL": st.column_config.NumberColumn("Capital Social", format="R$ %.2f"),
                            "MUNICIPIO": st.column_config.TextColumn("Cidade")
                        },
                        disabled=["RAZAO SOCIAL", "EMAIL", "MUNICIPIO", "UF"],
                        hide_index=True,
                        height=400,
                        width='stretch'
                    )

                    emails_selecionados = df_editado[df_editado["Selecionar"] == True]["EMAIL"].tolist()
                    df_para_envio = df_emails_raw[df_emails_raw["EMAIL"].isin(emails_selecionados)]
                    
                    st.caption(f"{len(df_para_envio)} empresas selecionadas manualmente.")

                intervalo = st.number_input("Intervalo entre envios (segundos)", min_value=1, value=2)

            with col_dir:
                st.subheader("Pré-visualização")
                if not df_para_envio.empty:
                    lead_exemplo = df_para_envio.iloc[0]
                    empresa_nome = lead_exemplo['NOME FANTASIA'] if lead_exemplo['NOME FANTASIA'] else lead_exemplo['RAZAO SOCIAL']
                    
                    preview_assunto = assunto_input.replace("{EMPRESA}", str(empresa_nome))
                    preview_corpo = corpo_input.replace("{EMPRESA}", str(empresa_nome))\
                                            .replace("{CIDADE}", str(lead_exemplo['MUNICIPIO']))\
                                            .replace("{UF}", str(lead_exemplo['UF']))
                    
                    st.markdown(f"**Para:** {lead_exemplo['EMAIL']}")
                    st.markdown(f"**Assunto:** {preview_assunto}")
                    st.markdown("---")
                    st.markdown(preview_corpo, unsafe_allow_html=True)
                    st.markdown("---")
                    
                    if st.button(f"Confirmar Envio ({len(df_para_envio)} e-mails)", type="primary"):
                        barra = st.progress(0)
                        status = st.empty()
                        sucessos = 0
                        erros = []
                        total_envio = len(df_para_envio)
                        
                        for i in range(total_envio):
                            lead = df_para_envio.iloc[i]
                            email_dest = lead['EMAIL']
                            empresa_nome = lead['NOME FANTASIA'] if lead['NOME FANTASIA'] else lead['RAZAO SOCIAL']
                            
                            assunto_final = assunto_input.replace("{EMPRESA}", str(empresa_nome))
                            corpo_final = corpo_input.replace("{EMPRESA}", str(empresa_nome))\
                                                    .replace("{CIDADE}", str(lead['MUNICIPIO']))\
                                                    .replace("{UF}", str(lead['UF']))
                            
                            status.text(f"Enviando {i+1}/{total_envio} para {email_dest}...")
                            
                            ok, msg = enviar_email(email_dest, assunto_final, corpo_final)
                            if ok:
                                sucessos += 1
                            else:
                                erros.append(f"{email_dest}: {msg}")
                            
                            barra.progress((i+1)/total_envio)
                            time.sleep(intervalo)
                        
                        status.empty()
                        st.success(f"Operação concluída. {sucessos} e-mails enviados.")
                        if erros:
                            st.error(f"{len(erros)} falhas de envio.")
                            with st.expander("Relatório de Falhas"):
                                st.write(erros)
                else:
                    st.info("Nenhuma empresa selecionada para visualização/envio.")
