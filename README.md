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
├── app.py                 # FastAPI web-server
├── train.py                # Modelni o'qitish skripti
├── predict.py               # Bitta rasm uchun inference + Grad-CAM
├── config.py                # Umumiy sozlamalar, sinf metama'lumotlari
├── requirements.txt
├── README.md
├── data/                    # <-- Kaggle datasetini shu yerga joylang
│   ├── Clean/
│   ├── Dusty/
│   ├── Bird-drop/            (mavjud bo'lsa)
│   ├── Physical-damage/      (mavjud bo'lsa)
│   ├── Electrical-damage/    (mavjud bo'lsa)
│   └── Snow-covered/         (mavjud bo'lsa)
├── model/
│   ├── model.pt              # Trening natijasida yaratiladi
│   ├── class_names.json      # Trening natijasida yaratiladi
│   └── plots/
│       ├── training_curves.png
│       └── confusion_matrix.png
├── static/
│   ├── style.css
│   └── app.js
└── templates/
    └── index.html
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
