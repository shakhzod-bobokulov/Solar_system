# Quyosh Paneli Chang/Nosozlik Aniqlash Tizimi

AI asosidagi tizim — quyosh panelining rasmiga qarab uni **TOZA** yoki
**CHANGLANGAN / NOSOZ** (chang, qush go'ng'i, jismoniy/elektr shikast, qor)
ekanligini aniqlaydi, ishonch darajasini, taxminiy quvvat yo'qotishini va
Grad-CAM issiqlik xaritasi orqali muammo joylashgan hududni ko'rsatadi.

- **Model**: MobileNetV3-Large yoki EfficientNet-B0 (ImageNet transfer learning), PyTorch
- **Backend**: FastAPI
- **UI**: O'zbek tilida, zamonaviy, dark/light mavzu, responsive (bitta HTML/JS sahifa)
- **Grad-CAM**: chang/shikast joylashgan hududni vizual ko'rsatish

---

## 1. Loyihaning tuzilishi

```
solar/
├── app.py                  # FastAPI web-server (sahifalar + API)
├── auth.py                 # Admin/foydalanuvchi autentifikatsiyasi, sessiya
├── store.py                # SQLite: tekshiruvlar, foydalanuvchilar, panellar, sozlamalar
├── mailer.py               # SMTP orqali tasdiqlash kodlari
├── imagetools.py           # EXIF GPS, rasm sifati tekshiruvi, kichik nusxa, ZIP
├── train.py                # Oddiy rasm modelini o'qitish skripti
├── predict.py              # Inference + Grad-CAM (oddiy rasm)
├── predict_thermal.py      # Inference (termal/infraqizil rasm)
├── seed_demo_user.py       # Sinov uchun demo foydalanuvchi yaratish
├── config.py               # Sozlamalar, sinf metama'lumotlari
├── requirements.txt
├── README.md
├── colab/
│   └── thermal_model.ipynb # Termal modelni Colab'da o'qitish daftari
├── data/                   # <-- Kaggle datasetini shu yerga joylang
│   ├── Clean/  Dusty/  Bird-drop/  Physical-damage/
│   └── Electrical-damage/  Snow-covered/   (oxirgi to'rttasi ixtiyoriy)
├── model/
│   ├── model.pt            # Trening natijasida yaratiladi
│   ├── class_names.json
│   ├── thermal_model.pt    # (ixtiyoriy) Colab natijasi
│   └── plots/              # training_curves.png, confusion_matrix.png
├── static/
│   ├── style.css, app.js, common.js, i18n.js (UZ/RU/EN)
│   ├── login.js, account.js, admin.js, map.js
│   ├── sw.js, manifest.webmanifest, icons/   # PWA
└── templates/
    ├── index.html, _controls.html
    ├── login.html, account.html, admin.html
```

---

## 2. O'rnatish

```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

pip install -r requirements.txt
```

> GPU (CUDA) mavjud bo'lsa, PyTorch avtomatik undan foydalanadi; aks holda CPU'da ishlaydi (sekinroq, lekin ishlaydi).

---

## 3. Kaggle datasetini yuklab olish

1. https://www.kaggle.com sahifasida ro'yxatdan o'ting.
2. **Settings → API → "Create New Token"** tugmasini bosing — bu `kaggle.json` faylini yuklab beradi.
3. Faylni joylashtiring:
   - Windows: `C:\Users\<foydalanuvchi>\.kaggle\kaggle.json`
   - Linux/Mac: `~/.kaggle/kaggle.json` (so'ng `chmod 600 ~/.kaggle/kaggle.json`)
4. Barcha 6 ta sinfni (Clean, Dusty, Bird-drop, Electrical-damage, Physical-Damage, Snow-Covered) o'z ichiga olgan tasdiqlangan dataset — **"Solar Panel Images: Clean and Faulty"** (muallif: pythonafroz):

   ```bash
   kaggle datasets download -d pythonafroz/solar-panel-images
   ```

   Agar boshqa versiyasini afzal ko'rsangiz, Kaggle'da shu nom bilan qidiring va dataset sahifasidagi "⋮" menyusidan **"Copy API command"** orqali o'sha datasetning aniq buyrug'ini oling:

   ```bash
   kaggle datasets download -d <owner>/<dataset-slug>
   ```

5. Yuklangan `.zip` faylni oching (extract):

   ```bash
   unzip solar-panel-images.zip -d data_raw
   ```

6. Rasmlarni **sinf nomiga mos alohida papkalarga** joylang, shunda `data/` quyidagi ko'rinishda bo'ladi (`torchvision.datasets.ImageFolder` shu tuzilishni talab qiladi):

   ```
   data/
   ├── Clean/
   │   ├── img_0001.jpg
   │   └── ...
   ├── Dusty/
   │   ├── img_0001.jpg
   │   └── ...
   ├── Bird-drop/          (dataset'da mavjud bo'lsa)
   ├── Physical-damage/    (dataset'da mavjud bo'lsa)
   ├── Electrical-damage/  (dataset'da mavjud bo'lsa)
   └── Snow-covered/       (dataset'da mavjud bo'lsa)
   ```

   Ko'p Kaggle versiyalarida rasmlar allaqachon shunga o'xshash papkalarda keladi — shunchaki ularni `data/` ichiga ko'chiring/nomlang. **Kamida `Clean/` va `Dusty/` papkalari bo'lishi shart**; qolganlari ixtiyoriy — qancha ko'p sinf bo'lsa, model shuncha batafsil bashorat qiladi.

---

## 4. Modelni o'qitish

```bash
python train.py --data-dir data --epochs 25 --batch-size 32 --backbone mobilenet_v3_large
```

Foydali parametrlar:

| Flag | Ma'nosi | Standart |
|---|---|---|
| `--data-dir` | Dataset papkasi | `data` |
| `--epochs` | Maksimal epoch soni | `25` |
| `--batch-size` | Batch hajmi | `32` |
| `--lr` | Learning rate | `1e-3` |
| `--patience` | Erta to'xtatish uchun sabr (epoch) | `5` |
| `--backbone` | `mobilenet_v3_large` yoki `efficientnet_b0` | `mobilenet_v3_large` |
| `--img-size` | Rasm o'lchami (px) | `224` |
| `--val-split` | Validatsiya ulushi | `0.2` |

Skript quyidagilarni bajaradi:

- Datasetni sinflar bo'yicha stratifikatsiyalangan train/val (80/20) ga bo'ladi
- Train uchun augmentatsiya qo'llaydi (crop, flip, rotation, color jitter)
- Sinflar nomutanosibligi uchun class-weighted loss ishlatadi
- `ReduceLROnPlateau` + early stopping bilan o'qitadi
- Eng yaxshi val-loss'ga ega vaznlarni saqlaydi
- Terminalga aniqlik (accuracy) va `classification_report` (precision/recall/F1) chiqaradi
- Quyidagilarni saqlaydi:
  - `model/model.pt` — vaznlar + metama'lumot
  - `model/class_names.json` — sinf nomlari ro'yxati
  - `model/plots/training_curves.png` — loss/accuracy grafiklari
  - `model/plots/confusion_matrix.png` — confusion matrix

> **Eslatma:** Birinchi ishga tushirishda ImageNet oldindan o'qitilgan vaznlarni yuklab olish uchun internet kerak bo'ladi (faqat bir marta, keyin `torch` keshlaydi). O'qitilgandan so'ng, ilova **to'liq offline** ishlaydi.

---

## 5. Web-serverni ishga tushirish

```bash
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

Brauzerda oching: **http://127.0.0.1:8000**

- Agar `model/model.pt` hali mavjud bo'lmasa, sahifa yuqorida ogohlantirish bilan ochiladi va trening bosqichlarini ko'rsatadi — server baribir ishlayveradi, xatoga tushmaydi.
- Model tayyor bo'lgach, sahifani yangilang — endi rasm yuklab tahlil qilishingiz mumkin.

> Demo uchun tayyor foydalanuvchi: `python seed_demo_user.py` (faqat mahalliy sinov uchun).

### UI imkoniyatlari

- Drag-and-drop yoki fayl tanlash orqali bir nechta rasmni birdaniga yuklash
- Har bir rasm uchun: oldindan ko'rish, bashorat qilingan sinf, barcha sinflar bo'yicha ishonch % (progress-bar chart)
- Verdikt belgisi: **"TOZA"** yoki **"CHANGLANGAN — tozalash tavsiya etiladi"**
- Changlanish darajasi: Past / O'rta / Yuqori (ishonch darajasiga asoslangan)
- Taxminiy quvvat yo'qotish %: sinf turiga qarab (masalan, Dusty → ~15–25%)
- **Grad-CAM issiqlik xaritasi** — rasm ustidagi tugma orqali chang/shikast joylashgan hudud ko'rsatiladi
- Joriy sessiyadagi barcha tekshiruvlar tarixi jadval ko'rinishida (vaqt, fayl, natija, ishonch, quvvat yo'qotish)
- Dark/Light mavzu almashtirish (yuqori o'ng burchakdagi tugma)
- To'liq responsive dizayn (mobil, planshet, desktop)

---

## 6. Yakka rasmni terminal orqali tekshirish

```bash
python predict.py path/to/rasm.jpg
```

Natija konsolga bashorat qilingan sinf va barcha sinflar bo'yicha foizlarni chiqaradi.

---

## 7. Xatolarni boshqarish

- Noto'g'ri/qo'llab-quvvatlanmaydigan fayl formati (masalan `.pdf`, `.txt`) yuklansa — o'sha faylga aniq xato xabari ko'rsatiladi, boshqa yuklangan rasmlar tahlili davom etadi.
- Buzilgan/ochilmaydigan rasm fayllari alohida aniqlanadi va xato sifatida ko'rsatiladi (butun so'rov barbod bo'lmaydi).
- 15 MB dan katta fayllar rad etiladi.
- Model hali o'qitilmagan bo'lsa, `/api/predict` aniq xabar bilan javob qaytaradi, ilova ishlashda davom etadi.

---

## 8. Texnik eslatmalar

- Grad-CAM oxirgi konvolyutsion blok (`model.features[-1]`) ustida hisoblanadi — bu MobileNetV3 va EfficientNet-B0 uchun ham amal qiladi.
- Sinf nomlari va o'zbekcha tarjimalari, quvvat yo'qotish diapazonlari `config.py` faylida markazlashtirilgan — dataset qo'shimcha sinflar bilan kelsa ham (`CLASS_INFO`da yo'q nom), tizim xato bermay, umumiy (fallback) qiymatlar bilan ishlayveradi.
- Tarix jadvali brauzer sessiyasida (JavaScript xotirasida) saqlanadi; sahifa yangilansa tozalanadi.

---

## Kirish (login), admin panel va tillar

- Tahlil qilish uchun kirish **shart emas** — mehmon ham foydalana oladi (tekshiruvlar admin panelda `guest` nomi bilan ko'rinadi). Kirish (`/login`) ixtiyoriy. Oddiy foydalanuvchilar o'sha sahifadagi **Ro'yxatdan o'tish** tabida hisob yaratadi (login 3–30 belgi, parol kamida 8 belgi; parollar scrypt bilan xeshlanadi).
- Admin hisobi muhit o'zgaruvchilaridan olinadi. Standart qiymatlar: `admin` / `admin123`.
  **Ishlatishdan oldin parolni o'zgartiring:**

  ```bash
  # PowerShell
  $env:ADMIN_USERNAME = "admin"
  $env:ADMIN_PASSWORD = "kuchli-parol"
  python app.py
  ```
- `/admin` (faqat admin) — foydalanuvchilar ro'yxati, barcha tekshiruvlar statistikasi, tarixi, CSV eksport va tarixni tozalash.
  Tekshiruvlar `checks.db` (SQLite) faylida saqlanadi.
- Ketma-ket 5 ta noto'g'ri urinishdan so'ng IP 5 daqiqaga bloklanadi.
- Interfeys tillari: **O'zbek, Русский, English** (tepadagi UZ / RU / EN tugmalari). Matnlar `static/i18n.js` da.

### Email tasdiqlash va parolni tiklash

Ro'yxatdan o'tishda foydalanuvchi emailiga 6 xonali kod yuboriladi (10 daqiqa amal qiladi,
5 ta noto'g'ri urinishdan keyin bekor bo'ladi, qayta yuborish 60 soniyada bir marta).
Kod tasdiqlangach hisob faollashadi. Shu mexanizm **"Parolni unutdingizmi?"** uchun ham ishlaydi.

Xat yuborish uchun SMTP sozlanadi (Gmail misolida):

1. Google hisobida 2 bosqichli tekshiruvni yoqing.
2. https://myaccount.google.com/apppasswords sahifasida **App password** yarating.
3. Muhit o'zgaruvchilarini o'rnating (parolni kodga yozmang):

   ```bash
   # PowerShell
   $env:SMTP_USER = "sizning@gmail.com"
   $env:SMTP_PASSWORD = "xxxx xxxx xxxx xxxx"   # App password
   python app.py
   ```

   Boshqa provayder uchun `SMTP_HOST` va `SMTP_PORT` (standart `smtp.gmail.com:587`) ni o'zgartiring.

`SMTP_USER` / `SMTP_PASSWORD` berilmasa, ilova ishlab chiqish rejimida ishlaydi: email yuborilmaydi,
kod **server konsoliga** chiqariladi (`[DEV] verify kodi (...): 123456`).

---

## Termal (infraqizil) model — Colab'da o'qitish

Oddiy rasm modelidan tashqari, **issiqlik (infraqizil) tasvirlar** uchun ikkinchi model bor:
nosozlik turini (12 sinf) va tasvirdagi **qizigan yuzani** ko'rsatadi.

- Daftar: [`colab/thermal_model.ipynb`](colab/thermal_model.ipynb)
- Ma'lumot: [RaptorMaps/InfraredSolarModules](https://github.com/RaptorMaps/InfraredSolarModules) (MIT, 20 000 ta 24×40 tasvir) — daftar o'zi yuklab oladi.
- Ishga tushirish: daftarni Google Colab'da oching → **Runtime → Change runtime type → GPU** → **Run all**.
- Natija: `thermal_model.pt`, `thermal_class_names.json`, `thermal_labels.json` (UZ/RU/EN) — yuklab olib `model/` papkasiga qo'ying.
- Issiqlik xaritasi ikki usulda: **Grad-CAM** (model e'tibori) va **issiq hudud maskasi** (tasvir yorqinligidan, `hot_area_percent`).

Cheklovlar: tasvirlar bitta modul qirqimi (butun dala suratasi emas), kulrang 8-bit (°C yo'q — issiq hudud nisbiy),
dataset tasodifiy bo'linadi (real dalada natija test natijasidan past bo'lishi mumkin).

**Ilovaga ulash:** `thermal_model.pt` ni `model/` papkasiga qo'ysangiz, bosh sahifada **"Termal (infraqizil)"** rejimi
o'zi yoqiladi (fayl bo'lmasa, tugma o'chiq turadi). Termal natijadagi quvvat yo'qotish foizlari
(`config.THERMAL_CLASS_INFO`) o'lchov emas, muhandislik mantiqiga asoslangan **taxminiy baho**.
Boshqa joydan yuklash uchun: `THERMAL_MODEL_PATH` muhit o'zgaruvchisi.

---

## Imkoniyatlar (sahifalar bo'yicha)

**Tahlil sahifasi (`/`) — hisobsiz ham ishlaydi**
- Rejim: oddiy rasm / termal (infraqizil). Yuklash: fayl tanlash, tashlash (papka ham), **kamera**, **papka**, **ZIP**, **Ctrl+V** (buferdan).
  Fayllar 3 tadan yuboriladi, umumiy **progress** ko'rsatiladi.
- Natija kartasi: sinf, ishonch, ta'sir darajasi, taxminiy quvvat yo'qotish; **issiqlik qatlami shaffoflik slayderi** bilan;
  rasmni bosib **kattalashtirish oynasi** (g'ildirak/ikki barmoq zoom, siljitish, Esc).
- **Ogohlantirishlar:** past ishonch (<60%), qorong'i / yorqin / xira / past ruxsatli rasm ("qayta oling" maslahati bilan).
- **"Natija to'g'rimi?"** — fikr (noto'g'ri bo'lsa, to'g'ri sinfni tanlash). Admin panelda ko'rinadi va modelni yaxshilash uchun ishlatilishi mumkin.
- **Yo'qotish kalkulyatori:** panel quvvati, soni, quyosh soati, tarif → oylik/yillik zarar (so'm). Qiymatlar brauzerda saqlanadi.
- **PDF hisobot:** brauzerning chop etish oynasi orqali "PDF sifatida saqlash" (barcha 3 tilda, kirill ham).
- Rasm EXIF'idagi **GPS** o'qiladi (telefon rasmlari yon tomonga burilgan bo'lsa ham to'g'rilanadi).

**Kabinet (`/account`) — kirgan foydalanuvchi uchun**
- **Tekshiruvlar tarixi** (qidiruv, sinf va panel bo'yicha filtr, kichik nusxa, o'chirish).
- **Panellar:** har panelga nom (va ixtiyoriy koordinata) berib, tekshiruvlarni shu panelga bog'lash; **trend**
  ("oldingi tekshiruvdan beri yomonlashdi, ~30 kun oldingiga nisbatan +12%") va mini-grafik.
- **Xarita:** GPS'li tekshiruvlar va koordinatali panellar (Leaflet + OpenStreetMap; internet kerak).

**Admin panel (`/admin`)**
- Boshqaruv paneli: ko'rsatkichlar, **14 kunlik / 12 oylik** grafik, **eng ko'p uchraydigan nosozliklar reytingi**, "noto'g'ri" fikrlar ulushi.
- Tekshiruvlar: kichik nusxa, rejim, fikr, GPS; qidiruv va filtrlar; CSV eksport.
- Foydalanuvchilar: **bloklash / blokdan chiqarish** (sessiya darhol to'xtaydi), o'chirish.
- Xarita (barcha foydalanuvchilar) va Sozlamalar (**admin parolini panel orqali o'zgartirish**).

**Telefonga o'rnatish (PWA):** HTTPS (yoki `localhost`) orqali ochilganda brauzer "Ilovani o'rnatish" taklif qiladi
(`manifest.webmanifest` + `sw.js`). Oddiy `http://<IP>:8000` orqali telefonda service worker ishlamaydi —
haqiqiy foydalanish uchun serverni HTTPS ortida (masalan, reverse proxy) joylashtiring.

**Maxfiylik:** har tekshiruvning 96×96 piksellik kichik nusxasi bazada (`checks.db`) saqlanadi; mehmon tekshiruvlari
`guest` nomi bilan yoziladi. Xarita uchun rasm GPS koordinatalari ham saqlanadi.

**Test uchun:** `SOLAR_DB_PATH` — boshqa baza fayli (haqiqiy `checks.db` ga tegmaslik uchun).
