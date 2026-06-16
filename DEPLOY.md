# Deploy — tusecreto.iot-robotics.cl

VPS Ubuntu 22.04 · Python 3.10.12 · Gunicorn · Nginx (coexiste con otras apps)

---

## 1. Clonar el repositorio

```bash
cd /var/www
sudo git clone https://github.com/RobCrack2023/tusecreto.git tusecreto
sudo chown -R $USER:$USER /var/www/tusecreto
cd /var/www/tusecreto
```

---

## 2. Entorno virtual y dependencias

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn          # servidor WSGI de producción
```

---

## 3. Variables de entorno (.env)

Crear el archivo `.env` en `/var/www/tusecreto/.env` con valores reales:

```env
SECRET_KEY=genera-una-clave-larga-y-aleatoria-aqui
ADMIN_DEFAULT_USER=admin
ADMIN_DEFAULT_PASSWORD=cambia-esto-por-una-contrasena-fuerte
VOTE_SALT=otro-valor-aleatorio-largo
```

Generar claves seguras:
```bash
python3 -c "import secrets; print(secrets.token_hex(48))"
```
986d4e16ce6835b25b7219d369780268fee58802c36115976d6fdb1313fdc4ad961059d19aae31166f696d7c391457d9
dcefa6b06ad2b87504cfbf639cd28b6457f7c22af0c4838d6f32fdde77efb5cb9cfcbff3afa4253dba840afc37f7ceee
Permisos estrictos sobre el archivo:
```bash
chmod 600 /var/www/tusecreto/.env
```

---

## 4. Carpetas de datos (uploads y stickers)

```bash
mkdir -p /var/www/tusecreto/static/uploads
mkdir -p /var/www/tusecreto/static/stickers
```

---

## 5. Inicializar la base de datos

```bash
cd /var/www/tusecreto
source venv/bin/activate
python -c "
from app import app, db
from models import Admin
from werkzeug.security import generate_password_hash
import config
with app.app_context():
    db.create_all()
    if not Admin.query.filter_by(username=config.ADMIN_DEFAULT_USER).first():
        db.session.add(Admin(
            username=config.ADMIN_DEFAULT_USER,
            password_hash=generate_password_hash(config.ADMIN_DEFAULT_PASSWORD),
        ))
        db.session.commit()
    print('BD inicializada OK')
"
```

---

## 6. Systemd service (Gunicorn)

Crear `/etc/systemd/system/tusecreto.service`:

```ini
[Unit]
Description=Portal Secreto — Gunicorn
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/tusecreto
EnvironmentFile=/var/www/tusecreto/.env
ExecStart=/var/www/tusecreto/venv/bin/gunicorn \
    --workers 3 \
    --bind unix:/run/tusecreto.sock \
    --access-logfile /var/log/tusecreto/access.log \
    --error-logfile /var/log/tusecreto/error.log \
    app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Crear carpeta de logs y habilitar el servicio:

```bash
sudo mkdir -p /var/log/tusecreto
sudo chown www-data:www-data /var/log/tusecreto
sudo chown -R www-data:www-data /var/www/tusecreto

sudo systemctl daemon-reload
sudo systemctl enable tusecreto
sudo systemctl start tusecreto
sudo systemctl status tusecreto
```

---

## 7. Nginx — virtual host del subdominio

Crear `/etc/nginx/sites-available/tusecreto`:

```nginx
server {
    listen 80;
    server_name tusecreto.iot-robotics.cl;

    # Logs separados de las otras apps
    access_log /var/log/nginx/tusecreto_access.log;
    error_log  /var/log/nginx/tusecreto_error.log;

    # Archivos estáticos servidos directamente por Nginx
    location /static/ {
        alias /var/www/tusecreto/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Todo lo demás va a Gunicorn
    location / {
        proxy_pass         http://unix:/run/tusecreto.sock;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;

        # Límite de tamaño de upload (debe coincidir con MAX_CONTENT_LENGTH en config.py)
        client_max_body_size 6M;
    }
}
```

Habilitar el sitio y recargar Nginx:

```bash
sudo ln -s /etc/nginx/sites-available/tusecreto /etc/nginx/sites-enabled/
sudo nginx -t          # verificar sintaxis
sudo systemctl reload nginx
```

---

## 8. SSL con Certbot (Let's Encrypt)

```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d tusecreto.iot-robotics.cl
```

Certbot modifica automáticamente el bloque Nginx para HTTPS y configura renovación automática.

---

## 9. IP real detrás de Nginx (para detección de país)

En `config.py` la app usa `request.remote_addr`. Detrás de Nginx esto devuelve `127.0.0.1`.
Para obtener la IP real del visitante, agregar en el virtual host de Nginx dentro del bloque `location /`:

```nginx
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
```

Y en `app.py`, después de crear la app Flask:

```python
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
```

> Ambas configuraciones ya están aplicadas: el header en el virtual host y `ProxyFix` en `app.py`.

---

## 10. Actualizar la app (workflow normal)

```bash
cd /var/www/tusecreto
git pull origin main
source venv/bin/activate
pip install -r requirements.txt   # si cambiaron dependencias
sudo systemctl restart tusecreto
```

---

## 11. Verificación rápida

```bash
# Ver logs en vivo
sudo journalctl -u tusecreto -f

# Probar que el socket responde
curl --unix-socket /run/tusecreto.sock http://localhost/

# Estado del servicio
sudo systemctl status tusecreto nginx
```

---

## Resumen de puertos y sockets

| Componente | Escucha en |
|------------|-----------|
| Gunicorn   | `/run/tusecreto.sock` (Unix socket, no puerto TCP) |
| Nginx      | `80` → redirect a `443` (tras Certbot) |
| Otras apps | Sus propios sockets/puertos, no hay conflicto |
