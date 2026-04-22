# EduSaaS — Keyingi sessiya uchun vazifalar

## 15-sessiya xulosasi (2026-04-21)

### Bajarildi
- ✅ **Task #46** — Teacher invite link UI (teachers-client.tsx): panel ichida Telegram havola bo'limi, modal yaratgandan so'ng avtomatik invite
- ✅ **Task #47** — Inspector CRUD + invite link UI: backend (inspectors.py) + frontend (inspectors-client.tsx, page.tsx), AppShell nav
- ✅ **Fix** — `PATCH /students/{id}` 500 UniqueViolationError: telegram_id boshqa usarga tegishli bo'lganda xatolik berardi — endi skip qiladi
- ✅ **DB Reset Pipeline** — To'liq qayta ishlandi:
  1. `reset_db.py` — barcha tenant schemalar + public jadvallar + alembic_version DROP
  2. `seed_tenants.py` (**YANGI**) — subscription_plans + public.tenants yozuvlari
  3. `alembic upgrade head` — barcha schemalar yaratiladi
  4. `seed_data.py` — faqat users + demo data
- ✅ **Task #48** — TypeScript: 0 xato. .next/types/routes.d.ts va validator.ts null bytes/truncation tuzatildi

---

## Keyingi sessiya uchun P0 vazifalar

### 1. DB ni qayta ishga tushirish (agar hali bajarilmagan)
```powershell
cd edusaas/backend
python reset_db.py     # "TASDIQLASH" deb tasdiqlang
python seed_tenants.py
alembic upgrade head
python seed_data.py
```

### 2. Student Detail Page — Payment history tab (Admin)
`src/app/[locale]/admin/students/[studentId]/student-detail-client.tsx`
- `payments` tab mavjud lekin to'liq emas
- `GET /students/{id}/payments` endpointi bor — API ga ulash kerak
- UI: jadval (sana, miqdor, guruh, metod, status)

### 3. Inspector payments page
`src/app/[locale]/inspector/payments/page.tsx` — hozir stub
- Admin payments-client.tsx ni re-export qilish yoki o'xshash ko'rinish

### 4. Teacher detail page — o'quvchilar ko'rinishi
`src/app/[locale]/admin/teachers/[teacherId]/teacher-detail-client.tsx`
- O'qituvchining guruhlari va har bir guruh o'quvchilari

### 5. Reports sahifasi
`src/app/[locale]/admin/reports/page.tsx` — hozir yo'q
- Oylik to'lov hisoboti, davomat hisoboti, o'qituvchi KPI

---

## Muhim texnik eslatmalar

### DB Reset tartibi (MUHIM)
```
reset_db.py → seed_tenants.py → alembic upgrade head → seed_data.py
```
`alembic upgrade head` `public.tenants` ni O'QIYDI → tenants avval bo'lishi SHART!

### Login ma'lumotlari (seed_data.py dan keyin)
```
Super Admin : superadmin@edusaas.uz   / Admin123!
Demo Admin  : admin@demo-markaz.uz    / Admin123!
O'qituvchilar: Teacher123!
O'quvchilar  : Student123!
Inspektorlar : Inspector123!
```

### Invite link tizimi
- `STU-XXXXXX` — student
- `TCH-XXXXXX` — teacher
- `INS-XXXXXX` — inspector
- `PRN-XXXXXX` — parent
- Payload: `user_link:{user_id}` (mavjud userni Telegram ga bog'laydi)

### Backend arxitektura
- Multi-tenant: `tenant_{slug}` schema per markaz
- Rolllar: `super_admin`, `admin`, `inspector`, `teacher`, `student`, `parent`
- JWT: 15 min access + 30 kun refresh
- Inspector = User with role="inspector" (alohida jadval yo'q)

### Frontend muhim fayllar
- `src/lib/api.ts` — barcha API funksiyalar + interfeylar
- `src/stores/auth.store.ts` — JWT, user state
- `src/components/shared/StudentTable.tsx` — reusable jadval
- `src/components/shared/ConfirmDialog.tsx` — delete confirm

### asyncpg muhim!
Python 3.13 da asyncpg ishlamaydi. Faqat Python 3.11:
```powershell
py -3.11 -m venv venv
```
