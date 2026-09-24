---
name: jev
description: TypeSafe Jev modeline "bu göreve hangi Claude modeli ve effort?" diye sorar ve kararı uygular. Kullanıcı "jev", "kararı jev versin", "hangi model", "hangi effort" dediğinde, ya da bağlamda JEV KARARI olmadığı hâlde anlamlı büyüklükte bir kodlama görevi geldiğinde MUTLAKA kullan. Hook zaten bir JEV KARARI eklediyse bu skill'i çalıştırma, o kararı uygula.
---

# Jev — karar zekâsı

> "Kota tasarrufu, hız ve sonuç kalitesini işte bu karar zekâ halletti."

Kararı sen vermiyorsun; **TypeSafe Jev modeli veriyor**. Senin işin Jev'e sormak ve kararı uygulamak.

## Normal akış

Projedeki `UserPromptSubmit` hook'u her prompt'ta Jev'e sorar ve bağlama bir **JEV KARARI** ekler. Bu karar varsa:

1. Karar kartını kod bloğu içinde göster.
2. İşi kartta yazan `jev-*` subagent'ına Agent aracıyla devret. Subagent konuşmayı görmez; amaç, dosya yolları, kısıtlar ve kabul kriterlerini içeren eksiksiz bir brif yaz.
3. Subagent dönünce sonucu kısaca özetle.

## Hook yoksa ya da elle karar istenirse

Şunu çalıştır ve çıktıyı kullanıcıya göster:

```bash
python3 "$CLAUDE_PROJECT_DIR"/.jev/jev_route.py "<görevin tek paragraflık özeti>"
```

Kullanıcı "sadece öner" dediyse çıktıdaki `/model` ve `/effort` komutlarını göster ve dur. Aksi hâlde kartta yazan subagent'a devret.

## Kurallar

- Jev'e yalnızca görevin kendisini gönder; konuşma geçmişini, kod dökümünü ya da alakasız ayrıntıyı ekleme. Jev gereksiz bağlamla kötüleşir.
- Kademeyi kendi kafana göre değiştirme. İki istisna var: kullanıcı açıkça bir model istediyse onun isteği geçerli; subagent `⬆️ YÜKSELT` ile döndüyse bir üst kademeye geç ve kullanıcıya tek satırla bildir.
- 🏛️ Usta kademesinde (Fable) devretmeden önce kullanıcıdan onay al. Fable bazı planlarda kullanım kredisinden düşebilir. Onay gelmezse `jev-derin` kullan.
- Zor kısım bitince kalan mekanik işleri (import düzeltme, test çoğaltma, doküman) `jev-dengeli` ya da `jev-hizli`ya ver.
- Jev'e ulaşılamazsa işi mevcut oturumda yap ve bunu tek satırla belirt.
