# Jev kurulumu

Jev, TypeSafe'in karar modelidir. Claude Code'un ya da Cursor'ın modelinin yerine geçmez; her görevde "hangi model, hangi effort?" sorusunu o cevaplar.

## Ortak adım
1. API anahtarı al: https://console.typesafe.ai/keys
2. Kabuk profiline ekle: `export TYPESAFE_API_KEY="..."`
3. `.jev/` klasörünü projenin köküne kopyala (Python 3, ek paket gerekmez).
4. Dene: `python3 .jev/jev_route.py "Kullanıcı tablosuna soft delete ekle"`

## Claude Code
1. `.claude/agents/`, `.claude/skills/jev/` ve `.claude/settings.json` dosyalarını projeye kopyala.
   Zaten bir `.claude/settings.json` varsa sadece `hooks.UserPromptSubmit` bloğunu birleştir.
2. Ana oturumu ucuz bir santral olarak aç: `/model sonnet` ve `/effort low`.
   Asıl işi Jev'in seçtiği subagent kendi model/effort ayarıyla yapar.
3. Normal şekilde prompt yaz. Her prompt'ta Jev'e sorulur, kart görünür, iş ilgili subagent'a gider.
   `/` ile başlayan komutlar Jev'e gönderilmez. Geçici kapatmak için: `JEV_DISABLED=1 claude`

Not: VS Code eklentisinde hook bağlamının modele ulaşmadığına dair açık bir hata kaydı var; en güvenilir çalışma ortamı CLI.

## Cursor
1. `.cursor/rules/jev.mdc` dosyasını projeye kopyala.
2. Cursor'da model elle seçildiği için Jev kartı verir ve hangi modele geçmen gerektiğini söyler.

## Ayar
E�ikler ve ağırlıklar `.jev/jev_route.py` dosyasının başında (`WEIGHTS`, `TIER_CUTS`, `RISK_FLOORS`).
Her karar `~/.jev/decisions.jsonl` dosyasına yazılır; bir hafta sonra bu günlüğe bakıp eşikleri kendi işlerine göre ayarla.
