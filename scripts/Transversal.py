import pandas as pd

def leer_activos(carpeta_input):
    ### Sección:  Lectura de activos
    df_activos = pd.read_csv(f'{carpeta_input}Activos.csv', sep = ';', decimal = ',')
    df_activos['USAR'] = df_activos['USAR'].fillna(0)
    df_activos['NOMBRE'] = df_activos['NOMBRE'].fillna(df_activos['SIMBOLO'])
    df_activos = df_activos[df_activos['USAR'] == 1].reset_index(drop = True)[['SIMBOLO', 'NOMBRE']]
    df_activos = df_activos.sort_values(by = 'SIMBOLO').reset_index(drop = True)

    #print('Sin Small Batch')
    #print('Small batch 240925')
    #df_activos = df_activos.head(5)
    return df_activos

def leer_parametros():
    carpeta_input = '../Inputs/'
    cofre = '../Cofre/' # donde se guardan / rescatan los valores con toda su info actualizada
    seguimiento = '../Seguimiento/' # donde se guardan archivos de seguimiento
    saving_step = 1000
    return carpeta_input, cofre, seguimiento, saving_step

def leer_configuracion():
    output_level = 30
    return output_level

n_sizes = {'BTCUSD': 130, 'ETHUSD': 130, 'TSLA': 120, 'GOOGL': 120, 'NVDA': 120, 'AMZN': 120}

#n_sizes_ejecucion = {'BTCUSD': 32, 'ETHUSD': 32, 'TSLA': 32, 'GOOGL': 32, 'NVDA': 32}
n_sizes_ejecucion = {'BTCUSD': 130, 'ETHUSD': 130, 'TSLA': 120, 'GOOGL': 120, 'NVDA': 120, 'AMZN': 120}
#{'BTCUSD': 100, 'ETHUSD': 100, 'TSLA': 80, 'GOOGL': 80, 'NVDA': 80, 'AMZN': 80}
#{'BTCUSD': 80, 'ETHUSD': 80, 'TSLA': 65, 'GOOGL': 50, 'NVDA': 65, 'AMZN': 65}

#{'BTCUSD': 40, 'ETHUSD': 40, 'TSLA': 36, 'GOOGL': 36, 'NVDA': 36}
