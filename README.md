# 💎 Joyería Dorada — Sistema de Gestión

Sistema interno de gestión para joyería con servicio de empeño.
Incluye CRM, inventario de joyas y caja/pagos.

## Instalación rápida

```bash
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Ejecutar la app
python app.py
```

Abrir en el navegador: **http://localhost:5000**

---

## Módulos

| Módulo | Descripción |
|--------|-------------|
| **Dashboard** | Resumen: empeños activos, vencidos, ingresos del mes, alertas |
| **Empeños** | Alta de contratos, renovación, registro de pagos, desempeño |
| **Caja** | Historial mensual de pagos con totales por tipo |
| **Clientes** | CRM: registro, búsqueda, historial por cliente |
| **Inventario** | Joyas propias y empeñadas, filtros por estado |

## Flujo de trabajo típico

1. Registrar **cliente** (con INE/identificación)
2. Registrar la **joya** en inventario (si no existe)
3. Crear el **empeño**: seleccionar cliente, joya, monto y plazo
4. Registrar **pagos** (interés, abono a capital, o desempeño total)
5. Si el cliente no desempeña: marcar como **perdido** → joya pasa al inventario propio

## Estructura del proyecto

```
joyeria/
├── app.py              # Aplicación Flask + modelos SQLAlchemy
├── requirements.txt
├── instance/
│   └── joyeria.db      # Base de datos SQLite (se crea automáticamente)
├── templates/
│   ├── base.html
│   ├── dashboard.html
│   ├── clientes.html / cliente_form.html / cliente_detalle.html
│   ├── inventario.html / joya_form.html
│   ├── empenios.html / empenio_form.html / empenio_detalle.html
│   └── caja.html
└── static/
    ├── css/main.css
    └── js/main.js
```
