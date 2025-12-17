import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go 
from streamlit_option_menu import option_menu
from datetime import datetime
import s3fs
import io

# ========================================================================================
# --- CONFIGURACIÓN DE PÁGINA Y CONSTANTES S3 ---
# ========================================================================================
st.set_page_config(page_title="Dashboard Trazabilidad", layout="wide")
st.title("Dashboard Trazabilidad Soporte (Backend S3)")

# Configuración de S3
BUCKET_NAME = "support-trac"
# Usamos la clave de archivo tal como la proporcionaste, S3 la maneja con espacios.
FILE_KEY = "TRAZABILIDAD_SOPORTE - data.csv" 

# Obtener credenciales de Streamlit Secrets
@st.cache_resource
def get_s3_auth():
    """Obtiene las credenciales de AWS desde st.secrets."""
    try:
        # Intenta acceder a las credenciales bajo la clave 'aws'
        secrets = st.secrets["aws"]
        
        return {
            'key': secrets['aws_access_key_id'],
            'secret': secrets['aws_secret_access_key']
        }
    except KeyError as e:
        st.error(f"Error: La clave de AWS '{e.args[0]}' no se encontró en st.secrets. Verifique la configuración en secrets.toml.")
        st.stop()
    except Exception as e:
        st.error(f"Error al obtener secretos: {e}")
        st.stop()


# ========================================================================================
# --- FUNCIONES DE LECTURA Y ESCRITURA S3 ---
# ========================================================================================

@st.cache_data(ttl=60) # Carga los datos y los mantiene en caché por 60 segundos
def load_data(): 
    """Lee el DataFrame desde S3 usando las credenciales."""
    auth = get_s3_auth()
    s3_path = f"s3://{BUCKET_NAME}/{FILE_KEY}"
    
    try:
        # Leer el CSV directamente desde S3
        df = pd.read_csv(s3_path, storage_options=auth, header=0)
        print(df.head(10))  # Debug: Ver las primeras 10 filas cargadas
        print(df.columns)  # Debug: Ver las columnas cargadas
        
        if df.empty:
            st.warning("El archivo en S3 está vacío.")
            return pd.DataFrame()
            
        # Limpieza de columnas, esencial al migrar de Sheets/Excel
        df.columns = df.columns.str.strip() 
        
        st.success(f"Datos cargados exitosamente desde S3: {len(df)} filas.")
        return df

    except Exception as e:
        st.error(f"Error al cargar datos desde S3. Verifique credenciales y ruta. Detalles: {e}")
        return pd.DataFrame()


def save_data(df_to_save):
    """Sobrescribe el archivo CSV en S3 con el DataFrame actualizado."""
    auth = get_s3_auth()
    s3_path = f"s3://{BUCKET_NAME}/{FILE_KEY}"
    
    try:
        # Escribir el DataFrame completo de vuelta a S3 (Sobrescribiendo)
        df_to_save.to_csv(s3_path, index=False, storage_options=auth)
        
        # 🚨 Limpiar el caché de la función load_data para que se vuelva a cargar
        load_data.clear() 
        
        st.success("Datos guardados y actualizados exitosamente en S3.")
        return True

    except Exception as e:
        st.error(f"Error al guardar datos en S3. Verifique permisos (s3:PutObject). Detalles: {e}")
        return False


# ========================================================================================
# --- Carga Inicial y Preprocesamiento ---
# ========================================================================================

# Inicializa el DataFrame en el estado de sesión si aún no existe
if 'df' not in st.session_state:
    st.session_state.df = load_data()

# ⚠️ NOTA: df apunta al objeto en st.session_state.df. 
# Si load_data() no hace la copia, usar .copy() aquí es más seguro.
df = st.session_state.df.copy() # <--- Sugerencia: Usar .copy() para evitar efectos secundarios inesperados

if df.empty:
    st.info("La aplicación no puede continuar sin datos. Cargue un CSV válido en S3.")
    st.stop()

# PREPROCESAMIENTO DE FECHAS

# --- Preprocesamiento Común (Ajustado al formato DD/MM/YYYY HH:MM) ---

# Asegúrate de que estas constantes estén definidas al inicio de tu script

COL_FECHA_ENTREGA = 'FECHA ENTREGA'
COL_FECHA_INGRESO = 'FECHA INGRESO'

COL_SERIAL = "SERIAL" # Se asume que esta columna existe y es única
COL_NOMBRE = "NOMBRE / RAZÓN SOCIAL" # Se asume la normalización

# --- Nuevas Constantes de Categorías ---
COL_GARANTIA = 'GARANTÍA'
COL_DIAGNOSTICO = 'DIAGNÓSTICO INICIAL'


OPCIONES_GARANTIA = ['SI', 'NO']
OPCIONES_DIAGNOSTICO = ['OPERACIONAL', 'COMPONENTES MECANICOS', 'HARDAWRE', 'SOFTWARE', 'OTROS']

OPCIONES_MODELO = ["X5RT", "X5R", "X5 MOBILE", "X5 STICK", "X25R", "X25RL", "OTROS"]
OPCIONES_ESTADO_INGRESO = ["REPARADO", "NUEVO", "USADO", "MALOGRADO"]
OPCIONES_ACCIONES = ["SOFTWARE", "HARDAWRE", "OPERACIONAL", "COMPONENTES MECANICOS", "OTROS"]
OPCIONES_DIAGNOSTICO_METTA = ["SI", "NO"]

DATE_COLS_LIST = ['FECHA INGRESO', 'FECHA ENTREGA', 'FECHA_SOPORTE'] # Incluir todas las columnas de fecha


# --- Preprocesamiento Común (AJUSTE CRÍTICO DEL FORMATO DE FECHA) ---

# ... (constantes y df no empty check) ...

if not df.empty:
    try:
        # 1. Procesar FECHA INGRESO
        if COL_FECHA_INGRESO in df.columns:
            # Quitamos el formato explícito
            # Esto es más flexible con los formatos que Pandas usa al guardar.
            df[COL_FECHA_INGRESO] = pd.to_datetime(
                df[COL_FECHA_INGRESO], 
                #dayfirst=True,              # Mantiene el orden DD/MM si es inferido
                errors='coerce',
                infer_datetime_format=True  # Permite a Pandas adivinar el nuevo formato
            )

            # 2. Crear las columnas de AÑO y MES
            #df.dropna(subset=[COL_FECHA_INGRESO], inplace=True) 

            # ... (Resto de la lógica de creación de AÑO y MES) ...
            if not df.empty:
                df["AÑO"] = df[COL_FECHA_INGRESO].dt.year
                df['MES'] = df[COL_FECHA_INGRESO].dt.strftime('%B')
                
                order = ['January', 'February', 'March', 'April', 'May', 'June', 
                         'July', 'August', 'September', 'October', 'November', 'December']
                df['MES'] = pd.Categorical(df['MES'], categories=order, ordered=True)
                
        # 3. Procesar FECHA ENTREGA (Aplicamos la misma lógica flexible)
        if COL_FECHA_ENTREGA in df.columns:
            df[COL_FECHA_ENTREGA] = pd.to_datetime(
                df[COL_FECHA_ENTREGA], 
                #dayfirst=True,
                errors='coerce',
                infer_datetime_format=True
            )
            
        # 4. REASIGNACIÓN DE DATOS
        st.session_state.df = df 

    except Exception as e:
        st.error(f"Error crítico durante la conversión de fechas. Error: {e}")


# ========================================================================================
# --- SIDEBAR Y NAVEGACIÓN ---
# ========================================================================================

with st.sidebar:
    selected = option_menu(
        menu_title="Menú principal",
        # Se añade la opción "Ingreso de Datos" para probar la función save_data
        options=["Inicio", "Ingreso de Datos", "Consultas", "Estado del Equipo", "Reportes", "Etapas"], 
        icons=["house", "pencil", "search", "bar-chart", "list-check", "clock"],
        default_index=0
    )

# ========================================================================================
# --- INGRESO DE DATOS (Módulo de Escritura y Edición) ---
# ========================================================================================

if selected == "Ingreso de Datos":
    st.header("Gestión y Edición Completa del Registro")
    st.warning("⚠️ Esta acción sobrescribirá el archivo completo en S3.")
    
    # 1. Selección de Modo
    modo = st.radio(
        "Seleccione la acción:",
        ["Nuevo Registro", "Editar Registro Existente"],
        horizontal=True
    )
    
    current_df = st.session_state.df.copy()
    default_values = {}
    selected_serial = "Nuevo"

    # 2. Lógica para cargar datos si es edición
    if modo == "Editar Registro Existente":
        serial_options = current_df[COL_SERIAL].dropna().unique().tolist()
        selected_serial = st.selectbox(
            "Seleccione el N° de Serie a Editar:",
            options=['-- Seleccione --'] + serial_options
        )
        
        if selected_serial != '-- Seleccione --':
            record_to_edit = current_df[current_df[COL_SERIAL] == selected_serial].iloc[0]
            default_values = record_to_edit.to_dict()

    # 3. Formulario Dinámico
    with st.form("data_management_form"):
        st.subheader(f"Datos del Equipo ({'Nuevo' if modo == 'Nuevo Registro' else 'Editando: ' + str(selected_serial)})")
        
        new_data = {}

        # --- BUCLE DE COLUMNAS ---
        # --- BUCLE DE COLUMNAS ACTUALIZADO ---
        for col in current_df.columns:
            if col in ['AÑO', 'MES']:
                continue

            default_value = default_values.get(col)
            default_str = str(default_value).strip() if pd.notna(default_value) else ''
            
            # 📅 CASO 1: FECHAS (Incluye FECHA_SOPORTE)
            if col in DATE_COLS_LIST:
                date_val = datetime.now().date()
                if default_str != '':
                    try:
                        date_val = pd.to_datetime(default_str).date()
                    except:
                        pass
                input_date = st.date_input(col, value=date_val)
                new_data[col] = input_date.strftime('%d/%m/%Y')
            
            # 🎯 CASO 2: MODELO (Categorías fijas)
            elif col == 'MODELO':
                opciones = [''] + OPCIONES_MODELO
                idx = opciones.index(default_str) if default_str in opciones else 0
                new_data[col] = st.selectbox(col, options=opciones, index=idx)

            # 🎯 CASO 3: ESTADO DE INGRESO
            elif col == 'ESTADO DE INGRESO':
                opciones = [''] + OPCIONES_ESTADO_INGRESO
                idx = opciones.index(default_str) if default_str in opciones else 0
                new_data[col] = st.selectbox(col, options=opciones, index=idx)

            # 🎯 CASO 4: ACCIONES REALIZADAS
            elif col == 'ACCIONES REALIZADAS':
                opciones = [''] + OPCIONES_ACCIONES
                idx = opciones.index(default_str) if default_str in opciones else 0
                new_data[col] = st.selectbox(col, options=opciones, index=idx)

            # 🎯 CASO 5: DIAGNOSTICO_METTA (SI/NO)
            elif col == 'DIAGNOSTICO_METTA':
                opciones = ['', 'SI', 'NO']
                idx = opciones.index(default_str) if default_str in opciones else 0
                new_data[col] = st.selectbox(col, options=opciones, index=idx)

            # 🎯 CASO 6: GARANTÍA (Ya existente)
            elif col == COL_GARANTIA:
                opciones = ['', 'SI', 'NO']
                idx = opciones.index(default_str) if default_str in opciones else 0
                new_data[col] = st.selectbox(col, options=opciones, index=idx)

            # 🔒 CASO 7: SERIAL (Clave primaria)
            elif col == COL_SERIAL:
                if modo == 'Editar Registro Existente':
                    new_data[col] = st.text_input(col, value=default_str, disabled=True)
                else:
                    new_data[col] = st.text_input(col, value=default_str)

            # ✍️ CASO 8: OTROS CAMPOS (Texto simple)
            else:
                new_data[col] = st.text_input(col, value=default_str)

        # --- BOTÓN DE GUARDADO (FUERA DEL BUCLE) ---
        submitted = st.form_submit_button(
            "Guardar Cambios en S3")
        
        if submitted:
                # 1. DESCLASIFICAR COLUMNAS (Mantenlo tal cual, es perfecto)
                for col in current_df.columns:
                    if current_df[col].dtype.name == 'category':
                        current_df[col] = current_df[col].astype(str)
                
                # 2. ASEGURAR QUE new_data TENGA TODAS LAS COLUMNAS DEL DATAFRAME
                # A veces, si una columna no pasó por el formulario, podría faltar en new_data.
                # Esto asegura que la nueva fila coincida exactamente con la estructura del DF.
                full_record = {col: new_data.get(col, "") for col in current_df.columns}
                new_record_series = pd.Series(full_record)
                
                # 3. LÓGICA DE NUEVO REGISTRO
                if modo == "Nuevo Registro":
                    new_serial_value_str = str(new_record_series[COL_SERIAL]).strip()
                    
                    is_empty = new_serial_value_str == ""
                    # Verificación de duplicados mejorada para ignorar espacios accidentales
                    is_duplicate = new_serial_value_str in current_df[COL_SERIAL].astype(str).str.strip().values 

                    if is_empty:
                        st.error(f"El campo '{COL_SERIAL}' no puede estar vacío.")
                    elif is_duplicate:
                        st.error(f"El N° de Serie '{new_serial_value_str}' ya existe.")
                    else:
                        # Usamos ignore_index=True para mantener el orden secuencial
                        updated_df = pd.concat([current_df, new_record_series.to_frame().T], ignore_index=True)
                        
                        if save_data(updated_df):
                            st.session_state.df = updated_df
                            st.success("✅ Registro creado exitosamente.")
                            st.rerun()
                            
                # 4. LÓGICA DE EDICIÓN
                elif modo == "Editar Registro Existente" and selected_serial != '-- Seleccione --':
                    idx = current_df[current_df[COL_SERIAL] == selected_serial].index
                    
                    if not idx.empty:
                        # Actualización de la fila
                        current_df.loc[idx[0]] = new_record_series
                        
                        if save_data(current_df):
                            st.session_state.df = current_df
                            st.success("✅ Registro actualizado exitosamente.")
                            st.rerun()
                    else:
                        st.error("Error: No se encontró el registro para actualizar.")

    st.subheader("Vista Previa (Últimos 10 Registros)")
    st.dataframe(st.session_state.df.tail(10), use_container_width=True)

# ... (El resto del script sigue igual)

# ========================================================================================
# --- CÓDIGO ORIGINAL (Adaptado para usar df = st.session_state.df) ---
# ========================================================================================

# INICIO
elif selected == "Inicio":
    st.header("Resumen General")
    # ... (código mantenido) ...
    col1, col2, col3 = st.columns(3)
    
    if "ENTREGADO CLIENTE" in df.columns:
        total_equipos = len(df)
        entregados = len(df[df["ENTREGADO CLIENTE"].astype(str).str.upper().isin(["SI", "SÍ"])])
        pendientes = total_equipos - entregados
        
        with col1:
            st.metric("Total Equipos", total_equipos)
        with col2:
            st.metric("Entregados", entregados)
        with col3:
            st.metric("Pendientes", pendientes)
            
        with st.expander("Equipos pendientes"):
            st.dataframe(df[df["ENTREGADO CLIENTE"].astype(str).str.upper().isin(["NO", "N/A", "PENDIENTE"]) | df["ENTREGADO CLIENTE"].isna()])
    else:
        st.warning("Columna 'ENTREGADO CLIENTE' no encontrada para el resumen de estado.")
        st.metric("Total Equipos", len(df))
        
    
    if 'MES' in df.columns:
        equipos_mes = df['MES'].value_counts().sort_index().reset_index()
        equipos_mes.columns = ['MES', 'CANTIDAD']
        fig = px.bar(equipos_mes, x='MES', y='CANTIDAD', title="Equipos ingresados por mes",
                     labels={'CANTIDAD': 'N° de equipos'}, color_discrete_sequence=["#00AACC"])
        st.plotly_chart(fig, use_container_width=True)


# CONSULTAS
elif selected == "Consultas":
    st.header("Filtros de Consulta")
    if "NOMBRE / RAZÓN SOCIAL" in df.columns and "SERIAL" in df.columns:
        cliente = st.multiselect("Cliente:", options=df["NOMBRE / RAZÓN SOCIAL"].unique())
        serial = st.multiselect("Número de Serie:", options=df["SERIAL"].unique())

        df_filtered = df.copy()
        if cliente:
            df_filtered = df_filtered[df_filtered["NOMBRE / RAZÓN SOCIAL"].isin(cliente)]
        if serial:
            df_filtered = df_filtered[df_filtered["SERIAL"].isin(serial)]

        cols_to_show = ["NOMBRE / RAZÓN SOCIAL", "MODELO", "SERIAL", "GARANTÍA", "OBSERVACIONES CLIENTE","FECHA INGRESO"]
        existing_cols = [c for c in cols_to_show if c in df_filtered.columns]
        
        st.dataframe(df_filtered[existing_cols])
    else:
        st.error("Columnas 'NOMBRE / RAZÓN SOCIAL' o 'SERIAL' faltantes para la consulta.")

# REPORTES
elif selected == "Reportes":
    st.header("Reportes")
    # ... (código mantenido, asumiendo que las columnas existen) ...
    if "AÑO" in df.columns and "ACCIONES REALIZADAS" in df.columns:
        año = st.selectbox("Seleccione el año:", sorted(df["AÑO"].dropna().unique(), reverse=True))
        df_año = df[df["AÑO"] == año]
        
        # -------------------------
        # 1) GRÁFICO DE ACCIONES REALIZADAS
        # -------------------------

        resumen = df_año.groupby(["MES", "ACCIONES REALIZADAS"]).size().reset_index(name="CANTIDAD")

        # Mapa de colores personalizado
        color_map = {
            "HARDAWRE": "#F32E07", "COMPONENTES MECANICOS": "#E36F0A", 
            "SOFTWARE": "#499FF4", "OPERACIONAL": "#3CD387", "OTROS": "#7E9B78"
        }

        st.subheader(f"Equipos Ingresados en {año}")
        fig = px.bar(
            resumen,
            x="MES",
            y="CANTIDAD",
            color="ACCIONES REALIZADAS",
            barmode='relative',
            color_discrete_map=color_map
        )
        st.plotly_chart(fig, use_container_width=True)

        # -------------------------
        # 2) RATIO DE DESPERFECTO DE FÁBRICA
        # -------------------------
        st.subheader("Ratio de desperfecto de fábrica")

        st.markdown("""
        El **ratio de desperfectos de fábrica** se calcula como:
        \n
        **(Hardware + Componentes Mecánicos) / Total de equipos comercializados del mes × 100**
        """)

        # Cargar CSV desde el usuario
        archivo_csv = st.file_uploader("Cargar archivo CSV con equipos comercializados por mes", type="csv")

        if archivo_csv is not None:
            # Se mantiene el resto del código del ratio (requiere el archivo subido por el usuario)
            # ... [La lógica de procesamiento del archivo subido se mantiene aquí] ...
            df_comercializados = pd.read_csv(archivo_csv)

            # 🔍 Normalizar nombres de columnas
            df_comercializados.columns = df_comercializados.columns.str.upper()

            # Se espera un CSV con columnas: MES, TOTAL_EQUIPOS
            if not {"MES", "TOTAL_EQUIPOS"}.issubset(df_comercializados.columns):
                st.error("El CSV debe contener las columnas: MES y TOTAL_EQUIPOS.")
            else:
                # Filtrar el DataFrame del año seleccionado
                df_fallas = df_año.copy()

                # Identificar desperfectos de fábrica
                df_fallas["DESPERFECTO_FABRICA"] = df_fallas["ACCIONES REALIZADAS"].isin([
                    "HARDAWRE", "COMPONENTES MECANICOS"
                ])

                # Calcular fallas por mes
                fallas_mes = df_fallas.groupby("MES")["DESPERFECTO_FABRICA"].sum().reset_index()
                fallas_mes.rename(columns={"DESPERFECTO_FABRICA": "FALLAS"}, inplace=True)

                # Unir con el CSV cargado
                ratio_df = pd.merge(fallas_mes, df_comercializados, on="MES", how="left")

                # Calcular ratio
                ratio_df["RATIO_DESPERFECTO"] = (ratio_df["FALLAS"] / ratio_df["TOTAL_EQUIPOS"]) * 100

                # Gráfico del ratio
                fig_ratio = px.line(
                    ratio_df,
                    x="MES",
                    y="RATIO_DESPERFECTO",
                    markers=True,
                    title=f"Ratio de desperfecto de fábrica ({año})",
                    labels={"RATIO_DESPERFECTO": "Ratio (%)"},
                )

                # Asegurar estilo de línea y marcadores
                fig_ratio.update_traces(
                    line_color="#F32E07",
                    line_width=4,
                    mode="lines+markers+text", 
                    marker=dict(size=10, color="#F32E07"),
                    text=[f"{v:.2f}%" for v in ratio_df["RATIO_DESPERFECTO"].fillna(0)],
                    textposition="top center",
                    textfont=dict(color="black", size=15)
                )

                # Ajuste del título (tamaño)
                fig_ratio.update_layout(
                    title_font=dict(size=28)
                )

                # Ajustar eje Y
                # Usar .max() + un margen, con manejo de NaNs o valores vacíos
                max_ratio = ratio_df["RATIO_DESPERFECTO"].max()
                if not pd.isna(max_ratio):
                    fig_ratio.update_yaxes(range=[0, max_ratio * 1.2])

                st.plotly_chart(fig_ratio, use_container_width=True)

                # Mostrar tabla resumen
                with st.expander("Ver datos del ratio"):
                    st.dataframe(ratio_df)

        else:
            st.info("Cargue un archivo CSV para calcular el ratio.")
    else:
        st.error("Columnas 'AÑO' o 'ACCIONES REALIZADAS' faltantes para el reporte.")


# ESTADO DEL EQUIPO
elif selected == "Estado del Equipo":
    st.header("Estado del Equipo")
    # ... (código mantenido) ...
    if "ACCIONES REALIZADAS" in df.columns:
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
    else:
        st.error("Columna 'ACCIONES REALIZADAS' faltante para este reporte.")

# ETAPAS
elif selected == "Etapas":
    st.header("Tiempos entre Etapas")
    # ... (código mantenido) ...
    if "FECHA ENTREGA" in df.columns and "FECHA INGRESO" in df.columns:
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
        # ... (métricas mantenidas) ...
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
    else:
        st.error("Columnas 'FECHA INGRESO' o 'FECHA ENTREGA' faltantes para el análisis de etapas.")