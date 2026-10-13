# 🚕 LamboTaxi — Instalación en Docker Desktop (Windows)

## Lo que necesitas instalar primero

1. **Docker Desktop para Windows**
   → https://www.docker.com/products/docker-desktop/
   Descarga e instala. Cuando termine, reinicia el PC.
   Verifica que funciona: abre CMD y escribe `docker --version`

2. **Git for Windows** (para tener una terminal decente)
   → https://git-scm.com/download/win
   Instala con opciones por defecto.

---

## PASO 1 — Crear la estructura de carpetas

Abre **PowerShell** o **CMD** y ejecuta:

```powershell
mkdir C:\lambotaxi
mkdir C:\lambotaxi\static
```

---

## PASO 2 — Copiar los archivos

Coloca cada archivo en su sitio:

```
C:\lambotaxi\
├── docker-compose.yml
├── Dockerfile
├── nginx.conf
├── requirements.txt
├── server.py
├── .env                  ← crear ahora (ver paso 3)
└── static\
    ├── app.html          ← es el lambotaxi.html, renombrado
    ├── login.html
    ├── admin.html
    ├── conductor.html
    ├── manifest.json
    ├── service-worker.js
    └── api-adapter.js
```

⚠️ El archivo `lambotaxi.html` debe copiarse como `static\app.html`

---

## PASO 3 — Crear el archivo .env

En la carpeta `C:\lambotaxi\`, crea un archivo llamado exactamente `.env`
(sin extensión .txt). Lo más fácil: abre Notepad y guarda como `.env`
seleccionando "Todos los archivos" en tipo.

Contenido:

```
DB_PASSWORD=MiPasswordSegura123
SECRET_KEY=clave_secreta_larga_aleatoria_min32caracteres_xyz789
ADMIN_EMAIL=tu@email.com
ADMIN_PASSWORD=Admin2025!
TOKEN_EXPIRY_HOURS=720
```

---

## PASO 4 — Arrancar

Abre **PowerShell** en la carpeta del proyecto:

```powershell
cd C:\lambotaxi

# Construir y arrancar (la primera vez tarda 2-3 minutos)
docker compose up -d --build
```

Docker Desktop descargará las imágenes (PostgreSQL, Nginx, Python) y construirá la app.

---

## PASO 5 — Verificar que funciona

```powershell
# Ver estado de los contenedores
docker compose ps
```

Debes ver tres filas con estado `running`:
- `lambotaxi_db`    — base de datos
- `lambotaxi_app`   — backend Python
- `lambotaxi_nginx` — servidor web

```powershell
# Comprobar que responde
curl http://localhost/health
# → {"db":"ok","status":"ok"}
```

Abre el navegador en: **http://localhost**

---

## PASO 6 — Entrar en la app

- **App principal:** http://localhost
- **Panel admin:**  http://localhost/admin-panel
- **Conductor:**    http://localhost/conductor

Usa el email y password que pusiste en el `.env` como `ADMIN_EMAIL` y `ADMIN_PASSWORD`.

Desde el panel admin puedes registrar usuarios y aprobarlos.

---

## También lo ves en Docker Desktop

Abre Docker Desktop → pestaña **Containers**.
Verás el grupo `lambotaxi` con los 3 contenedores.
Puedes arrancar/parar/ver logs desde la interfaz gráfica.

---

## Comandos del día a día (PowerShell)

```powershell
cd C:\lambotaxi

# Ver logs en tiempo real
docker compose logs -f app

# Reiniciar el backend (tras cambiar server.py)
docker compose restart app

# Parar todo
docker compose down

# Arrancar de nuevo
docker compose up -d

# Rebuild completo (tras cambiar server.py o requirements.txt)
docker compose up -d --build

# Borrar todo incluida la base de datos (cuidado)
docker compose down -v
```

---

## Actualizar los archivos HTML

Los HTML en `static\` se actualizan sin rebuild. Solo copia el archivo nuevo:

```powershell
# Ejemplo: actualizar la app principal
copy C:\Descargas\lambotaxi.html C:\lambotaxi\static\app.html
# Recarga el navegador. Listo.
```

---

## Acceder desde el móvil (iPhone/Android)

Para acceder desde tu iPhone en la misma red WiFi:

1. Averigua la IP local de tu PC Windows:
   ```powershell
   ipconfig
   # Busca "Dirección IPv4" — algo como 192.168.1.50
   ```

2. En el iPhone, abre Safari y entra en:
   `http://192.168.1.50`

Verás LamboTaxi en el móvil sin instalar nada.

---

## Solución de problemas

**"Puerto 80 en uso"**
Otro programa usa el puerto 80 (IIS, Skype, otro servidor).
Solución: edita `docker-compose.yml` y cambia `"80:80"` por `"8080:80"`,
luego accede en http://localhost:8080

**"docker compose" no se reconoce**
Asegúrate de que Docker Desktop está abierto y corriendo.

**El contenedor app falla al arrancar**
```powershell
docker compose logs app
```
Busca el error. Lo más común: `.env` mal escrito o con espacios extra.

**Borrar todo y empezar desde cero**
```powershell
docker compose down -v
docker compose up -d --build
```
