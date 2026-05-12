# -*- coding: utf-8 -*-
def validar_cedula(cedula):
    """
    Valida una cédula dominicana según el algoritmo de la JCE
    Args:
        cedula (str): Número de cédula a validar (puede contener guiones o espacios)    
    Returns:
        tuple: (bool, str) (True/False, mensaje de error/exito)
    """
    try:
        
        # Limpiar la cédula (eliminar guiones, espacios)
        cedula = cedula.replace("-", "").replace(" ", "").strip()
        
        # Validaciones básicas
        if not cedula.isdigit():
            return False, "La cédula debe contener solo números"
        
        if len(cedula) != 11:
            return False, "La cédula debe tener 11 dígitos"
        
        # La cédula debe tener 11 dígitos
        if len(cedula)== 11:
            if (int(cedula[0:3]) < 122 and int(cedula[0:3]) > 0 or int(cedula[0:3]) == 402):
                suma = 0
                mutliplicador = 1
                verificador = 0
                for i in range(10):
                    # Se multiplica cada dígito por su paridad
                    multiplicador = 1 if i % 2 == 0 else 2
                    parte = int(cedula[i])
                    digito = parte * multiplicador
                    # Si la multiplicación da de dos dígitos, se suman entre sí
                    if(digito>9):
                        digito = digito//10 + digito%10
                    # Y se va haciendo la acumulación de esa suma
                    suma = suma + digito
                # Al final se obtiene el verificador con la siguiente fórmula
                verificador = (10 - (suma % 10) ) % 10
                # Se comprueba que coincidan
                if(verificador == int(cedula[10]) ):
                    return True, "Cédula válida"
                # El dígito verificador no es válido
                else:
                    return False, f"Dígito verificador {verificador} inválido"
            # La serie no es válida
            else:
                return False, "Serie inválida"        
    except Exception as e:
        return False, f"Error al validar: {str(e)}"

valida, resultado = validar_cedula("04701294789")
print(f"{resultado}")