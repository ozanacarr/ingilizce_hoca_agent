# Hoca: 3D sınıfta İngilizce öğretmenin

Sen orta sırada oturuyorsun, öğretmenin Ms. Clara tahtanın yanında duruyor. Tahtaya yazıyor, sırana soru kartları
bırakıyor, hatalarını kırmızı kalemle düzeltiyor, yeni kelimeleri kelime duvarına asıyor ve seni hatırlıyor.
Onunla **yazarak** da **konuşarak** da ders yapabilirsin.

## Çalıştırma

Gerekenler: **Python 3.10 veya üstü** ve bir tarayıcı (mikrofon için Chrome ya da Edge).

- **Windows:** `baslat.bat` dosyasına çift tıkla.
- **macOS / Linux:** terminalde `./baslat.sh` çalıştır.

İlk seferde gerekli paketleri kurar, sonra tarayıcıda sınıfı açar.

Elle çalıştırmak istersen:

```bash
.venv\Scripts\python -m uvicorn server.main:app --port 8765
```

Sonra tarayıcıda `http://localhost:8765` adresini aç. Mikrofon için **Chrome** ya da **Edge** kullan.

## Öğretmen kimin hesabıyla çalışır?

Hoca her kullanıcının **kendi** Claude hesabıyla çalışır. Kimse başkasının hesabını ya da anahtarını kullanmaz.
Sunucu açılınca şu sırayla bakar:

| Rozet | Ne zaman | Ne olur |
|---|---|---|
| **CLAUDE PRO / MAX** | Bilgisayarda Claude Code kurulu ve hesabınla giriş yapılmış | Öğretmen Claude aboneliğinle çalışır. Ek ücret yok; kullanım aboneliğinin limitlerinden düşer. |
| **CANLI · API** | Claude Code yok ama `.env` dosyasında `ANTHROPIC_API_KEY` var | Öğretmen Claude API ile çalışır (Claude Opus 5.5). Kullanım kadar ücretlidir. |
| **DEMO** | İkisi de yoksa | Hazır yazılmış bir ders oynar. Arayüzü görmek için; gerçek yapay zeka değildir. |

**Kendi Claude aboneliğinle kullanmak için** (Pro, Max...):

1. Claude Code'u kur: https://claude.com/claude-code
2. Bir terminalde hesabınla giriş yap:

```bash
claude auth login
```

3. Hoca'yı başlat ya da sayfayı yenile. Sınıfın üstünde **CLAUDE PRO** rozetini görürsün.

Arka planda ne oluyor: Hoca, Claude Code'u görünmeden başlatır, ona öğretmen kişiliğini verir ve sınıf araçlarını
(tahta, soru kartı, kırmızı kalem...) `server/mcp_bridge.py` üzerinden bağlar. Claude Code'un dosya okuma, komut
çalıştırma gibi kendi araçları tamamen kapalıdır; öğretmen sadece sınıfı kullanabilir.

İsteğe bağlı ayarlar (`.env` dosyasına yazılır): `HOCA_ENGINE=claude|api|demo` (motoru zorla),
`HOCA_CLAUDE_MODEL` (Claude Code modeli, ör. `sonnet`), `HOCA_MODEL` (API modeli),
`HOCA_EFFORT=low|medium|high` (öğretmenin ne kadar derin düşüneceği; `low` daha hızlı cevap verir).

## Klasörler

```
server/            Python: öğretmenin beyni
  teacher.py       Öğretmenin kişiliği, öğretim yöntemi ve API motoru
  claude_code_teacher.py  Claude Code motoru (kullanıcının kendi Claude aboneliği)
  mcp_bridge.py    Sınıf araçlarını Claude Code'a bağlayan köprü
  tools.py         Öğretmenin araçları (tahtaya yaz, soru sor, düzelt, kelime ekle, XP ver...)
  memory.py        Öğrenci hafızası: profil, hata defteri, kelime kutusu, beceriler, ders geçmişi
  demo.py          Anahtarsız demo ders
  main.py          Web sunucusu (FastAPI + WebSocket)
data/              Öğretmeni besleyen veriler (JSON, elle düzenlenebilir)
  curriculum.json  CEFR seviyelerine göre konular ve ders akışı
  turkish_errors.json  Türklerin sık yaptığı hatalar
  vocab.json       Seviye ve temaya göre başlangıç kelimeleri
  student.json     Senin hafızan (canlı modda oluşur; silersen öğretmen seni unutur)
web/               3D sınıf (JavaScript, Three.js)
```

## Öğretmen nasıl çalışıyor?

1. Ders başında `memory.py` senin özetini çıkarır: seviyen, sık yaptığın hatalar, tekrar zamanı gelen kelimeler, son dersler.
2. Bu özet, müfredat ve Türklere özgü hata listesiyle birlikte öğretmene verilir.
3. Öğretmen konuşur (balon + ses) ve araç çağırır. Her araç sınıfta görünen bir şey yapar ve hafızanı günceller.
4. Kelimeler aralıklı tekrar kutularında tutulur. Bildiğin kelime daha seyrek, unuttuğun daha sık sorulur.

**Yeni bir şey eklemek istersen:** müfredata konu eklemek için `data/curriculum.json` dosyasını, öğretmenin
kişiliğini değiştirmek için `server/teacher.py` içindeki `TEACHER_PROMPT` metnini düzenle. Yeni bir araç için
`server/tools.py` dosyasına bak.
