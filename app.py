import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go 
from google.oauth2 import service_account
from googleapiclient.discovery import build
from streamlit_option_menu import option_menu
from datetime import datetime

#========================================================================================
# Configuración de la página
st.set_page_config(page_title="Dashboard Trazabilidad", layout="wide")
st.title("Dashboard Trazabilidad Soporte")

# Autenticación con Google Sheets
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Detectar si estamos en Local o Cloud
if "service_account" in st.secrets:
    # Streamlit Cloud → secrets organizados en secciones
    sa_info = st.secrets["service_account"]
else:
    # Local → secrets como diccionario plano
    sa_info = st.secrets

credentials = service_account.Credentials.from_service_account_info(
    sa_info, scopes=SCOPES
)
service = build("sheets", "v4", credentials=credentials)

# ID de la hoja y nombre de la hoja
SPREADSHEET_ID = "1n1RzG32GYqTAK8Zm_Iqg3PEdt9U_YG4Nx-YwRCopMm8"
SHEET_NAME = "data"


@st.cache_data(ttl=60) # actualiza cada 60 segundos, reactiva pero no sobre carga el app
def load_data(): 
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!B2:AD"
    ).execute()

    values = result.get("values", [])
    if not values:
        st.warning("No se encontraron datos en la hoja de cálculo.")
        return pd.DataFrame()

    headers = values[0]
    data = values[1:]
    return pd.DataFrame(data, columns=headers)

# Cargar datos
df = load_data()

# Preprocesamiento común
if not df.empty:
    df['FECHA INGRESO'] = pd.to_datetime(df['FECHA INGRESO'], format='%d/%m/%Y', errors='coerce')
    df['FECHA ENTREGA'] = pd.to_datetime(df['FECHA ENTREGA'], format='%d/%m/%Y', errors='coerce')
    df["AÑO"] = df["FECHA INGRESO"].dt.year
    df['MES'] = df['FECHA INGRESO'].dt.strftime('%B')
    order = ['January', 'February', 'March', 'April', 'May', 'June', 
             'July', 'August', 'September', 'October', 'November', 'December']
    df['MES'] = pd.Categorical(df['MES'], categories=order, ordered=True)

# Sidebar
with st.sidebar:
    selected = option_menu(
        menu_title="Menú principal",
        options=["Inicio", "Consultas", "Estado del Equipo", "Reportes", "Etapas"],
        icons=["house", "search", "bar-chart", "list-check", "clock"],
        default_index=0
    )

#========================================================================================
# INICIO
if selected == "Inicio":
    st.header("Resumen General")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Equipos", len(df))
    with col2:
        st.metric("Entregados", len(df[df["ENTREGADO CLIENTE"] == "SI"]))
    with col3:
        st.metric("Pendientes", len(df[df["ENTREGADO CLIENTE"] != "SI"]))

    equipos_mes = df['MES'].value_counts().sort_index().reset_index()
    equipos_mes.columns = ['MES', 'CANTIDAD']
    fig = px.bar(equipos_mes, x='MES', y='CANTIDAD', title="Equipos ingresados por mes",
                 labels={'CANTIDAD': 'N° de equipos'}, color_discrete_sequence=["#00AACC"])
    st.plotly_chart(fig, use_container_width=True)

      # Mostrar outliers detectados

    with st.expander("Equipos pendientes"):
        st.dataframe(df[df["ENTREGADO CLIENTE"] != "SI"])
#========================================================================================
# CONSULTAS
elif selected == "Consultas":
    st.header("Filtros de Consulta")
    cliente = st.multiselect("Cliente:", options=df["NOMBRE / RAZÓN SOCIAL"].unique())
    serial = st.multiselect("Número de Serie:", options=df["SERIAL"].unique())

    df_filtered = df.copy()
    if cliente:
        df_filtered = df_filtered[df_filtered["NOMBRE / RAZÓN SOCIAL"].isin(cliente)]
    if serial:
        df_filtered = df_filtered[df_filtered["SERIAL"].isin(serial)]

    st.dataframe(df_filtered[["NOMBRE / RAZÓN SOCIAL", "MODELO", "SERIAL", "GARANTÍA", "OBSERVACIONES CLIENTE"]])

#========================================================================================
# REPORTES 
elif selected == "Reportes":
    st.header("Reportes")
    año = st.selectbox("Seleccione el año:", sorted(df["AÑO"].dropna().unique(), reverse=True))
    df_año = df[df["AÑO"] == año]
    
    resumen = df_año.groupby(["MES", "ACCIONES REALIZADAS"]).size().reset_index(name="CANTIDAD")

    # Mapa de colores personalizado
    color_map = {
        "HARDAWRE": "#F32E07",               # rojo intenso
        "COMPONENTES MECANICOS": "#E36F0A",  # rojo menos intenso
        "SOFTWARE": "#499FF4",               # azul oscuro
        "OPERACIONAL": "#3CD387",            # verde claro
        "OTROS": "#7E9B78"                   # rosado claro
    }

    fig = px.bar(
        resumen,
        x="MES",
        y="CANTIDAD",
        color="ACCIONES REALIZADAS",
        title=f"Equipos solucionados en {año}",
        barmode='relative',
        color_discrete_map=color_map
    )

    st.plotly_chart(fig, use_container_width=True)


#========================================================================================
# ESTADO DEL EQUIPO
elif selected == "Estado del Equipo":
    st.header("Estado del Equipo")
    con_diag = df[df["ACCIONES REALIZADAS"].notna() & (df["ACCIONES REALIZADAS"] != "")]
    sin_diag = df[df["ACCIONES REALIZADAS"].isna() | (df["ACCIONES REALIZADAS"] == "")]
    total = len(df)

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Con diagnóstico", f"{len(con_diag)}", f"{len(con_diag)/total*100:.1f}%")
    with col2:
        st.metric("Pendientes", f"{len(sin_diag)}", f"{len(sin_diag)/total*100:.1f}%")

    fig = go.Figure(go.Pie(
        labels=['Con diagnóstico', 'Sin diagnóstico'],
        values=[len(con_diag), len(sin_diag)],
        hole=0.5,
        marker_colors=['#4233ff', '#ff3333'],
        textinfo='percent+value',
        pull=[0.1, 0]
    ))
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("Ver detalles"):
        st.dataframe(df[["NOMBRE / RAZÓN SOCIAL", "DIAGNÓSTICO INICIAL", "ACCIONES REALIZADAS"]])

#========================================================================================
# ETAPAS
elif selected == "Etapas":
    st.header("Tiempos entre Etapas")

    # Calcular el tiempo total
    df["Tiempo Total"] = (df["FECHA ENTREGA"] - df["FECHA INGRESO"]).dt.days

    # Calcular el primer y tercer cuartil
    Q1 = df["Tiempo Total"].quantile(0.25)
    Q3 = df["Tiempo Total"].quantile(0.75)
    IQR = Q3 - Q1

    lower_bound = Q1 - 2.9 * IQR
    upper_bound = Q3 + 2.9 * IQR

    # Filtrar datos sin outliers
    df_sin_outliers = df[(df["Tiempo Total"] >= lower_bound) & (df["Tiempo Total"] <= upper_bound)]

    # Mostrar metricas sin outliers
    cols = st.columns(4)
    with cols[0]:
        avg_time = df_sin_outliers["Tiempo Total"].mean()
        st.metric("Promedio (sin outliers)", f"{round(avg_time,1)} días" if not pd.isna(avg_time) else "N/A")
    with cols[1]:
        st.metric("Mínimo", f"{df_sin_outliers['Tiempo Total'].min()} días")
    with cols[2]:
        st.metric("Máximo", f"{df_sin_outliers['Tiempo Total'].max()} días")
    with cols[3]:
        st.metric("Mediana", f"{df_sin_outliers['Tiempo Total'].median()} días")

    # Mostrar tabla general 
    st.subheader("Detalle por Equipo ")
    st.dataframe(df_sin_outliers[["NOMBRE / RAZÓN SOCIAL", "FECHA INGRESO", "FECHA ENTREGA", "Tiempo Total"]])

    # Mostrar outliers detectados
    outliers = df[(df["Tiempo Total"] < lower_bound) | (df["Tiempo Total"] > upper_bound)]
    if not outliers.empty:
        with st.expander("Identificar tiempos atípicos detectados"):
            st.dataframe(outliers[["NOMBRE / RAZÓN SOCIAL", "FECHA INGRESO", "FECHA ENTREGA", "Tiempo Total"]])