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


n_sizes = {'BTCUSD': 50, 'ETHUSD': 50, 'TSLA': 40, 'GOOGL': 40}
    
