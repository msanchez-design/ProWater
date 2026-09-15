# 💧 Sistema de Gestión - Reparto de Agua

App web para reemplazar las planillas de Excel: carga de remitos, facturación mensual
automática y estado de cuenta / saldo por cliente. Pensada para que la usen 2-3 personas
al mismo tiempo desde cualquier lugar (celular o PC), sin instalar nada.

## Qué incluye esta primera versión

- **Clientes**: alta/edición, abono, precios de extras, teléfono, dirección, CUIT.
- **Remitos**: carga diaria de entregas (bidones 20L/10L, sifones, dispensers).
- **Facturación mensual**: con un botón genera automáticamente el consumo de todos los
  clientes activos del mes (abono + lo que se les entregó de más ese mes según los
  remitos cargados). Se puede marcar como "facturado" para que no se pise.
- **Estado de cuenta**: por cliente, con el historial de facturaciones y pagos, y el
  saldo actualizado automáticamente (como tu hoja "Historico" pero sin que vos tengas
  que calcular nada a mano).
- **Dashboard**: deuda total, ranking de clientes con más deuda, últimos remitos.
- Login con usuario y contraseña (para que cada persona cargue con su nombre).

## 1) Correrlo en tu computadora (VS Code)

1. Instalá [Python 3.11+](https://www.python.org/downloads/) si no lo tenés.
2. Abrí la carpeta `water_app` en VS Code.
3. Abrí una terminal en VS Code (Ctrl+ñ o Terminal > New Terminal) y creá un entorno virtual:

   ```bash
   python -m venv venv
   # Windows:
   venv\Scripts\activate
   # Mac/Linux:
   source venv/bin/activate
   ```

4. Instalá las dependencias:

   ```bash
   pip install -r requirements.txt
   ```

5. Copiá `.env.example` a `.env` y por ahora dejalo tal cual (así arranca con una base
   de datos local de prueba, sin tocar Supabase):

   ```bash
   copy .env.example .env      # Windows
   cp .env.example .env        # Mac/Linux
   ```

   Para probar rápido en local, cambiá esta línea del `.env` por:
   ```
   DATABASE_URL=sqlite:///./local_dev.db
   ```

6. Arrancá la app:

   ```bash
   uvicorn app.main:app --reload
   ```

7. Abrí el navegador en **http://127.0.0.1:8000**. La primera vez se crea automáticamente
   un usuario administrador con el email/contraseña que pusiste en `.env`
   (`ADMIN_EMAIL` / `ADMIN_PASSWORD`).

## 2) Pasar tus clientes actuales de Excel al sistema

Con la app ya conectada a la base de datos que vayas a usar (ver paso 3), corré:

```bash
python scripts/importar_clientes_excel.py "FACTURACION_MENSUAL_CONSUMO_SEPTIEMBRE_2026.xlsx" "ESTADO_DEUDA_CLIENTES.xlsx"
```

Esto trae nombre, CUIT, condición fiscal y teléfono de tus dos planillas. **Los precios
de abono y extras te recomiendo revisarlos y completarlos a mano una vez** desde
"Clientes > Editar", porque en las planillas varían mucho de cliente a cliente y mes a
mes, y preferí no adivinar mal un precio. Es una carga única; de ahí en adelante el
sistema ya calcula todo solo.

## 3) Base de datos en Supabase (gratis, accesible desde cualquier lado)

1. Entrá a [supabase.com](https://supabase.com) con tu cuenta y creá un **New Project**
   (elegí una región cercana, ej. South America).
2. Guardá bien la contraseña que te pide al crear el proyecto.
3. Andá a **Project Settings > Database > Connection string > URI**, copiala.
4. Pegala en tu `.env` en `DATABASE_URL` tal cual (empieza con `postgresql://`), reemplazando
   `TU_PASSWORD` por la contraseña real. No hace falta que instales nada de PostgreSQL en
   tu PC: la app usa un driver 100% en Python (`pg8000`) que no requiere compilar nada.
5. Reiniciá la app (`uvicorn app.main:app --reload`) y ya va a crear las tablas solas ahí.

Desde ese momento, todos los usuarios (aunque estén en distintos lugares) leen y escriben
la misma base de datos en la nube.

## 4) Publicarla gratis (Render)

1. Subí esta carpeta a un repositorio de GitHub (podés hacerlo desde VS Code:
   Source Control > Publish to GitHub).
2. Entrá a [render.com](https://render.com), creá cuenta con GitHub.
3. **New > Web Service**, elegí tu repositorio.
4. Configuración:
   - **Build command**: `pip install -r requirements.txt`
   - **Start command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Plan**: Free
5. En la sección **Environment**, cargá las mismas variables del `.env`
   (`DATABASE_URL`, `SECRET_KEY`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`) — nunca subas el
   archivo `.env` al repositorio.
6. Deploy. Te da una URL tipo `https://tu-app.onrender.com` que anda en cualquier
   celular o PC, sin instalar nada.

> Nota: el plan free de Render "duerme" la app si nadie la usa por un rato y tarda unos
> segundos en despertar en el próximo ingreso. Es normal y no afecta los datos.

## 5) Cómo usarlo día a día

1. Cada repartidor/administrativo carga un **remito** por cada entrega (Remitos > Cargar remito).
2. A fin de mes, alguien entra a **Facturación**, elige el período y toca
   "Generar facturación" — el sistema arma automáticamente el consumo de cada cliente.
   Se puede revisar y ajustar antes de marcarlo como facturado.
3. A medida que cobran, cargan el **pago** desde la ficha del cliente (Clientes > [nombre]).
4. El **saldo** de cada cliente se actualiza solo; el dashboard siempre muestra quién debe.

## 6) Próximos pasos (cuando esta base ya esté probada)

- **App para celular**: como el backend ya es una API (FastAPI), el siguiente paso es
  envolver esta misma app como PWA instalable (2-3 líneas de configuración) o construir
  una app nativa liviana que consuma los mismos endpoints — no hay que rehacer nada de
  la lógica de negocio.
- Roles diferenciados (repartidor solo carga remitos; admin ve todo).
- Generación de PDF de factura/remito.
- Recordatorios automáticos de deuda por WhatsApp/email.
- Importación de la hoja "PENDIENTES DE CARGA" (conciliación de transferencias bancarias)
  para que no tengas que buscar a mano qué cliente pagó qué.

## Estructura del proyecto

```
water_app/
  app/
    main.py          # rutas de la aplicación
    models.py         # tablas de la base de datos
    crud.py            # cálculo de facturación y saldos
    auth.py             # login
    database.py          # conexión a la base
    templates/             # páginas HTML
    static/style.css        # estilos
  scripts/
    importar_clientes_excel.py
  requirements.txt
  .env.example
  Procfile
```
