### Sección:  Librerías y Módulos
import sys
import time

### Sección: # Librerías
import pandas as pd
import numpy as np
import datetime as dt
#import itertools
import os
import tqdm
import matplotlib.pyplot as plt
import yfinance as yf
#import mip
import pickle
import matplotlib.pyplot as plt
import tqdm

from sklearn.model_selection import train_test_split

#import import_ipynb # permite importar módulos ipynb
import warnings
warnings.filterwarnings("ignore")


from sklearn.model_selection import train_test_split
from sklearn.preprocessing import PolynomialFeatures
from sklearn.linear_model import LinearRegression
from random import randint



################## NUEVA VERSION 240902 ##############################    

def generate_df_subconjunto_funcion(last_date, df, n_datos, continuar_si_hay_menos = True): # Análogo a generate_df_intervalos
    # Last_t es cual es el día que se está mirando hacia atrás
    # k esla proporción de datos (donde k = 1 es desde el inicio)

    #print('ARGS')
    #print(last_date, df, n_datos, continuar_si_hay_menos)
    
    df = df[df['Date'] < last_date].reset_index(drop = True)
    df = df.tail(n_datos).reset_index(drop = True)
    
    if (len(df) < n_datos) and continuar_si_hay_menos:
        return df, True
    
    return df, False
    

def fibonacci(sub_df, close_point, campos_extremos):
    
    if len(sub_df) == 0:
        return 0

    sub_df['MIN'], sub_df['MAX'] = sub_df[campos_extremos].min(axis = 1), sub_df[campos_extremos].max(axis = 1) # Se identifican los t en los que están los máximos y los mínimos del periodo
    sub_df['EXTREMO'] = np.where(sub_df['MIN'] == sub_df['MIN'].min(), 'MIN', np.where(sub_df['MAX'] == sub_df['MAX'].max(), 'MAX', ''))

    df_extremos = sub_df[sub_df['EXTREMO'] != ''].drop_duplicates(subset = ['EXTREMO']).reset_index(drop = True) # Se aislan los extremos
    
    if len(df_extremos) != 2:
        v_fibonacci = 0 # caso por defecto si LEN = 1
        return v_fibonacci

    if df_extremos['EXTREMO'][0] == 'MIN': # si el minimo ocurre antes del máximo: Fibonacci a la baja
        minimo, maximo = df_extremos['MIN'][0], df_extremos['MAX'][1]
        v_fibonacci = (maximo - close_point) / (maximo - minimo) # a la baja
        v_fibonacci = - v_fibonacci # a la baja
    else:
        minimo, maximo = df_extremos['MIN'][1], df_extremos['MAX'][0]
        v_fibonacci = (close_point - minimo) / (maximo - minimo) # al alza
    
    return v_fibonacci
    

def generate_fibonacci(df, df_all_data, df_iteracion):
    
    df['Close point'] = df['Close']
    
    n_datos, modo_vela = df_iteracion['n_datos'][0], df_iteracion['modo_vela'][0]
    campos_extremos = ['Open', 'Close'] if modo_vela == 'cuerpo' else ['Low', 'High']
    
    df_fibonacci = df[['Date', 't', 'Close point'] + campos_extremos].copy()

    df_fibonacci[['sub_df', 'continuar']] = df_fibonacci['Date'].apply(lambda x: pd.Series(generate_df_subconjunto_funcion(x, df_all_data, n_datos))) # pd series porque el output tiene 2 o más valores
    
    df_fibonacci['X'] = df_fibonacci.apply(lambda row: fibonacci(row['sub_df'], row['Close point'], campos_extremos), axis = 1)

    return df_fibonacci


def generate_media_movil(df, df_all_data, df_iteracion):
    
    n_datos, campo_precio = df_iteracion['n_datos'][0], df_iteracion['campo'][0]
    df_all_data['X'] = df_all_data[campo_precio].shift(1).rolling(window = n_datos).mean() # .shift(1): hasta t - 1
        
    return df_all_data 

def generate_suavexp(df, df_all_data, df_iteracion):
    
    alpha, campo_precio = df_iteracion['alpha'][0], df_iteracion['campo'][0] 
    df_all_data['X'] = df_all_data[campo_precio].shift(1).ewm(alpha = alpha, adjust = False).mean() # adjust = True, termina normalizando los datos para ajustarlos con los reales

    return df_all_data 


        
############################################### 


def pickle_act(file_name, variable = None, mode = 'open', eliminar_si_problemas = False):
    
    """
    Guarda o carga una variable utilizando la biblioteca pickle.

    Parameters:
        - file_path (str): La ruta al archivo pickle.
        - variable: La variable a guardar (si mode='save') o None (si mode='open').
        - mode (str): 'save' para guardar la variable, 'open' para cargar la variable.

    Returns:
        La variable cargada si mode='open' o None si mode='save'.
    """
    
    dic_mode = {'save': 'wb', 'open': 'rb'}
    
    #while True:
    #    try:
    #print(f'{file_name}.pkl')
    with open(f'{file_name}.pkl', dic_mode[mode]) as file:
        if mode == 'save':
            pickle.dump(variable, file)
            return None
        else:
            #print('file en funciones transversales', f'{file_name}.pkl')
            if eliminar_si_problemas:
                try:
                    variable = pickle.load(file)
                except:
                    os.remove(f'{file_name}.pkl')
                    return pd.DataFrame()
            else:
                print(file_name)
                print(file)
                variable = pickle.load(file)
            return variable
        
def sub_df(df, t):
    df = df[df['t'] <= t]
    return df

def split_and_assign(df, test_size):
    if len(df) > 1:
        train_df, test_df = train_test_split(df, test_size = test_size, shuffle = False) # cambio el 240619 (validar funcionamiento)
    else:
        train_df, test_df = df, pd.DataFrame(columns = df.columns)
    return pd.Series({'train_df': train_df, 'test_df': test_df})

def sort_df(df):
    return df.sort_values(by = 't').reset_index(drop=True)

def obtener_last_y(df):
    if len(df) > 0:
        return df['Close'].iloc[-1]
    else:
        return None

def obtener_valores(df_t, train, test):
    x_train = np.array(train['t'])
    x_test = np.array(test['t'])
    x_total = np.array(df_t['t'])
    y = np.array(train['Close'])
    return pd.Series({'x_train': x_train, 'x_test': x_test, 'x_total': x_total, 'y': y})

def polinomios(x_train, x_test, y, test_df, last_y, x_predict, lista_R, g):
    try:
        #df_resultado = pd.DataFrame()
        #if len(x_test) > 0:
        poly_features = PolynomialFeatures(degree = g)

        x_poly_train = poly_features.fit_transform(x_train.reshape(-1, 1))

        model = LinearRegression()
        model.fit(x_poly_train, y)

        x_poly_test = poly_features.fit_transform(x_test.reshape(-1, 1))
        
        #y_plot_train = model.predict(x_poly_train)
        y_plot_test = model.predict(x_poly_test)
        
        test_df_ecm = test_df.copy()
        test_df_ecm[f'Y_pred_{g}'] = y_plot_test
        test_df_ecm[f'ECM'] = (test_df_ecm[f'Y_pred_{g}'] - test_df_ecm[f'Close']) ** 2
        ecm = test_df_ecm[f'ECM'].mean()
        
        x_poly_predict = poly_features.fit_transform(x_predict.reshape(-1, 1))
        y_predict_vector = model.predict(x_poly_predict)
        
        all_dic = {f'ecm_{g}': ecm}
        for i, y_predict in enumerate(y_predict_vector):
            #print(y_predict)
            if y_predict < 0:
                y_predict = 0
        
            n_dias = lista_R[i]
            rendimiento = (y_predict / last_y) ** (1 / n_dias) - 1 # rendimiento promedio por periodo
            new_serie_dic = {f'predict_{g}_{n_dias}': y_predict, f'rendimiento_{g}_{n_dias}': rendimiento}
            all_dic = {**all_dic, **new_serie_dic}

            #new_df = pd.DataFrame({'Date': lista_dates, 't': lista_t, 'n_dias': n_dias, 'predict': predict, 'rendimiento': rendimiento, 'ecm': ecm})
            #df_resultado = pd.concat([df_resultado, new_df])

    except Exception as e:
        #print('Error', e)
        metricas = ['predict', 'rendimiento']
        all_dic = {**{f'ecm_{g}': np.nan}, **{f'{m}_{g}_{n_dias}': np.nan for n_dias in lista_R for m in metricas}}

    df = pd.Series(all_dic)
    return df
    

### Sección:  Clase Valor
class Valor():

    def __init__(self, simbolo, nombre, cofre, saving_step = 1000, output = False):

        # Se guardan en el init, los atributos iniciales del objeto
        self.simbolo = simbolo # Nombre del simbolo con el que es reconocido en el mercado
        self.nombre = nombre # nombre con el que el Valor será tratado en el código
        self.cofre = f'{cofre}Valor/' # donde se guardan y rescatan los valores, con su info actualizada
        self.ultima_fecha_data = dt.datetime(2000, 1, 1).date() # valor por defecto
        self.raw_x = pd.DataFrame({'DATE': [], 'NAME': []}) # valor por defecto
        self.output = output # Si se quiere mostrar información en pantalla
    
        self.rescatar() # Rescata el objeto (y toda su información) si existe

        # independiente del valor rescatado, se actualizan
        self.output = output # Si se quiere mostrar información en pantalla (aparece de nuevo, para actualizarse...arriba, rescatar depende de self output)
        self.saving_step = saving_step # Cada cuantas nuevos POFS, se guarda la clase para respaldarla
        
        return None
            
    def rescatar(self):
        #print(f'{self.simbolo}.pkl', self.cofre)
        if f'{self.simbolo}.pkl' not in os.listdir(self.cofre):
            return None # Si no se encuentra, no se pueden rescatar los atributos
        
        if self.output:
            print(f'Rescate en {self.cofre} {self.simbolo}') # Muestra que existe el rescate
            
        valor_cargado = pickle_act(f'{self.cofre}{self.simbolo}') # De lo contrario, se lee el objeto guardado y se rescatan sus atributos
        for key, value in vars(valor_cargado).items(): # vars contiene los atributo y sus valores como diccionario (str, obj) vars = {'x': valor de x, 'y': valor de y}
            setattr(self, key, value) # setattr(objeto, atributo, valor) -> objeto.atributo = valor, actúa sobre la clase self, recibe un key (str) y un value (obj) y los asigna a la clase como atributos: self.key = value...es similar a usar un globals(), pero en una clase

        return None
    
    def guardar(self):
        #print('Guardar')
        pickle_act(f'{self.cofre}{self.simbolo}', variable = self, mode = 'save')
        return None
        
    def extraer_data(self, reintentar = 5, time_sleep = 30, reextraer_todo = False):
        if self.ultima_fecha_data >= dt.datetime.now().date() - dt.timedelta(days = 1): # Si la ultima fecha de datos es, al menos ayer, no se extrae
            if not reextraer_todo:
                if self.output:
                    print('Data ya actualizada')
                return None # Actualzada! No se extrae
        
        for i in range(reintentar): # Se intenta extraer la data hasta [reintentar] veces
            self.raw_data_new = yf.download(self.simbolo) # Descarga de datos
            if len(self.raw_data_new) > 0: # Si se descargó algo, se rompe el ciclo
                break
            print(i + 1, f' Sleep {time_sleep} s. para volver a intentarlo')
            time.sleep(time_sleep)
        if len(self.raw_data_new) == 0: # Si no se descargó nada, no se actualiza y se mantiene la última data correctamente descargada (a veces hay fallas en la descarga)
            return None
        
        self.raw_data = self.raw_data_new.reset_index() # Se resetea el índice
        self.raw_data['Date'] = pd.to_datetime(self.raw_data['Date'], format = '%Y-%m-%d').dt.date # Traspaso a formato día
        self.ultima_fecha_data = self.raw_data['Date'].max() # Último día para el que existen los datos
        
        # Cortar los datos el día de ayer  (último día habil, o en que la bolsa estuvo abierta para este valor)
        self.raw_data = self.raw_data[self.raw_data['Date'] < dt.datetime.now().date()].reset_index(drop = True)
        
        if self.output: # se muestran encabezado y cola
            display(self.raw_data.head()) # encabezado
            display(self.raw_data.tail()) # cola

        return None
    
    def ajustar_data(self, date_0 = dt.datetime(2024, 1, 1).date(), interpolar = False):
        
        date_0 = pd.to_datetime(date_0) # Convertir 'date_0' a datetime64[ns]
        self.raw_data['Date'] = pd.to_datetime(self.raw_data['Date']) # Convertir 'Date' en 'self.adj_data' a datetime64[ns]
        
        if interpolar:
            df_base_dates = pd.DataFrame({'Date': pd.date_range(start = self.raw_data['Date'].min(), end = self.raw_data['Date'].max())}) # Se crea un dataframe con todas las fechas (entre min y max)
            self.adj_data = df_base_dates.merge(self.raw_data, on = 'Date', how = 'left') # Merge con la data existente
            self.adj_data[['Open', 'High', 'Low', 'Close', 'Volume']] = self.adj_data[['Open', 'High', 'Low', 'Close', 'Volume']].interpolate(method = 'linear').astype(float) # Interpolacion y declaración de precios y volumenes como floats
        else:
            self.adj_data = self.raw_data.copy() # Se copia la data original
            #print('No interpolar')
        
        self.adj_data['t'] = (self.adj_data['Date'] - date_0).dt.days # Se crea la columna t (date_0 es un día de referencia)
        self.precio_max = self.adj_data['High'].max() # Precio máximo. Se guardan en el self para volver a precios originales

        for c in ['Open', 'High', 'Low', 'Close']: # Todas las columnas de precios se normalizan
            if len(self.adj_data[self.adj_data[c].isna()]) > 0: # Solo validador
                print(self.adj_data[self.adj_data[c].isna()]) # Se muestran los registros con nulos
                print(f'El activo {self.simbolo} contiene nulos. No puede ser incluido')  # Solo validador, no debería haber nulos
            self.adj_data[c] = self.adj_data[c] / self.precio_max  # Estandarización
            
        self.vol_max = self.adj_data['Volume'].max() # Análogo para volumen
        self.adj_data['Volume'] = self.adj_data['Volume'] / self.vol_max
        
        self.adj_data['rendimiento'] = self.adj_data['Close'].pct_change() # Se calcula el rendimiento
        self.adj_data = self.adj_data[['Date', 't', 'Open', 'High', 'Low', 'Close', 'Volume', 'rendimiento']] # Ordenamiento de campos
        return None

    def generar_df_combinaciones(self, lista_dates, diccionario_combinaciones, iteradores, base_name, incluir_dates_en_iterar, df_explicito):
        
        # iteradores: además de date, en que se está iterando (dentro de diccionario_combinaciones.keys()) para obtener los resultados
        if len(df_explicito) > 0:
            print('generar_df_combinaciones expl')
            df_all = pd.DataFrame({'DATE': lista_dates, 'AUX': 'aux'})
            df_explicito['AUX'] = 'aux'
            df_all = df_all.merge(df_explicito, on = 'AUX')
            df_all['NAME'] = base_name + '_' + df_all['NAME']
        
        else:
            print('generar_df_combinaciones NO expl')
            # Genera todas las combinaciones necesarias requeridas
            df_all = pd.DataFrame({'DATE': lista_dates, 'AUX': 'aux'})
            for name in diccionario_combinaciones:
                new_df = pd.DataFrame({name: diccionario_combinaciones[name], 'AUX': 'aux'})
                df_all = df_all.merge(new_df, on = 'AUX')
            df_all = df_all.drop(columns = 'AUX')
            df_all['NAME'] = base_name + '_'
            for name in diccionario_combinaciones: # Nombre concreto al campo
                df_all['NAME'] = df_all['NAME'] + df_all[name].astype(str) + '_'
            df_all['NAME'] = df_all['NAME'].str[:-1]
        
        if len(self.raw_x) > 0: # Si no existe raw_x, entonces se genera todo df_all
            self.raw_x['EXISTE'] = True # Para no agregarle el campo EXISTE al self.raw_x. self.rw_x contiene toda la info hasta el momento de las POFs generadas para este valor
            
            df_all['DATE'] = pd.to_datetime(df_all['DATE']) # formato datetime en ambos dfs
            self.raw_x['DATE'] = pd.to_datetime(self.raw_x['DATE'])
            
            print('generar_df_combinaciones pre merge')
            #display(df_all)
            #display(self.raw_x)
            
            df_all = df_all.merge(self.raw_x, on = ['DATE', 'NAME'], how = 'left')
            df_all['EXISTE'] = df_all['EXISTE'].fillna(False) # SI ya existe
            df_all = df_all[~df_all['EXISTE']].reset_index(drop = True) # Entonces no se vuelve a generar
                
        if incluir_dates_en_iterar: # En cada uno de los casos, que es lo que se considera
            if len(df_explicito) > 0:
                df_iterar = df_all[['DATE'] + list(df_explicito.columns)].drop_duplicates().reset_index(drop = True)
            else:
                df_iterar = df_all[['DATE'] + iteradores].drop_duplicates().reset_index(drop = True)
        else:
            df_iterar = df_all[iteradores].drop_duplicates().reset_index(drop = True)

        return df_iterar, df_all
    
    

        
    def generate_df_subconjunto(self, df_iteracion, continuar_si_hay_menos = True): # Análogo a generate_df_intervalos
        # Last_t es cual es el día que se está mirando hacia atrás
        # k esla proporción de datos (donde k = 1 es desde el inicio)
        last_date, n_datos = df_iteracion['DATE'][0], df_iteracion['n_datos'][0]
        df = self.adj_data[self.adj_data['Date'] <= last_date].reset_index(drop = True)
        df = df.tail(n_datos).reset_index(drop = True)
        
        if (len(df) < n_datos) and continuar_si_hay_menos:
            return df, True
        
        return df, False
    
            
    def crear_POF(self, name, configuraciones, modulo):
        
        print('COMENTAR FUNCION!!!!')
        
        diccionario_combinaciones = configuraciones['diccionario_combinaciones']
        iteradores = configuraciones['iteradores']
        incluir_dates_en_iterar = configuraciones['incluir_dates_en_iterar']
        df_explicito = configuraciones['df_explicito']
        continuar_si_hay_menos = configuraciones['continuar_si_hay_menos']
        
        lista_dates = self.adj_data['Date'].unique()
        
        df_iterar, df_all = self.generar_df_combinaciones(lista_dates, diccionario_combinaciones, iteradores, name, incluir_dates_en_iterar, df_explicito)
            
        for i in tqdm.tqdm(range(len(df_iterar))):
            df_iteracion = df_iterar.iloc[i:i + 1].reset_index(drop = True)
            
            continuar, df_all_data = False, self.adj_data
            if incluir_dates_en_iterar:
                df_all_data, continuar = self.generate_df_subconjunto(df_iteracion, continuar_si_hay_menos)
                
            # Lo que falta
            #print('Revision POF')
            display(df_iteracion)
            #display(df_all)
            df_iteracion['SELECCION'] = True # Se filtran lo casos (en raw X) de la tupla seleccionada en df_iteracion (configuración del caso particular)
            df_all_seleccion = df_all.merge(df_iteracion, on = iteradores, how = 'left')
            df_all_seleccion['SELECCION'] = df_all_seleccion['SELECCION'].fillna(False)
            df_all_seleccion = df_all_seleccion[df_all_seleccion['SELECCION']].reset_index(drop = True)
            df_all_seleccion = df_all_seleccion.drop(columns = 'SELECCION')
            
            if 'EXISTE' not in df_all_seleccion.columns:
                df_all_seleccion['EXISTE'] = False
            df_all_seleccion = df_all_seleccion[['DATE', 'EXISTE']].rename(columns = {'DATE': 'Date'})
            
            df = df_all_data.merge(df_all_seleccion, on = 'Date', how = 'left')
            df['EXISTE'] = df['EXISTE'].fillna(True)
            df = df[~df['EXISTE']].reset_index(drop = True)
            df = df.drop(columns = 'EXISTE') # Se obtienen todos los dates para los cuales no existen datos en raw X (datos para alimentar la red neuronal que ya están guardados)
             
            if continuar:
                continue
            
            df_resultado = modulo(df, df_all_data, df_iteracion) # Obtener valores (df: todas las tuplas faltantes, df_all_data: toda la información)
            
            # Limpieza
            df_resultado = df_resultado.rename(columns = {'Date': 'DATE'}) # DATE siempre debe ir en mayúscula
            df_resultado = df_resultado[['DATE', 'X']]
            df_resultado['X'] = df_resultado['X'].fillna(0)
            
            if incluir_dates_en_iterar:
                df_resultado['DATE'] = df_iteracion['DATE'][0]
                
            # nombre
            name_i = name # name: nombre original del pof
            for c in iteradores:
                name_i = name_i + '_' + str(df_iteracion[c][0])
                      
            df_resultado['NAME'] = name_i 
                
            self.alimentar_raw_X(df_resultado) # Se guardan los nuevos registros en raw Y. Principal output para RN

            if ((i + 1) % self.saving_step == 0) or (i == len(df_iterar) - 1): # Se guarda cada saving_step iteraciones, o en la última de ellas
                self.raw_x.to_csv('raw_x.csv', index = False, sep = ';', decimal = ',')
                print('GUARDAR \n\n\n\n\n')
                self.guardar()
            
        return None




    #### abajo antiguas #######################
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
    """
    def generar_media_movil(self, df, campo, n):
        df[f'Media_movil_{campo}_{n}'] = df[campo].shift(1).rolling(window = n).mean() # .shift(1): hasta t - 1
        for i in range(n - 1, 0, -1):
            df[f'Media_movil_{campo}_{n}'] = df[f'Media_movil_{campo}_{n}'].fillna(df[campo].shift(1).rolling(window = i).mean())
        df[f'Media_movil_{campo}_{n}'] = df[f'Media_movil_{campo}_{n}'].fillna(0)
        return df

    def generar_media_movil_multiplicativa(self, df, campo, n):
        i = n
        dic_funcion = {'rendimiento': lambda x: np.prod(1 + x) ** (1 / i) - 1, 'Close': lambda x: np.prod(x) ** (1 / i)}
        df[f'Media_movil_multiplicativa_{campo}_{n}'] = df[campo].shift(1).rolling(window = n).apply(dic_funcion[campo]) # .shift(1): hasta t - 1
        for i in range(n - 1, 0, -1):
            df[f'Media_movil_multiplicativa_{campo}_{n}'] = df[f'Media_movil_multiplicativa_{campo}_{n}'].fillna(df[campo].shift(1).rolling(window = i).apply(dic_funcion[campo]))
        df[f'Media_movil_multiplicativa_{campo}_{n}'] = df[f'Media_movil_multiplicativa_{campo}_{n}'].fillna(1)
        return df
    
    def generar_suavizamiento_exponencial(self, df, campo, alfa):
        df[f'Suavizamiento_Exponencial_{campo}_{alfa}'] = df[campo].shift(1).ewm(alpha = alfa, adjust = False).mean() # adjust = True, termina normalizando los datos para ajustarlos con los reales
        df[f'Suavizamiento_Exponencial_{campo}_{alfa}'] = df[f'Suavizamiento_Exponencial_{campo}_{alfa}'].fillna(0)
        return df
    """

    def generar_outputs(self, df, campo, R):
        
        #print('R', R)
        #print(df.head())
        df['Date'] = pd.to_datetime(df['Date'])
        min_date = df['Date'].min()
        # crear df con dates entre df['Date'].min() - 10 y df['Date'].min()
        df_base_dates = pd.DataFrame({'Date': pd.date_range(start = min_date - dt.timedelta(days = int(R)), end = min_date - dt.timedelta(days = 1))}) # Esta ampliación hacia atrás, permite que el rolling funcione bien los primeros días
        #df_base_dates['Date'] = pd.to_datetime(df_base_dates['Date'])
        
        df = pd.concat([df, df_base_dates])
        df = df.sort_values(by = 'Date')

        dic_funciones = {'Rendimiento': lambda x: np.prod(1 + x) ** (1 / R) - 1, 'Varianza': lambda x: np.var(x)} # El rendimiento estimado es promedio por periodo
        df[f'{campo}_{R}'] = df['rendimiento'].shift(-R).rolling(window = R).apply(dic_funciones[campo]) # .shift(-1): hasta t - 1
        df = df[df['Date'] >= min_date]
        return df
    
    def generar_output_all(self, lista_R, saving_step = 100):
        # lista_R..para cuantos días hacia adelante, se quieren obtener los outputs
            
        base_name = 'Y'
        campos_output = ['Rendimiento', 'Varianza']
        diccionario_combinaciones = {'CAMPO': campos_output, 'R': lista_R}
        iteradores = ['CAMPO', 'R']
        lista_dates = self.adj_data['Date'].unique()
        df_iterar = self.generar_df_combinaciones(lista_dates, diccionario_combinaciones, iteradores, base_name, incluir_dates_en_iterar = False)
        
        #print('df_iterar df_output')
        #print(df_iterar)
        for i in tqdm.tqdm(range(len(df_iterar))):
            campo, R = df_iterar.loc[i] 
            print('NAME', R, campo)
            df = self.generate_df_subconjunto(self.adj_data['Date'].max(), 1) # En este caso,no se obtiene una proporcion k -> df = df_ajustado
            df_y = self.generar_outputs(df, campo, R)
            df_y = df_y[['Date', f'{campo}_{R}']].rename(columns = {'Date': 'DATE', f'{campo}_{R}': 'X'})
            df_y['NAME'] = f'{base_name}_{campo}_{R}' # incluir name de referencia (los outputs se identifican con un Y_)
            
            display(df_y.head(5))
            self.alimentar_raw_X(df_y) # Se guardan los nuevos registros en raw Y. Principal output para RN

            if ((i + 1) % saving_step == 0) or (i == len(df_iterar) - 1): # Se guarda cada saving_step iteraciones, o en la última de ellas
                
                self.guardar()
    


    
    def alimentar_raw_X(self, df):
        df = df[['DATE', 'NAME', 'X']]
        df['X'] = df['X'].fillna(0)
        #print(df)
        self.raw_x = pd.concat([df, self.raw_x], axis = 0) # Lo más nuevo, siempre primero
        self.raw_x = self.raw_x.drop_duplicates(subset = ['DATE', 'NAME']).reset_index(drop = True)
        return None

    # No ocupada por ahora 240606
    def alimentar_raw_Y(self, df):
        df = df[['DATE', 'NAME', 'Y']]
        df['Y'] = df['Y'].fillna(0)
        #print(df)
        self.raw_y = pd.concat([df, self.raw_y], axis = 0) # Lo más nuevo, siempre primero
        self.raw_y = self.raw_y.drop_duplicates(subset = ['DATE', 'NAME']).reset_index(drop = True)
        return None
    
    # No ocupada por ahora 240606
    def generar_figuras_all(self, lista_k, lista_figuras, saving_step = 100):
        
        # Para figuras
        base_name = 'Figura'
        lista_parametros = ['B0L', 'B1L', 'B0U', 'B1U']  
        diccionario_combinaciones = {'FIGURA': lista_figuras, 'PARAMETROS': lista_parametros, 'K': lista_k}
        iteradores = ['K']
        lista_dates = self.adj_data['Date'].unique()
        df_iterar = self.generar_df_combinaciones(lista_dates, diccionario_combinaciones, iteradores, base_name)
        
        #print('df_iterar', len(df_iterar))
        #print(df_iterar)
        
        for i in tqdm.tqdm(range(len(df_iterar))):
            date, k = df_iterar.loc[i]
            #print(date, k)
            df = self.generate_df_subconjunto(date, k) # Si no existe la combinación en los registros, se crea
            #graficar(df, k, campos = ['Open', 'Close']) # Gráfico de apertura (salmon) y cierre (skyblue)
            df_variables_all = self.generate_figuras(df) # Obtener valores
            df_variables_all['DATE'] = date # incluir date
            df_variables_all['NAME'] = base_name + '_' + df_variables_all['figura_name'] + '_' + df_variables_all['PARAMETRO'] + '_' + str(k) # incluir name de referencia
            self.alimentar_raw_X(df_variables_all) # Se guardan los nuevos registros en raw X. Principal input para RN
            
            if ((i + 1) % saving_step == 0) or (i == len(df_iterar) - 1): # Se guarda cada saving_step iteraciones, o en la última de ellas
                self.guardar()
            
        return None

    """
    # No ocupada por ahora 240606
    def generar_fibonacci_all(self, lista_k, saving_step = 100):
        
        base_name = 'Fibonacci'
        diccionario_combinaciones = {'modo_fib': ['valor', 'up_down'], 'K': lista_k}
        iteradores = ['K']
        lista_dates = self.adj_data['Date'].unique()
        df_iterar = self.generar_df_combinaciones(lista_dates, diccionario_combinaciones, iteradores, base_name)
        #sys.exit('Rev0')
        for i in tqdm.tqdm(range(len(df_iterar))):
            date, k = df_iterar.loc[i]
            #print(date, k)
            df = self.generate_df_subconjunto(date, k) # Si no existe la combinación en los registros, se crea
            df_fibonacci = self.generate_fibonacci(df) # Obtener valores
            df_fibonacci['DATE'] = date # incluir date
            df_fibonacci['NAME'] = base_name + '_' + df_fibonacci['modo_fib'] + '_' + str(k) # incluir name de referencia
            self.alimentar_raw_X(df_fibonacci) # Se guardan los nuevos registros en raw X. Principal input para RN
            
            if ((i + 1) % saving_step == 0) or (i == len(df_iterar) - 1): # Se guarda cada saving_step iteraciones, o en la última de ellas
                print('Guardar')
                self.guardar()

        return None
    

    def generar_media_movil_all(self, lista_n, lista_campos, saving_step = 100):
        
        base_name = 'Media_movil'
        diccionario_combinaciones = {'N': lista_n, 'CAMPO': lista_campos}
        iteradores = ['N', 'CAMPO']
        lista_dates = self.adj_data['Date'].unique()
        df_iterar = self.generar_df_combinaciones(lista_dates, diccionario_combinaciones, iteradores, base_name, incluir_dates_en_iterar = False)
        
        #print('df_iterar')
        #print(df_iterar)
        for i in tqdm.tqdm(range(len(df_iterar))):
            n, campo = df_iterar.loc[i]
            df = self.generate_df_subconjunto(self.adj_data['Date'].max(), 1) # En este caso,no se obtiene una proporcion k -> df = df_ajustado
            df_mm = self.generar_media_movil(df, campo, n)
            df_mm = df_mm[['Date', f'{base_name}_{campo}_{n}']].rename(columns = {'Date': 'DATE', f'{base_name}_{campo}_{n}': 'X'})
            df_mm['NAME'] = base_name + '_' + str(n) + '_' + campo # incluir name de referencia
            self.alimentar_raw_X(df_mm) # Se guardan los nuevos registros en raw X. Principal input para RN
            #print(df_mm)

            if ((i + 1) % saving_step == 0) or (i == len(df_iterar) - 1): # Se guarda cada saving_step iteraciones, o en la última de ellas
                self.guardar()

    def generar_media_movil_multiplicativa_all(self, lista_n, lista_campos, saving_step = 100):
        
        base_name = 'Media_movil_multiplicativa'
        diccionario_combinaciones = {'N': lista_n, 'CAMPO': lista_campos}
        iteradores = ['N', 'CAMPO']
        lista_dates = self.adj_data['Date'].unique()
        df_iterar = self.generar_df_combinaciones(lista_dates, diccionario_combinaciones, iteradores, base_name, incluir_dates_en_iterar = False)
        
        #print('df_iterar mmm')
        #print(df_iterar)
        for i in tqdm.tqdm(range(len(df_iterar))):
            n, campo = df_iterar.loc[i]
            df = self.generate_df_subconjunto(self.adj_data['Date'].max(), 1) # En este caso,no se obtiene una proporcion k -> df = df_ajustado
            df_mm = self.generar_media_movil_multiplicativa(df, campo, n)
            #print(df_mm)
            
            df_mm = df_mm[['Date', f'{base_name}_{campo}_{n}']].rename(columns = {'Date': 'DATE', f'{base_name}_{campo}_{n}': 'X'})
            df_mm['NAME'] = base_name + '_' + str(n) + '_' + campo # incluir name de referencia
            self.alimentar_raw_X(df_mm) # Se guardan los nuevos registros en raw X. Principal input para RN
            #print(df_mm)

            if ((i + 1) % saving_step == 0) or (i == len(df_iterar) - 1): # Se guarda cada saving_step iteraciones, o en la última de ellas
                self.guardar()
    
    def generar_suavizamiento_exponencial_all(self, lista_alpha, lista_campos, saving_step = 100):
        
        base_name = 'Suavizamiento_Exponencial'
        diccionario_combinaciones = {'ALPHA': lista_alpha, 'CAMPO': lista_campos}
        iteradores = ['ALPHA', 'CAMPO']
        lista_dates = self.adj_data['Date'].unique()
        df_iterar = self.generar_df_combinaciones(lista_dates, diccionario_combinaciones, iteradores, base_name, incluir_dates_en_iterar = False)
        
        #print('df_iterar df_se')
        #print(df_iterar)
        for i in tqdm.tqdm(range(len(df_iterar))):
            alpha, campo = df_iterar.loc[i]
            df = self.generate_df_subconjunto(self.adj_data['Date'].max(), 1) # En este caso,no se obtiene una proporcion k -> df = df_ajustado
            df_se = self.generar_suavizamiento_exponencial(df, campo, alpha)
            #print(df_se)
            df_se = df_se[['Date', f'{base_name}_{campo}_{alpha}']].rename(columns = {'Date': 'DATE', f'{base_name}_{campo}_{alpha}': 'X'})
            df_se['NAME'] = base_name + '_' + str(alpha) + '_' + campo # incluir name de referencia
            self.alimentar_raw_X(df_se) # Se guardan los nuevos registros en raw X. Principal input para RN
            #print(df_se)

            if ((i + 1) % saving_step == 0) or (i == len(df_iterar) - 1): # Se guarda cada saving_step iteraciones, o en la última de ellas
                self.guardar()
        return None

    def generar_polinomicas_all(self, lista_grados, lista_R, lista_test_sizes = [0.2, 0.3], saving_step = 100):
        
        base_name = 'Polinomio'
        diccionario_combinaciones = {'GRADO': lista_grados, 'R': lista_R, 'TEST_SIZE': lista_test_sizes}
        iteradores = list(diccionario_combinaciones.keys())
        lista_dates = self.adj_data['Date'].unique()
        
        metricas = ['predict', 'rendimiento']   
        df_explicito = pd.DataFrame()
        for g in lista_grados:
            for test_size in lista_test_sizes: # Nuevo 240619
                lista_campos_g = [f'ecm_{g}_{test_size}'] + [f'{m}_{g}_{n_dias}_{test_size}'for n_dias in lista_R for m in metricas] 
                lista_g = [g] + [g for n_dias in lista_R for m in metricas]
                lista_r = [0] + [n_dias for n_dias in lista_R for m in metricas] 
                lista_ts = [test_size] + [test_size for n_dias in lista_R for m in metricas]
                new_df = pd.DataFrame({'NAME': lista_campos_g, 'GRADO': lista_g, 'R': lista_r, 'TEST_SIZE': lista_ts})
                df_explicito = pd.concat([df_explicito, new_df])
        
        df_iterar = self.generar_df_combinaciones(lista_dates, diccionario_combinaciones, iteradores, base_name, incluir_dates_en_iterar = True, df_explicito = df_explicito)
        
        #print('df_iterar df_polinomicas')
        #display(df_iterar) # solo quedan los existentes
        #return df_iterar
        for g in lista_grados:
            df_iterar_g = df_iterar[df_iterar['GRADO'] == g].reset_index(drop = True).sort_values(by = 'DATE')
            
            if len(df_iterar_g) == 0:
                if ((g + 1) % saving_step == 0) or (g == len(df_iterar) - 1): # Se guarda cada saving_step iteraciones, o en la última de ellas
                    self.guardar()
                continue
                
            print('Grado', g)
            for test_size in lista_test_sizes: # Nuevo 240619
                df_pl = self.generar_polinomicas(g, test_size, df_iterar_g)
                df_pl = df_pl.rename(columns = {'Date': 'DATE'})
                df_pl = df_pl.melt(id_vars = ['DATE'], var_name = 'NAME', value_name = 'X')
                df_pl['NAME'] = base_name + '_' + df_pl['NAME'] # incluir name de referencia
                
                display('df_pl 2')
                display(df_pl)
                #sys.exit('Salida en Clase Valor')
                
                self.alimentar_raw_X(df_pl) # Se guardan los nuevos registros en raw X. Principal input para RN
                #sys.exit('Hasta aqui una sola instancia')

            if ((g + 1) % saving_step == 0) or (g == len(df_iterar) - 1): # Se guarda cada saving_step iteraciones, o en la última de ellas
                self.guardar()
        return None
    """            
    
    def generar_polinomicas(self, grado, test_size, df_iterar_g):
        # df adj
        df = self.adj_data.copy().reset_index(drop = True)
        df['t'] = df.index # cambio 240531
        t_max = df['t'].max() # Se guarda el máximo de t
        df['t'] *= (1 / t_max)
        df = df[['Date', 't', 'Close']]
        
        print('df en generar polinomicas')
        display(df.head(3))
        display(df.tail(3))
        
        #display('df_iterar_g')
        #display(df_iterar_g)
        
        #df_iterar_g_dates = list(df_iterar_g['DATE'].unique())
        #df = df[df['Date'].isin(df_iterar_g_dates)].reset_index(drop = True)
    
        #display('df')
        #display(df)
        
        #sys.exit('A1 en clase valor')

        # df_predict_dates
        n_dias = df_iterar_g['R'].max()
        lista_R = list(df_iterar_g['R'].unique())
        lista_R.remove(0)
        
        df_predict_dates = pd.DataFrame({'Date': pd.date_range(start = df['Date'].max() + dt.timedelta(days = 1), end = df['Date'].max() + dt.timedelta(days = 1 + int(n_dias)))}) # Se crean las fechas a predecir
        df_predict_dates['Date'] = df_predict_dates['Date'].dt.date # Se traspasa a formato día
        df_predict_dates['t'] = df_predict_dates.index + t_max + 1 # Se crea la columna t
        df_predict_dates['t'] *= (1 / t_max) # Normalización
        
        print('df_predict_dates')
        display(df_predict_dates.head(3))
        display(df_predict_dates.tail(3))
    
        df_pl = polinomicas(df, test_size, df_iterar_g, grado, df_predict_dates, lista_R) 
        
        #print('TEST SIZE', test_size)
        #display('df_pl 1')
        #display(df_pl)
        return df_pl 

    
    ########################################## NO OCUPADAS ##############################################################
    
    # No ocupada por ahora 240606
    def generate_figuras(self, df, lista_figuras = ['libre', 'canal', 'arriba plano', 'abajo plano', 'canal lateral'], modo_vela = 'cuerpo', sep = ';', output = False):
        df_figuras = pd.read_csv('../Configuracion/configuracion_figuras.csv', sep = sep) # Se lee el archivo de configuración
        df_figuras = df_figuras[df_figuras['nombre_figura'].isin(lista_figuras)].reset_index(drop = True) # Se filtran las figuras declaradas
        
        campos = ['Open', 'Close'] if modo_vela == 'cuerpo' else ['High', 'Low']# Selección de campos...open y close para modo_vela = cuerpo, High y Low para modo_vela = sombra

        data_points = pd.melt(df[['t'] + campos], id_vars = ['t'], value_vars = campos, value_name = 'y')[['t', 'y']] # melt lleva "campos" a una sola columna "y" agrupada
        
        # Se busca que datapoints sean las coordeenadas (t, y) de una nube de puntos
        df_variables_all = pd.DataFrame()
        
        for i in range(len(df_figuras)):
            figura, slope_inf, slope_sup, paralelas = df_figuras[['nombre_figura', 'slope_inf', 'slope_sup', 'paralelas']].iloc[i]
            df_variables = generate_figure(data_points, figura, slope_inf, slope_sup, paralelas, output)
            #print(figura)
            #print(df_variables)
            df_variables_all = pd.concat([df_variables_all, df_variables], axis = 0)
        
        df_variables_all = df_variables_all.melt(id_vars = ['figura_name'], var_name = 'PARAMETRO', value_name = 'X')
        
        #print('Figuras')
        #print(df_variables_all) # Continuar acá: Buscar 240410 en C:\Users\mvaldiviad\OneDrive - Falabella\Escritorio\Proyectos Personales\Trading_Model\Trading_model_codes\modulo_clases.ipynb: 
        #sys.exit()
        return df_variables_all
    
