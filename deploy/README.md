# Деплой Rivalens на VPS с существующим nginx

На VPS уже работает хостовый nginx на 80/443 (другой проект), поэтому
Rivalens не поднимает собственный nginx-контейнер: backend и frontend
биндятся только на `127.0.0.1` (порты 8001 и 3001), а хостовый nginx
проксирует на них по имени `rivalens.ru`.

## Требования

- VPS с Ubuntu 22.04+, root-доступ
- Хостовый nginx уже установлен и слушает 80/443 (`systemctl status nginx`)
- Домен `rivalens.ru` с возможностью настроить A-запись на IP VPS

## 1. Docker + compose plugin

```bash
curl -fsSL https://get.docker.com | sh
apt-get install -y docker-compose-plugin
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
openssl rand -hex 16   # POSTGRES_PASSWORD (в .env.prod подставить ДВАЖДЫ: POSTGRES_PASSWORD и DATABASE_URL)
nano .env.prod         # подставить JWT_SECRET, POSTGRES_PASSWORD (×2), AI_API_KEY
chmod 600 .env.prod
```

## 4. Поднять стек

```bash
docker compose -f docker-compose.prod.yml up -d --build
sleep 30
curl -s http://127.0.0.1:8001/health   # ожидается {"status":"ok"}
```

## 5. DNS

A-запись у регистратора: `rivalens.ru -> <IP-вашего-VPS>`. Проверка:

```bash
dig +short rivalens.ru
```

## 6. Хостовый nginx

```bash
cp deploy/rivalens.ru.nginx.conf /etc/nginx/sites-available/rivalens.ru
ln -s /etc/nginx/sites-available/rivalens.ru /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

Проверка (по HTTP, до SSL): `curl -sI http://rivalens.ru | head -3`

## 7. SSL через certbot на хосте

```bash
certbot --nginx -d rivalens.ru --agree-tos -m admin@rivalens.ru
# certbot сам допишет ssl_certificate и 443 в конфиг
systemctl reload nginx
curl -sI https://rivalens.ru | head -3
```

## 8. Обновление Rivalens

```bash
cd /opt/Rivalens && git pull
docker compose -f docker-compose.prod.yml up -d --build
```

## Полезное

- Логи: `docker compose -f docker-compose.prod.yml logs -f backend`
- Ручной прогон проверок: `curl -X POST http://127.0.0.1:8001/api/v1/admin/run-all`
  (с Bearer-токеном; см. `backend/app/api/admin.py`)
- Продление сертификата: certbot на хосте обычно ставит свой systemd-timer
  (`certbot renew --deploy-hook "systemctl reload nginx"`); проверить:
  `systemctl list-timers | grep certbot`

## SMTP (email-уведомления)

Уведомления включены по умолчанию (`NOTIFICATIONS_ENABLED=true`); без
`SMTP_HOST` письма просто не отправляются (warning в логах), остальное
работает.

Проверенные варианты SMTP:

| Провайдер | Host | Port | Примечание |
|---|---|---|---|
| Яндекс | `smtp.yandex.ru` | 465 | пароль приложения (не основной): https://id.yandex.ru/security/app-passwords |
| Gmail | `smtp.gmail.com` | 587 | App Password: https://myaccount.google.com/apppasswords |
| SendGrid | `smtp.sendgrid.net` | 587 | user — буквально `apikey`, пароль — API-ключ |

Пример (Яндекс):

```ini
SMTP_HOST=smtp.yandex.ru
SMTP_PORT=465
SMTP_USER=rivalens@yandex.ru
SMTP_PASSWORD=<app-password>
SMTP_FROM=rivalens@yandex.ru
NOTIFICATIONS_ENABLED=true
```

После правки `.env.prod`: `docker compose -f docker-compose.prod.yml up -d backend`.

## ЮKassa (оплата тарифов)

1. В `.env.prod` добавить (shopId и секретный ключ — из ЛК ЮKassa,
   раздел «Интеграция»):

```ini
YOOKASSA_SHOP_ID=<shopId>
YOOKASSA_SECRET_KEY=<secretKey>
YOOKASSA_RETURN_URL=https://rivalens.ru/billing/success
```

2. После правки: `docker compose -f docker-compose.prod.yml up -d backend`.

3. В ЛК ЮKassa настроить HTTP-уведомления (webhook):
   - ЛК ЮKassa → **Интеграция → HTTP-уведомления**
   - URL: `https://rivalens.ru/api/v1/billing/webhook`
   - События: `payment.succeeded`
   - Сохранить

Поток оплаты: фронт вызывает `POST /api/v1/billing/checkout` →
backend создаёт платёж в ЮKassa и отдаёт `confirmation_url` →
пользователь платит на стороне ЮKassa → ЮKassa шлёт webhook
`payment.succeeded` → backend активирует тариф. Без webhook'а тариф
не активируется — платёж есть, тарифа нет.

Важно: secretKey хранить только в `.env.prod` (gitignored).

## Backups

Ежедневный дамп Postgres с хранением 7 последних копий:

```bash
chmod +x deploy/backup.sh
crontab -e
# 0 3 * * * /opt/Rivalens/deploy/backup.sh >> /var/log/rivalens-backup.log 2>&1
```

Ручной запуск: `/opt/Rivalens/deploy/backup.sh` — создаёт
`/opt/Rivalens/backups/rivalens_ГГГГММДД_ЧЧММСС.sql.gz`.

Восстановление:

```bash
gunzip -c /opt/Rivalens/backups/rivalens_YYYYMMDD_HHMMSS.sql.gz | \
  docker compose -f /opt/Rivalens/docker-compose.prod.yml \
  --env-file /opt/Rivalens/.env.prod exec -T postgres \
  psql -U rivalens -d rivalens
```

Каталог `/backups/` в git не попадает (.gitignore). Бэкапы лежат на том же
VPS — для продакшена стоит настроить копирование наружу (rsync на другую
машину / object storage) отдельным шагом.
