# Деплой Rivalens на VPS

Пошаговая инструкция для продакшен-деплоя (Ubuntu 22.04+, 2 GB RAM).

## Требования

- VPS с Ubuntu 22.04+ и root-доступом (в примерах — `212.57.127.83`)
- Домен `rivalens.ru` с возможностью настроить A-запись на IP VPS
- Установленный Docker (шаг 1)

## 1. Установка Docker

```bash
curl -fsSL https://get.docker.com | sh
apt-get install -y docker-compose-plugin
```

Проверка:

```bash
docker --version
docker compose version
```

## 2. Клонирование репозитория

```bash
cd /opt
git clone https://github.com/FELAGI0/Rivalens.git
cd Rivalens
```

## 3. Настройка окружения

```bash
cp .env.prod.example .env.prod
openssl rand -hex 32   # JWT_SECRET
openssl rand -hex 16   # POSTGRES_PASSWORD
nano .env.prod         # подставить: JWT_SECRET, POSTGRES_PASSWORD (2 места: POSTGRES_PASSWORD и DATABASE_URL), AI_API_KEY
chmod 600 .env.prod
```

Важно: пароль Postgres встречается в `.env.prod` дважды — `POSTGRES_PASSWORD`
и внутри `DATABASE_URL` — они должны совпадать.

## 4. Запуск

```bash
docker compose -f docker-compose.prod.yml up -d --build
sleep 30
curl -s http://localhost/health   # ожидается {"status":"ok"}
```

## 5. DNS

Настроить у регистратора домена A-запись:

```
rivalens.ru.  A  <IP-вашего-VPS>   # например 212.57.127.83
```

Проверка (может занять до пары часов на распространение):

```bash
dig +short rivalens.ru
```

## 6. SSL-сертификат (Let's Encrypt, webroot)

```bash
docker run --rm \
  -v /opt/Rivalens/deploy/letsencrypt:/etc/letsencrypt \
  -v /opt/Rivalens/deploy/certbot-www:/var/www/certbot \
  certbot/certbot certonly --webroot -w /var/www/certbot \
  -d rivalens.ru --email admin@rivalens.ru --agree-tos --non-interactive
```

Сертификаты окажутся в `deploy/letsencrypt/live/rivalens.ru/`.

## 7. Включение HTTPS

1. В `deploy/nginx.conf` раскомментировать блок `server { listen 443 ... }`.
2. Перезапустить nginx:

```bash
docker compose -f docker-compose.prod.yml restart nginx
```

3. Проверить:

```bash
curl -sI https://rivalens.ru | head -3   # ожидается HTTP/2 200 (или 301 -> https)
```

## 8. Обновление приложения

```bash
cd /opt/Rivalens
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

## 9. Автопродление SSL (cron, раз в неделю)

```bash
crontab -e
```

Добавить строку:

```
0 3 * * 1 docker run --rm -v /opt/Rivalens/deploy/letsencrypt:/etc/letsencrypt -v /opt/Rivalens/deploy/certbot-www:/var/www/certbot certbot/certbot renew --webroot -w /var/www/certbot && docker compose -f /opt/Rivalens/docker-compose.prod.yml restart nginx
```

(certbot пишет логи в `/var/log/letsencrypt` внутри вольюма; `deploy/letsencrypt`
и `deploy/certbot-www` создаёт Docker при первом запуске — владельцем будет
root, это нормально.)

## Полезное

- Логи: `docker compose -f docker-compose.prod.yml logs -f backend`
- Ручной прогон проверок: `curl -X POST http://localhost/api/v1/admin/run-all`
  (с Bearer-токеном; см. `backend/app/api/admin.py`)
