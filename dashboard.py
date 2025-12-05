import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import csv
import unicodedata
import os
import re

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Intelligence Sales PB",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- ESTILOS CUSTOMIZADOS ---
st.markdown("""
<style>
    .metric-card-container {
        background-color: #f0f2f6;
        border: 1px solid #dce1e6;
        padding: 20px;
        border-radius: 10px;
        color: #31333F;
    }
    /* Destacar abas */
    .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {
        font-size: 1.1rem;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# --- CONSTANTES ---
CORES = {'AGO': '#A6CEE3', 'SET': '#1F78B4', 'OUT': '#B2DF8A', 'NOV': '#E31A1C'}
COR_MEDIA = '#999999'
COR_DESTAQUE = '#E31A1C'

CIDADES_ALVO = [
    "CAJAZEIRAS", "CAMPINA GRANDE", "CATOLE DO ROCHA", "ITAPORANGA",
    "JUAZEIRINHO", "LIVRAMENTO", "MARIZOPOLIS", "MONTEIRO", "PATOS",
    "PIANCO", "POMBAL", "SANTA LUZIA", "SAO BENTO", "SOUSA"
]

# --- FUNÇÕES DE CARREGAMENTO ---

@st.cache_data(show_spinner=False)
def normalizar_texto(texto):
    if not isinstance(texto, str): return str(texto)
    return ''.join(c for c in unicodedata.normalize('NFD', texto) 
                   if unicodedata.category(c) != 'Mn').upper().strip()

@st.cache_data(show_spinner=True)
def ler_arquivo_universal(caminho_arquivo, label_mes):
    if not os.path.exists(caminho_arquivo):
        return pd.DataFrame()

    dados = []
    cidade_atual = None
    
    try:
        with open(caminho_arquivo, 'r', encoding='latin1', errors='replace') as f:
            linhas = f.readlines()
            
        for linha in linhas:
            linha = linha.strip()
            if not linha: continue
            if linha.startswith('#'): continue 

            linha_limpa = linha.replace('"', '')
            
            # --- 1. DETECTAR CIDADE ---
            if linha_limpa.startswith('PB'):
                # Caso A: Separado por vírgula (OUTU.csv)
                if ',' in linha_limpa:
                    partes = linha_limpa.split(',')
                    if len(partes) > 1:
                        cand = partes[1].strip()
                        if len(cand) > 2:
                            cidade_atual = normalizar_texto(cand)
                            continue
                
                # Caso B: Separado por espaço (OUT antigo)
                resto = linha_limpa[2:].strip().lstrip(' ,.-')
                if ',,' in resto: resto = resto.split(',')[0]
                if len(resto) > 2:
                    cidade_atual = normalizar_texto(resto)
                continue
                
            if any(x in linha for x in ['RMOV', 'Emissão:', 'Produto', 'Total :', 'TOTAL CIDADE']): continue
                
            # --- 2. EXTRAIR DADOS ---
            try:
                qtd, valor = 0.0, 0.0
                prod_nome = ""
                
                csv_reader = csv.reader([linha])
                cols_csv = next(csv_reader)
                cols_espaco = re.split(r'\s{2,}', linha_limpa)
                
                # Lógica Híbrida: CSV vs Texto Visual
                if len(cols_csv) >= 7 and any(c and any(char.isdigit() for char in c) for c in cols_csv[2:]):
                    if ',' in cols_csv[6]: valor = float(cols_csv[6].strip().replace('.', '').replace(',', '.'))
                    if ',' in cols_csv[2]: qtd = float(cols_csv[2].strip().replace('.', '').replace(',', '.'))
                    
                    # Nome: Col 1 (OUTU) ou Col 0 (AGO)
                    raw_0 = cols_csv[0].strip()
                    raw_1 = cols_csv[1].strip() if len(cols_csv) > 1 else ""
                    prod_nome = raw_1 if (raw_1 and len(raw_1) > 2 and not re.match(r'^[\d.,]+$', raw_1)) else raw_0

                elif len(cols_espaco) >= 5:
                    v_str = cols_espaco[-2]
                    if ',' in v_str: valor = float(v_str.replace('.', '').replace(',', '.'))
                    for item in cols_espaco[1:-2]:
                        if re.match(r'^\d{1,6},\d{2}$', item):
                            pq = float(item.replace('.', '').replace(',', '.'))
                            if pq > 0: qtd = pq; break
                    prod_nome = cols_espaco[0]

                if valor > 0 or qtd > 0:
                    nome = prod_nome.strip()
                    if '-' in nome: 
                        p = nome.split('-', 1)
                        if len(p) > 1: nome = p[1].strip()
                    if nome.startswith('0') and len(nome) > 1 and not nome[1].isdigit(): nome = nome[1:]
                    
                    dados.append({
                        'Cidade': cidade_atual if cidade_atual else "DESCONHECIDA",
                        'Produto': nome,
                        f'Qtd_{label_mes}': qtd,
                        f'Vlr_{label_mes}': valor
                    })
            except: continue
    except Exception: return pd.DataFrame()

    return pd.DataFrame(dados)

@st.cache_data(show_spinner=True)
def carregar_consolidado():
    arquivos = {'AGO': ['AGO.csv'], 'SET': ['SET.csv'], 'OUT': ['OUTU.csv', 'OUT (2).csv', 'OUT.csv'], 'NOV': ['NOV.csv']}
    dfs = []
    
    # Placeholder de carregamento
    msg = st.empty()
    
    for mes, nomes in arquivos.items():
        found = next((n for n in nomes if os.path.exists(n)), None)
        if found:
            msg.text(f"Processando {found}...")
            df = ler_arquivo_universal(found, mes)
            if not df.empty:
                if 'Cidade' not in df.columns: df['Cidade'] = "DESCONHECIDA"
                dfs.append(df.groupby(['Cidade', 'Produto'])[[f'Qtd_{mes}', f'Vlr_{mes}']].sum().reset_index())
        else:
            st.toast(f"⚠️ Arquivo de {mes} não encontrado.", icon="⚠️")
    
    msg.empty()
    
    if not dfs: return pd.DataFrame()
    
    df_final = dfs[0]
    for d in dfs[1:]: df_final = pd.merge(df_final, d, on=['Cidade', 'Produto'], how='outer')
    
    df_final = df_final.fillna(0)
    for m in ['AGO', 'SET', 'OUT', 'NOV']:
        if f'Vlr_{m}' not in df_final.columns: df_final[f'Vlr_{m}'] = 0.0
        if f'Qtd_{m}' not in df_final.columns: df_final[f'Qtd_{m}'] = 0.0

    df_final.columns = df_final.columns.str.strip()
    
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

# --- APP MAIN ---

def main():
    df = carregar_consolidado()

    if df.empty or 'Cidade' not in df.columns:
        st.error("⚠️ Dados não encontrados. Verifique se os arquivos CSV estão na pasta.")
        return

    lista_cidades = sorted(df['Cidade'].unique())
    if not lista_cidades:
        st.warning("Arquivos lidos, mas nenhuma das cidades alvo foi encontrada.")
        return

    # --- SIDEBAR ---
    with st.sidebar:
        st.title("🎯 Filtros")
        cidade_sel = st.selectbox("Cidade:", lista_cidades)
        st.info("Este painel compara o desempenho atual (Novembro) com a média dos 3 meses anteriores.")

    df_cidade = df[df['Cidade'] == cidade_sel]

    # --- HEADER ---
    st.title(f"📊 Painel de Performance: {cidade_sel}")
    
    v_ago = df_cidade['Vlr_AGO'].sum()
    v_set = df_cidade['Vlr_SET'].sum()
    v_out = df_cidade['Vlr_OUT'].sum()
    v_nov = df_cidade['Vlr_NOV'].sum()
    
    media = (v_ago + v_set + v_out) / 3
    delta = v_nov - media

    # Cards KPI
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Agosto", f"R$ {v_ago:,.0f}")
    c2.metric("Setembro", f"R$ {v_set:,.0f}")
    c3.metric("Outubro", f"R$ {v_out:,.0f}")
    c4.metric("Novembro", f"R$ {v_nov:,.0f}", delta=f"R$ {delta:,.0f} (vs Média)")

    st.divider()

    # --- ABAS ---
    tab1, tab2, tab3, tab4 = st.tabs([
        "📅 Visão Temporal", "⚖️ Comparativo", "📋 Detalhamento", "👥 Clientes (Próx. Passo)"
    ])

    # 1. Evolução
    with tab1:
        col_graf1, col_graf2 = st.columns([1, 1])
        with col_graf1:
            st.subheader("Faturamento Mensal")
            fig = go.Figure(data=[
                go.Bar(name='Ago', x=['Total'], y=[v_ago], marker_color=CORES['AGO'], text=f"R$ {v_ago/1000:.0f}k"),
                go.Bar(name='Set', x=['Total'], y=[v_set], marker_color=CORES['SET'], text=f"R$ {v_set/1000:.0f}k"),
                go.Bar(name='Out', x=['Total'], y=[v_out], marker_color=CORES['OUT'], text=f"R$ {v_out/1000:.0f}k"),
                go.Bar(name='Nov', x=['Total'], y=[v_nov], marker_color=CORES['NOV'], text=f"R$ {v_nov/1000:.0f}k")
            ])
            fig.update_traces(textposition='auto')
            fig.update_layout(height=400, barmode='group')
            st.plotly_chart(fig, use_container_width=True)
        
        with col_graf2:
            st.subheader("Top Produtos (Evolução)")
            top_ev = df_cidade.sort_values('Total_Geral', ascending=False).head(10)
            fig2 = go.Figure()
            for m, c in [('AGO', CORES['AGO']), ('SET', CORES['SET']), ('OUT', CORES['OUT']), ('NOV', CORES['NOV'])]:
                fig2.add_trace(go.Bar(y=top_ev['Produto'], x=top_ev[f'Vlr_{m}'], name=m, orientation='h', marker_color=c))
            fig2.update_layout(height=400, barmode='group', yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig2, use_container_width=True)

    # 2. Comparativo
    with tab2:
        st.subheader("Média Histórica vs Novembro")
        top_nov = df_cidade.sort_values('Vlr_NOV', ascending=False).head(15)
        fig_comp = go.Figure()
        fig_comp.add_trace(go.Bar(
            y=top_nov['Produto'], x=top_nov['Media_3M_Vlr'],
            name='Média (3 Meses)', orientation='h', marker_color=COR_MEDIA,
            text=top_nov['Media_3M_Vlr'].apply(lambda x: f"{x/1000:.1f}k"), textposition='auto'
        ))
        fig_comp.add_trace(go.Bar(
            y=top_nov['Produto'], x=top_nov['Vlr_NOV'],
            name='Novembro', orientation='h', marker_color=COR_DESTAQUE,
            text=top_nov['Vlr_NOV'].apply(lambda x: f"{x/1000:.1f}k"), textposition='auto'
        ))
        fig_comp.update_layout(height=600, barmode='group', yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig_comp, use_container_width=True)

    # 3. Tabela
    with tab3:
        c_filt, c_tab = st.columns([1, 4])
        with c_filt:
            st.write("##### Filtros")
            status_disp = sorted(df_cidade['Status'].unique().tolist())
            padrao = [s for s in ['Queda', 'Parou', 'Cresceu'] if s in status_disp]
            filtro_status = st.multiselect("Status:", status_disp, default=padrao)
            
            sort_opt = st.radio("Ordenar:", ["Maior Valor (Nov)", "Maior Queda"])
        
        with c_tab:
            df_view = df_cidade[df_cidade['Status'].isin(filtro_status)]
            if sort_opt == "Maior Valor (Nov)":
                df_view = df_view.sort_values('Vlr_NOV', ascending=False)
            else:
                df_view['Diff'] = df_view['Vlr_NOV'] - df_view['Media_3M_Vlr']
                df_view = df_view.sort_values('Diff', ascending=True)

            st.dataframe(
                df_view[['Produto', 'Status', 'Media_3M_Qtd', 'Qtd_NOV', 'Media_3M_Vlr', 'Vlr_NOV']],
                column_config={
                    "Media_3M_Qtd": st.column_config.NumberColumn("Qtd Média", format="%.1f"),
                    "Qtd_NOV": st.column_config.NumberColumn("Qtd Nov", format="%.0f"),
                    "Media_3M_Vlr": st.column_config.NumberColumn("Média R$", format="R$ %.2f"),
                    "Vlr_NOV": st.column_config.NumberColumn("Nov R$", format="R$ %.2f"),
                },
                use_container_width=True,
                height=600
            )

    # 4. Clientes
    with tab4:
        st.markdown("### 👥 Análise de Clientes")
        st.warning("⚠️ Atenção: Os arquivos carregados atualmente (Curva ABC de Produtos) não contêm os nomes dos clientes.")
        st.info("Para ativar esta aba, o próximo passo é exportar do sistema um relatório que contenha as colunas: 'Cliente', 'Cidade' e 'Valor Total'.")

if __name__ == "__main__":
    main()