import streamlit as st
import duckdb
import pandas as pd
import time
import os

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Consulta CNPJ",
    layout="wide"
)

# Caminho dos dados particionados (leitura otimizada)
CAMINHO_DADOS = "dados_app/*.parquet"

# --- FUNÇÕES ---
def formatar_moeda(valor):
    if pd.isna(valor): return "R$ 0,00"
    try:
        return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return str(valor)

# --- SIDEBAR (FILTROS) ---
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

# --- ÁREA PRINCIPAL ---
st.title("Base de Dados EMPRESAS - Consulta por CNAE")

# Verificação silenciosa do diretório
if not os.path.exists("dados_app"):
    st.error("Diretório de dados não encontrado.")
    st.stop()

if st.sidebar.button("Pesquisar", type="primary"):
    
    if not cnae_input:
        st.warning("Informe o código CNAE.")
    else:
        cnae_limpo = "".join(filter(str.isdigit, cnae_input))
        start_time = time.time()
        
        # --- QUERY SQL (DuckDB Engine) ---
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
        
        # Lógica de Filtros
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
            # Conexão temporária em memória
            con = duckdb.connect(database=':memory:')
            
            # Execução
            df_final = con.execute(query, params).df()
            
            total_rows = len(df_final)
            tempo_total = time.time() - start_time
            
            if total_rows > 0:
                st.success(f"Processamento concluído. {total_rows} registros encontrados em {tempo_total:.2f}s")
                st.divider()

                # Métricas
                m1, m2, m3 = st.columns(3)
                m1.metric("Total de Registros", total_rows)
                m2.metric("Maior Capital Social", formatar_moeda(df_final['CAPITAL SOCIAL'].max()))
                
                try:
                    qtd_matriz = len(df_final[df_final['identificador_matriz_filial'].astype(str) == '1'])
                except:
                    qtd_matriz = 0
                    
                m3.metric("Distribuição", f"{qtd_matriz} Matrizes / {total_rows - qtd_matriz} Filiais")

                st.write(f"### Visualização ({limitador_linhas} linhas)")
                
                # Tabela Otimizada
                st.dataframe(
                    df_final.head(limitador_linhas),
                    column_config={
                        "CAPITAL SOCIAL": st.column_config.NumberColumn(
                            "Capital Social",
                            format="R$ %.2f",
                        ),
                        "CNPJ": st.column_config.TextColumn("CNPJ"),
                    },
                    width="stretch",
                    height=500,
                    hide_index=True
                )

                # Exportação
                nome_arquivo = f"exportacao_cnae{cnae_limpo}.csv"
                csv = df_final.to_csv(index=False, sep=';', encoding='utf-8-sig').encode('utf-8-sig')
                
                st.download_button(
                    label="Baixar CSV",
                    data=csv,
                    file_name=nome_arquivo,
                    mime="text/csv",
                    type="primary",
                    use_container_width=True
                )

            else:
                st.info("Nenhum registro encontrado com os critérios selecionados.")
                
        except Exception as e:
            st.error(f"Erro na execução da consulta: {e}")