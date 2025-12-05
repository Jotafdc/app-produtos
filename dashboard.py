import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import csv
import unicodedata
import os
import re

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Gestão Comercial PB", layout="wide", initial_sidebar_state="expanded")

# --- ESTILOS ---
st.markdown("""
<style>
    .stMetric {background-color: #f9f9f9; padding: 15px; border-radius: 10px; border: 1px solid #eee;}
    div[data-testid="stMetricValue"] {font-size: 20px;}
</style>
""", unsafe_allow_html=True)

CORES = {'AGO': '#A6CEE3', 'SET': '#1F78B4', 'OUT': '#B2DF8A', 'NOV': '#E31A1C'}
COR_MEDIA, COR_DESTAQUE = '#999999', '#E31A1C'

# Lista Filtrada (Sem Alagoa Grande e Uirauna, conforme pedido anterior)
CIDADES_ALVO = [
    "CAJAZEIRAS", "CAMPINA GRANDE", "CATOLE DO ROCHA", "ITAPORANGA",
    "JUAZEIRINHO", "LIVRAMENTO", "MARIZOPOLIS", "MONTEIRO", "PATOS",
    "PIANCO", "POMBAL", "SANTA LUZIA", "SAO BENTO", "SOUSA"
]

# --- FUNÇÕES DE LIMPEZA AVANÇADA ---

def normalizar_texto(texto):
    if not isinstance(texto, str): return str(texto)
    return ''.join(c for c in unicodedata.normalize('NFD', texto) 
                   if unicodedata.category(c) != 'Mn').upper().strip()

def limpar_nome_produto(nome):
    """
    Função 'Detergente': Remove qualquer sujeira para garantir que
    o produto de Agosto case com o de Outubro.
    """
    if not isinstance(nome, str): return ""
    
    # 1. Remove códigos iniciais (ex: "2013-ACM" -> "ACM")
    if '-' in nome:
        partes = nome.split('-', 1)
        # Se a primeira parte for curta (código), pega o resto
        if len(partes[0]) < 12 and any(c.isdigit() for c in partes[0]):
            nome = partes[1]
    
    # 2. Remove sujeira do final (ex: "-.", ".", "-") de forma segura
    # rstrip remove apenas do final da string
    nome = nome.rstrip(' .-,')
    
    # 3. Remove a sequencia especifica "-." que aparece nos seus arquivos
    nome = nome.replace('-.', '')

    # 4. Remove zeros à esquerda que sobraram
    nome = nome.strip()
    while nome.startswith('0') and len(nome) > 1 and not nome[1].isdigit():
        nome = nome[1:]
        
    # 5. Remove espaços duplos (Transforma "ACM  BRANCO" em "ACM BRANCO")
    nome = " ".join(nome.split())
    
    return nome.strip()

@st.cache_data(show_spinner=True)
def ler_arquivo_universal(caminho_arquivo, label_mes):
    if not os.path.exists(caminho_arquivo): return pd.DataFrame()
    dados = []
    cidade_atual = None
    
    try:
        with open(caminho_arquivo, 'r', encoding='latin1', errors='replace') as f:
            linhas = f.readlines()
            
        for linha in linhas:
            linha = linha.strip()
            if not linha or linha.startswith('#'): continue
            
            linha_limpa = linha.replace('"', '')
            
            # --- DETECTAR CIDADE ---
            if linha_limpa.startswith('PB'):
                # Tenta vírgula (OUTU/AGO)
                if ',' in linha_limpa:
                    partes = linha_limpa.split(',')
                    if len(partes) > 1:
                        cand = partes[1].strip()
                        if len(cand) > 2:
                            cidade_atual = normalizar_texto(cand)
                            continue
                # Tenta espaço (OUT antigo)
                resto = linha_limpa[2:].strip().lstrip(' ,.-')
                if ',,' in resto: resto = resto.split(',')[0]
                if len(resto) > 2:
                    cidade_atual = normalizar_texto(resto)
                continue
            
            if any(x in linha for x in ['RMOV', 'Emissão:', 'Produto', 'Total :', 'TOTAL CIDADE']): continue
            
            # --- EXTRAIR DADOS ---
            try:
                qtd, valor = 0.0, 0.0
                prod_nome = ""
                
                csv_reader = csv.reader([linha])
                cols_csv = next(csv_reader)
                cols_espaco = re.split(r'\s{2,}', linha_limpa)
                
                # Formato A: CSV (OUTU/AGO)
                if len(cols_csv) >= 7 and any(c and any(char.isdigit() for char in c) for c in cols_csv[2:]):
                    if ',' in cols_csv[6]: valor = float(cols_csv[6].strip().replace('.', '').replace(',', '.'))
                    if ',' in cols_csv[2]: qtd = float(cols_csv[2].strip().replace('.', '').replace(',', '.'))
                    
                    # Nome: Tenta Col 1 (OUTU), senão Col 0 (AGO)
                    raw_0 = cols_csv[0].strip()
                    raw_1 = cols_csv[1].strip() if len(cols_csv) > 1 else ""
                    # Se a col 1 tem texto e não é número, é o nome (OUTU)
                    prod_nome = raw_1 if (raw_1 and len(raw_1) > 2 and not re.match(r'^[\d.,]+$', raw_1)) else raw_0

                # Formato B: Texto (OUT antigo)
                elif len(cols_espaco) >= 5:
                    v_str = cols_espaco[-2]
                    if ',' in v_str: valor = float(v_str.replace('.', '').replace(',', '.'))
                    for item in cols_espaco[1:-2]:
                        if re.match(r'^\d{1,6},\d{2}$', item):
                            pq = float(item.replace('.', '').replace(',', '.'))
                            if pq > 0: qtd = pq; break
                    prod_nome = cols_espaco[0]

                if valor > 0 or qtd > 0:
                    # APLICA A LIMPEZA PODEROSA AQUI
                    nome_limpo = limpar_nome_produto(prod_nome)
                    
                    # Filtro de segurança: Nome muito curto geralmente é lixo de leitura
                    if len(nome_limpo) > 2:
                        dados.append({
                            'Cidade': cidade_atual if cidade_atual else "DESCONHECIDA",
                            'Produto': nome_limpo,
                            f'Qtd_{label_mes}': qtd,
                            f'Vlr_{label_mes}': valor
                        })
            except: continue
    except: return pd.DataFrame()
    return pd.DataFrame(dados)

@st.cache_data(show_spinner=True)
def carregar_consolidado():
    # Ordem de preferência: Tenta OUTU.csv primeiro para Outubro
    arquivos = {'AGO': ['AGO.csv'], 'SET': ['SET.csv'], 'OUT': ['OUTU.csv', 'OUT (2).csv', 'OUT.csv'], 'NOV': ['NOV.csv']}
    dfs = []
    
    msg = st.empty()
    
    for mes, nomes in arquivos.items():
        found = next((n for n in nomes if os.path.exists(n)), None)
        if found:
            msg.text(f"Lendo {found}...")
            df = ler_arquivo_universal(found, mes)
            if not df.empty:
                if 'Cidade' not in df.columns: df['Cidade'] = "DESCONHECIDA"
                # Agrupa somando (AGORA COM NOMES IGUAIS)
                dfs.append(df.groupby(['Cidade', 'Produto'])[[f'Qtd_{mes}', f'Vlr_{mes}']].sum().reset_index())
        else:
            st.warning(f"Arquivo de {mes} não encontrado.")
            
    msg.empty()
    
    if not dfs: return pd.DataFrame()
    
    # Consolida (Merge Total)
    df_final = dfs[0]
    for d in dfs[1:]: df_final = pd.merge(df_final, d, on=['Cidade', 'Produto'], how='outer')
    
    df_final = df_final.fillna(0)
    for m in ['AGO', 'SET', 'OUT', 'NOV']:
        if f'Vlr_{m}' not in df_final.columns: df_final[f'Vlr_{m}'] = 0.0
        if f'Qtd_{m}' not in df_final.columns: df_final[f'Qtd_{m}'] = 0.0

    df_final.columns = df_final.columns.str.strip()
    
    # Filtro Cidades (Rigoroso)
    if 'Cidade' in df_final.columns:
        norm = [normalizar_texto(c) for c in CIDADES_ALVO]
        df_final = df_final[df_final['Cidade'].isin(norm)]
    
    # Cálculos
    df_final['Media_3M_Vlr'] = (df_final['Vlr_AGO'] + df_final['Vlr_SET'] + df_final['Vlr_OUT']) / 3
    df_final['Media_3M_Qtd'] = (df_final['Qtd_AGO'] + df_final['Qtd_SET'] + df_final['Qtd_OUT']) / 3
    df_final['Total_Geral'] = df_final['Vlr_AGO'] + df_final['Vlr_SET'] + df_final['Vlr_OUT'] + df_final['Vlr_NOV']
    
    def status(row):
        nov = row['Vlr_NOV']
        media = row['Media_3M_Vlr']
        if nov > 0 and media == 0: return 'Novo'
        if nov == 0 and media > 0: return 'Parou'
        if nov > media: return 'Cresceu'
        return 'Caiu'
    df_final['Status'] = df_final.apply(status, axis=1)
    
    return df_final

# --- APP ---

def main():
    df = carregar_consolidado()

    if df.empty or 'Cidade' not in df.columns:
        st.error("Erro: Dados não carregados.")
        return

    lista_cidades = sorted(df['Cidade'].unique())
    if not lista_cidades:
        st.warning("Nenhuma cidade da lista foi encontrada nos arquivos.")
        return

    # Sidebar
    with st.sidebar:
        st.title("🎯 Filtros")
        cidade_sel = st.selectbox("Cidade:", lista_cidades)

    df_cidade = df[df['Cidade'] == cidade_sel]

    st.title(f"📊 Painel: {cidade_sel}")
    
    v_ago = df_cidade['Vlr_AGO'].sum()
    v_set = df_cidade['Vlr_SET'].sum()
    v_out = df_cidade['Vlr_OUT'].sum()
    v_nov = df_cidade['Vlr_NOV'].sum()
    
    # Média real dos 3 meses
    media = (v_ago + v_set + v_out) / 3
    delta = v_nov - media

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Agosto", f"R$ {v_ago:,.0f}")
    col2.metric("Setembro", f"R$ {v_set:,.0f}")
    col3.metric("Outubro", f"R$ {v_out:,.0f}")
    col4.metric("Novembro", f"R$ {v_nov:,.0f}", delta=f"R$ {delta:,.0f}")

    st.divider()

    tab1, tab2, tab3 = st.tabs(["📅 Evolução", "⚖️ Comparativo", "📋 Detalhe"])

    with tab1:
        c1, c2 = st.columns(2)
        with c1:
            fig = go.Figure(data=[
                go.Bar(name='Ago', x=['Total'], y=[v_ago], marker_color=CORES['AGO'], text=f"{v_ago/1000:.0f}k"),
                go.Bar(name='Set', x=['Total'], y=[v_set], marker_color=CORES['SET'], text=f"{v_set/1000:.0f}k"),
                go.Bar(name='Out', x=['Total'], y=[v_out], marker_color=CORES['OUT'], text=f"{v_out/1000:.0f}k"),
                go.Bar(name='Nov', x=['Total'], y=[v_nov], marker_color=CORES['NOV'], text=f"{v_nov/1000:.0f}k")
            ])
            fig.update_layout(height=400, barmode='group')
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            top = df_cidade.sort_values('Total_Geral', ascending=False).head(10)
            fig2 = go.Figure()
            for m, c in [('AGO', CORES['AGO']), ('SET', CORES['SET']), ('OUT', CORES['OUT']), ('NOV', CORES['NOV'])]:
                fig2.add_trace(go.Bar(y=top['Produto'], x=top[f'Vlr_{m}'], name=m, orientation='h', marker_color=c))
            fig2.update_layout(height=400, barmode='group', yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig2, use_container_width=True)

    with tab2:
        top_nov = df_cidade.sort_values('Vlr_NOV', ascending=False).head(15)
        fig_comp = go.Figure()
        fig_comp.add_trace(go.Bar(y=top_nov['Produto'], x=top_nov['Media_3M_Vlr'], name='Média', orientation='h', marker_color=COR_MEDIA))
        fig_comp.add_trace(go.Bar(y=top_nov['Produto'], x=top_nov['Vlr_NOV'], name='Nov', orientation='h', marker_color=COR_DESTAQUE))
        fig_comp.update_layout(height=600, barmode='group', yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig_comp, use_container_width=True)

    with tab3:
        # Filtro Seguro
        status_disp = sorted(df_cidade['Status'].unique().tolist())
        padrao = [s for s in ['Queda', 'Parou', 'Cresceu'] if s in status_disp]
        filtro = st.multiselect("Status", status_disp, default=padrao)
        
        df_view = df_cidade[df_cidade['Status'].isin(filtro)].sort_values('Vlr_NOV', ascending=False)
        st.dataframe(
            df_view[['Produto', 'Status', 'Media_3M_Qtd', 'Qtd_NOV', 'Media_3M_Vlr', 'Vlr_NOV']],
            column_config={
                "Media_3M_Qtd": st.column_config.NumberColumn("Qtd Média", format="%.1f"),
                "Qtd_NOV": st.column_config.NumberColumn("Qtd Nov", format="%.0f"),
                "Media_3M_Vlr": st.column_config.NumberColumn("Média R$", format="R$ %.0f"),
                "Vlr_NOV": st.column_config.NumberColumn("Nov R$", format="R$ %.0f"),
            },
            use_container_width=True,
            height=600
        )

if __name__ == "__main__":
    main()