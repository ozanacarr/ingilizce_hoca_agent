// Ses: öğretmenin konuşması (metinden sese) ve senin mikrofonun (sesten metne).
// Tarayıcının hazır özelliklerini kullanır. Mikrofon en iyi Chrome ve Edge'de çalışır.

const TURKISH_HINT = /[çğışöüÇĞİŞÖÜ]|\b(bu|ve|için|değil|ile|bir|şimdi|zaman|kullanırız|demek|evet|hayır|yani)\b/i;

export class Voice {
  constructor({ onSpeakingChange }) {
    this.enabled = true;
    this.onSpeakingChange = onSpeakingChange || (() => {});
    this.buffer = '';
    this.queue = [];
    this.speaking = false;
    this.voices = { en: null, tr: null };
    this.supported = 'speechSynthesis' in window;
    if (this.supported) {
      const pick = () => {
        const all = speechSynthesis.getVoices();
        const prefer = (lang, names) =>
          names.map((n) => all.find((v) => v.lang.startsWith(lang) && v.name.includes(n))).find(Boolean) ||
          all.find((v) => v.lang === (lang === 'en' ? 'en-US' : 'tr-TR')) ||
          all.find((v) => v.lang.startsWith(lang)) || null;
        this.voices.en = prefer('en', ['Aria', 'Jenny', 'Samantha', 'Google US English', 'Zira']);
        this.voices.tr = prefer('tr', ['Emel', 'Google Türkçe', 'Yelda', 'Tolga']);
      };
      pick();
      speechSynthesis.onvoiceschanged = pick;
    }
  }

  // Tarayıcılar sesi ilk kullanıcı tıklamasından sonra açar.
  unlock() {
    if (!this.supported) return;
    const u = new SpeechSynthesisUtterance(' ');
    u.volume = 0;
    speechSynthesis.speak(u);
  }

  setEnabled(on) {
    this.enabled = on;
    if (!on) this.stop();
  }

  // Konuşmayı hemen kes (ör. mikrofon açılınca öğretmen sussun)
  stop() {
    if (!this.supported) return;
    this.queue = [];
    this.buffer = '';
    speechSynthesis.cancel();
    this._setSpeaking(false);
  }

  // Öğretmenin metni akarken cümle cümle seslendir
  feed(delta) {
    this.buffer += delta;
    let m;
    while ((m = this.buffer.match(/^(.+?[.!?…])(\s+)/s))) {
      this._enqueue(m[1]);
      this.buffer = this.buffer.slice(m[0].length);
    }
  }

  flush() {
    if (this.buffer.trim()) this._enqueue(this.buffer);
    this.buffer = '';
  }

  _enqueue(sentence) {
    const text = sentence.replace(/[*_#`]/g, '').trim();
    if (!text || !this.enabled || !this.supported) return;
    this.queue.push(text);
    if (!this.speaking) this._next();
  }

  _next() {
    const text = this.queue.shift();
    if (!text) {
      this._setSpeaking(false);
      return;
    }
    const tr = TURKISH_HINT.test(text);
    const u = new SpeechSynthesisUtterance(text);
    u.lang = tr ? 'tr-TR' : 'en-US';
    const v = tr ? this.voices.tr : this.voices.en;
    if (v) u.voice = v;
    u.rate = tr ? 1.0 : 0.95;
    u.onend = u.onerror = () => this._next();
    this._setSpeaking(true);
    speechSynthesis.speak(u);
  }

  _setSpeaking(on) {
    if (this.speaking !== on) {
      this.speaking = on;
      this.onSpeakingChange(on);
    }
  }
}

export class Mic {
  constructor({ onInterim, onFinal, onStateChange }) {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    this.supported = Boolean(SR);
    this.listening = false;
    this.onStateChange = onStateChange || (() => {});
    if (!this.supported) return;
    this.rec = new SR();
    this.rec.lang = 'en-US';
    this.rec.interimResults = true;
    this.rec.continuous = false;
    this.rec.onresult = (e) => {
      let interim = '', final = '';
      for (const r of e.results) (r.isFinal ? (final += r[0].transcript) : (interim += r[0].transcript));
      if (final) onFinal(final.trim());
      else onInterim(interim);
    };
    this.rec.onend = () => this._set(false);
    this.rec.onerror = () => this._set(false);
  }

  toggle() {
    if (!this.supported) return;
    if (this.listening) {
      this.rec.stop();
    } else {
      this.rec.start();
      this._set(true);
    }
  }

  _set(on) {
    this.listening = on;
    this.onStateChange(on);
  }
}
