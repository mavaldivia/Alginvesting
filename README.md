
# Sobre esta versión (Alginvesting v1)
- Creada el 240902


# Etapas y versiones oficiales

## 1. Valor (240610)

- Etapa que procesa la clase valor, con todas las variabels dependientes e independientes, con el fin de generar matries de input y output para entrenamiento y testeo

## 2. FFNN_y_BusqInt (240610)

- Contiene las lógicas de FFNN y Búsqueda inteligente
    [OK: Debería estar bien] Lógica de ejecucion para Rend10, Var30, etc....{Ren o varianza} + n_dias 
    
    (df_seguimiento no debería pertenecer a busq int??) -> Tiene asignado el campo metrica + n_dias (output_level)..debería funcionar bien

    [OK] (se crea nombre nuevo) Incluir en el nombre de Búsqueda inteligente ("A1")....debería generarse un nuevo directorio en "Cofre/Red Neuronal" y en "Seguimiento"

    [Continuar aqui 240614: Ir a Sección "Proceso predic"...generar dataframe y calcular rendimiento y varianza a n_dias] Generar etapa predict, y empezar con las primeras predicciones

    RLM para covarianzas entre activos

    Volver a revisr Markowitz e integrar como módulo (KKT)

## 3. Covarianza

- Permite obtener un proxy de las covarianzas i, j, ocupando RLM

## 4. Markowitz

 Toma ls resultados de (2) y (3): Proyección de rendimiento y matriz de covarianza, para generar carteras eficientes


## Otros módulos:

Clase_Valor: Contiene la clase Valor y toda su lógica


## TO DO



6. Explorar librerías que detecten patrones chartistas e implementarlas + 
Identificación de areas relevantes: CONTINUAR AL FINAL DEL CÓDIGO EN Areas.ipynb



8. En etapa df_polinómicas (etapa F), incluir otro campo que sea % horizonte, de tal forma de tomar el x% de los últimos datos (ej, 50%)
Esto, porque acciones como Apple, fueron muy planas durante años, y empezaron a moverse solo los útlimos años, entonces en las polinómicas existen sesgos
7. Implementar neural prophet


## OK 
1. Matriz de covarianza: BUSCAR # Continuar aqui 240621: Listo para ejecutar RLM [CONTINUAR AQUI 240621]
3.[2024-06-19] Polinomios...deben tomar como est set, el x% de los datos FINALES...x es un parámetro que identifica el campo (ej 20% o 30%)
2. Modelo de markowitz con predicciones (formalizadas)

9. Crear un modelo base, e ir evaluando el desempeño de las mejoras sobre este resultado 
(ir a Markowitz.ipynb y buscar...# Continuar aqui! desarrollando estrategia)

5. Leer df_activos con una función transversal en común (para tomar los mismos activos)---De la misma forma, la cantidad de días futuros de predicción (ej, n = 30) implica proyectar el rendimiento promedio diario a 30 días, pero tambien la covarianza...
4. En la matriz df (para predicciones), normalizar la data (N (0,1)) y, en la salida, desnormalizarla (solo Y)


