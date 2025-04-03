
# Sobre esta versión (Alginvesting v1)
- Creada el 240902


# Etapas y versiones oficiales

## 1. Valor (240902)

- Etapa que procesa la clase valor, con todas las variabels dependientes e independientes, con el fin de generar matries de input y output para entrenamiento y testeo [POFs: Portions of food]

## 2. GAN (241230)

### Etapas

- 1. Construir matrices (input y output): Se lee la info de los vectores generados en (1_Valor) y se obtiene:

    a. la matriz X, para los activos, la que contiene un día histórico en las filas y features explicativos en las columnas (POFs)

    b. El vector de rendimiento Y, de cada activo y cada día

- 2. Se obtiene df_precios, por activo-día

- 3. Train, Test & Control: 
        a. Se seleccionan los campos de input (POFs) que serán ocupados (función filtrar_campos)

        b. Se separan los datos en train / control...además de predict, que corresponde solo al último día

- 4. Clusters:
    Ejecución y búsqueda de nuevos clusters
    [TO DO] Falta tener un registro por activo de cuantas iteraciones existen y cual es la mejor asignación (si faltan días, asignar por centroide)

