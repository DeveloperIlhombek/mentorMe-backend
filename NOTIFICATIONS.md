# EduSaaS — Notification tizimi (runbook)

Telegram bot + in-app real-vaqt bildirishnoma tizimi.

## Arxitektura

```
┌─────────────┐    enqueue()    ┌──────────────────────┐
│ Event source│────────────────▶│ NotificationService  │
│ (API/Beat)  │                 │ (dedupe, prefs, q.h) │
└─────────────┘                 └──────────┬───────────┘
                                           │
                  ┌────────────────────────┼─────────────────────┐
                  ▼                        ▼                     ▼
         Notification (DB)        Celery .delay()      Redis PUBLISH
         status=queued            send_telegram_*      notif:{slug}:{uid}
                                         │                     │
                                         ▼                     ▼
                                  Telegram Bot API     WebSocket /ws/notifications
                                  (HTTPX, retry)        (Frontend)
```

## Komponentlar

| Komponent | Fayl | Vazifa |
|---|---|---|
| Models | `app/models/tenant/notification*.py`, `broadcast_job.py`, `public/telegram_link.py` | DB |
| Service | `app/services/notification_service.py` | Markaziy enqueue |
| Sender | `app/tasks/notifications.py` | Telegram yuboruvchi (retry, rate-limit) |
| Dispatchers | `app/tasks/event_dispatchers.py` | Beat-driven fan-out |
| Broadcast | `app/tasks/broadcast.py` | E'lon yuborish |
| WebSocket | `app/api/v1/ws.py` | Frontend real-time |
| Linking | `app/api/v1/telegram_link.py`, `bot/handlers/start.py` | Deep-link |
| Preferences | `app/api/v1/notifications.py`, `bot/handlers/preferences.py` | Foydalanuvchi sozlamalari |

## .env yangi maydonlar
 
```env
BOT_TOKEN=...                 # @BotFather dan
BOT_USERNAME=EduSaaSBot       # deep-link uchun
BOT_WEBHOOK_URL=https://api.edusaas.uz/webhook/bot
BOT_WEBHOOK_SECRET=<random_64_hex>
BOT_MODE=auto                 # auto|webhook|polling
TELEGRAM_RATE_LIMIT_PER_SEC=25
NOTIF_QUIET_START=22:00
NOTIF_QUIET_END=07:00
NOTIF_LINK_TOKEN_TTL_DAYS=7
```

## Deploy

### 1. Migration
```bash
alembic upgrade head   # 014_notification_system_v2 qo'llaydi
```

### 2. Webhook secret_token o'rnatish
`BOT_WEBHOOK_SECRET` ni 32+ belgi qilib generate qiling:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 3. Servislarni ishga tushirish
```bash
# API
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Celery worker (Telegram sender + dispatchers + broadcast)
celery -A app.tasks.celery_app worker --loglevel=info --concurrency=4

# Celery beat (scheduled dispatchers)
celery -A app.tasks.celery_app beat --loglevel=info

# Bot (faqat dev/polling)
python run_bot.py
```

## Kategoriyalar va prioritet

| Category | Critical? | Toggle qilinadimi? | Quiet hours |
|---|---|---|---|
| `attendance` | ✅ | ❌ | ignore |
| `payment` | ✅ | ❌ | ignore |
| `system` | ✅ | ❌ | ignore |
| `lesson` | ❌ | ✅ | respect |
| `grade` | ❌ | ✅ | respect |
| `kpi` | ❌ | ✅ | respect |
| `progress` | ❌ | ✅ | respect |
| `broadcast` | ❌ | ✅ | respect |
| `subscription` | ❌ | ✅ | respect |

Critical kategoriyalar — quiet hours va opt-out larni bypass qiladi.

## Account linking

1. Admin: `POST /api/v1/admin/users/{user_id}/telegram-link`
   → `{token, deep_link, expires_at}`
2. Foydalanuvchi: `t.me/<bot>?start=<token>` ochadi
3. Bot `/start <token>` handleri:
   - `public.telegram_link_tokens` dan tenant_slug+user_id ni topadi
   - User.telegram_id ni biriktiradi
   - Tokenni o'chiradi
   - Welcome menyu ko'rsatiladi
4. Bekor qilish: `DELETE /api/v1/admin/users/{user_id}/telegram-link`

## Broadcast

```bash
POST /api/v1/admin/broadcast
{
  "title": "Bayram bilan!",
  "body":  "Hurmatli ota-onalar, bayram bilan tabriklaymiz.",
  "filters": {"role": ["parent"], "branch_id": null, "group_id": null},
  "channels": ["telegram", "in_app"]
}
```
Progress: `GET /api/v1/admin/broadcast/{id}` → `{total, sent, failed, status}`.
Bekor qilish: `POST /api/v1/admin/broadcast/{id}/cancel`.

## Beat schedule

| Task | Cron | Vazifa |
|---|---|---|
| `dispatch_lesson_reminders` | `*/5 * * * *` | 30 min qolgan darslar |
| `dispatch_attendance_pending_reminder` | `09:30, 14:00, 18:00` | Davomat kiritmagan teacher |
| `dispatch_progress_deadline_reminder` | `09:00 daily` | Baholash deadline |
| `dispatch_payment_reminders` | `09:00 / 25th` | Keyingi oy to'lovi |
| `dispatch_overdue_payment_reminders` | `09:00 / 5th` | Qarzdor parent + admin |
| `dispatch_subscription_warning` | `10:00 daily` | Trial 7 kun qolgan tenant admin |
| `flush_scheduled` | `* * * * *` | Quiet hours scheduled fallback |

## Troubleshooting

### Telegram xabar yetib bormaydi
1. `Notification.status` ni tekshiring: `queued` qotib qoldimi yoki `failed`?
2. `Notification.error` ni o'qing — `not_linked` / `bot_blocked` / `chat_not_found`.
3. Celery worker ishlayaptimi: `celery -A app.tasks.celery_app inspect active`.
4. Rate limit: 429 ko'p bo'lsa `TELEGRAM_RATE_LIMIT_PER_SEC` ni kamaytiring.

### WebSocket ulanmaydi
1. JWT token to'g'rimi (access, expired emas)?
2. Redis ishlayaptimi: `redis-cli ping`.
3. Channel listen: `redis-cli SUBSCRIBE 'notif:tenant_slug:user_id'`.

### Deep-link ishlamaydi
1. `public.telegram_link_tokens` da yozuv bormi?
2. Expires_at o'tib ketganmi (TTL 7 kun)?
3. Foydalanuvchi boshqa profilga biriktirilganmi (warning ko'rsatiladi)?

## Observability

Strukturali log keylari (grep uchun):
- `notif.enqueued`, `notif.skip.dedupe`, `notif.skip.user_missing`
- `notif.send.ok`, `notif.send.blocked`, `notif.send.429`, `notif.send.error`
- `broadcast.done`, `broadcast.cancelled`
- `ws.connect`, `ws.disconnect`
- `webhook.secret.mismatch`
